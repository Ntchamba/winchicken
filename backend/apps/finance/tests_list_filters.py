"""GET /api/sales/?sale_date= — the cashier's "Ventes du jour" total.

The page summed today's rows out of page 1 of every sale (20 rows, newest first): from the 21st
sale of a day, the FCFA total shown to the cashier was short. It now asks for the day's sales and
reads every page (frontend api/pagination.js).
"""
import datetime as dt
from decimal import Decimal

from rest_framework.test import APITestCase

from apps.core.models import Farm, User, UserRole, create_role_profile
from apps.finance.models import ProductType, Sale

TODAY = dt.date(2026, 9, 24)


class SaleDateFilterTests(APITestCase):
    def setUp(self):
        self.farm = Farm.objects.create(name='Ferme Caisse')
        cashier = User.objects.create_user(email='caisse@filtre.local', password='x', name='C', role=UserRole.CASHIER, farm=self.farm)
        create_role_profile(cashier)
        self.client.force_authenticate(user=cashier)
        for _ in range(25):
            Sale.objects.create(farm=self.farm, product_type=ProductType.EGG, quantity=1, unit_price=Decimal('2500'), sale_date=TODAY)
        Sale.objects.create(farm=self.farm, product_type=ProductType.EGG, quantity=1, unit_price=Decimal('9999'), sale_date=TODAY - dt.timedelta(days=1))

    def test_only_the_days_sales_are_listed(self):
        data = self.client.get('/api/sales/', {'sale_date': TODAY.isoformat()}).data
        self.assertEqual(data['count'], 25)
        self.assertTrue(all(r['sale_date'] == TODAY.isoformat() for r in data['results']))

    def test_without_the_filter_every_day_is_listed(self):
        self.assertEqual(self.client.get('/api/sales/').data['count'], 26)

    def test_a_malformed_date_is_refused_in_french(self):
        response = self.client.get('/api/sales/', {'sale_date': '24/09/2026'})
        self.assertEqual(response.status_code, 400)
        self.assertIn('Date invalide', str(response.data))
