"""Protocol scheduling — which protocol line is due on which day of the cycle.

_protocol_line_occurrence decides it for the task list, the month calendar and the scheduled
reminders alike, so its boundaries are pinned here: first and last day of a range, the day after,
open-ended lines, unit conversion, and the two ranges that were silently never due — a line with
no end (it borrowed the end's default unit, DAY, while the start was in weeks) and a line whose
end, once converted to days, comes before its start.
"""
from types import SimpleNamespace

from rest_framework.test import APITestCase

from apps.core.models import Farm, User, UserRole, create_role_profile
from apps.houses.models import PoultryHouse
from apps.houses.services import _protocol_line_occurrence
from apps.protocols.models import ProtocolCategory, ProtocolTemplate


def line(from_value, from_unit='DAY', to_value=None, to_unit='DAY', until_end=False):
    return SimpleNamespace(from_value=from_value, from_unit=from_unit, to_value=to_value, to_unit=to_unit, until_end=until_end)


class OccurrenceTests(APITestCase):
    def due(self, ln, day):
        return _protocol_line_occurrence(ln, day)

    def test_range_is_inclusive_at_both_ends(self):
        ln = line(5, to_value=10)
        self.assertIsNone(self.due(ln, 4))
        self.assertEqual(self.due(ln, 5), (1, 6))
        self.assertEqual(self.due(ln, 10), (6, 6))
        self.assertIsNone(self.due(ln, 11))

    def test_day_zero_line(self):
        self.assertEqual(self.due(line(0, to_value=0), 0), (1, 1))
        self.assertIsNone(self.due(line(0, to_value=0), 1))

    def test_until_end_runs_from_its_first_day_with_no_length(self):
        ln = line(3, until_end=True, to_value=5)          # to_value ignored when until_end
        self.assertIsNone(self.due(ln, 2))
        self.assertEqual(self.due(ln, 3), (1, None))
        self.assertEqual(self.due(ln, 300), (298, None))

    def test_units_are_converted_to_days(self):
        ln = line(1, 'WEEK', to_value=2, to_unit='WEEK')   # days 7..14
        self.assertIsNone(self.due(ln, 6))
        self.assertEqual(self.due(ln, 7), (1, 8))
        self.assertEqual(self.due(ln, 14), (8, 8))
        self.assertIsNone(self.due(ln, 15))
        self.assertEqual(self.due(line(1, 'MONTH', to_value=1, to_unit='MONTH'), 30), (1, 1))

    def test_a_line_with_no_end_is_a_single_day_in_its_own_unit(self):
        # "Semaine 2" with no end: day 14 only. It used to compute the end as 2 *days* (the end's
        # default unit) and so was due on no day at all.
        ln = line(2, 'WEEK', to_value=None, to_unit='DAY')
        self.assertEqual(self.due(ln, 14), (1, 1))
        self.assertIsNone(self.due(ln, 13))
        self.assertIsNone(self.due(ln, 15))

    def test_mixed_units_in_order(self):
        ln = line(10, 'DAY', to_value=2, to_unit='WEEK')   # days 10..14
        self.assertEqual(self.due(ln, 10), (1, 5))
        self.assertEqual(self.due(ln, 14), (5, 5))


class ProtocolSaveRangeTests(APITestCase):
    """Saving a line whose end, in days, is before its start is refused instead of stored as a
    task that never comes due."""

    def setUp(self):
        self.farm = Farm.objects.create(name='Ferme Plages')
        self.house = PoultryHouse.objects.create(house_code=f'H-OC-{self.farm.id}', farm=self.farm, name='B', max_capacity=100)
        self.category = ProtocolCategory.objects.create(house=self.house, label='Alimentation', icon='Soup')
        admin = User.objects.create_user(email='admin@oc.local', password='x', name='A', role=UserRole.ADMIN, farm=self.farm)
        create_role_profile(admin)
        self.client.force_authenticate(user=admin)

    def save(self, **ln):
        body = {'category': self.category.id, 'what': 'Aliment', 'details': '', 'until_end': False, **ln}
        return self.client.put(f'/api/houses/{self.house.house_code}/protocol/', {'lines': [body]}, format='json')

    def test_end_before_start_once_converted_is_refused(self):
        resp = self.save(from_value=2, from_unit='WEEK', to_value=3, to_unit='DAY')
        self.assertEqual(resp.status_code, 400, resp.data)
        self.assertIn('avant le début', str(resp.data))
        self.assertFalse(ProtocolTemplate.objects.filter(house=self.house).exists())

    def test_end_on_the_start_day_is_accepted(self):
        self.assertEqual(self.save(from_value=1, from_unit='WEEK', to_value=7, to_unit='DAY').status_code, 200)

    def test_an_end_in_weeks_after_a_start_in_days_is_accepted(self):
        # Day 10 to day 14: the raw numbers (2 < 10) would say otherwise; the units must count.
        self.assertEqual(self.save(from_value=10, from_unit='DAY', to_value=2, to_unit='WEEK').status_code, 200)

    def test_until_end_ignores_the_end_fields(self):
        self.assertEqual(self.save(from_value=2, from_unit='WEEK', to_value=1, to_unit='DAY', until_end=True).status_code, 200)

    def test_no_end_is_accepted(self):
        self.assertEqual(self.save(from_value=2, from_unit='WEEK', to_value=None, to_unit='DAY').status_code, 200)
