from datetime import date
from decimal import Decimal

from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from apps.core.models import Farm, User, UserRole, create_role_profile
from apps.finance.models import Expense, ExpenseCategory, ProductType, PurchaseOrder, Sale, SalaryPayment, WorkHoursEntry
from apps.stock.models import ItemCategory, StockCategory, StockItem, StockMovement


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


class PurchaseOrderTests(APITestCase):
    """Purchase order creation, receiving, and cancellation (2026-08-27, purchase-order task).
    Role list per that task: Caissier/Administrateur/Gérant de ferme, enforced server-side."""

    def setUp(self):
        self.farm = Farm.objects.create(name='Ferme PO Test')
        self.item = StockItem.objects.create(
            item_code='FEED-1-001', farm=self.farm, category=StockCategory.objects.get(farm=self.farm, kind='FEED'), name='Aliment démarrage', unit='kg',
        )

    def _user(self, role, email):
        user = User.objects.create_user(email=email, name='T', role=role, farm=self.farm)
        create_role_profile(user)
        return user

    def _auth(self, user):
        token = RefreshToken.for_user(user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token.access_token}')

    def _create_order(self, user):
        self._auth(user)
        return self.client.post('/api/purchase-orders/', {
            'item': self.item.item_code, 'supplier': 'Fournisseur A', 'quantity': 100, 'amount': '25000.00',
        })

    def test_cashier_admin_and_farm_manager_can_create(self):
        for role, email in [(UserRole.CASHIER, 'c@t.com'), (UserRole.ADMIN, 'a@t.com'), (UserRole.FARM_MANAGER, 'm@t.com')]:
            user = self._user(role, email)
            resp = self._create_order(user)
            self.assertEqual(resp.status_code, 201, f'{role} should be able to create: {resp.data}')
            self.assertEqual(resp.data['status'], 'PENDING')

    def test_other_roles_forbidden_from_creating(self):
        for role, email in [
            (UserRole.FARMER, 'f@t.com'), (UserRole.WORKER, 'w@t.com'),
            (UserRole.TECHNICIAN, 'tech@t.com'), (UserRole.SECONDARY_ADMIN, 'sa@t.com'),
        ]:
            user = self._user(role, email)
            resp = self._create_order(user)
            self.assertEqual(resp.status_code, 403, f'{role} should be forbidden: {resp.data}')

    def test_creating_does_not_touch_stock(self):
        admin = self._user(UserRole.ADMIN, 'admin2@t.com')
        self._create_order(admin)
        self.assertEqual(StockMovement.objects.count(), 0)

    def test_receiving_creates_stock_movement_with_todays_date_not_order_date(self):
        admin = self._user(UserRole.ADMIN, 'admin3@t.com')
        create_resp = self._create_order(admin)
        order_code = create_resp.data['order_code']
        # Backdate order_date to prove movement_date is the receiving date, not the order date.
        PurchaseOrder.objects.filter(order_code=order_code).update(order_date=date(2020, 1, 1))

        resp = self.client.patch(f'/api/purchase-orders/{order_code}/', {'status': 'RECEIVED'}, format='json')
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(resp.data['status'], 'RECEIVED')

        self.assertEqual(StockMovement.objects.count(), 1)
        movement = StockMovement.objects.get()
        self.assertEqual(movement.item_id, self.item.item_code)
        self.assertEqual(movement.movement_type, 'IN')
        self.assertEqual(movement.quantity, 100)
        self.assertEqual(movement.supplier, 'Fournisseur A')
        self.assertIsNone(movement.batch_id)
        self.assertEqual(movement.movement_date, date.today())

    def test_receiving_records_optional_supplier_batch_number(self):
        admin = self._user(UserRole.ADMIN, 'admin4@t.com')
        order_code = self._create_order(admin).data['order_code']
        resp = self.client.patch(
            f'/api/purchase-orders/{order_code}/', {'status': 'RECEIVED', 'supplierBatchNumber': 'LOT-42'}, format='json'
        )
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(StockMovement.objects.get().supplier_batch_number, 'LOT-42')

    def test_receiving_updates_current_quantity(self):
        from apps.stock.calculations import current_quantity
        admin = self._user(UserRole.ADMIN, 'admin5@t.com')
        order_code = self._create_order(admin).data['order_code']
        self.assertEqual(current_quantity(self.item), 0)
        self.client.patch(f'/api/purchase-orders/{order_code}/', {'status': 'RECEIVED'}, format='json')
        self.assertEqual(current_quantity(self.item), 100)

    def test_cancelling_creates_no_stock_movement(self):
        admin = self._user(UserRole.ADMIN, 'admin6@t.com')
        order_code = self._create_order(admin).data['order_code']
        resp = self.client.patch(f'/api/purchase-orders/{order_code}/', {'status': 'CANCELLED'}, format='json')
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(resp.data['status'], 'CANCELLED')
        self.assertEqual(StockMovement.objects.count(), 0)

    def test_received_order_cannot_be_changed_again(self):
        admin = self._user(UserRole.ADMIN, 'admin7@t.com')
        order_code = self._create_order(admin).data['order_code']
        self.client.patch(f'/api/purchase-orders/{order_code}/', {'status': 'RECEIVED'}, format='json')

        resp = self.client.patch(f'/api/purchase-orders/{order_code}/', {'status': 'CANCELLED'}, format='json')
        self.assertEqual(resp.status_code, 400)
        # Still exactly one StockMovement — the rejected re-PATCH didn't create a second one.
        self.assertEqual(StockMovement.objects.count(), 1)

    def test_cancelled_order_cannot_be_changed_again(self):
        admin = self._user(UserRole.ADMIN, 'admin8@t.com')
        order_code = self._create_order(admin).data['order_code']
        self.client.patch(f'/api/purchase-orders/{order_code}/', {'status': 'CANCELLED'}, format='json')

        resp = self.client.patch(f'/api/purchase-orders/{order_code}/', {'status': 'RECEIVED'}, format='json')
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(StockMovement.objects.count(), 0)

    def test_list_filters_by_status_and_category(self):
        admin = self._user(UserRole.ADMIN, 'admin9@t.com')
        pending_code = self._create_order(admin).data['order_code']
        received_code = self._create_order(admin).data['order_code']
        self.client.patch(f'/api/purchase-orders/{received_code}/', {'status': 'RECEIVED'}, format='json')

        pending_only = self.client.get('/api/purchase-orders/', {'status': 'PENDING'})
        codes = [o['order_code'] for o in pending_only.data['results']] if 'results' in pending_only.data else [o['order_code'] for o in pending_only.data]
        self.assertEqual(codes, [pending_code])

        vet_item = StockItem.objects.create(item_code='VET-1-001', farm=self.farm, category=StockCategory.objects.get(farm=self.farm, kind='VETERINARY'), name='Vaccin', unit='dose')
        self._auth(admin)
        self.client.post('/api/purchase-orders/', {'item': vet_item.item_code, 'supplier': 'X', 'quantity': 5, 'amount': '1000.00'})
        feed_only = self.client.get('/api/purchase-orders/', {'category': 'FEED'})
        feed_codes = [o['order_code'] for o in (feed_only.data['results'] if 'results' in feed_only.data else feed_only.data)]
        self.assertEqual(set(feed_codes), {pending_code, received_code})

    def test_audit_log_records_receive_and_cancel(self):
        admin = self._user(UserRole.ADMIN, 'admin10@t.com')
        order_code = self._create_order(admin).data['order_code']
        self.client.patch(f'/api/purchase-orders/{order_code}/', {'status': 'RECEIVED'}, format='json')

        audit = self.client.get('/api/audit-log/')
        actions = [e['action'] for e in (audit.data['results'] if 'results' in audit.data else audit.data)]
        self.assertIn('purchase_order.received', actions)

    def test_cashier_can_now_record_an_expense(self):
        cashier = self._user(UserRole.CASHIER, 'cashier-exp@t.com')
        self._auth(cashier)
        resp = self.client.post('/api/expenses/', {
            'category': 'FEED', 'amount': '5000.00', 'expense_date': str(date.today()), 'supplier': 'Fournisseur X',
        })
        self.assertEqual(resp.status_code, 201, resp.data)


