"""Integration chain 5 — worker assignment -> the task in that worker's "Mes tâches" -> completion
-> hours -> payroll -> payment -> labour expense -> cash position.

Completing a task does not record hours in this codebase: hours are self-reported through
/api/work-hours/ and payroll is hours x hourly rate. The chain below is the one that exists;
the campaign report says so.
"""
import datetime as dt
import threading
from decimal import Decimal

from django.db import connection
from django.test import TransactionTestCase
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase

from apps.batches.models import BatchStatus, PoultryBatch, ProductionType
from apps.core.models import Farm, User, UserRole, create_role_profile
from apps.finance.models import Expense, SalaryPayment, WorkHoursEntry
from apps.houses.models import PoultryHouse
from apps.protocols.models import ProtocolCategory, ProtocolTemplate, TaskCompletion


def build_crew(tag):
    farm = Farm.objects.create(name=f'Ferme {tag}')
    people = {}
    for key, role, name in (('admin', UserRole.ADMIN, 'Paul Admin'), ('awa', UserRole.WORKER, 'Awa Ouvrière'),
                            ('ben', UserRole.WORKER, 'Ben Ouvrier')):
        user = User.objects.create_user(email=f'{key}@{tag}.local', password='x', name=name, role=role, farm=farm)
        create_role_profile(user)
        people[key] = user
    house = PoultryHouse.objects.create(house_code=f'H-{farm.id}-001', farm=farm, name='Poulailler A', max_capacity=500)
    today = timezone.localdate()
    PoultryBatch.objects.create(
        batch_code=f'B-{farm.id}', house=house, production_type=ProductionType.BROILER, initial_count=500,
        start_date=today - dt.timedelta(days=2), status=BatchStatus.ACTIVE,
    )
    line = ProtocolTemplate.objects.create(
        house=house, category=ProtocolCategory.objects.get(house=house, label='Alimentation'),
        from_value=1, until_end=True, what='Nettoyer les abreuvoirs',
    )
    return farm, people, house, line


