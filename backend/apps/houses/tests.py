from datetime import date, timedelta

from rest_framework import status
from rest_framework.test import APITestCase

from apps.alerts.models import Alert, AlertRule, AlertRuleType, SmsMessage, TriggerMode
from apps.batches.models import PoultryBatch, ProductionType
from apps.core.models import Farm, User, UserRole, create_role_profile
from apps.houses.models import PoultryHouse
from apps.protocols.models import ProtocolCategory, ProtocolTemplate, ProtocolTimeSlot
from apps.protocols.services import expand_protocol_to_alert_rules


class ProtocolSaveAlertRuleRegenerationTests(APITestCase):
    """PUT /api/houses/{houseCode}/protocol/ regenerating `PROTOCOL_TASK` `AlertRule` rows
    (`apps.protocols.services.expand_protocol_to_alert_rules`) — docs/deviations.md Part 15,
    Part B. This exact scenario broke before this project's Part C protocol-editing task: a
    protocol edit must update *future* scheduled rows to match the new schedule, while never
    touching `Alert`/`SmsMessage` history tied to a row whose date has already passed.
    """

    def setUp(self):
        self.farm = Farm.objects.create(name='Ferme Protocole Test')
        self.admin = User.objects.create_user(
            email='admin@protocol-test.local', password='x', name='Admin', role=UserRole.ADMIN, farm=self.farm,
        )
        create_role_profile(self.admin)
        self.client.force_authenticate(user=self.admin)

        self.house = PoultryHouse.objects.create(house_code='H-PROTO-1', farm=self.farm, name='Bâtiment', max_capacity=1000)
        self.category = ProtocolCategory.objects.create(house=self.house, label='Alimentation', icon='Soup')
        today = date.today()
        self.batch = PoultryBatch.objects.create(
            batch_code='BATCH-PROTO-1', house=self.house, production_type=ProductionType.BROILER,
            initial_count=500, start_date=today - timedelta(days=10),
        )

        # A PAST PROTOCOL_TASK row that already fired — simulates a row created when its
        # scheduled_date was still current, days ago (expand_protocol_to_alert_rules only ever
        # *creates* rows dated today-or-later, so this is built directly to represent history
        # that already exists by the time a later protocol edit happens).
        self.past_rule = AlertRule.objects.create(
            farm=self.farm, batch=self.batch, rule_type=AlertRuleType.PROTOCOL_TASK,
            trigger_mode=TriggerMode.SCHEDULED, scheduled_date=today - timedelta(days=9),
        )
        self.past_alert = Alert.objects.create(rule=self.past_rule, batch=self.batch, message='Ancienne tâche')
        self.past_sms = SmsMessage.objects.create(
            alert=self.past_alert, recipient='+221700000000', idempotency_key='past-sms-1',
        )

        # A future-dated protocol line (day 15, 5 days from now at day_of_cycle=10).
        self.line = ProtocolTemplate.objects.create(
            house=self.house, category=self.category, from_value=15, what='Vaccination initiale',
        )
        expand_protocol_to_alert_rules(self.batch)

    def test_editing_the_protocol_regenerates_only_the_future_row(self):
        future_rule = AlertRule.objects.get(batch=self.batch, protocol_line=self.line)
        original_scheduled_date = future_rule.scheduled_date

        payload = {'lines': [{
            'category': self.category.id, 'from_value': 20, 'from_unit': 'DAY',
            'to_value': None, 'to_unit': 'DAY', 'until_end': False,
            'what': 'Vaccination retardée', 'details': '',
        }]}
        response = self.client.put(f'/api/houses/{self.house.house_code}/protocol/', payload, format='json')
        self.assertEqual(response.status_code, 200, response.data)

        # The old future-dated row is gone; a new one exists reflecting the edited protocol
        # (a different scheduled_date — day 20, not day 15).
        new_line = ProtocolTemplate.objects.get(house=self.house)
        regenerated_rule = AlertRule.objects.get(batch=self.batch, protocol_line=new_line)
        self.assertNotEqual(regenerated_rule.scheduled_date, original_scheduled_date)
        self.assertFalse(AlertRule.objects.filter(pk=future_rule.pk).exists())

        # Past history: completely untouched by the edit.
        self.assertTrue(AlertRule.objects.filter(pk=self.past_rule.pk).exists())
        self.assertTrue(Alert.objects.filter(pk=self.past_alert.pk).exists())
        self.assertTrue(SmsMessage.objects.filter(pk=self.past_sms.pk).exists())
        self.past_alert.refresh_from_db()
        self.assertEqual(self.past_alert.message, 'Ancienne tâche')


