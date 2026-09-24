"""Integration chain 4 — sale / expense / purchase order recorded -> finance aggregates (summary,
transactions ledger) -> cash position -> "Bilan global" finance branch. Through the API, on the
real database, including the concurrent taps a phone produces.
"""
import datetime as dt
import threading
from decimal import Decimal

from django.db import connection
from django.test import TransactionTestCase
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase

from apps.core.models import Farm, User, UserRole, create_role_profile
from apps.finance.models import Expense, PurchaseOrder, Sale
from apps.stock.calculations import current_quantity
from apps.stock.models import StockCategory, StockItem, StockMovement


def build_finance_farm(tag):
    farm = Farm.objects.create(name=f'Ferme {tag}')
    users = {}
    for role in (UserRole.ADMIN, UserRole.CASHIER, UserRole.WORKER):
        user = User.objects.create_user(email=f'{role.lower()}@{tag}.local', password='x', name=f'{role} {tag}', role=role, farm=farm)
        create_role_profile(user)
        users[role] = user
    item = StockItem.objects.create(
        item_code=f'FEE-{farm.id}-001', farm=farm, category=StockCategory.objects.get(farm=farm, kind='FEED'),
        name='Provende', unit='kg', unit_price=Decimal('450'),
    )
    return farm, users, item


