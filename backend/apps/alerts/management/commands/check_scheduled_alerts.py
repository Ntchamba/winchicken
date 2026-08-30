from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = (
        "Evaluate SCHEDULED AlertRule rows once now (the same work the per-minute "
        "'check-scheduled-alerts' Celery Beat task does): fire the Alert + SMS for any whose "
        "trigger_time matches the current farm-local time and whose schedule says it is due "
        "today. Idempotent. Use --at HH:MM to simulate a specific wall-clock minute."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--at',
            help="Wall-clock HH:MM (farm-local) to evaluate as 'now', on today's date. "
                 "Defaults to the real current time.",
            default=None,
        )

    def handle(self, *args, **options):
        from zoneinfo import ZoneInfo

        from django.conf import settings

        from apps.alerts.services import fire_scheduled_alerts

        now = None
        if options['at']:
            try:
                hour, minute = (int(p) for p in options['at'].split(':'))
            except ValueError:
                self.stderr.write(self.style.ERROR('Invalid --at; expected HH:MM.'))
                return
            tz = ZoneInfo(settings.FARM_TIME_ZONE)
            now = timezone.now().astimezone(tz).replace(hour=hour, minute=minute, second=0, microsecond=0)

        created = fire_scheduled_alerts(now=now)
        self.stdout.write(self.style.SUCCESS(
            f'{len(created)} alert(s) fired '
            f'(farm tz {settings.FARM_TIME_ZONE}).'
        ))
        for alert in created:
            self.stdout.write(f'  - {alert.rule.rule_type} · batch {alert.batch_id} · {alert.message!r}')
