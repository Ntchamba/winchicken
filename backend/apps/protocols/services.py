from datetime import timedelta

UNIT_TO_DAYS = {'DAY': 1, 'WEEK': 7, 'MONTH': 30}

# Category labels treated as "vaccination" for AlertRule expansion. Matches the label the
# frontend seeds by default (apps.protocols.models.DEFAULT_PROTOCOL_CATEGORIES) — a custom
# category renamed away from "Vaccination" simply won't expand, which is the expected
# behaviour (nothing in the schema marks a category as vaccination-typed beyond its label).
VACCINATION_CATEGORY_LABEL = 'Vaccination'


def expand_protocol_to_alert_rules(batch):
    """Creates ONE_TIME SCHEDULED AlertRule rows from `batch.house`'s protocol lines, offset
    from `PoultryBatch.start_date` (cahier des charges §4.6: "Étendu en lignes AlertRule à la
    création d'une bande, décalées par rapport à PoultryBatch.startDate").

    - One VACCINE_DUE rule per protocol line in a category labeled "Vaccination", firing on
      `start_date + from_value` (converted to days via `from_unit`).
    - One SANITARY_VOID_END rule firing on `planned_end_date`, if set, reminding that the house
      needs its sanitary void once the batch closes.

    Idempotent: re-running for the same batch (e.g. a retried request) does not duplicate rows,
    since each rule is looked up by its (farm, batch, rule_type, fire_date) key.
    """
    from apps.alerts.models import AlertRule, AlertRuleType, ScheduleFrequency, TriggerMode
    from apps.protocols.models import ProtocolTemplate

    farm = batch.house.farm
    created = []

    vaccination_lines = ProtocolTemplate.objects.filter(
        house=batch.house, category__label__iexact=VACCINATION_CATEGORY_LABEL
    )
    for line in vaccination_lines:
        offset_days = line.from_value * UNIT_TO_DAYS.get(line.from_unit, 1)
        fire_date = batch.start_date + timedelta(days=offset_days)
        rule, was_created = AlertRule.objects.get_or_create(
            farm=farm,
            batch=batch,
            rule_type=AlertRuleType.VACCINE_DUE,
            fire_date=fire_date,
            defaults={
                'trigger_mode': TriggerMode.SCHEDULED,
                'frequency': ScheduleFrequency.ONE_TIME,
                'active': True,
                'note': line.what,
            },
        )
        if was_created:
            created.append(rule)

    if batch.planned_end_date:
        rule, was_created = AlertRule.objects.get_or_create(
            farm=farm,
            batch=batch,
            rule_type=AlertRuleType.SANITARY_VOID_END,
            fire_date=batch.planned_end_date,
            defaults={
                'trigger_mode': TriggerMode.SCHEDULED,
                'frequency': ScheduleFrequency.ONE_TIME,
                'active': True,
                'note': 'Fin de bande prévue — préparer le vide sanitaire.',
            },
        )
        if was_created:
            created.append(rule)

    return created
