"""Saving a house protocol must not destroy that house's task-completion history.

`PUT /api/houses/{code}/protocol/` used to delete every ProtocolTemplate row for the house and
recreate it. `TaskCompletion.protocol_template` is CASCADE, and so is
`TaskCompletion.time_slot`, so an ordinary save — including opening the form and pressing save
without changing anything — wiped every completion the house had ever recorded.

The consequence was not just lost history. The `OUT` StockMovement survived (SET_NULL), so the
stock stayed down, but `get_or_create` in `complete_task_occurrence` no longer found the
completion: the task read as outstanding again and the next tap deducted a second time. One
day's feeding took 80 kg instead of 40 (FIX 3.5, bug A).

These send the GET payload straight back, unchanged, the way the form does.
"""
import datetime as dt
from decimal import Decimal

from rest_framework.test import APITestCase

from apps.batches.models import BatchStatus, PoultryBatch, ProductionType
from apps.core.models import Farm, User, UserRole, create_role_profile
from apps.houses.models import PoultryHouse
from apps.houses.services import compute_tasks_now
from apps.protocols.models import (
    ProtocolCategory, ProtocolTemplate, ProtocolTimeSlot, TaskCompletion,
)
from apps.protocols.services import expand_protocol_to_alert_rules
from apps.stock.calculations import current_quantity
from apps.stock.consumption import complete_task_occurrence
from apps.stock.models import MovementType, StockCategory, StockItem, StockMovement


