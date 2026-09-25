"""The project-wide paginator gives every list a total order (2026-09-25).

Lists sorted by a non-unique column (sale date, case date, salary period) let Postgres order tied
rows differently for each page's query, so reading every page could return a row twice and miss
another — the till's "Total du jour" reads every page and adds them up.
"""
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.core.models import Farm, User, UserRole, create_role_profile
from apps.core.pagination import StablePageNumberPagination
from apps.finance.models import Sale


class StableOrderingTests(TestCase):
    def ordering_of(self, queryset):
        from rest_framework.request import Request
        from rest_framework.test import APIRequestFactory

        paginator = StablePageNumberPagination()
        paginator.page_size = 20
        paginator.paginate_queryset(queryset, Request(APIRequestFactory().get('/')))
        return list(paginator.page.paginator.object_list.query.order_by)

    def test_primary_key_breaks_ties_after_the_models_own_ordering(self):
        self.assertEqual(self.ordering_of(Sale.objects.all()), ['-sale_date', 'pk'])

    def test_a_views_explicit_ordering_is_kept_in_front(self):
        self.assertEqual(self.ordering_of(Sale.objects.order_by('customer')), ['customer', 'pk'])

    def test_an_ordering_that_already_ends_on_the_key_is_left_alone(self):
        self.assertEqual(self.ordering_of(Sale.objects.order_by('-id')), ['-id'])

    def test_an_unordered_list_gets_the_key(self):
        self.assertEqual(self.ordering_of(User.objects.order_by()), ['pk'])


class EveryRowOnExactlyOnePageTests(APITestCase):
    def test_same_day_sales_read_page_by_page(self):
        farm = Farm.objects.create(name='Ferme pages')
        admin = User.objects.create_user(email='a@pages.local', password='x', name='A', role=UserRole.ADMIN, farm=farm)
        create_role_profile(admin)
        self.client.force_authenticate(admin)
        today = timezone.localdate()
        ids = {
            Sale.objects.create(farm=farm, product_type='BIRD', quantity=1, unit_price=Decimal('100'),
                                total_amount=Decimal('100'), sale_date=today).id
            for _ in range(45)
        }
        seen = []
        for page in (1, 2, 3):
            seen += [row['id'] for row in self.client.get('/api/sales/', {'sale_date': today.isoformat(), 'page': page}).data['results']]
        self.assertEqual(sorted(seen), sorted(ids))