class SalariesTests(APITestCase):
    """Payroll module (2026-08-27, Finances restructure Part D) — rate configuration, hours
    logging ownership model, monthly calculation, and the pay -> Expense side effect."""

    def setUp(self):
        self.farm = Farm.objects.create(name='Ferme Salaires Test')
        self.admin = User.objects.create_user(email='admin@sal-test.com', name='Admin', role=UserRole.ADMIN, farm=self.farm)
        create_role_profile(self.admin)
        self.manager = User.objects.create_user(email='fm@sal-test.com', name='Gérant', role=UserRole.FARM_MANAGER, farm=self.farm)
        create_role_profile(self.manager)
        self.worker = User.objects.create_user(email='worker@sal-test.com', name='Ouvrier', role=UserRole.WORKER, farm=self.farm)
        create_role_profile(self.worker)
        self.other_worker = User.objects.create_user(email='worker2@sal-test.com', name='Ouvrier 2', role=UserRole.WORKER, farm=self.farm)
        create_role_profile(self.other_worker)

    def _auth(self, user):
        token = RefreshToken.for_user(user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token.access_token}')

    def test_admin_and_farm_manager_can_set_hourly_rate_other_roles_cannot(self):
        self._auth(self.admin)
        resp = self.client.patch(f'/api/employees/{self.worker.id}/hourly-rate/', {'hourly_rate': '2500'}, format='json')
        self.assertEqual(resp.status_code, 200, resp.data)
        self.worker.refresh_from_db()
        self.assertEqual(self.worker.hourly_rate, Decimal('2500.00'))

        self._auth(self.manager)
        resp = self.client.patch(f'/api/employees/{self.worker.id}/hourly-rate/', {'hourly_rate': '3000'}, format='json')
        self.assertEqual(resp.status_code, 200, resp.data)

        self._auth(self.worker)
        resp = self.client.patch(f'/api/employees/{self.worker.id}/hourly-rate/', {'hourly_rate': '9999'}, format='json')
        self.assertEqual(resp.status_code, 403)

    def test_employee_can_self_report_hours_but_not_for_someone_else(self):
        self._auth(self.worker)
        resp = self.client.post('/api/work-hours/', {'date': str(date.today()), 'hours_worked': '8'}, format='json')
        self.assertEqual(resp.status_code, 201, resp.data)
        self.assertEqual(resp.data['user'], self.worker.id)

        resp = self.client.post(
            '/api/work-hours/', {'user': self.other_worker.id, 'date': str(date.today()), 'hours_worked': '5'}, format='json'
        )
        self.assertEqual(resp.status_code, 400)

    def test_admin_can_log_hours_on_behalf_of_an_employee(self):
        self._auth(self.admin)
        resp = self.client.post(
            '/api/work-hours/', {'user': self.worker.id, 'date': str(date.today()), 'hours_worked': '6'}, format='json'
        )
        self.assertEqual(resp.status_code, 201, resp.data)
        self.assertEqual(resp.data['user'], self.worker.id)

    def test_worker_only_sees_their_own_hours_admin_sees_everyones(self):
        WorkHoursEntry.objects.create(user=self.worker, date=date.today(), hours_worked=8)
        WorkHoursEntry.objects.create(user=self.other_worker, date=date.today(), hours_worked=7)

        self._auth(self.worker)
        resp = self.client.get('/api/work-hours/')
        results = resp.data['results'] if 'results' in resp.data else resp.data
        self.assertEqual(len(results), 1)

        self._auth(self.admin)
        resp = self.client.get('/api/work-hours/')
        results = resp.data['results'] if 'results' in resp.data else resp.data
        self.assertEqual(len(results), 2)

    def test_calculate_computes_hours_times_rate_and_pay_creates_labor_expense(self):
        self.worker.hourly_rate = Decimal('1500.00')
        self.worker.save()
        today = date.today()
        WorkHoursEntry.objects.create(user=self.worker, date=today.replace(day=1), hours_worked=8)
        WorkHoursEntry.objects.create(user=self.worker, date=today.replace(day=2), hours_worked=6)

        self._auth(self.admin)
        resp = self.client.post('/api/salary-payments/calculate/', {'month': today.month, 'year': today.year}, format='json')
        self.assertEqual(resp.status_code, 200, resp.data)
        payment = next(p for p in resp.data if p['user'] == self.worker.id)
        self.assertEqual(Decimal(payment['total_hours']), Decimal('14.00'))
        self.assertEqual(Decimal(payment['amount']), Decimal('14.00') * Decimal('1500.00'))
        self.assertEqual(payment['status'], 'PENDING')

        pay_resp = self.client.post(f"/api/salary-payments/{payment['id']}/pay/")
        self.assertEqual(pay_resp.status_code, 200, pay_resp.data)
        self.assertEqual(pay_resp.data['status'], 'PAID')

        expense = Expense.objects.get(category=ExpenseCategory.LABOR)
        self.assertEqual(expense.amount, Decimal('14.00') * Decimal('1500.00'))
        self.assertIsNone(expense.batch_id)
        self.assertEqual(expense.expense_date, date.today())

        # Paying again is rejected — final, not silently re-appliable.
        second_pay = self.client.post(f"/api/salary-payments/{payment['id']}/pay/")
        self.assertEqual(second_pay.status_code, 400)
        self.assertEqual(Expense.objects.filter(category=ExpenseCategory.LABOR).count(), 1)

    def test_recalculating_never_touches_an_already_paid_payment(self):
        self.worker.hourly_rate = Decimal('1000.00')
        self.worker.save()
        today = date.today()
        WorkHoursEntry.objects.create(user=self.worker, date=today, hours_worked=5)
        self._auth(self.admin)
        payment_id = self.client.post(
            '/api/salary-payments/calculate/', {'month': today.month, 'year': today.year}, format='json'
        ).data[0]['id']
        self.client.post(f'/api/salary-payments/{payment_id}/pay/')

        # More hours logged after payment — recalculating must not touch the PAID row.
        WorkHoursEntry.objects.create(user=self.worker, date=today, hours_worked=100)
        self.client.post('/api/salary-payments/calculate/', {'month': today.month, 'year': today.year}, format='json')

        payment = SalaryPayment.objects.get(pk=payment_id)
        self.assertEqual(payment.status, 'PAID')
        self.assertEqual(payment.total_hours, Decimal('5.00'))

    def test_salaries_section_hidden_from_other_roles_server_side(self):
        self._auth(self.worker)
        self.assertEqual(self.client.get('/api/salary-payments/').status_code, 403)
        self.assertEqual(self.client.post('/api/salary-payments/calculate/', {}, format='json').status_code, 403)

    def test_farm_manager_can_calculate_and_pay(self):
        self.worker.hourly_rate = Decimal('800.00')
        self.worker.save()
        today = date.today()
        WorkHoursEntry.objects.create(user=self.worker, date=today, hours_worked=3)
        self._auth(self.manager)
        resp = self.client.post('/api/salary-payments/calculate/', {'month': today.month, 'year': today.year}, format='json')
        self.assertEqual(resp.status_code, 200, resp.data)
        payment_id = resp.data[0]['id']
        pay_resp = self.client.post(f'/api/salary-payments/{payment_id}/pay/')
        self.assertEqual(pay_resp.status_code, 200, pay_resp.data)


