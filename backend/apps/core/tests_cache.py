"""The short-lived cache on the aggregate screens (apps.core.cache, 2026-09-25).

What matters is that a cache never shows a change late: any write — through the API, or
through the ORM from a Celery task — must make the next load recompute.
"""
from decimal import Decimal
from unittest.mock import patch

from django.core.cache import caches
from django.db import connection, transaction
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APITestCase, APITransactionTestCase

from apps.core import cache as response_cache
from apps.core.models import Farm, User, UserRole, create_role_profile
from apps.finance.models import Sale

LIVE = {
    'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache', 'LOCATION': 'cache-tests-default'},
    'responses': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache', 'LOCATION': 'cache-tests', 'TIMEOUT': 30},
}


@override_settings(CACHES=LIVE)
class AggregateCacheTests(APITestCase):
    def setUp(self):
        caches['responses'].clear()
        self.farm = Farm.objects.create(name='Ferme cache')
        self.admin = User.objects.create_user(email='a@cache.local', password='x', name='A', role=UserRole.ADMIN, farm=self.farm)
        create_role_profile(self.admin)
        self.client.force_authenticate(self.admin)

    def overview(self):
        with CaptureQueriesContext(connection) as ctx:
            resp = self.client.get('/api/farm/overview/')
        self.assertEqual(resp.status_code, 200)
        return resp.data, len(ctx.captured_queries)

    def sale(self, amount):
        return Sale.objects.create(farm=self.farm, product_type='BIRD', quantity=1, unit_price=Decimal(amount),
                                   total_amount=Decimal(amount), sale_date=timezone.localdate())

    def test_a_second_load_is_served_without_recomputing(self):
        first, cold = self.overview()
        second, warm = self.overview()
        self.assertEqual(first, second)
        self.assertEqual(warm, 0)
        self.assertGreater(cold, 0)

    def test_a_write_through_the_api_shows_on_the_next_load(self):
        self.overview()
        with patch('apps.core.cache.bump_data_version', wraps=response_cache.bump_data_version) as bump:
            resp = self.client.post('/api/sales/', {
                'product_type': 'BIRD', 'quantity': 1, 'unit_price': 5000, 'sale_date': timezone.localdate().isoformat(),
            }, format='json')
        self.assertLess(resp.status_code, 400, resp.data)
        bump.assert_called()
        _, queries = self.overview()
        self.assertGreater(queries, 0)

    def test_an_unreachable_cache_is_no_cache_not_an_error(self):
        with patch.object(caches['responses'], 'get_or_set', side_effect=ConnectionError):
            data, queries = self.overview()
        self.assertGreater(queries, 0)
        self.assertIn('core', data)

    def test_yesterdays_answer_is_not_served_today(self):
        self.overview()
        tomorrow = timezone.localdate() + timezone.timedelta(days=1)
        with patch('apps.core.cache.timezone.localdate', return_value=tomorrow):
            _, queries = self.overview()
        self.assertGreater(queries, 0)


@override_settings(CACHES=LIVE)
class AggregateCacheCommitTests(APITransactionTestCase):
    """Real commits: the invalidation runs on commit, which a TestCase never reaches."""

    setUp = AggregateCacheTests.setUp
    overview = AggregateCacheTests.overview
    sale = AggregateCacheTests.sale

    def test_a_committed_orm_write_from_outside_a_request_invalidates(self):
        """A Celery task writes through the ORM, with no request to bump anything."""
        self.overview()
        with transaction.atomic():
            self.sale('7000')
        _, queries = self.overview()
        self.assertGreater(queries, 0)

    def test_a_rolled_back_write_does_not_stop_the_next_one_from_invalidating(self):
        self.overview()
        try:
            with transaction.atomic():
                self.sale('1000')
                raise RuntimeError
        except RuntimeError:
            pass
        _, still_cached = self.overview()
        self.assertEqual(still_cached, 0)
        with transaction.atomic():
            self.sale('2000')
        _, queries = self.overview()
        self.assertGreater(queries, 0)

    def test_many_rows_in_one_transaction_bump_once(self):
        with patch('apps.core.cache.bump_data_version') as bump:
            with transaction.atomic():
                for amount in ('1', '2', '3'):
                    self.sale(amount)
        self.assertEqual(bump.call_count, 1)
