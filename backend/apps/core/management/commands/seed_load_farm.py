"""Seed a deliberately oversized farm into a throwaway *load-test* database.

Exists to find where the app degrades: every default is far beyond the real farm (a million
birds, twenty thousand employees). The shape of the data follows what the app itself writes —
houses get their default protocol categories from the same `post_save` signal, PROTOCOL_TASK
alert rules come from `expand_protocol_to_alert_rules`, every completed task that consumes stock
points at the OUT movement it made — so a slow screen here is slow for a reason the real farm
can reach, only sooner.

High-volume rows go through `bulk_create`, which skips `post_save`: the LOW_STOCK / deviation /
push-notification signals never fire during seeding, so nothing is queued and nothing is sent.

Refuses to run unless the database name ends with `_load`, and unless the database is empty.
The dev and `_test` databases can never match. See `backend/scripts/load_test.sh` for the full
create -> migrate -> seed -> measure cycle.
"""
import datetime as dt
import random
import time as walltime
from decimal import Decimal

from django.contrib.auth.hashers import make_password
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.utils import timezone

from apps.alerts.models import (
    Alert, AlertRule, AlertRuleType, AlertStatus, ScheduleFrequency, SmsMessage, SmsStatus, TriggerMode,
)
from apps.batches.models import BatchStatus, DailyLog, PoultryBatch, ProductionType
from apps.core.models import (
    ROLE_PROFILE_MODELS, AuditLogEntry, Farm, User, UserRole, create_role_profile,
)
from apps.finance.models import (
    Expense, ExpenseCategory, OrderStatus, ProductType, PurchaseOrder, SalaryPayment,
    SalaryPaymentStatus, Sale, WorkHoursEntry,
)
from apps.houses.models import PoultryHouse
from apps.houses.services import _protocol_line_occurrence
from apps.maintenance.models import EquipmentFault, UnusualCase
from apps.protocols.models import ProtocolCategory, ProtocolTemplate, ProtocolTimeSlot, TaskCompletion
from apps.protocols.services import expand_protocol_to_alert_rules
from apps.stock.models import (
    FeedStage, MovementType, StockCategory, StockComposition, StockCompositionIngredient,
    StockItem, StockMovement, Supplier,
)

LOAD_DB_SUFFIX = '_load'
CHUNK = 5000

# (category label, from, to, until_end, what, stock key, qty/day per 1 000 birds, slots)
# Stock keys resolve to the items `_stock` creates. Quantities are per 1 000 birds so a line
# scales with the batch it feeds.
PROTOCOL = [
    ('Alimentation', 1, 14, False, 'Aliment démarrage', 'starter', 30, [(6, 30), (17, 30)]),
    ('Alimentation', 15, 28, False, 'Aliment croissance', 'grower', 55, [(6, 30), (17, 30)]),
    ('Alimentation', 29, None, True, 'Aliment finition', 'finisher', 80, [(6, 30), (17, 30)]),
    ('Santé et soins', 1, None, True, 'Contrôle eau et abreuvoirs', None, None, [(6, 0), (12, 0), (18, 0)]),
    ('Santé et soins', 1, 5, False, 'Vitamines anti-stress', 'vitamin', 1, [(8, 0)]),
    ('Santé et soins', 15, 19, False, 'Vitamines croissance', 'vitamin', 1, [(8, 0)]),
    ('Santé et soins', 1, None, True, 'Tournée sanitaire', None, None, [(7, 0), (16, 0)]),
    ('Vaccination', 1, None, False, 'Marek / Newcastle', 'vaccine', 1, []),
    ('Vaccination', 7, None, False, 'Gumboro', 'vaccine', 1, []),
    ('Vaccination', 14, None, False, 'Newcastle rappel', 'vaccine', 1, []),
    ('Vaccination', 21, None, False, 'Gumboro rappel', 'vaccine', 1, []),
    ('Nettoyage', 1, None, True, 'Ajout de litière', 'litter', 2, []),
    ('Température', 1, None, True, 'Relevé température', None, None, [(9, 0), (15, 0), (21, 0)]),
]

NON_WORKER_ROLES = [
    (UserRole.SECONDARY_ADMIN, 0.0002), (UserRole.FARM_MANAGER, 0.001),
    (UserRole.TECHNICIAN, 0.0015), (UserRole.CASHIER, 0.001),
]