class FinanceEvolutionTests(APITestCase):
    """Ventes/Achats section endpoints (2026-08-27, Finances restructure Parts B/C)."""

    def setUp(self):
        self.farm = Farm.objects.create(name='Ferme Evolution Test')
        self.admin = User.objects.create_user(email='admin@evo-test.com', name='Admin', role=UserRole.ADMIN, farm=self.farm)
        create_role_profile(self.admin)
        self.worker = User.objects.create_user(email='worker@evo-test.com', name='Ouvrier', role=UserRole.WORKER, farm=self.farm)
        create_role_profile(self.worker)

    def _auth(self, user):
        token = RefreshToken.for_user(user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token.access_token}')

    def test_admin_gets_full_sales_evolution(self):
        Sale.objects.create(farm=self.farm, product_type=ProductType.BIRD, quantity=10, unit_price=1000, sale_date=date.today())
        self._auth(self.admin)
        resp = self.client.get('/api/finance/sales-evolution/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['access'], 'full')
        self.assertEqual(resp.data['totalRevenue'], 10000.0)
        self.assertEqual(resp.data['salesCount'], 1)
        self.assertEqual(resp.data['breakdown'], [{'productType': 'BIRD', 'amount': 10000.0}])

    def test_worker_gets_restricted_sales_evolution(self):
        self._auth(self.worker)
        resp = self.client.get('/api/finance/sales-evolution/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['access'], 'restricted')
        self.assertNotIn('totalRevenue', resp.data)
        self.assertIn(resp.data['trend'], ('up', 'down', 'flat'))

    def test_achats_includes_received_purchase_order_mapped_to_expense_category(self):
        item = StockItem.objects.create(item_code='FEED-2-001', farm=self.farm, category=StockCategory.objects.get(farm=self.farm, kind='FEED'), name='Aliment', unit='kg')
        po = PurchaseOrder.objects.create(
            farm=self.farm, item=item, supplier='X', quantity=10, amount=2000, status='RECEIVED',
        )
        self._auth(self.admin)
        resp = self.client.get('/api/finance/purchases-evolution/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['totalSpent'], 2000.0)
        self.assertEqual(resp.data['breakdown'], [{'category': 'FEED', 'amount': 2000.0}])