class HouseProtocolTimeSlotTests(APITestCase):
    """PUT/GET /api/houses/{houseCode}/protocol/ round-tripping `ProtocolTimeSlot` rows
    (Bug 1 fix, 2026-08-27, docs/deviations.md) — the root cause was two-fold: the serializer
    never exposed `time_slots` at all, and the "Modifier"/onboarding UI never rendered a
    "Horaires" section, not a data/migration problem (the model + migration already existed and
    were applied)."""

    def setUp(self):
        self.farm = Farm.objects.create(name='Ferme Horaires Test')
        self.admin = User.objects.create_user(
            email='admin@timeslot-test.local', password='x', name='Admin', role=UserRole.ADMIN, farm=self.farm,
        )
        create_role_profile(self.admin)
        self.client.force_authenticate(user=self.admin)
        self.house = PoultryHouse.objects.create(house_code='H-SLOT-1', farm=self.farm, name='Bâtiment', max_capacity=1000)
        self.category = ProtocolCategory.objects.create(house=self.house, label='Alimentation', icon='Soup')
        self.url = f'/api/houses/{self.house.house_code}/protocol/'

    def _payload(self, time_slots):
        return {'lines': [{
            'category': self.category.id, 'from_value': 1, 'from_unit': 'DAY',
            'to_value': None, 'to_unit': 'DAY', 'until_end': True,
            'what': 'Nourrissage', 'details': '', 'time_slots': time_slots,
        }]}

    def test_saving_and_reloading_two_time_slots_round_trips_correctly(self):
        payload = self._payload([
            {'start_time': '07:00', 'end_time': '09:00'},
            {'start_time': '18:00', 'end_time': '20:00'},
        ])
        response = self.client.put(self.url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        slots = sorted(response.data[0]['time_slots'], key=lambda s: s['start_time'])
        self.assertEqual(len(slots), 2)
        self.assertEqual((slots[0]['start_time'], slots[0]['end_time']), ('07:00:00', '09:00:00'))
        self.assertEqual((slots[1]['start_time'], slots[1]['end_time']), ('18:00:00', '20:00:00'))

        # Reload, as the "Modifier" modal does on open — must reflect what was just saved.
        reload_response = self.client.get(self.url)
        self.assertEqual(len(reload_response.data[0]['time_slots']), 2)

    def test_line_with_no_time_slots_is_valid(self):
        response = self.client.put(self.url, self._payload([]), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data[0]['time_slots'], [])

    def test_end_before_start_is_rejected(self):
        response = self.client.put(self.url, self._payload([{'start_time': '09:00', 'end_time': '07:00'}]), format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_re_saving_the_protocol_replaces_time_slots_not_merges_them(self):
        self.client.put(self.url, self._payload([{'start_time': '07:00', 'end_time': '09:00'}]), format='json')
        response = self.client.put(self.url, self._payload([{'start_time': '12:00', 'end_time': '13:00'}]), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(len(response.data[0]['time_slots']), 1)
        self.assertEqual(response.data[0]['time_slots'][0]['start_time'], '12:00:00')
        # The old ProtocolTimeSlot row was actually deleted (cascade from the full-replace),
        # not just unlinked/orphaned.
        self.assertEqual(ProtocolTimeSlot.objects.count(), 1)


class TaskAssignmentTests(APITestCase):
    """PATCH /api/houses/{houseCode}/tasks-now/{taskId}/assign/ and GET /api/tasks/mine/
    (docs/deviations.md Part 15, Part E) — assigning a protocol-line task to an employee makes
    it show up, correctly, in that employee's own "Mes tâches" view."""

    def setUp(self):
        self.farm = Farm.objects.create(name='Ferme Tâches Test')
        self.admin = User.objects.create_user(
            email='admin@task-test.local', password='x', name='Admin', role=UserRole.ADMIN, farm=self.farm,
        )
        create_role_profile(self.admin)
        self.farmer = User.objects.create_user(
            email='farmer@task-test.local', password='x', name='Fermier Test', role=UserRole.FARMER, farm=self.farm,
        )
        create_role_profile(self.farmer)
        self.worker = User.objects.create_user(
            email='worker@task-test.local', password='x', name='Ouvrier Test', role=UserRole.WORKER, farm=self.farm,
        )
        create_role_profile(self.worker)

        self.house = PoultryHouse.objects.create(house_code='H-TASK-1', farm=self.farm, name='Bâtiment', max_capacity=1000)
        self.category = ProtocolCategory.objects.create(house=self.house, label='Alimentation', icon='Soup')
        self.line = ProtocolTemplate.objects.create(
            house=self.house, category=self.category, from_value=1, until_end=True, what='Distribution aliment',
        )
        self.batch = PoultryBatch.objects.create(
            batch_code='BATCH-TASK-1', house=self.house, production_type=ProductionType.BROILER,
            initial_count=500, start_date=date.today() - timedelta(days=1),  # day_of_cycle=1, matching from_value=1
        )
        self.assign_url = f'/api/houses/{self.house.house_code}/tasks-now/{self.line.id}/assign/'

    def test_admin_assigns_task_and_it_appears_in_the_employees_my_tasks_view(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.patch(self.assign_url, {'assignees': [self.worker.id]}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['assignedToNames'], ['Ouvrier Test'])

        self.client.force_authenticate(user=self.worker)
        mine = self.client.get('/api/tasks/mine/')
        self.assertEqual(mine.status_code, status.HTTP_200_OK)
        self.assertEqual(len(mine.data), 1)
        self.assertEqual(mine.data[0]['what'], 'Distribution aliment')
        self.assertEqual(mine.data[0]['houseCode'], self.house.house_code)

        # Unassigned to anyone else — additive, not a restriction (Part E item 4): still visible
        # via the ordinary tasks-now panel, just not surfaced in a *different* user's "mine".
        self.client.force_authenticate(user=self.farmer)
        farmer_mine = self.client.get('/api/tasks/mine/')
        self.assertEqual(farmer_mine.data, [])
        tasks_now = self.client.get(f'/api/houses/{self.house.house_code}/tasks-now/')
        self.assertEqual(len(tasks_now.data['tasks']), 1)

    def test_worker_cannot_assign_tasks(self):
        self.client.force_authenticate(user=self.worker)
        response = self.client.patch(self.assign_url, {'assignees': [self.worker.id]}, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_clearing_an_assignment(self):
        self.client.force_authenticate(user=self.admin)
        self.client.patch(self.assign_url, {'assignees': [self.worker.id]}, format='json')
        response = self.client.patch(self.assign_url, {'assignees': []}, format='json')
        self.assertEqual(response.data['assignedTo'], [])

    def test_admin_can_assign_a_task_to_themselves(self):
        # Feature 4 (2026-08-27, docs/deviations.md) — any role, including the assigner's own
        # Admin account, can be the assignee; not just operational roles.
        self.client.force_authenticate(user=self.admin)
        response = self.client.patch(self.assign_url, {'assignees': [self.admin.id]}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['assignedTo'], [self.admin.id])

        mine = self.client.get('/api/tasks/mine/')
        self.assertEqual(len(mine.data), 1)


class AssignableUsersViewTests(APITestCase):
    """GET /api/tasks/assignable-users/ (2026-08-27 bugfix, docs/deviations.md) — replaces
    TasksNowPanel's previous reuse of GET /api/employees/, which 403'd a Farm Manager/Farmer
    assigner and excluded the requester's own account from the options."""

    def setUp(self):
        self.farm = Farm.objects.create(name='Ferme Assignable Test')
        self.admin = User.objects.create_user(
            email='admin@assignable-test.local', password='x', name='Admin', role=UserRole.ADMIN, farm=self.farm,
        )
        create_role_profile(self.admin)
        self.farmer = User.objects.create_user(
            email='farmer@assignable-test.local', password='x', name='Fermier', role=UserRole.FARMER, farm=self.farm,
        )
        create_role_profile(self.farmer)
        self.worker = User.objects.create_user(
            email='worker@assignable-test.local', password='x', name='Ouvrier', role=UserRole.WORKER, farm=self.farm,
        )
        create_role_profile(self.worker)

    def test_farmer_can_list_every_role_including_admin_and_themselves(self):
        self.client.force_authenticate(user=self.farmer)
        response = self.client.get('/api/tasks/assignable-users/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        names = {u['name'] for u in response.data}
        self.assertEqual(names, {'Admin', 'Fermier', 'Ouvrier'})

    def test_worker_cannot_list_assignable_users(self):
        self.client.force_authenticate(user=self.worker)
        response = self.client.get('/api/tasks/assignable-users/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class CycleMilestonesTests(APITestCase):
    """GET /api/houses/{houseCode}/milestones/ and /api/tasks/upcoming/ (docs/deviations.md
    Part 16, Part B/C) — full-cycle projection and the 48h-window filter built on the same
    `compute_cycle_milestones`."""

    def setUp(self):
        self.farm = Farm.objects.create(name='Ferme Timeline Test')
        self.admin = User.objects.create_user(email='admin@timeline-test.local', password='x', name='Admin', role=UserRole.ADMIN, farm=self.farm)
        create_role_profile(self.admin)
        self.house = PoultryHouse.objects.create(house_code='H-TL-1', farm=self.farm, name='Bâtiment Timeline', max_capacity=1000)
        self.category = ProtocolCategory.objects.create(house=self.house, label='Vaccination', icon='Syringe')
        # day 1 (past, batch is 10 days in), day 12 (near-future, within 48h), day 30 (far future)
        ProtocolTemplate.objects.create(house=self.house, category=self.category, from_value=1, what='Passé')
        ProtocolTemplate.objects.create(house=self.house, category=self.category, from_value=12, what='Bientôt')
        ProtocolTemplate.objects.create(house=self.house, category=self.category, from_value=30, what='Plus tard')
        self.batch = PoultryBatch.objects.create(
            batch_code='BATCH-TL-1', house=self.house, production_type=ProductionType.BROILER,
            initial_count=500, start_date=date.today() - timedelta(days=10), planned_end_date=date.today() + timedelta(days=46),
        )
        self.client.force_authenticate(user=self.admin)

    def test_milestones_positioned_and_flagged_past_or_upcoming(self):
        response = self.client.get(f'/api/houses/{self.house.house_code}/milestones/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['dayOfCycle'], 10)
        self.assertEqual(response.data['cycleLength'], 56)
        by_what = {m['what']: m for m in response.data['milestones']}
        self.assertEqual(by_what['Passé']['day'], 1)
        self.assertTrue(by_what['Passé']['isPast'])
        self.assertEqual(by_what['Bientôt']['day'], 12)
        self.assertFalse(by_what['Bientôt']['isPast'])
        self.assertFalse(by_what['Plus tard']['isPast'])

    def test_upcoming_48h_includes_only_the_near_future_milestone(self):
        response = self.client.get('/api/tasks/upcoming/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        whats = [r['what'] for r in response.data]
        self.assertEqual(whats, ['Bientôt'])
        self.assertEqual(response.data[0]['houseName'], 'Bâtiment Timeline')




class ProtocolEditPermissionTests(APITestCase):
    """PUT /api/houses/{code}/protocol/ is `CanEditHouseProtocol` (Admin / Farm Manager / the
    house's Farmer). Unauthorized roles get a 403 and the protocol is left untouched."""

    def setUp(self):
        self.farm = Farm.objects.create(name='Ferme Perm Protocole')
        self.house = PoultryHouse.objects.create(house_code='H-PP-1', farm=self.farm, name='Bâtiment', max_capacity=1000)
        self.category = ProtocolCategory.objects.create(house=self.house, label='Alimentation', icon='Soup')
        ProtocolTemplate.objects.create(house=self.house, category=self.category, from_value=1, what='Existant')
        self.payload = {'lines': [{
            'category': self.category.id, 'from_value': 5, 'from_unit': 'DAY',
            'to_value': None, 'to_unit': 'DAY', 'until_end': False, 'what': 'Modifié', 'details': '',
        }]}

    def _user(self, role, email):
        user = User.objects.create_user(email=email, password='x', name='U', role=role, farm=self.farm)
        create_role_profile(user)
        return user

    def test_worker_gets_403_and_protocol_is_unchanged(self):
        self.client.force_authenticate(user=self._user(UserRole.WORKER, 'w@pp.local'))
        resp = self.client.put(f'/api/houses/{self.house.house_code}/protocol/', self.payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(list(ProtocolTemplate.objects.filter(house=self.house).values_list('what', flat=True)), ['Existant'])

    def test_cashier_gets_403(self):
        self.client.force_authenticate(user=self._user(UserRole.CASHIER, 'c@pp.local'))
        resp = self.client.put(f'/api/houses/{self.house.house_code}/protocol/', self.payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_can_edit(self):
        self.client.force_authenticate(user=self._user(UserRole.ADMIN, 'a@pp.local'))
        resp = self.client.put(f'/api/houses/{self.house.house_code}/protocol/', self.payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(list(ProtocolTemplate.objects.filter(house=self.house).values_list('what', flat=True)), ['Modifié'])


class MarquerCommeFaitTests(APITestCase):
    """POST /api/houses/{code}/tasks-now/{lineId}/complete/ — the single, validation-triggered
    stock-deduction mechanism (2026-08-31). Idempotent; non-blocking insufficient-stock check."""

    def setUp(self):
        from apps.stock.calculations import current_quantity
        from apps.stock.models import MovementType, StockCategory, StockItem, StockMovement

        self._cq = current_quantity
        self._MovementType = MovementType
        self._StockMovement = StockMovement

        self.farm = Farm.objects.create(name='Ferme Fait')
        self.admin = User.objects.create_user(email='a@fait.local', password='x', name='A', role=UserRole.ADMIN, farm=self.farm)
        create_role_profile(self.admin)
        self.client.force_authenticate(self.admin)
        self.house = PoultryHouse.objects.create(house_code='H-F-1', farm=self.farm, name='Salle', max_capacity=1000)
        self.today = date.today()
        self.batch = PoultryBatch.objects.create(
            batch_code='BATCH-F-1', house=self.house, production_type=ProductionType.BROILER,
            initial_count=500, start_date=self.today - timedelta(days=3),  # day_of_cycle 3
        )
        self.category = ProtocolCategory.objects.create(house=self.house, label='Alimentation', icon='Soup')
        self.cat = StockCategory.objects.get(farm=self.farm, kind='FEED')
        self.item = StockItem.objects.create(
            item_code='FEE-1-001', farm=self.farm, category=self.cat, name='Aliment démarrage', unit='kg',
        )
        StockMovement.objects.create(item=self.item, movement_type=MovementType.IN, quantity=100, movement_date=self.today)
        self.line = ProtocolTemplate.objects.create(
            house=self.house, category=self.category, from_value=1, from_unit='DAY',
            to_value=15, to_unit='DAY', what='Alimentation', stock_item=self.item, quantity_per_day=40,
        )
        self.url = f'/api/houses/{self.house.house_code}/tasks-now/{self.line.id}/complete/'

    def test_no_deduction_just_because_a_day_passed(self):
        """A day inside the line's range with no "Marquer comme fait" → stock unchanged."""
        self.assertEqual(self._cq(self.item), 100)  # nothing auto-deducts anymore

    def test_marking_done_creates_one_out_movement(self):
        resp = self.client.post(self.url, {}, format='json')
        self.assertEqual(resp.status_code, 201, resp.data)
        self.assertEqual(resp.data['status'], 'done')
        self.assertEqual(resp.data['movement']['quantity'], 40)
        mv = self._StockMovement.objects.get(id=resp.data['movement']['id'])
        self.assertEqual(mv.movement_type, self._MovementType.OUT)
        self.assertEqual(mv.batch_id, self.batch.batch_code)
        self.assertEqual(mv.item_id, self.item.item_code)
        self.assertEqual(mv.protocol_line_id, self.line.id)
        self.assertEqual(self._cq(self.item), 60)

    def test_marking_done_twice_is_idempotent(self):
        self.client.post(self.url, {}, format='json')
        resp2 = self.client.post(self.url, {}, format='json')
        self.assertEqual(resp2.status_code, 200)
        self.assertEqual(resp2.data['status'], 'already_done')
        self.assertEqual(self._StockMovement.objects.filter(movement_type=self._MovementType.OUT).count(), 1)
        self.assertEqual(self._cq(self.item), 60)

    def test_row_without_resource_records_completion_no_movement(self):
        bare = ProtocolTemplate.objects.create(
            house=self.house, category=self.category, from_value=1, to_value=15, what='Nettoyage',
        )
        resp = self.client.post(f'/api/houses/{self.house.house_code}/tasks-now/{bare.id}/complete/', {}, format='json')
        self.assertEqual(resp.status_code, 201)
        self.assertIsNone(resp.data['movement'])
        self.assertEqual(self._StockMovement.objects.filter(movement_type=self._MovementType.OUT).count(), 0)

    def test_insufficient_stock_is_non_blocking_and_writes_nothing_without_force(self):
        self.line.quantity_per_day = 250  # > 100 on hand
        self.line.save(update_fields=['quantity_per_day'])
        resp = self.client.post(self.url, {}, format='json')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['status'], 'insufficient_stock')
        self.assertEqual(resp.data['shortfall']['needed'], 250)
        self.assertEqual(resp.data['shortfall']['onHand'], 100)
        self.assertEqual(self._StockMovement.objects.filter(movement_type=self._MovementType.OUT).count(), 0)

    def test_force_completes_despite_insufficient_stock(self):
        self.line.quantity_per_day = 250
        self.line.save(update_fields=['quantity_per_day'])
        resp = self.client.post(self.url, {'force': True}, format='json')
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.data['status'], 'done')
        self.assertEqual(self._cq(self.item), -150)  # allowed to go negative

    def test_dose_per_bird_uses_current_count(self):
        self.line.quantity_per_day = None
        self.line.dose_per_bird = 0.1  # 0.1 * 500 birds = 50
        self.line.save(update_fields=['quantity_per_day', 'dose_per_bird'])
        resp = self.client.post(self.url, {}, format='json')
        self.assertEqual(resp.data['movement']['quantity'], 50)
        self.assertEqual(self._cq(self.item), 50)