class ProtocolUpsertTests(APITestCase):
    def setUp(self):
        self.farm = Farm.objects.create(name='Ferme Protocole')
        self.admin = User.objects.create_user(
            email='admin@proto.local', password='x', name='Admin',
            role=UserRole.ADMIN, farm=self.farm,
        )
        create_role_profile(self.admin)
        self.worker = User.objects.create_user(
            email='worker@proto.local', password='x', name='Ouvrier',
            role=UserRole.WORKER, farm=self.farm,
        )
        create_role_profile(self.worker)

        self.house = PoultryHouse.objects.create(
            house_code=f'H-{self.farm.id}-001', farm=self.farm, name='Poulailler', max_capacity=500,
        )
        self.batch = PoultryBatch.objects.create(
            batch_code='BATCH-P-1', house=self.house, name='Bande', production_type=ProductionType.BROILER,
            initial_count=500, start_date=dt.date.today() - dt.timedelta(days=1),
            planned_end_date=dt.date.today() + dt.timedelta(days=55), status=BatchStatus.ACTIVE,
        )
        feed = StockCategory.objects.get(farm=self.farm, kind='FEED')
        self.item = StockItem.objects.create(
            item_code=f'FEE-{self.farm.id}-001', farm=self.farm, category=feed, name='Provende',
            unit='kg', alert_threshold=10, unit_price=Decimal('450.00'),
        )
        StockMovement.objects.create(
            item=self.item, movement_type=MovementType.IN, quantity=500, movement_date=dt.date.today(),
        )
        category = ProtocolCategory.objects.filter(house=self.house, label='Alimentation').first()
        self.line = ProtocolTemplate.objects.create(
            house=self.house, category=category, from_value=1, until_end=True,
            what='Aliment démarrage', details='', stock_item=self.item, quantity_per_day=40,
        )
        self.slot = ProtocolTimeSlot.objects.create(
            protocol_line=self.line, start_time='06:30', end_time='07:30',
        )

    def _save_unchanged(self):
        """GET the protocol and PUT it straight back — the do-nothing save."""
        self.client.force_authenticate(user=self.admin)
        read = self.client.get(f'/api/houses/{self.house.house_code}/protocol/')
        self.assertEqual(read.status_code, 200)
        written = self.client.put(
            f'/api/houses/{self.house.house_code}/protocol/', {'lines': read.data}, format='json',
        )
        self.assertEqual(written.status_code, 200, written.data)
        return written

    def test_an_unchanged_save_keeps_the_line_and_its_slot_identity(self):
        self._save_unchanged()
        self.line.refresh_from_db()
        self.assertEqual(ProtocolTemplate.objects.filter(house=self.house).count(), 1)
        self.assertEqual(
            list(ProtocolTemplate.objects.filter(house=self.house).values_list('id', flat=True)),
            [self.line.id], 'the line must be updated in place, not recreated with a new id',
        )
        self.assertEqual(
            list(self.line.time_slots.values_list('id', flat=True)), [self.slot.id],
            'an unchanged time slot must keep its id — TaskCompletion.time_slot is CASCADE',
        )

    def test_an_unchanged_save_keeps_a_completion(self):
        complete_task_occurrence(self.line, self.batch, time_slot=self.slot, user=self.worker)
        self.assertEqual(TaskCompletion.objects.filter(protocol_template=self.line).count(), 1)

        self._save_unchanged()

        self.assertEqual(
            TaskCompletion.objects.filter(protocol_template=self.line).count(), 1,
            'saving the protocol must not delete the completion history',
        )

    def test_the_task_still_reads_as_done_after_a_protocol_save(self):
        complete_task_occurrence(self.line, self.batch, time_slot=self.slot, user=self.worker)
        self._save_unchanged()

        _, tasks = compute_tasks_now(self.house)
        task = next(t for t in tasks if str(t['id']) == str(self.line.id))
        self.assertTrue(task['done'], 'a completed task must still read as done after a save')
        self.assertEqual(task['completedByName'], 'Ouvrier')

    def test_a_protocol_save_cannot_cause_a_second_deduction(self):
        self.assertEqual(current_quantity(self.item), 500)
        complete_task_occurrence(self.line, self.batch, time_slot=self.slot, user=self.worker)
        self.assertEqual(current_quantity(self.item), 460)

        self._save_unchanged()

        first_movement = StockMovement.objects.get(item=self.item, movement_type=MovementType.OUT)

        # The worker taps "Marquer comme fait" again on the same occurrence.
        result = complete_task_occurrence(self.line, self.batch, time_slot=self.slot, user=self.worker)
        self.assertTrue(result['already_done'], 'the occurrence must still be recognised as done')
        # It hands back the movement already on file rather than writing a second one.
        self.assertEqual(result['movement'].pk, first_movement.pk)
        self.assertEqual(StockMovement.objects.filter(item=self.item, movement_type=MovementType.OUT).count(), 1)
        self.assertEqual(
            current_quantity(self.item), 460,
            'one occurrence must never deduct twice because the protocol was saved in between',
        )

    def test_editing_one_line_leaves_another_line_completion_alone(self):
        category = ProtocolCategory.objects.filter(house=self.house, label='Santé et soins').first()
        other = ProtocolTemplate.objects.create(
            house=self.house, category=category, from_value=1, until_end=True,
            what='Vitamines', details='',
        )
        complete_task_occurrence(self.line, self.batch, time_slot=self.slot, user=self.worker)

        self.client.force_authenticate(user=self.admin)
        read = self.client.get(f'/api/houses/{self.house.house_code}/protocol/')
        lines = list(read.data)
        for entry in lines:
            if entry['id'] == other.id:
                entry['what'] = 'Vitamines et anti-infectieux'
        response = self.client.put(
            f'/api/houses/{self.house.house_code}/protocol/', {'lines': lines}, format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)

        other.refresh_from_db()
        self.assertEqual(other.what, 'Vitamines et anti-infectieux')
        self.assertEqual(
            TaskCompletion.objects.filter(protocol_template=self.line).count(), 1,
            'editing one line must not clear the completions of another',
        )

    def test_a_new_line_is_created_and_an_omitted_line_is_deleted(self):
        self.client.force_authenticate(user=self.admin)
        read = self.client.get(f'/api/houses/{self.house.house_code}/protocol/')
        category = ProtocolCategory.objects.filter(house=self.house, label='Nettoyage').first()
        lines = list(read.data) + [{
            'category': category.id, 'from_value': 7, 'from_unit': 'DAY', 'to_value': 7,
            'to_unit': 'DAY', 'until_end': False, 'what': 'Ajout de litière', 'details': '',
            'time_slots': [],
        }]
        self.client.put(f'/api/houses/{self.house.house_code}/protocol/', {'lines': lines}, format='json')
        self.assertEqual(ProtocolTemplate.objects.filter(house=self.house).count(), 2)
        self.assertEqual(TaskCompletion.objects.filter(protocol_template=self.line).count(), 0)

        # Now drop the original line entirely — an omission is a deletion.
        read = self.client.get(f'/api/houses/{self.house.house_code}/protocol/')
        kept = [entry for entry in read.data if entry['id'] != self.line.id]
        self.client.put(f'/api/houses/{self.house.house_code}/protocol/', {'lines': kept}, format='json')
        self.assertFalse(ProtocolTemplate.objects.filter(pk=self.line.pk).exists())
        self.assertEqual(ProtocolTemplate.objects.filter(house=self.house).count(), 1)

    def test_an_id_from_another_house_creates_a_line_rather_than_hijacking_one(self):
        other_house = PoultryHouse.objects.create(
            house_code=f'H-{self.farm.id}-002', farm=self.farm, name='Poulailler 2', max_capacity=500,
        )
        other_category = ProtocolCategory.objects.filter(house=other_house, label='Alimentation').first()
        foreign = ProtocolTemplate.objects.create(
            house=other_house, category=other_category, from_value=1, until_end=True,
            what='Ne pas toucher', details='',
        )

        category = ProtocolCategory.objects.filter(house=self.house, label='Nettoyage').first()
        self.client.force_authenticate(user=self.admin)
        response = self.client.put(
            f'/api/houses/{self.house.house_code}/protocol/',
            {'lines': [{
                'id': foreign.id, 'category': category.id, 'from_value': 1, 'from_unit': 'DAY',
                'to_value': 1, 'to_unit': 'DAY', 'until_end': False, 'what': 'Détournement',
                'details': '', 'time_slots': [],
            }]},
            format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)

        foreign.refresh_from_db()
        self.assertEqual(foreign.what, 'Ne pas toucher', "a line from another house must not be editable")
        self.assertEqual(foreign.house_id, other_house.house_code)

    def test_a_protocol_save_keeps_the_notification_history_of_its_alert_rules(self):
        """`expand_protocol_to_alert_rules` runs on every protocol save. It used to delete the
        batch's PROTOCOL_TASK rules and recreate them, and `Alert.rule` is CASCADE — so the
        notification-bell history, `is_read` state included, went with them."""
        from apps.alerts.models import Alert, AlertRule, AlertRuleType

        expand_protocol_to_alert_rules(self.batch)
        rule = AlertRule.objects.filter(batch=self.batch, rule_type=AlertRuleType.PROTOCOL_TASK).first()
        self.assertIsNotNone(rule)
        alert = Alert.objects.create(rule=rule, batch=self.batch, message='Aliment démarrage', is_read=True)

        self._save_unchanged()

        self.assertTrue(
            Alert.objects.filter(pk=alert.pk).exists(),
            'saving the protocol must not delete the alerts already raised from its rules',
        )
        alert.refresh_from_db()
        self.assertTrue(alert.is_read, 'the bell read state must survive too')
        self.assertTrue(AlertRule.objects.filter(pk=rule.pk).exists())

    def test_removing_a_line_removes_the_alert_rules_it_generated(self):
        from apps.alerts.models import AlertRule, AlertRuleType

        expand_protocol_to_alert_rules(self.batch)
        self.assertTrue(
            AlertRule.objects.filter(batch=self.batch, protocol_line=self.line).exists(),
        )

        self.client.force_authenticate(user=self.admin)
        self.client.put(f'/api/houses/{self.house.house_code}/protocol/', {'lines': []}, format='json')

        self.assertFalse(ProtocolTemplate.objects.filter(house=self.house).exists())
        self.assertFalse(
            AlertRule.objects.filter(
                batch=self.batch, rule_type=AlertRuleType.PROTOCOL_TASK, active=True,
            ).exists(),
            'a rule whose line is gone must not survive the reconcile',
        )

    def test_changing_a_slot_time_replaces_only_that_slot(self):
        evening = ProtocolTimeSlot.objects.create(
            protocol_line=self.line, start_time='18:30', end_time='19:30',
        )
        self.client.force_authenticate(user=self.admin)
        read = self.client.get(f'/api/houses/{self.house.house_code}/protocol/')
        lines = list(read.data)
        lines[0]['time_slots'] = [
            {'start_time': '06:30:00', 'end_time': '07:30:00'},
            {'start_time': '19:00:00', 'end_time': '20:00:00'},
        ]
        self.client.put(f'/api/houses/{self.house.house_code}/protocol/', {'lines': lines}, format='json')

        slot_ids = set(self.line.time_slots.values_list('id', flat=True))
        self.assertIn(self.slot.id, slot_ids, 'the untouched morning slot keeps its identity')
        self.assertNotIn(evening.id, slot_ids, 'the retimed evening slot is a different occurrence')
        self.assertEqual(len(slot_ids), 2)

    def test_a_protocol_save_keeps_every_assignee_of_a_line(self):
        """FIX 7, requirement 5. The pre-3.5 delete-and-recreate took the assignment with the
        row; the upsert must not, and `ProtocolTemplateSerializer` deliberately does not expose
        `assignees`, so the M2M is simply never touched by a save. Pinned here because the form
        posting a line back without its assignees is exactly what used to clear them."""
        second = User.objects.create_user(
            email='worker2@proto.local', password='x', name='Ouvrier 02',
            role=UserRole.WORKER, farm=self.farm,
        )
        create_role_profile(second)
        self.line.assignees.set([self.worker, second])

        self._save_unchanged()

        self.line.refresh_from_db()
        self.assertEqual(
            sorted(self.line.assignees.values_list('id', flat=True)),
            sorted([self.worker.id, second.id]),
            'a protocol save must not clear the line assignment',
        )
        _, tasks = compute_tasks_now(self.house)
        task = next(t for t in tasks if str(t['id']) == str(self.line.id))
        self.assertEqual(sorted(task['assignedTo']), sorted([self.worker.id, second.id]))

    def test_an_edited_line_keeps_its_assignees(self):
        """The same line, renamed and re-ranged — the row is updated in place, so the set rides
        along. A rename that reads as delete + create is how the assignment used to die."""
        self.line.assignees.set([self.worker])
        self.client.force_authenticate(user=self.admin)
        read = self.client.get(f'/api/houses/{self.house.house_code}/protocol/')
        lines = [{**line, 'what': 'Aliment croissance', 'from_value': 3} for line in read.data]
        written = self.client.put(
            f'/api/houses/{self.house.house_code}/protocol/', {'lines': lines}, format='json',
        )
        self.assertEqual(written.status_code, 200, written.data)

        self.line.refresh_from_db()
        self.assertEqual(self.line.what, 'Aliment croissance')
        self.assertEqual(list(self.line.assignees.values_list('id', flat=True)), [self.worker.id])
