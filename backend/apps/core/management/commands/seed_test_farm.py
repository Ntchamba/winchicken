"""Seed a realistic farm into the *test* database, for live verification work.

Exists so verification never runs against real farm data: the isolated stack
(docker-compose.test.yml) starts with an empty database, and this fills it with enough
material for the dashboards to show something real — houses with active batches, daily logs
carrying mortality, stock above and below its reorder threshold, sales and expenses.

Refuses to run unless the database name ends with `_test`. That guard is the point of the
command, not a formality: a seeder pointed at the wrong database is exactly the accident it
is meant to prevent. `--force` is deliberately not offered.
"""
import datetime as dt
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

from apps.batches.models import BatchStatus, DailyLog, PoultryBatch, ProductionType
from apps.core.models import Farm, User, UserRole, create_role_profile
from apps.finance.models import Expense, ExpenseCategory, ProductType, Sale
from apps.houses.models import PoultryHouse
from apps.protocols.models import ProtocolCategory, ProtocolTemplate, ProtocolTimeSlot
from apps.stock.models import MovementType, StockCategory, StockItem, StockMovement

TEST_DB_SUFFIX = '_test'


class Command(BaseCommand):
    help = 'Seed a demo farm into the test database (refuses to run on any other database).'

    def add_arguments(self, parser):
        parser.add_argument('--email', default='admin@test.local')
        parser.add_argument('--password', default='TestVerify123!')
        parser.add_argument('--farm-name', default='Ferme de vérification')

    def handle(self, *args, **options):
        db_name = connection.settings_dict['NAME']
        if not str(db_name).endswith(TEST_DB_SUFFIX):
            raise CommandError(
                f'Refusing to seed: database is "{db_name}", which does not end with '
                f'"{TEST_DB_SUFFIX}". Run this only against the isolated test stack '
                '(docker-compose.test.yml).'
            )

        if Farm.objects.exists():
            raise CommandError(
                'This database already has a farm. Flush it first '
                '(manage.py flush --no-input && manage.py migrate) — refusing to seed on top.'
            )

        with transaction.atomic():
            farm = self._build(options)

        self.stdout.write(self.style.SUCCESS(
            f'Seeded "{farm.name}" into {db_name}.\n'
            f'  login: {options["email"]} / {options["password"]}\n'
            f'  houses: {PoultryHouse.objects.count()}  batches: {PoultryBatch.objects.count()}  '
            f'daily logs: {DailyLog.objects.count()}  stock items: {StockItem.objects.count()}'
        ))

    def _build(self, options):
        today = dt.date.today()
        farm = Farm.objects.create(name=options['farm_name'])

        admin = User.objects.create_user(
            email=options['email'], password=options['password'],
            name='Admin Vérification', role=UserRole.ADMIN, farm=farm,
        )
        create_role_profile(admin)
        farm.refresh_from_db()

        # Two houses: one healthy, one carrying visibly worse mortality, so a status that
        # depends on the numbers has something to actually differ on.
        healthy = self._house(farm, 1, 'Poulailler Nord', 600)
        strained = self._house(farm, 2, 'Poulailler Sud', 400)

        good_batch = self._batch(healthy, 'Bande Nord', 600, today - dt.timedelta(days=21))
        weak_batch = self._batch(strained, 'Bande Sud', 400, today - dt.timedelta(days=28))

        # ~1.5% cumulative mortality on the healthy batch, ~9% on the strained one.
        self._daily_logs(good_batch, days=21, daily_mortality=0, extra_every=7, extra=3)
        self._daily_logs(weak_batch, days=28, daily_mortality=1, extra_every=4, extra=2)

        stock_items = self._stock(farm)
        # A house only counts as configured once it has protocol lines
        # (apps.core.services.is_farm_configured), which is also what puts real occurrences on
        # the calendar and in "tâches du jour".
        for house in (healthy, strained):
            self._protocol(house, stock_items)
        self._finance(farm, good_batch, admin, today)
        return farm

    def _protocol(self, house, stock_items):
        by_label = {c.label: c for c in ProtocolCategory.objects.filter(house=house)}
        feeding = by_label.get('Alimentation')
        vaccination = by_label.get('Vaccination')
        cleaning = by_label.get('Nettoyage')

        rows = [
            (feeding, 1, 15, False, 'Aliment démarrage', '3000 kcal, 22,5% de protéines',
             stock_items.get('FEE-T-001'), 40),
            (feeding, 16, None, True, 'Aliment croissance', '3150 kcal, 21,5% de protéines',
             stock_items.get('FEE-T-002'), 55),
            (vaccination, 1, 1, False, 'Maladie de Newcastle', 'Hitchner B1, goutte oculaire',
             stock_items.get('VET-T-001'), 1),
            (cleaning, 1, None, True, 'Ajout de litière', '', None, None),
        ]
        for category, frm, to, until_end, what, details, item, qty in rows:
            if category is None:
                continue
            line = ProtocolTemplate.objects.create(
                house=house, category=category, from_value=frm, to_value=to,
                until_end=until_end, what=what, details=details,
                stock_item=item, quantity_per_day=qty if item else None,
            )
            if category is feeding:
                ProtocolTimeSlot.objects.create(
                    protocol_line=line, start_time=dt.time(6, 30), end_time=dt.time(7, 30),
                )
                ProtocolTimeSlot.objects.create(
                    protocol_line=line, start_time=dt.time(18, 30), end_time=dt.time(19, 30),
                )

    def _house(self, farm, seq, name, capacity):
        return PoultryHouse.objects.create(
            house_code=f'H-{farm.id}-{seq:03d}', farm=farm, name=name,
            max_capacity=capacity, size_m2=capacity // 8,
        )

    def _batch(self, house, name, count, start):
        return PoultryBatch.objects.create(
            batch_code=f'BATCH-TEST-{house.house_code[-3:]}', house=house, name=name,
            production_type=ProductionType.BROILER, initial_count=count, start_date=start,
            planned_end_date=start + dt.timedelta(days=56), status=BatchStatus.ACTIVE,
        )

    def _daily_logs(self, batch, days, daily_mortality, extra_every, extra):
        start = batch.start_date
        for day in range(days):
            log_date = start + dt.timedelta(days=day)
            mortality = daily_mortality + (extra if day and day % extra_every == 0 else 0)
            DailyLog.objects.create(
                batch=batch, log_date=log_date, mortality=mortality,
                feed_consumed_kg=round(batch.initial_count * 0.055 * (1 + day / 40), 1),
                water_consumed_l=round(batch.initial_count * 0.10 * (1 + day / 40), 1),
                avg_sample_weight=round(0.042 + day * 0.056, 3),
            )

    def _stock(self, farm):
        feed = StockCategory.objects.get(farm=farm, kind='FEED')
        vet = StockCategory.objects.get(farm=farm, kind='VETERINARY')

        # (code, category, name, unit, threshold, price, stock in, stock out)
        rows = [
            ('FEE-T-001', feed, 'Provende démarrage', 'kg', 200, '450.00', 1200, 400),
            ('FEE-T-002', feed, 'Provende croissance', 'kg', 200, '470.00', 900, 150),
            # Deliberately below its reorder threshold, so the stock status has a real trigger.
            ('VET-T-001', vet, 'Vaccin Newcastle', 'flacon', 10, '3500.00', 12, 9),
        ]
        created = {}
        for code, category, name, unit, threshold, price, qty_in, qty_out in rows:
            item = StockItem.objects.create(
                item_code=code, farm=farm, category=category, name=name, unit=unit,
                alert_threshold=threshold, unit_price=Decimal(price),
            )
            StockMovement.objects.create(
                item=item, movement_type=MovementType.IN, quantity=qty_in,
                movement_date=dt.date.today() - dt.timedelta(days=30),
            )
            if qty_out:
                StockMovement.objects.create(
                    item=item, movement_type=MovementType.OUT, quantity=qty_out,
                    movement_date=dt.date.today() - dt.timedelta(days=3),
                )
            created[code] = item
        return created

    def _finance(self, farm, batch, cashier, today):
        for weeks_ago, qty, price in ((6, 120, '2600.00'), (3, 95, '2700.00'), (1, 140, '2750.00')):
            Sale.objects.create(
                farm=farm, batch=batch, cashier=cashier, product_type=ProductType.BIRD,
                quantity=qty, unit_price=Decimal(price),
                sale_date=today - dt.timedelta(weeks=weeks_ago), customer='Marché central',
            )
        for weeks_ago, category, amount in (
            (7, ExpenseCategory.FEED, '180000.00'),
            (5, ExpenseCategory.VETERINARY, '42000.00'),
            (2, ExpenseCategory.LABOR, '65000.00'),
            (1, ExpenseCategory.FEED, '120000.00'),
        ):
            Expense.objects.create(
                farm=farm, batch=batch, category=category, amount=Decimal(amount),
                expense_date=today - dt.timedelta(weeks=weeks_ago), supplier='Agrivet SARL',
            )