class FinanceChainTests(APITestCase):
    def setUp(self):
        self.farm, self.users, self.item = build_finance_farm('finance')
        self.today = timezone.localdate()

    def as_(self, role):
        self.client.force_authenticate(user=self.users[role])
        return self.client

    def sale(self, **over):
        body = {'product_type': 'EGG', 'quantity': 100, 'unit_price': '2500', 'sale_date': self.today.isoformat(), 'customer': 'Marché', **over}
        return self.as_(UserRole.CASHIER).post('/api/sales/', body, format='json')

    def expense(self, **over):
        body = {'category': 'FEED', 'amount': '300000', 'expense_date': self.today.isoformat(), 'supplier': 'Agrivet', **over}
        return self.as_(UserRole.ADMIN).post('/api/expenses/', body, format='json')

    def receive_order(self, quantity=200, amount='100000'):
        client = self.as_(UserRole.ADMIN)
        created = client.post('/api/purchase-orders/', {'item': self.item.item_code, 'quantity': quantity, 'amount': amount, 'supplier': 'Agrivet'}, format='json')
        self.assertEqual(created.status_code, 201, created.data)
        received = client.patch(f"/api/purchase-orders/{created.data['order_code']}/", {'status': 'RECEIVED'}, format='json')
        self.assertEqual(received.status_code, 200, received.data)
        return created.data['order_code']

    def summary(self):
        response = self.as_(UserRole.ADMIN).get('/api/finance/summary/')
        self.assertEqual(response.status_code, 200)
        return response.data

    def finance_branch(self):
        return self.as_(UserRole.ADMIN).get('/api/farm/overview/').data['branches']['finance']

    def test_money_in_and_out_reaches_the_summary_the_ledger_and_the_overview(self):
        self.assertEqual(self.sale().status_code, 201)
        self.assertEqual(self.expense().status_code, 201)
        self.receive_order()

        summary = self.summary()
        this_month = summary['months'][-1]
        self.assertEqual((this_month['revenue'], this_month['expenses']), (250000.0, 400000.0))
        self.assertEqual(summary['cashOnHand'], -150000.0)
        self.assertEqual(current_quantity(self.item), 200)  # the received order stocked the item

        branch = self.finance_branch()
        self.assertEqual((branch['tier'], branch['message'], branch['cash']), ('critical', 'Trésorerie négative', -150000.0))

        # The ledger is the cash position's detail: its rows must add up to it.
        ledger = self.as_(UserRole.ADMIN).get('/api/finance/transactions/').data
        self.assertEqual(sum(r['amount'] for r in ledger['results']), summary['cashOnHand'])
        self.assertEqual(ledger['count'], 3)

        self.sale(quantity=1200)  # +3 000 000
        branch = self.finance_branch()
        self.assertEqual((branch['tier'], branch['cash']), ('good', 2850000.0))

    def test_a_cashier_sees_directions_not_amounts(self):
        self.sale()
        response = self.as_(UserRole.CASHIER).get('/api/finance/summary/')
        self.assertEqual(response.data['access'], 'restricted')
        self.assertNotIn('cashOnHand', response.data)
        self.assertEqual(self.as_(UserRole.CASHIER).get('/api/finance/transactions/').status_code, 403)

    def test_no_money_recorded_reads_as_low_cash_not_an_error(self):
        self.assertEqual(self.summary()['cashOnHand'], 0.0)
        self.assertEqual(self.finance_branch()['tier'], 'watch')

    # --- failure branches -------------------------------------------------------------------

    def test_impossible_sales_are_refused_and_leave_the_cash_alone(self):
        tomorrow = (self.today + dt.timedelta(days=1)).isoformat()
        for over in ({'quantity': -5}, {'quantity': 0}, {'unit_price': '-100'}, {'sale_date': tomorrow}, {'quantity': 1e15}):
            response = self.sale(**over)
            self.assertEqual(response.status_code, 400, (over, response.status_code, getattr(response, 'data', None)))
        self.assertFalse(Sale.objects.exists())
        self.assertEqual(self.summary()['cashOnHand'], 0.0)

    def test_impossible_expenses_are_refused(self):
        tomorrow = (self.today + dt.timedelta(days=1)).isoformat()
        for over in ({'amount': '-300000'}, {'amount': '0'}, {'expense_date': tomorrow}):
            self.assertEqual(self.expense(**over).status_code, 400, over)
        self.assertFalse(Expense.objects.exists())

    def test_a_bad_ledger_page_is_a_400_not_a_crash(self):
        client = self.as_(UserRole.ADMIN)
        for page in ('abc', '0', '-1'):
            self.assertEqual(client.get('/api/finance/transactions/', {'page': page}).status_code, 400, page)

    def test_a_received_order_cannot_be_received_again(self):
        code = self.receive_order()
        response = self.as_(UserRole.ADMIN).patch(f'/api/purchase-orders/{code}/', {'status': 'CANCELLED'}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(current_quantity(self.item), 200)

    def test_an_order_code_is_never_reused_after_an_order_disappears(self):
        # A stock item deletion cascades to its orders; the count-based code then collided with a
        # surviving order's primary key (500).
        first = self.receive_order()
        self.receive_order()
        PurchaseOrder.objects.filter(order_code=first).delete()
        response = self.as_(UserRole.ADMIN).post('/api/purchase-orders/', {'item': self.item.item_code, 'quantity': 1, 'amount': '10'}, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(PurchaseOrder.objects.count(), 2)


class ConcurrentFinanceTests(TransactionTestCase):
    """Two taps on the same button at once, with real transactions."""

    def setUp(self):
        self.farm, self.users, self.item = build_finance_farm('finconc')

    def race(self, method, url, body, n=4):
        barrier = threading.Barrier(n)
        statuses = []

        def tap():
            client = APIClient()
            client.force_authenticate(user=self.users[UserRole.ADMIN])
            try:
                barrier.wait()
                statuses.append(getattr(client, method)(url, body, format='json').status_code)
            finally:
                connection.close()

        threads = [threading.Thread(target=tap) for _ in range(n)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        return statuses

    def test_receiving_an_order_twice_at_once_stocks_it_once(self):
        client = APIClient()
        client.force_authenticate(user=self.users[UserRole.ADMIN])
        code = client.post('/api/purchase-orders/', {'item': self.item.item_code, 'quantity': 200, 'amount': '100000'}, format='json').data['order_code']
        statuses = self.race('patch', f'/api/purchase-orders/{code}/', {'status': 'RECEIVED'})
        self.assertEqual(StockMovement.objects.filter(item=self.item).count(), 1, statuses)
        self.assertEqual(current_quantity(self.item), 200)
        self.assertNotIn(500, statuses)

    def test_creating_orders_at_once_gives_each_its_own_code(self):
        statuses = self.race('post', '/api/purchase-orders/', {'item': self.item.item_code, 'quantity': 1, 'amount': '10'})
        self.assertEqual(sorted(statuses), [201] * 4, statuses)
        self.assertEqual(PurchaseOrder.objects.count(), 4)
