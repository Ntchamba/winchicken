"""Marking a protocol task done, and undoing it.

The deduction path (apps.stock.consumption) and the complete endpoint already existed but were
unreachable from the UI, so nothing exercised them end to end. These pin the behaviour the
frontend now depends on: completion state travels with the task, the stock actually moves, and
an undo puts it back.
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
from apps.stock.calculations import current_quantity
from apps.stock.models import MovementType, StockCategory, StockItem, StockMovement


class TaskCompletionTests(APITestCase):
    def setUp(self):
        self.farm = Farm.objects.create(name='Ferme Completion')
        self.admin = User.objects.create_user(
            email='admin@completion.local', password='x', name='Admin',
            role=UserRole.ADMIN, farm=self.farm,
        )
        create_role_profile(self.admin)
        self.worker = User.objects.create_user(
            email='worker@completion.local', password='x', name='Ouvrier',
            role=UserRole.WORKER, farm=self.farm,
        )
        create_role_profile(self.worker)

        self.house = PoultryHouse.objects.create(
            house_code=f'H-{self.farm.id}-001', farm=self.farm, name='Poulailler', max_capacity=500,
        )
        self.batch = PoultryBatch.objects.create(
            batch_code='BATCH-C-1', house=self.house, name='Bande', production_type=ProductionType.BROILER,
            initial_count=500, start_date=dt.date.today(),
            planned_end_date=dt.date.today() + dt.timedelta(days=56), status=BatchStatus.ACTIVE,
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
        # Day 1 of the cycle, so the line is due.
        self.batch.start_date = dt.date.today() - dt.timedelta(days=1)
        self.batch.save()

    def _complete(self, force=False, as_user=None):
        self.client.force_authenticate(user=as_user or self.worker)
        body = {'force': True} if force else {}
        return self.client.post(
            f'/api/houses/{self.house.house_code}/tasks-now/{self.line.id}/complete/', body, format='json',
        )

    def _uncomplete(self, as_user=None):
        self.client.force_authenticate(user=as_user or self.worker)
        return self.client.post(
            f'/api/houses/{self.house.house_code}/tasks-now/{self.line.id}/uncomplete/', {}, format='json',
        )

    # --- task payload -----------------------------------------------------

    def test_task_starts_not_done_and_is_completable(self):
        _, tasks = compute_tasks_now(self.house)
        task = next(t for t in tasks if t['id'] == str(self.line.id))
        self.assertFalse(task['done'])
        self.assertTrue(task['completable'])
        self.assertIsNone(task['completedAt'])

    def test_task_reads_as_done_after_completion_rather_than_disappearing(self):
        self._complete()
        _, tasks = compute_tasks_now(self.house)
        task = next((t for t in tasks if t['id'] == str(self.line.id)), None)
        self.assertIsNotNone(task, 'a completed task must still be listed')
        self.assertTrue(task['done'])
        self.assertEqual(task['completedByName'], 'Ouvrier')
        self.assertIsNotNone(task['completedAt'])

    def test_weighing_reminder_is_not_completable(self):
        self.batch.weighing_frequency = 'DAY'
        self.batch.save()
        _, tasks = compute_tasks_now(self.house)
        weighing = next(t for t in tasks if str(t['id']).startswith('weighing-'))
        self.assertFalse(weighing['completable'])

    # --- stock deduction --------------------------------------------------

    def test_completing_deducts_the_line_quantity_from_stock(self):
        self.assertEqual(current_quantity(self.item), 500)
        resp = self._complete()
        self.assertEqual(resp.status_code, 201, resp.data)
        self.assertEqual(resp.data['status'], 'done')
        self.assertEqual(current_quantity(self.item), 460)
        self.assertEqual(resp.data['movement']['quantity'], 40)

    def test_completing_twice_creates_only_one_movement(self):
        self._complete()
        resp = self._complete()
        self.assertEqual(resp.data['status'], 'already_done')
        self.assertEqual(current_quantity(self.item), 460)
        self.assertEqual(TaskCompletion.objects.count(), 1)

    def test_a_line_with_no_linked_resource_completes_without_a_movement(self):
        self.line.stock_item = None
        self.line.quantity_per_day = None
        self.line.save()
        resp = self._complete()
        self.assertEqual(resp.status_code, 201, resp.data)
        self.assertIsNone(resp.data['movement'])
        self.assertEqual(current_quantity(self.item), 500)

    # --- insufficient stock ----------------------------------------------

    def test_insufficient_stock_asks_for_confirmation_and_writes_nothing(self):
        StockMovement.objects.create(
            item=self.item, movement_type=MovementType.OUT, quantity=480, movement_date=dt.date.today(),
        )
        self.assertEqual(current_quantity(self.item), 20)
        resp = self._complete()
        self.assertEqual(resp.data['status'], 'insufficient_stock')
        self.assertEqual(resp.data['shortfall']['needed'], 40)
        self.assertEqual(resp.data['shortfall']['onHand'], 20)
        self.assertEqual(TaskCompletion.objects.count(), 0)
        self.assertEqual(current_quantity(self.item), 20)

    def test_forcing_past_a_shortfall_records_the_completion_and_goes_negative(self):
        # Deliberate: the work was done, and the farm may have sourced feed elsewhere. The
        # completion is the truth; the negative balance is the signal to reconcile.
        StockMovement.objects.create(
            item=self.item, movement_type=MovementType.OUT, quantity=480, movement_date=dt.date.today(),
        )
        resp = self._complete(force=True)
        self.assertEqual(resp.data['status'], 'done')
        self.assertEqual(current_quantity(self.item), -20)
        self.assertEqual(TaskCompletion.objects.count(), 1)

    # --- undo -------------------------------------------------------------

    def test_undo_removes_the_completion_and_puts_the_stock_back(self):
        self._complete()
        self.assertEqual(current_quantity(self.item), 460)
        resp = self._uncomplete()
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(resp.data['status'], 'undone')
        self.assertEqual(resp.data['restored'], 40)
        self.assertEqual(current_quantity(self.item), 500)
        self.assertEqual(TaskCompletion.objects.count(), 0)

    def test_undo_leaves_no_movement_rows_behind(self):
        self._complete()
        self._uncomplete()
        self.assertEqual(StockMovement.objects.filter(movement_type=MovementType.OUT).count(), 0)

    def test_undo_on_something_never_completed_is_a_no_op_not_an_error(self):
        resp = self._uncomplete()
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['status'], 'not_done')
        self.assertEqual(current_quantity(self.item), 500)

    def test_complete_undo_complete_settles_on_one_deduction(self):
        self._complete()
        self._uncomplete()
        self._complete()
        self.assertEqual(current_quantity(self.item), 460)
        self.assertEqual(TaskCompletion.objects.count(), 1)

    def test_task_reads_as_not_done_again_after_undo(self):
        self._complete()
        self._uncomplete()
        _, tasks = compute_tasks_now(self.house)
        task = next(t for t in tasks if t['id'] == str(self.line.id))
        self.assertFalse(task['done'])

    # --- permissions ------------------------------------------------------

    def test_a_worker_may_complete_and_undo(self):
        self.assertEqual(self._complete(as_user=self.worker).status_code, 201)
        self.assertEqual(self._uncomplete(as_user=self.worker).status_code, 200)

    def test_completion_requires_authentication(self):
        self.client.force_authenticate(user=None)
        resp = self.client.post(
            f'/api/houses/{self.house.house_code}/tasks-now/{self.line.id}/uncomplete/', {}, format='json',
        )
        self.assertEqual(resp.status_code, 401)


class TwiceDailyTaskTests(APITestCase):
    """A protocol line with `ProtocolTimeSlot` rows is one task *per slot per day*, not one task
    per day.

    Feeding twice a day is the norm on a poultry farm, not an edge case. `compute_tasks_now` used
    to emit a single occurrence per line with `time_slot=null`, so a 55 kg morning + evening line
    deducted 55 kg instead of 110: stock read as depleting half as fast as it really did,
    threshold alerts fired late, feed cost was understated by half, and the evening worker had no
    task to complete. The slot expansion these pin already existed in `compute_month_schedule`
    (the Calendrier path) — this is the same rule applied to "maintenant".
    """

    def setUp(self):
        self.farm = Farm.objects.create(name='Ferme Slots')
        self.worker = User.objects.create_user(
            email='worker@slots.local', password='x', name='Ouvrier',
            role=UserRole.WORKER, farm=self.farm,
        )
        create_role_profile(self.worker)
        self.house = PoultryHouse.objects.create(
            house_code=f'H-{self.farm.id}-001', farm=self.farm, name='Poulailler', max_capacity=500,
        )
        self.batch = PoultryBatch.objects.create(
            batch_code='BATCH-S-1', house=self.house, name='Bande', production_type=ProductionType.BROILER,
            initial_count=500, start_date=dt.date.today() - dt.timedelta(days=1),
            planned_end_date=dt.date.today() + dt.timedelta(days=55), status=BatchStatus.ACTIVE,
        )
        feed = StockCategory.objects.get(farm=self.farm, kind='FEED')
        self.item = StockItem.objects.create(
            item_code=f'FEE-{self.farm.id}-001', farm=self.farm, category=feed, name='Provende',
            unit='kg', alert_threshold=10, unit_price=Decimal('450.00'),
        )
        StockMovement.objects.create(
            item=self.item, movement_type=MovementType.IN, quantity=1000, movement_date=dt.date.today(),
        )
        category = ProtocolCategory.objects.filter(house=self.house, label='Alimentation').first()
        self.line = ProtocolTemplate.objects.create(
            house=self.house, category=category, from_value=1, until_end=True,
            what='Aliment croissance', details='', stock_item=self.item, quantity_per_day=55,
        )
        self.morning = ProtocolTimeSlot.objects.create(
            protocol_line=self.line, start_time=dt.time(7, 0), end_time=dt.time(9, 0),
        )
        self.evening = ProtocolTimeSlot.objects.create(
            protocol_line=self.line, start_time=dt.time(18, 0), end_time=dt.time(20, 0),
        )

    def _tasks_for_line(self):
        _, tasks = compute_tasks_now(self.house)
        return [t for t in tasks if t['id'] == str(self.line.id)]

    def _complete(self, slot, force=True):
        self.client.force_authenticate(user=self.worker)
        return self.client.post(
            f'/api/houses/{self.house.house_code}/tasks-now/{self.line.id}/complete/',
            {'time_slot_id': slot.id, 'force': force}, format='json',
        )

    def _uncomplete(self, slot):
        self.client.force_authenticate(user=self.worker)
        return self.client.post(
            f'/api/houses/{self.house.house_code}/tasks-now/{self.line.id}/uncomplete/',
            {'time_slot_id': slot.id}, format='json',
        )

    def test_a_twice_daily_line_is_two_occurrences_carrying_their_own_window(self):
        tasks = self._tasks_for_line()
        self.assertEqual(len(tasks), 2)
        self.assertEqual(
            [(t['timeSlotId'], t['startTime'], t['endTime']) for t in tasks],
            [(self.morning.id, '07h00', '09h00'), (self.evening.id, '18h00', '20h00')],
        )

    def test_a_line_with_no_slots_is_still_exactly_one_untimed_occurrence(self):
        ProtocolTimeSlot.objects.filter(protocol_line=self.line).delete()
        tasks = self._tasks_for_line()
        self.assertEqual(len(tasks), 1)
        self.assertIsNone(tasks[0]['timeSlotId'])
        self.assertIsNone(tasks[0]['startTime'])
        self.assertIsNone(tasks[0]['endTime'])

    def test_completing_both_slots_deducts_the_quantity_twice(self):
        self.assertEqual(current_quantity(self.item), 1000)
        self.assertEqual(self._complete(self.morning).status_code, 201)
        self.assertEqual(current_quantity(self.item), 945)
        self.assertEqual(self._complete(self.evening).status_code, 201)
        self.assertEqual(current_quantity(self.item), 890)
        self.assertEqual(TaskCompletion.objects.filter(protocol_template=self.line).count(), 2)

    def test_completing_one_slot_leaves_the_other_outstanding(self):
        self._complete(self.morning)
        by_slot = {t['timeSlotId']: t for t in self._tasks_for_line()}
        self.assertTrue(by_slot[self.morning.id]['done'])
        self.assertFalse(by_slot[self.evening.id]['done'])
        self.assertEqual(by_slot[self.morning.id]['completedByName'], 'Ouvrier')

    def test_completing_the_same_slot_twice_deducts_once(self):
        self.assertEqual(self._complete(self.morning).status_code, 201)
        self.assertEqual(self._complete(self.morning).status_code, 200)
        self.assertEqual(current_quantity(self.item), 945)
        self.assertEqual(TaskCompletion.objects.filter(protocol_template=self.line).count(), 1)

    def test_undoing_one_slot_restores_only_that_slots_quantity(self):
        self._complete(self.morning)
        self._complete(self.evening)
        self.assertEqual(current_quantity(self.item), 890)
        self.assertEqual(self._uncomplete(self.morning).status_code, 200)
        self.assertEqual(current_quantity(self.item), 945)
        by_slot = {t['timeSlotId']: t for t in self._tasks_for_line()}
        self.assertFalse(by_slot[self.morning.id]['done'])
        self.assertTrue(by_slot[self.evening.id]['done'])
