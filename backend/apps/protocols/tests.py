from datetime import date

from django.test import TestCase

from apps.batches.models import BatchStatus, PoultryBatch
from apps.alerts.models import AlertRule, AlertRuleType
from apps.core.models import Farm
from apps.houses.models import PoultryHouse
from apps.protocols.models import ProtocolCategory, ProtocolTemplate


class ProtocolToAlertRuleExpansionTests(TestCase):
    """Cahier des charges §4.6: a protocol's Vaccination lines and the batch's planned end
    date expand into AlertRule rows at batch creation (apps.batches.signals ->
    apps.protocols.services.expand_protocol_to_alert_rules)."""

    def setUp(self):
        self.farm = Farm.objects.create(name='Test Farm')
        self.house = PoultryHouse.objects.create(house_code='H-TEST', farm=self.farm, name='House', max_capacity=100)

    def test_vaccination_line_creates_vaccine_due_rule(self):
        vaccination = ProtocolCategory.objects.get(house=self.house, label='Vaccination')
        ProtocolTemplate.objects.create(house=self.house, category=vaccination, from_value=7, from_unit='DAY', what='Newcastle vaccine')

        batch = PoultryBatch.objects.create(
            batch_code='BATCH-1', house=self.house, production_type='BROILER',
            initial_count=100, current_count=100, start_date=date(2026, 1, 1), status=BatchStatus.ACTIVE,
        )

        rule = AlertRule.objects.get(batch=batch, rule_type=AlertRuleType.VACCINE_DUE)
        self.assertEqual(rule.fire_date, date(2026, 1, 8))
        self.assertEqual(rule.note, 'Newcastle vaccine')

    def test_planned_end_date_creates_sanitary_void_rule(self):
        batch = PoultryBatch.objects.create(
            batch_code='BATCH-2', house=self.house, production_type='BROILER',
            initial_count=100, current_count=100, start_date=date(2026, 1, 1),
            planned_end_date=date(2026, 2, 15), status=BatchStatus.ACTIVE,
        )
        self.assertTrue(AlertRule.objects.filter(batch=batch, rule_type=AlertRuleType.SANITARY_VOID_END, fire_date=date(2026, 2, 15)).exists())

    def test_non_vaccination_category_does_not_expand(self):
        feeding = ProtocolCategory.objects.get(house=self.house, label='Alimentation')
        ProtocolTemplate.objects.create(house=self.house, category=feeding, from_value=1, from_unit='DAY', what='Starter feed')

        batch = PoultryBatch.objects.create(
            batch_code='BATCH-3', house=self.house, production_type='BROILER',
            initial_count=100, current_count=100, start_date=date(2026, 1, 1), status=BatchStatus.ACTIVE,
        )
        self.assertFalse(AlertRule.objects.filter(batch=batch, rule_type=AlertRuleType.VACCINE_DUE).exists())
