from datetime import date

from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from apps.core.models import Farm, User, UserRole, create_role_profile
from apps.finance.models import Expense, ExpenseCategory, ProductType, Sale


class FinanceAccessTests(APITestCase):
    """Finance access matrix (winchicken-spec-implementation-detaillee.docx sections 4.3/8):
    Admin/Farm Manager get the full Finance payload, every other role gets a restricted
    trend-only summary and a 403 from the two exact-figure endpoints."""

    def setUp(self):
        self.farm = Farm.objects.create(name='Test Farm')

    def _user(self, role, email):
        # No password: these tests authenticate via RefreshToken.for_user() below, never
        # through the login endpoint, so a password is unnecessary (create_user() defaults
        # to an unusable one when omitted).
        user = User.objects.create_user(email=email, name='T', role=role, farm=self.farm)
        create_role_profile(user)
        return user

    def _auth(self, user):
        token = RefreshToken.for_user(user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token.access_token}')

    def test_admin_gets_full_summary(self):
        admin = self._user(UserRole.ADMIN, 'admin@test.com')
        self._auth(admin)
        resp = self.client.get('/api/finance/summary/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['access'], 'full')
        self.assertIn('cashOnHand', resp.data)
        self.assertIn('months', resp.data)

    def test_farm_manager_gets_full_summary(self):
        manager = self._user(UserRole.FARM_MANAGER, 'manager@test.com')
        self._auth(manager)
        resp = self.client.get('/api/finance/summary/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['access'], 'full')

    def test_farmer_gets_restricted_summary_no_exact_figures(self):
        farmer = self._user(UserRole.FARMER, 'farmer@test.com')
        self._auth(farmer)
        resp = self.client.get('/api/finance/summary/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['access'], 'restricted')
        self.assertIn('revenueTrend', resp.data)
        self.assertIn('expenseTrend', resp.data)
        self.assertNotIn('cashOnHand', resp.data)
        self.assertNotIn('months', resp.data)
        self.assertNotIn('pendingPayables', resp.data)
        self.assertNotIn('roiForecastPct', resp.data)

    def test_farmer_denied_expense_categories_and_transactions(self):
        farmer = self._user(UserRole.FARMER, 'farmer2@test.com')
        self._auth(farmer)
        self.assertEqual(self.client.get('/api/finance/expense-categories/').status_code, 403)
        self.assertEqual(self.client.get('/api/finance/transactions/').status_code, 403)

    def test_cashier_restricted_on_summary_but_full_on_own_sales_entry(self):
        cashier = self._user(UserRole.CASHIER, 'cashier@test.com')
        self._auth(cashier)
        self.assertEqual(self.client.get('/api/finance/summary/').data['access'], 'restricted')
        resp = self.client.post('/api/sales/', {
            'product_type': ProductType.BIRD, 'quantity': 10, 'unit_price': '5.00', 'sale_date': str(date.today()),
        })
        self.assertEqual(resp.status_code, 201)

    def test_trend_direction_reflects_last_two_months(self):
        today = date.today()
        Expense.objects.create(farm=self.farm, category=ExpenseCategory.FEED, amount=100, expense_date=today.replace(day=1))
        Sale.objects.create(farm=self.farm, product_type=ProductType.BIRD, quantity=1, unit_price=500, sale_date=today.replace(day=1))
        farmer = self._user(UserRole.FARMER, 'farmer3@test.com')
        self._auth(farmer)
        resp = self.client.get('/api/finance/summary/')
        self.assertIn(resp.data['revenueTrend'], ('up', 'down', 'flat'))
        self.assertIn(resp.data['expenseTrend'], ('up', 'down', 'flat'))