class WorkforceChainTests(APITestCase):
    def setUp(self):
        self.farm, self.people, self.house, self.line = build_crew('equipe')
        self.today = timezone.localdate()

    def as_(self, who):
        self.client.force_authenticate(user=self.people[who])
        return self.client

    def assign(self, *who):
        return self.as_('admin').patch(
            f'/api/houses/{self.house.house_code}/tasks-now/{self.line.id}/assign/',
            {'assignees': [self.people[w].id for w in who]}, format='json',
        )

    def mine(self, who):
        return [t for t in self.as_(who).get('/api/tasks/mine/').data if t['id'] == str(self.line.id)]

    def hours(self, who, hours, day=None, for_who=None):
        body = {'date': (day or self.today).isoformat(), 'hours_worked': hours}
        if for_who:
            body['user'] = self.people[for_who].id
        return self.as_(who).post('/api/work-hours/', body, format='json')

    def test_assign_see_complete_log_hours_get_paid_and_the_cash_moves(self):
        self.assertEqual(self.assign('awa').status_code, 200)
        [task] = self.mine('awa')
        self.assertFalse(task['done'])
        self.assertEqual(self.mine('ben'), [])

        response = self.as_('awa').post(f'/api/houses/{self.house.house_code}/tasks-now/{self.line.id}/complete/', {}, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        [task] = self.mine('awa')
        self.assertTrue(task['done'])
        self.assertEqual(TaskCompletion.objects.get().completed_by, self.people['awa'])

        self.as_('admin').patch(f"/api/employees/{self.people['awa'].id}/hourly-rate/", {'hourly_rate': '1500'}, format='json')
        self.assertEqual(self.hours('awa', '8').status_code, 201)
        self.assertEqual(self.hours('admin', '2.5', for_who='awa').status_code, 201)  # admin correction

        response = self.as_('admin').post('/api/salary-payments/calculate/', {'month': self.today.month, 'year': self.today.year}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        payment = SalaryPayment.objects.get(user=self.people['awa'])
        self.assertEqual((payment.total_hours, payment.amount, payment.status), (Decimal('10.5'), Decimal('15750'), 'PENDING'))

        self.assertEqual(self.as_('admin').post(f'/api/salary-payments/{payment.id}/pay/').status_code, 200)
        expense = Expense.objects.get(category='LABOR')
        self.assertEqual((expense.amount, expense.supplier), (Decimal('15750'), 'Awa Ouvrière'))
        self.assertEqual(self.as_('admin').get('/api/finance/summary/').data['cashOnHand'], -15750.0)

        # Paid is final: a later correction and recalculation leave the paid amount alone.
        self.hours('admin', '4', for_who='awa')
        self.as_('admin').post('/api/salary-payments/calculate/', {'month': self.today.month, 'year': self.today.year}, format='json')
        payment.refresh_from_db()
        self.assertEqual((payment.amount, payment.status), (Decimal('15750'), 'PAID'))
        self.assertEqual(self.as_('admin').post(f'/api/salary-payments/{payment.id}/pay/').status_code, 400)

    def test_an_unassigned_task_is_in_nobodys_list_but_any_worker_can_do_it(self):
        self.assertEqual(self.mine('awa'), [])
        house_tasks = self.as_('ben').get(f'/api/houses/{self.house.house_code}/tasks-now/').data['tasks']
        [task] = [t for t in house_tasks if t['id'] == str(self.line.id)]
        self.assertEqual(task['assignedTo'], [])
        response = self.as_('ben').post(f'/api/houses/{self.house.house_code}/tasks-now/{self.line.id}/complete/', {}, format='json')
        self.assertEqual(response.status_code, 201)

    def test_two_assignees_share_one_occurrence(self):
        self.assign('awa', 'ben')
        self.as_('ben').post(f'/api/houses/{self.house.house_code}/tasks-now/{self.line.id}/complete/', {}, format='json')
        [task] = self.mine('awa')
        self.assertTrue(task['done'])
        self.assertEqual(task['completedByName'], 'Ben Ouvrier')

    def test_clearing_the_assignment_takes_the_task_off_the_list(self):
        self.assign('awa')
        self.assertEqual(self.assign().status_code, 200)
        self.assertEqual(self.mine('awa'), [])

    def test_a_worker_cannot_assign_or_log_hours_for_someone_else(self):
        response = self.as_('awa').patch(
            f'/api/houses/{self.house.house_code}/tasks-now/{self.line.id}/assign/', {'assignees': [self.people['awa'].id]}, format='json',
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.hours('awa', '8', for_who='ben').status_code, 400)

    def test_impossible_hours_are_refused(self):
        tomorrow = self.today + dt.timedelta(days=1)
        for hours, day in (('-3', None), ('0', None), ('25', None), ('8', tomorrow)):
            self.assertEqual(self.hours('awa', hours, day).status_code, 400, (hours, day))
        self.assertEqual(self.hours('awa', '16').status_code, 201)
        self.assertEqual(self.hours('awa', '9').status_code, 400)  # 25 h in one day, over two entries
        self.assertEqual(WorkHoursEntry.objects.count(), 1)

    def test_impossible_rates_and_periods_are_refused(self):
        for rate in ('-1500', 'NaN', 'Infinity', 'abc'):
            response = self.as_('admin').patch(f"/api/employees/{self.people['awa'].id}/hourly-rate/", {'hourly_rate': rate}, format='json')
            self.assertEqual(response.status_code, 400, rate)
        for month in (0, 13):
            response = self.as_('admin').post('/api/salary-payments/calculate/', {'month': month, 'year': 2026}, format='json')
            self.assertEqual(response.status_code, 400, month)
        self.assertFalse(SalaryPayment.objects.exists())

    def test_an_employee_without_a_rate_is_left_out_of_payroll(self):
        self.hours('awa', '8')
        self.as_('admin').post('/api/salary-payments/calculate/', {}, format='json')
        self.assertFalse(SalaryPayment.objects.exists())


class ConcurrentPayTests(TransactionTestCase):
    def test_paying_twice_at_once_records_one_labour_expense(self):
        farm, people, _, _ = build_crew('paie')
        people['awa'].hourly_rate = Decimal('1000')
        people['awa'].save()
        today = timezone.localdate()
        WorkHoursEntry.objects.create(user=people['awa'], date=today, hours_worked=Decimal('8'))
        admin = APIClient()
        admin.force_authenticate(user=people['admin'])
        admin.post('/api/salary-payments/calculate/', {}, format='json')
        payment = SalaryPayment.objects.get()

        barrier = threading.Barrier(4)
        statuses = []

        def tap():
            client = APIClient()
            client.force_authenticate(user=people['admin'])
            try:
                barrier.wait()
                statuses.append(client.post(f'/api/salary-payments/{payment.id}/pay/').status_code)
            finally:
                connection.close()

        threads = [threading.Thread(target=tap) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(Expense.objects.filter(category='LABOR').count(), 1, statuses)
        self.assertEqual(sorted(statuses), [200, 400, 400, 400])
