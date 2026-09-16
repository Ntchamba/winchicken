"""An assignment must stay visible and clearable on the day its task is not due.

Reported (FIX 4): a WEIGHING_REMINDER assigned to Ouvrier 01 on day 0 vanished from the admin
panel and from /api/tasks/mine/ the moment the cycle rolled to day 1, while
`AlertRule.assignees` sat in the database with no UI able to see or clear it.

The cause is the due-today filter, not an expired target. `compute_tasks_now` feeds both views
and only emits what is due *right now* — `weighing_reminder_task` returns None unless
`day_of_cycle % cadence == 0`, and `_protocol_line_occurrence` returns None outside the line's
day range. Assignment display was hung off that list, so it inherited the filter. The weekly
reminder had not expired at all: it is due again six days later.
"""
import datetime as dt

from rest_framework.test import APITestCase

from apps.alerts.models import AlertRule, AlertRuleType
from apps.batches.models import BatchStatus, PoultryBatch, ProductionType
from apps.batches.services import sync_weighing_reminder
from apps.core.models import Farm, User, UserRole, create_role_profile
from apps.houses.models import PoultryHouse
from apps.protocols.models import ProtocolCategory, ProtocolTemplate


class AssignmentVisibilityTests(APITestCase):
    def setUp(self):
        self.farm = Farm.objects.create(name='Ferme Affectation')
        self.admin = User.objects.create_user(
            email='admin@affect.local', password='x', name='Admin',
            role=UserRole.ADMIN, farm=self.farm,
        )
        create_role_profile(self.admin)
        self.worker = User.objects.create_user(
            email='ouvrier01@affect.local', password='x', name='Ouvrier 01',
            role=UserRole.WORKER, farm=self.farm,
        )
        create_role_profile(self.worker)

        self.house = PoultryHouse.objects.create(
            house_code=f'H-{self.farm.id}-001', farm=self.farm, name='Poulailler', max_capacity=1000,
        )
        self.batch = PoultryBatch.objects.create(
            batch_code='BATCH-A-1', house=self.house, name='Bande', production_type=ProductionType.BROILER,
            initial_count=1000, start_date=dt.date.today(),
            planned_end_date=dt.date.today() + dt.timedelta(days=56), status=BatchStatus.ACTIVE,
            weighing_frequency='WEEK',
        )
        sync_weighing_reminder(self.batch)
        self.rule = AlertRule.objects.get(batch=self.batch, rule_type=AlertRuleType.WEIGHING_REMINDER)
        self.rule.assignees.add(self.worker)

        category = ProtocolCategory.objects.filter(house=self.house, label='Alimentation').first()
        self.line = ProtocolTemplate.objects.create(
            house=self.house, category=category, from_value=1, to_value=15,
            what='Aliment démarrage', details='',
        )
        self.line.assignees.add(self.worker)

    def _roll_to_day(self, day):
        self.batch.start_date = dt.date.today() - dt.timedelta(days=day)
        self.batch.save(update_fields=['start_date'])

    def _assignments(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(f'/api/houses/{self.house.house_code}/assignments/')
        self.assertEqual(response.status_code, 200)
        return {row['id']: row for row in response.data}

    def test_the_weighing_assignment_is_listed_on_the_day_it_is_due(self):
        rows = self._assignments()
        weighing = rows[f'weighing-{self.batch.batch_code}']
        self.assertEqual(weighing['assignedToNames'], ['Ouvrier 01'])
        self.assertTrue(weighing['activeToday'])

    def test_the_weighing_assignment_is_still_listed_the_day_after(self):
        self._roll_to_day(1)
        rows = self._assignments()
        weighing = rows.get(f'weighing-{self.batch.batch_code}')
        self.assertIsNotNone(weighing, 'the assignment must not vanish when the task is not due')
        self.assertEqual(weighing['assignedToNames'], ['Ouvrier 01'])
        self.assertFalse(weighing['activeToday'], 'and it must be marked as not due today')
        self.assertEqual(weighing['periodLabel'], 'Hebdomadaire')

    def test_a_protocol_assignment_is_still_listed_past_the_end_of_its_range(self):
        self._roll_to_day(20)
        rows = self._assignments()
        line = rows.get(str(self.line.id))
        self.assertIsNotNone(line)
        self.assertFalse(line['activeToday'])
        self.assertEqual(line['periodLabel'], 'Jours 1 à 15')

    def test_the_old_task_list_still_shows_only_what_is_due(self):
        """The fix must widen assignment visibility without polluting "à effectuer maintenant"."""
        self._roll_to_day(20)
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(f'/api/houses/{self.house.house_code}/tasks-now/')
        ids = {str(task['id']) for task in response.data['tasks']}
        self.assertNotIn(f'weighing-{self.batch.batch_code}', ids)
        self.assertNotIn(str(self.line.id), ids)

    def test_an_assignment_that_is_not_due_today_can_still_be_cleared(self):
        self._roll_to_day(1)
        self.client.force_authenticate(user=self.admin)
        response = self.client.patch(
            f'/api/houses/{self.house.house_code}/tasks-now/weighing-{self.batch.batch_code}/assign/',
            {'assignees': []}, format='json',
        )
        self.assertEqual(response.status_code, 200)
        self.rule.refresh_from_db()
        self.assertEqual(list(self.rule.assignees.all()), [])
        self.assertNotIn(f'weighing-{self.batch.batch_code}', self._assignments())

    def test_a_protocol_assignment_out_of_range_can_still_be_cleared(self):
        self._roll_to_day(20)
        self.client.force_authenticate(user=self.admin)
        response = self.client.patch(
            f'/api/houses/{self.house.house_code}/tasks-now/{self.line.id}/assign/',
            {'assignees': []}, format='json',
        )
        self.assertEqual(response.status_code, 200)
        self.line.refresh_from_db()
        self.assertEqual(list(self.line.assignees.all()), [])

    def test_unassigned_tasks_are_not_listed(self):
        self.line.assignees.clear()
        self.assertNotIn(str(self.line.id), self._assignments())

    def test_a_worker_cannot_read_the_assignment_list(self):
        self.client.force_authenticate(user=self.worker)
        response = self.client.get(f'/api/houses/{self.house.house_code}/assignments/')
        self.assertEqual(response.status_code, 403)

    def test_activeToday_agrees_with_the_task_list_rather_than_recomputing_it(self):
        """The two must never be able to disagree — `activeToday` is derived from the same
        `compute_tasks_now` output the panel renders."""
        for day in (0, 1, 7, 16):
            with self.subTest(day=day):
                self._roll_to_day(day)
                self.client.force_authenticate(user=self.admin)
                tasks = self.client.get(f'/api/houses/{self.house.house_code}/tasks-now/').data['tasks']
                due_ids = {str(task['id']) for task in tasks}
                for task_id, row in self._assignments().items():
                    self.assertEqual(row['activeToday'], task_id in due_ids)
