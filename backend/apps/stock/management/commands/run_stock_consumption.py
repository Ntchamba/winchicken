from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = (
        "Run the protocol-driven daily stock consumption once now (the same work the "
        "'daily-stock-consumption' Celery Beat task does at midnight). Idempotent — re-running "
        "the same day creates nothing new."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--date', help='ISO date (YYYY-MM-DD) to run for; defaults to today.', default=None,
        )

    def handle(self, *args, **options):
        from apps.stock.services import run_daily_consumption

        run_date = None
        if options['date']:
            from django.utils.dateparse import parse_date

            run_date = parse_date(options['date'])
            if run_date is None:
                self.stderr.write(self.style.ERROR('Invalid --date; expected YYYY-MM-DD.'))
                return

        created = run_daily_consumption(today=run_date)
        self.stdout.write(self.style.SUCCESS(
            f'{len(created)} stock movement(s) created for {run_date or timezone.now().date()}.'
        ))