class Command(BaseCommand):
    help = 'Seed an oversized farm into a *_load database for load testing (refuses any other DB).'

    def add_arguments(self, parser):
        parser.add_argument('--birds', type=int, default=1_000_000)
        parser.add_argument('--houses', type=int, default=50)
        parser.add_argument('--employees', type=int, default=20_000)
        parser.add_argument('--days', type=int, default=30, help='Days of history to generate.')
        parser.add_argument('--stock-items', type=int, default=200)
        parser.add_argument('--sales-per-day', type=int, default=200)
        parser.add_argument('--expenses-per-day', type=int, default=100)
        parser.add_argument('--orders-per-day', type=int, default=50)
        parser.add_argument('--closed-batches-per-house', type=int, default=1)
        parser.add_argument('--seed', type=int, default=20260925)
        parser.add_argument('--email', default='admin@load.local')
        parser.add_argument('--password', default='LoadTest123!')

    def handle(self, *args, **o):
        db_name = connection.settings_dict['NAME']
        if not str(db_name).endswith(LOAD_DB_SUFFIX):
            raise CommandError(
                f'Refusing to seed: database is "{db_name}", which does not end with '
                f'"{LOAD_DB_SUFFIX}". Point DB_NAME at a throwaway load database.'
            )
        if Farm.objects.exists():
            raise CommandError('This database already has a farm — drop and recreate it first.')

        self.rng = random.Random(o['seed'])
        self.o = o
        self.today = timezone.localdate()
        self.t0 = walltime.monotonic()
        self.password_hash = make_password(o['password'])
        with transaction.atomic():
            self._build()
        self._log('done')
        self.stdout.write(self.style.SUCCESS(
            f'Seeded {db_name}. login: {o["email"]} / {o["password"]}\n' + self._counts()
        ))

    # -- helpers ---------------------------------------------------------------------------

    def _log(self, step):
        self.stdout.write(f'[{walltime.monotonic() - self.t0:7.1f}s] {step}')
        self.stdout.flush()

    def _bulk(self, model, rows):
        created = []
        for i in range(0, len(rows), CHUNK):
            created += model.objects.bulk_create(rows[i:i + CHUNK])
        return created

    def _counts(self):
        models = [
            PoultryHouse, PoultryBatch, DailyLog, User, WorkHoursEntry, SalaryPayment,
            ProtocolTemplate, ProtocolTimeSlot, TaskCompletion, StockItem, StockMovement,
            Sale, Expense, PurchaseOrder, AlertRule, Alert, SmsMessage, AuditLogEntry,
        ]
        return '\n'.join(f'  {m.__name__:18} {m.objects.count():>9,}' for m in models)

    # -- build -----------------------------------------------------------------------------

    def _build(self):
        o = self.o
        self.farm = Farm.objects.create(name='Ferme de charge', location='Test de charge')
        self.admin = User.objects.create_user(
            email=o['email'], password=o['password'], name='Admin Charge', role=UserRole.ADMIN, farm=self.farm,
        )
        create_role_profile(self.admin)
        self._employees()
        self._log(f'{User.objects.count():,} users')
        self._stock()
        self._log(f'{StockItem.objects.count()} stock items')
        self._houses_and_batches()
        self._log(f'{PoultryBatch.objects.count()} batches')
        self._protocols()
        self._log(f'{ProtocolTemplate.objects.count()} protocol lines')
        self._daily_logs()
        self._log(f'{DailyLog.objects.count():,} daily logs')
        self._task_history()
        self._log(f'{TaskCompletion.objects.count():,} completions')
        self._stock_deliveries()
        self._log(f'{StockMovement.objects.count():,} stock movements')
        self._work_hours()
        self._log(f'{WorkHoursEntry.objects.count():,} work-hours entries')
        self._finance()
        self._log('finance')
        self._alert_history()
        self._log(f'{Alert.objects.count():,} alerts')
        self._incidents_and_audit()

    def _employees(self):
        n = self.o['employees']
        roles = []
        for role, share in NON_WORKER_ROLES:
            roles += [role] * max(1, int(n * share))
        roles += [UserRole.FARMER] * self.o['houses']  # one Fermier per house
        roles += [UserRole.WORKER] * max(0, n - len(roles))
        users = [
            User(
                farm=self.farm, name=f'Employé {i:05d}', email=f'emp{i:05d}@load.local',
                phone=f'+2376{90000000 + i:08d}', role=role, password=self.password_hash,
                hourly_rate=Decimal(self.rng.choice(['500.00', '650.00', '800.00', '1000.00'])),
            )
            for i, role in enumerate(roles[:n])
        ]
        users = self._bulk(User, users)
        for role, model in ROLE_PROFILE_MODELS.items():
            self._bulk(model, [model(user_id=u.id) for u in users if u.role == role])
        self.farmers = [u for u in users if u.role == UserRole.FARMER]
        self.workers = [u for u in users if u.role == UserRole.WORKER]
        self.employees = users
        self.cashiers = [u for u in users if u.role == UserRole.CASHIER] or [self.admin]

    def _stock(self):
        cats = {c.kind: c for c in StockCategory.objects.filter(farm=self.farm)}
        self.suppliers = self._bulk(Supplier, [
            Supplier(farm=self.farm, name=f'Fournisseur {i:02d}', contact=f'+2376{80000000 + i}')
            for i in range(30)
        ])
        named = [
            ('starter', 'FEED', 'Aliment démarrage', 'kg', FeedStage.STARTER, 5000, '450'),
            ('grower', 'FEED', 'Aliment croissance', 'kg', FeedStage.GROWER, 5000, '470'),
            ('finisher', 'FEED', 'Aliment finition', 'kg', FeedStage.FINISHER, 5000, '480'),
            ('vaccine', 'VETERINARY', 'Vaccin Newcastle', 'flacon', FeedStage.NOT_APPLICABLE, 20, '3500'),
            ('vitamin', 'VETERINARY', 'Vitamines', 'kg', FeedStage.NOT_APPLICABLE, 50, '6000'),
            ('litter', 'BEDDING', 'Copeaux', 'sac', FeedStage.NOT_APPLICABLE, 100, '1500'),
        ]
        items = []
        self.item_by_key = {}
        for key, kind, name, unit, stage, threshold, price in named:
            item = StockItem(
                item_code=f'LD-{key.upper()}', farm=self.farm, category=cats[kind], name=name, unit=unit,
                feed_stage=stage, alert_threshold=threshold, unit_price=Decimal(price),
                supplier=self.rng.choice(self.suppliers),
            )
            items.append(item)
            self.item_by_key[key] = item
        kinds = ['FEED', 'VETERINARY', 'EQUIPMENT', 'BEDDING']
        for i in range(max(0, self.o['stock_items'] - len(named))):
            kind = kinds[i % len(kinds)]
            items.append(StockItem(
                item_code=f'LD-{i:05d}', farm=self.farm, category=cats[kind], name=f'Article {kind.lower()} {i:04d}',
                unit='unité' if kind == 'EQUIPMENT' else 'kg', alert_threshold=self.rng.choice([0, 10, 50, 200]),
                unit_price=Decimal(self.rng.randint(100, 50000)), supplier=self.rng.choice(self.suppliers),
            ))
        self.items = self._bulk(StockItem, items)
        comps = self._bulk(StockComposition, [
            StockComposition(farm=self.farm, name=f'Formule {i}', output_item=self.item_by_key['grower'],
                             base_output_quantity=1000)
            for i in range(5)
        ])
        self._bulk(StockCompositionIngredient, [
            StockCompositionIngredient(composition=c, item=self.rng.choice(self.items), quantity=self.rng.randint(10, 400))
            for c in comps for _ in range(6)
        ])

    def _houses_and_batches(self):
        o = self.o
        per_house = o['birds'] // o['houses']
        self.houses, self.active = [], []
        closed = []
        for h in range(o['houses']):
            house = PoultryHouse.objects.create(  # .create, not bulk: the signal seeds its categories
                house_code=f'H-L-{h + 1:03d}', farm=self.farm, name=f'Bâtiment {h + 1:03d}',
                size_m2=per_house // 10, max_capacity=int(per_house * 1.1),
            )
            self.houses.append(house)
            farmer = self.farmers[h % len(self.farmers)] if self.farmers else None
            start = self.today - dt.timedelta(days=o['days'] + h % 10)
            for c in range(o['closed_batches_per_house']):
                cstart = start - dt.timedelta(days=(c + 1) * 60)
                closed.append(PoultryBatch(
                    batch_code=f'LB-{h + 1:03d}-C{c + 1}', house=house, farmer=farmer, name=f'Bande close {h + 1}-{c + 1}',
                    production_type=ProductionType.BROILER, breed='Cobb 500', initial_count=per_house,
                    start_date=cstart, planned_end_date=cstart + dt.timedelta(days=45),
                    actual_end_date=cstart + dt.timedelta(days=45), status=BatchStatus.CLOSED,
                ))
            self.active.append(PoultryBatch(
                batch_code=f'LB-{h + 1:03d}', house=house, farmer=farmer, name=f'Bande {h + 1:03d}',
                production_type=ProductionType.LAYER if h % 10 == 9 else ProductionType.BROILER,
                breed='Cobb 500', initial_count=per_house, start_date=start,
                planned_end_date=start + dt.timedelta(days=45), status=BatchStatus.ACTIVE, weighing_frequency='WEEK',
            ))
        self._bulk(PoultryBatch, closed + self.active)
        self.closed = closed

    def _protocols(self):
        """Protocol lines + slots per house, assignees spread so every worker holds a task, then
        the PROTOCOL_TASK rules through the app's own expansion."""
        workers_by_house = {h.house_code: self.workers[i::len(self.houses)] for i, h in enumerate(self.houses)}
        slots, through = [], []
        self.lines_by_house = {}
        for house in self.houses:
            cats = {c.label: c for c in ProtocolCategory.objects.filter(house=house)}
            per_1000 = house.max_capacity / 1.1 / 1000
            lines = []
            for label, frm, to, until_end, what, key, qty, times in PROTOCOL:
                item = self.item_by_key.get(key) if key else None
                lines.append(ProtocolTemplate(
                    house=house, category=cats[label], from_value=frm, to_value=to, until_end=until_end,
                    what=what, stock_item=item, quantity_per_day=round(qty * per_1000, 1) if item else None,
                ))
            lines = self._bulk(ProtocolTemplate, lines)
            self.lines_by_house[house.house_code] = lines
            for line, (*_, times) in zip(lines, PROTOCOL):
                for hh, mm in times:
                    slots.append(ProtocolTimeSlot(
                        protocol_line=line, start_time=dt.time(hh, mm), end_time=dt.time(min(hh + 1, 23), mm),
                    ))
            workers = workers_by_house[house.house_code]
            for i, w in enumerate(workers):
                through.append(ProtocolTemplate.assignees.through(protocoltemplate_id=lines[i % len(lines)].id, user_id=w.id))
        self._bulk(ProtocolTimeSlot, slots)
        self._bulk(ProtocolTemplate.assignees.through, through)
        for batch in self.active:
            expand_protocol_to_alert_rules(batch)
            rule = AlertRule.objects.create(
                farm=self.farm, rule_type=AlertRuleType.WEIGHING_REMINDER, trigger_mode=TriggerMode.SCHEDULED,
                frequency=ScheduleFrequency.WEEKLY, trigger_time=dt.time(7, 0), batch=batch,
            )
            rule.assignees.set(workers_by_house[batch.house_id][:3])

    def _daily_logs(self):
        logs = []
        for batch in self.active + self.closed:
            end = min(self.today - dt.timedelta(days=1), batch.actual_end_date or self.today)
            first = max(batch.start_date, end - dt.timedelta(days=self.o['days'] - 1)) if batch in self.active else batch.start_date
            alive = batch.initial_count
            d = first
            while d <= end:
                day = (d - batch.start_date).days
                mortality = int(alive * self.rng.uniform(0.0003, 0.0015))
                alive -= mortality
                feed = round(alive * (0.02 + day * 0.004), 1)  # kg/bird/day rises with age
                logs.append(DailyLog(
                    batch=batch, log_date=d, mortality=mortality, feed_consumed_kg=feed,
                    water_consumed_l=round(feed * self.rng.uniform(1.7, 2.1), 1),
                    avg_sample_weight=round(0.042 + day * 0.058, 3) if day % 7 == 0 else None,
                    eggs_collected=int(alive * 0.8) if batch.production_type == ProductionType.LAYER else None,
                ))
                d += dt.timedelta(days=1)
        self._bulk(DailyLog, logs)

    def _task_history(self):
        """Every due occurrence of the last `days` days, ~95 % done by one of the line's workers.
        A stock-consuming completion carries its OUT movement, as `complete_task_occurrence` does."""
        from apps.batches.services import day_of_cycle

        assignees = {}
        for row in ProtocolTemplate.assignees.through.objects.values('protocoltemplate_id', 'user_id'):
            assignees.setdefault(row['protocoltemplate_id'], []).append(row['user_id'])
        slots_by_line = {}
        for s in ProtocolTimeSlot.objects.all():
            slots_by_line.setdefault(s.protocol_line_id, []).append(s)

        pending = []  # (completion, movement or None)
        for batch in self.active:
            lines = self.lines_by_house[batch.house_id]
            for back in range(self.o['days'], 0, -1):
                d = self.today - dt.timedelta(days=back)
                cycle = day_of_cycle(batch, d)
                for line in lines:
                    if _protocol_line_occurrence(line, cycle) is None:
                        continue
                    line_slots = slots_by_line.get(line.id) or [None]
                    for slot in line_slots:
                        if self.rng.random() > 0.95:
                            continue
                        who = self.rng.choice(assignees.get(line.id) or [self.admin.id])
                        movement = None
                        if line.stock_item_id and line.quantity_per_day:
                            movement = StockMovement(
                                item_id=line.stock_item_id, batch=batch, protocol_line=line,
                                movement_type=MovementType.OUT, quantity=round(line.quantity_per_day / len(line_slots), 2),
                                movement_date=d, note=f'Tâche : {line.what}',
                            )
                        pending.append((TaskCompletion(
                            protocol_template=line, batch=batch, date=d, time_slot=slot, completed_by_id=who,
                        ), movement))
        movements = self._bulk(StockMovement, [m for _, m in pending if m])
        it = iter(movements)
        for completion, movement in pending:
            if movement:
                completion.stock_movement = next(it)
        self._bulk(TaskCompletion, [c for c, _ in pending])
        # completed_at is auto_now_add — back-date it to the occurrence's day.
        with connection.cursor() as cur:
            cur.execute(
                "UPDATE protocols_taskcompletion SET completed_at = (date + time '10:00') AT TIME ZONE %s",
                [str(timezone.get_current_timezone())],
            )

    def _stock_deliveries(self):
        """Weekly IN movements sized so the named items end above their threshold, plus a few
        movements for every other item."""
        used = {}
        for m in StockMovement.objects.filter(movement_type=MovementType.OUT).values('item_id', 'quantity'):
            used[m['item_id']] = used.get(m['item_id'], 0) + m['quantity']
        rows = []
        weeks = max(1, self.o['days'] // 7 + 1)
        for item in self.items:
            total = used.get(item.item_code, 0) * 1.15 + self.rng.randint(0, 500)
            for w in range(weeks):
                rows.append(StockMovement(
                    item=item, movement_type=MovementType.IN, quantity=round(total / weeks, 1),
                    movement_date=self.today - dt.timedelta(days=self.o['days'] - w * 7),
                    supplier=item.supplier.name if item.supplier else '', supplier_batch_number=f'LOT-{w}',
                ))
        self._bulk(StockMovement, rows)

    def _work_hours(self):
        rows = []
        for u in self.employees:
            for back in range(self.o['days'], 0, -1):
                rows.append(WorkHoursEntry(
                    user=u, date=self.today - dt.timedelta(days=back),
                    hours_worked=Decimal(self.rng.choice(['6.00', '7.50', '8.00', '9.00'])),
                ))
        self._bulk(WorkHoursEntry, rows)
        last = (self.today.replace(day=1) - dt.timedelta(days=1))
        self._bulk(SalaryPayment, [
            SalaryPayment(
                farm=self.farm, user=u, period_month=last.month, period_year=last.year,
                total_hours=Decimal('180.00'), hourly_rate_snapshot=u.hourly_rate,
                amount=u.hourly_rate * 180, status=SalaryPaymentStatus.PAID, paid_date=self.today.replace(day=1),
            )
            for u in self.employees
        ])

    def _finance(self):
        o = self.o
        sales, expenses, orders = [], [], []
        seq = 0
        order_dates = []
        for back in range(o['days'] - 1, -1, -1):
            d = self.today - dt.timedelta(days=back)
            for _ in range(o['sales_per_day']):
                batch = self.rng.choice(self.active)
                qty = self.rng.randint(10, 500)
                price = Decimal(self.rng.choice([2500, 2600, 2750, 3000]))
                sales.append(Sale(
                    farm=self.farm, batch=batch, cashier=self.rng.choice(self.cashiers),
                    product_type=self.rng.choice([ProductType.BIRD, ProductType.BIRD, ProductType.EGG, ProductType.MANURE]),
                    quantity=qty, unit_price=price, total_amount=price * qty, sale_date=d,
                    customer=f'Client {self.rng.randint(1, 400)}',
                ))
            for _ in range(o['expenses_per_day']):
                expenses.append(Expense(
                    farm=self.farm, batch=self.rng.choice(self.active + [None]),
                    category=self.rng.choice(list(ExpenseCategory.values)),
                    amount=Decimal(self.rng.randint(5, 500) * 1000), expense_date=d,
                    supplier=self.rng.choice(self.suppliers).name,
                ))
            for _ in range(o['orders_per_day']):
                seq += 1
                item = self.rng.choice(self.items)
                qty = self.rng.randint(10, 2000)
                orders.append(PurchaseOrder(
                    order_code=f'PO-L-{seq:06d}', farm=self.farm, cashier=self.rng.choice(self.cashiers), item=item,
                    supplier=item.supplier.name if item.supplier else '', quantity=qty,
                    amount=item.unit_price * qty,
                    status=OrderStatus.PENDING if back < 3 else self.rng.choice([OrderStatus.RECEIVED, OrderStatus.RECEIVED, OrderStatus.CANCELLED]),
                ))
                order_dates.append(d)
        self._bulk(Sale, sales)
        self._bulk(Expense, expenses)
        self._bulk(PurchaseOrder, orders)
        with connection.cursor() as cur:  # order_date is auto_now_add — spread it over the window
            for i in range(0, len(orders), CHUNK):
                chunk = list(zip(orders[i:i + CHUNK], order_dates[i:i + CHUNK]))
                cur.executemany(
                    'UPDATE finance_purchaseorder SET order_date = %s WHERE order_code = %s',
                    [(d, po.order_code) for po, d in chunk],
                )

    def _alert_history(self):
        """One fired Alert per scheduled rule per past day, one SMS each (the app writes one per
        assignee; one keeps the table at a plausible size without changing its access pattern)."""
        rules = list(AlertRule.objects.filter(trigger_mode=TriggerMode.SCHEDULED, frequency=ScheduleFrequency.DAILY))
        alerts, stamps = [], []
        tz = timezone.get_current_timezone()
        for rule in rules:
            for back in range(self.o['days'], 0, -1):
                d = self.today - dt.timedelta(days=back)
                alerts.append(Alert(
                    rule=rule, batch_id=rule.batch_id, status=AlertStatus.NEW, severity='info',
                    message=f'Tâche à effectuer ({rule.trigger_time:%Hh%M})', is_read=back > 2,
                ))
                stamps.append(dt.datetime.combine(d, rule.trigger_time, tzinfo=tz))
        alerts = self._bulk(Alert, alerts)
        with connection.cursor() as cur:
            for i in range(0, len(alerts), CHUNK):
                cur.executemany(
                    'UPDATE alerts_alert SET triggered_at = %s WHERE id = %s',
                    [(s, a.id) for a, s in zip(alerts[i:i + CHUNK], stamps[i:i + CHUNK])],
                )
        self._bulk(SmsMessage, [
            SmsMessage(alert=a, recipient=f'+2376{90000000 + n % 20000:08d}', body=a.message,
                       idempotency_key=f'load-{a.id}', provider_status=SmsStatus.SENT, provider='console')
            for n, a in enumerate(alerts)
        ])

    def _incidents_and_audit(self):
        techs = [u for u in self.employees if u.role == UserRole.TECHNICIAN] or [self.admin]
        self._bulk(UnusualCase, [
            UnusualCase(case_code=f'UC-L-{i:05d}', batch=self.rng.choice(self.active),
                        worker=self.rng.choice(self.workers), case_description='Comportement anormal observé',
                        resolved=i % 4 != 0)
            for i in range(400)
        ])
        self._bulk(EquipmentFault, [
            EquipmentFault(fault_code=f'EF-L-{i:05d}', house=self.rng.choice(self.houses),
                           technician=self.rng.choice(techs), fault_description='Abreuvoir défectueux',
                           status='REPORTED' if i % 3 == 0 else 'RESOLVED')
            for i in range(200)
        ])
        self._bulk(AuditLogEntry, [
            AuditLogEntry(farm=self.farm, user=self.admin, user_name_snapshot=self.admin.name,
                          action='batch.updated', target_description=f'Bande {i % 50 + 1:03d}')
            for i in range(10_000)
        ])
