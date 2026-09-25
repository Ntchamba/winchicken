"""Measure every screen's API calls against a seeded `*_load` database.

Replays, in-process through the full Django + DRF stack (auth, permissions, serialisation), the
exact GET requests each screen fires — the lists below were captured from a real browser
visiting each route, not read from the source. For each request: median wall time over
`--repeat` runs, query count, time spent in SQL, response size and HTTP status. Then the write
paths: task completion round-trip, the three Excel imports, and the scheduled-alert Celery task.

Every write runs inside a transaction that is rolled back, so the database is identical from one
run to the next and before/after numbers compare like with like. Celery runs eagerly with an
in-memory broker and SMS goes to the console provider: nothing leaves the process.

Refuses to run unless the database name ends with `_load`.

    python manage.py bench_load --json /tmp/before.json
"""
import io
import json
import os
import re
import statistics
import time
from datetime import datetime, timedelta

from django.conf import settings
from django.core.cache import caches
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.test import Client, override_settings
from django.utils import timezone

LOAD_DB_SUFFIX = '_load'

# Every screen also fires these (sidebar badges, house list, shell) — measured once, as "shell".
SHELL = [
    '/api/auth/me/', '/api/alerts/unread-count/', '/api/stock-items/low-count/',
    '/api/unusual-cases/?resolved=false', '/api/equipment-faults/?status=OPEN', '/api/houses/',
    '/api/batches/?status=ACTIVE', '/api/purchase-orders/pending-count/',
]

SCREENS = {
    'Tableau de bord': [
        '/api/batches/health-score/', '/api/tasks/upcoming/', '/api/batches/growth-curves/',
        '/api/alerts/?open=1',
    ],
    'Vue globale (arbre)': ['/api/farm/overview/'],
    'Bâtiment (hub)': [
        '/api/unusual-cases/?house_code={house}&resolved=false',
        '/api/equipment-faults/?house_code={house}&status=OPEN',
        '/api/batches/growth-curves/?house_code={house}', '/api/houses/{house}/tasks-now/',
        '/api/batches/?house_code={house}',
    ],
    'Bâtiment – Évolution': [
        '/api/batches/growth-curves/?house_code={house}', '/api/batches/?house_code={house}',
        '/api/batches/{batch}/kpi/weekly/',
    ],
    'Bâtiment – Tâches': [
        '/api/houses/{house}/assignments/', '/api/tasks/assignable-users/?q=&limit=50',
        '/api/houses/{house}/tasks-now/', '/api/batches/?house_code={house}',
    ],
    'Bâtiment – Pesée': [
        '/api/batches/growth-curves/?house_code={house}', '/api/batches/{batch}/daily-logs/?weighed=1',
    ],
    'Protocole': [
        '/api/farms/{farm}/stock-items/', '/api/houses/{house}/protocol-categories/?page=1',
        '/api/houses/{house}/protocol/',
    ],
    'Finances – Globale': [
        '/api/finance/summary/?range=6m', '/api/finance/expense-categories/?range=6m',
        '/api/finance/transactions/?page=1&type=all',
    ],
    'Finances – Ventes': ['/api/finance/sales-evolution/?period=month'],
    'Finances – Achats': ['/api/finance/purchases-evolution/?period=month'],
    'Finances – Salaires': ['/api/salary-payments/', '/api/employees/payroll/'],
    'Stock': [
        '/api/farms/{farm}/stock-evolution/', '/api/farms/{farm}/stock-items/',
        '/api/farms/{farm}/suppliers/', '/api/farms/{farm}/stock-compositions/',
    ],
    'Bons de commande': ['/api/farms/{farm}/stock-items/', '/api/purchase-orders/?page=1'],
    'Employés': ['/api/employees/'],
    'Caisse': ['/api/sales/?sale_date={today}&page={page}'],
    'Alertes': ['/api/alerts/'],
    # The grid reads the month's summary; a day's list loads when it is opened (2026-09-25).
    'Calendrier': ['/api/protocols/schedule/?month={month}&view=summary', '/api/protocols/schedule/?date={today}'],
    'Mes tâches (ouvrier)': ['@worker', '/api/tasks/mine/'],
    'Journal d’audit': ['/api/audit-log/?page=1'],
}


class _QueryCounter:
    """Counts and times every query run inside the block. Django's own query log is a deque
    capped at 9 000 entries, which silently under-reports an import that runs more."""

    def __enter__(self):
        self.count, self.ms = 0, 0.0
        self._cm = connection.execute_wrapper(self)
        self._cm.__enter__()
        return self

    def __exit__(self, *exc):
        self._cm.__exit__(*exc)

    def __call__(self, execute, sql, params, many, context):
        t0 = time.perf_counter()
        try:
            return execute(sql, params, many, context)
        finally:
            self.count += 1
            self.ms += (time.perf_counter() - t0) * 1000


class Command(BaseCommand):
    help = 'Time every screen\'s API calls against a *_load database (refuses any other DB).'

    def add_arguments(self, parser):
        parser.add_argument('--repeat', type=int, default=3)
        parser.add_argument('--json', help='Write the raw results to this file.')
        parser.add_argument(
            '--dump', help='Write every GET response body into this directory, to diff two code versions.',
        )
        parser.add_argument('--only', help='Comma-separated, case-insensitive substrings of the screens / sections to run.')
        parser.add_argument('--import-rows', type=int, default=2000)
        # Separate, smaller default: every new account hashes a generated password (~1 s each).
        parser.add_argument('--employee-import-rows', type=int, default=100)
        parser.add_argument(
            '--warm-cache', action='store_true',
            help='Keep the aggregate response cache between repeats (default: cleared, so each run computes).',
        )
        parser.add_argument('--email', default='admin@load.local')
        parser.add_argument('--password', default='LoadTest123!')

    def handle(self, *args, **o):
        db_name = connection.settings_dict['NAME']
        if not str(db_name).endswith(LOAD_DB_SUFFIX):
            raise CommandError(f'Refusing to run: database "{db_name}" does not end with "{LOAD_DB_SUFFIX}".')

        from config.celery import app as celery_app
        celery_app.conf.update(task_always_eager=True, broker_url='memory://', result_backend='cache+memory://')
        self.o = o
        self.only = {s.strip() for s in o['only'].split(',')} if o['only'] else None
        self.results = {'db': db_name, 'at': timezone.now().isoformat(), 'requests': {}, 'screens': {}, 'writes': {}}
        with override_settings(
            SMS_PROVIDER='console', WEB_PUSH_ENABLED=False, ALLOWED_HOSTS=['*'],
            CELERY_TASK_ALWAYS_EAGER=True,
        ):
            self._run()
        if o['json']:
            with open(o['json'], 'w') as fh:
                json.dump(self.results, fh, indent=1, ensure_ascii=False)

    # -- plumbing --------------------------------------------------------------------------

    def _want(self, name):
        return self.only is None or any(tok.lower() in name.lower() for tok in self.only)

    def _client(self, email, password):
        client = Client()
        resp = client.post('/api/auth/login/', {'email': email, 'password': password}, content_type='application/json')
        if resp.status_code != 200:
            raise CommandError(f'Login failed for {email}: {resp.status_code} {resp.content[:200]!r}')
        return client, {'HTTP_AUTHORIZATION': f'Bearer {resp.json()["access"]}'}

    def _measure(self, client, headers, method, url, **kw):
        times, last = [], None
        for _ in range(self.o['repeat'] if method == 'get' else 1):
            if not self.o['warm_cache']:
                # Time the work, not a hit of the short-lived aggregate cache (apps.core.cache).
                caches['responses'].clear()
            with _QueryCounter() as ctx:
                t0 = time.perf_counter()
                resp = getattr(client, method)(url, **headers, **kw)
                body = resp.content if hasattr(resp, 'content') else b''
                elapsed = (time.perf_counter() - t0) * 1000
            times.append(elapsed)
            last = (resp, ctx, body)
        resp, ctx, body = last
        if self.o.get('dump') and method == 'get':
            os.makedirs(self.o['dump'], exist_ok=True)
            name = re.sub(r'[^A-Za-z0-9]+', '_', url).strip('_') + ('_worker' if headers is not self.admin_h else '')
            with open(os.path.join(self.o['dump'], name + '.json'), 'wb') as fh:
                fh.write(body)
        return {
            'ms': round(statistics.median(times), 1), 'queries': ctx.count, 'sql_ms': round(ctx.ms, 1), 'kb': round(len(body) / 1024, 1), 'status': resp.status_code,
        }

    def _row(self, label, r):
        flag = '' if r['status'] < 400 else f'  !! HTTP {r["status"]}'
        self.stdout.write(
            f'  {label:62} {r["ms"]:>9.1f} ms {r["queries"]:>6} q {r["sql_ms"]:>9.1f} ms sql {r["kb"]:>9.1f} KB{flag}'
        )
        self.stdout.flush()

    # -- run -------------------------------------------------------------------------------

    def _run(self):
        from apps.batches.models import BatchStatus, PoultryBatch
        from apps.core.models import Farm, User, UserRole

        farm = Farm.objects.get()
        batch = PoultryBatch.objects.filter(status=BatchStatus.ACTIVE).order_by('batch_code').first()
        today = timezone.localdate()
        ctx = {
            'farm': farm.id, 'house': batch.house_id, 'batch': batch.batch_code, 'today': today.isoformat(),
            'month': today.strftime('%Y-%m'), 'page': 1,
        }
        admin, admin_h = self._client(self.o['email'], self.o['password'])
        self.admin_h = admin_h
        # A worker whose line is due every day (until_end), so "Mes tâches" has something in it.
        worker_user = (
            User.objects.filter(role=UserRole.WORKER, assigned_protocol_tasks__until_end=True)
            .order_by('id').first()
        )
        worker = worker_h = None
        if worker_user:
            worker, worker_h = self._client(worker_user.email, self.o['password'])

        seen = {}

        def measure_get(url, client, headers):
            if url not in seen:
                seen[url] = self._measure(client, headers, 'get', url)
                self.results['requests'][url] = seen[url]
            return seen[url]

        self.stdout.write(f'\n== Screens ({self.o["repeat"]} runs, median) — {self.results["db"]}')
        if self._want('shell'):
            self.stdout.write('\n[Shell — fired by every screen]')
            rows = [measure_get(u, admin, admin_h) for u in SHELL]
            for u, r in zip(SHELL, rows):
                self._row(u, r)
            self.results['screens']['shell'] = self._total(rows)
        for name, urls in SCREENS.items():
            if not self._want(name):
                continue
            client, headers = admin, admin_h
            if urls[0] == '@worker':
                urls = urls[1:]
                if worker is None:
                    continue
                client, headers = worker, worker_h
            self.stdout.write(f'\n[{name}]')
            rows = []
            for template in urls:
                if '{page}' in template:  # the cashier reads every page of today's sales
                    rows += self._all_pages(template, ctx, client, headers)
                    continue
                url = template.format(**ctx)
                r = measure_get(url, client, headers) if client is admin else self._measure(client, headers, 'get', url)
                self._row(url, r)
                rows.append(r)
            self.results['screens'][name] = self._total(rows)
            t = self.results['screens'][name]
            self.stdout.write(f'  {"= screen (sequential sum / slowest call)":62} {t["ms"]:>9.1f} ms {t["queries"]:>6} q   slowest {t["max_ms"]:.1f} ms')

        if self._want('complete'):
            self._task_round_trip(admin, admin_h, batch)
        if self._want('import'):
            self._imports(admin, admin_h, farm)
        if self._want('alerts'):
            self._scheduled_alerts()

    def _total(self, rows):
        return {
            'ms': round(sum(r['ms'] for r in rows), 1), 'max_ms': max((r['ms'] for r in rows), default=0),
            'queries': sum(r['queries'] for r in rows), 'kb': round(sum(r['kb'] for r in rows), 1),
        }

    def _all_pages(self, template, ctx, client, headers):
        rows, page = [], 1
        while page <= 100:  # fetchAllPages' MAX_PAGES
            url = template.format(**{**ctx, 'page': page})
            r = self._measure(client, headers, 'get', url)
            rows.append(r)
            data = json.loads(client.get(url, **headers).content)
            if not data.get('next'):
                break
            page += 1
        total = self._total(rows)
        label = f'{template.format(**{**ctx, "page": "1…"})} ×{len(rows)} pages'
        self._row(label, {**total, 'sql_ms': sum(r['sql_ms'] for r in rows), 'status': 200})
        self.results['requests'][label] = total
        return rows

    # -- writes (rolled back) --------------------------------------------------------------

    class _Rollback(Exception):
        pass

    def _rolled_back(self, fn):
        try:
            with transaction.atomic():
                out = fn()
                raise self._Rollback
        except self._Rollback:
            return out

    def _task_round_trip(self, client, headers, batch):
        from apps.houses.services import compute_tasks_now

        self.stdout.write('\n[Task completion round-trip — "Marquer comme fait" then undo]')
        _, tasks = compute_tasks_now(batch.house)
        task = next((t for t in tasks if t['completable'] and not t['done']), None)
        if task is None:  # everything is done today: undo one first so there is one to complete
            task = next(t for t in tasks if t['completable'])
        base = f'/api/houses/{batch.house_id}/tasks-now/{task["id"]}'
        body = json.dumps({'time_slot_id': task['timeSlotId']})

        def go():
            out = {}
            if task['done']:
                client.post(f'{base}/uncomplete/', body, content_type='application/json', **headers)
            out['complete'] = self._measure(client, headers, 'post', f'{base}/complete/', data=body, content_type='application/json')
            out['refresh tasks-now'] = self._measure(client, headers, 'get', f'/api/houses/{batch.house_id}/tasks-now/')
            out['uncomplete'] = self._measure(client, headers, 'post', f'{base}/uncomplete/', data=body, content_type='application/json')
            return out

        out = self._rolled_back(go)
        for k, r in out.items():
            self._row(f'{k} ({task["what"]})', r)
        self.results['writes']['task_round_trip'] = out

    def _imports(self, client, headers, farm):
        from openpyxl import Workbook

        n = self.o['import_rows']
        self.stdout.write(f'\n[Excel imports — {n:,} rows each, rolled back]')

        def xlsx(header, rows):
            wb = Workbook()
            ws = wb.active
            ws.append(header)
            for r in rows:
                ws.append(r)
            buf = io.BytesIO()
            wb.save(buf)
            buf.seek(0)
            buf.name = 'charge.xlsx'
            return buf

        stock = lambda: xlsx(  # noqa: E731
            ['Article', 'Catégorie', 'Détail', 'Unité', "Seuil d'alerte", 'Prix unitaire', 'Fournisseur'],
            [[f'Import article {i:05d}', 'Aliment', 'Starter', 'kg', 100, 450, 'Fournisseur 01'] for i in range(n)],
        )
        employees = lambda: xlsx(  # noqa: E731
            ['Nom', 'Email', 'Rôle', 'Civilité', 'Taux horaire'],
            [[f'Import employé {i:05d}', f'imp{i:05d}@load.local', 'Ouvrier', 'M.', 650]
             for i in range(self.o['employee_import_rows'])],
        )
        protocol = lambda: xlsx(  # noqa: E731
            ['Catégorie', 'De', 'À', 'Action', 'Détails', 'Consommation', 'Unité', 'Quantité/jour', 'Créneaux'],
            [['Alimentation', i % 60 + 1, i % 60 + 3, f'Ligne {i}', '', 'Aliment croissance', 'kg', 55,
              '06:30-07:30;18:30-19:30'] for i in range(n)],
        )
        cases = [
            ('stock (aperçu, dry_run)', f'/api/farms/{farm.id}/stock-items/import-xlsx/', stock, {'dry_run': '1'}),
            ('stock (confirmé)', f'/api/farms/{farm.id}/stock-items/import-xlsx/', stock, {}),
            ('protocole (analyse)', '/api/protocols/import-xlsx/', protocol, {}),
            (f'employés (création de {self.o["employee_import_rows"]} comptes)', '/api/employees/import-xlsx/', employees, {}),
        ]
        self.results['writes']['imports'] = {}
        for label, url, make, extra in cases:
            if url == '/api/employees/import-xlsx/':
                # A background job since 2026-09-25: the request only checks and queues the file
                # (measured with the queueing stubbed out), the Celery task does the work.
                from unittest import mock

                from apps.core.import_jobs import run_job

                def job():
                    with mock.patch('apps.core.tasks.run_employee_import.delay') as delay:
                        request = self._measure(client, headers, 'post', url, data={'file': make(), **extra})
                    with _QueryCounter() as ctx:
                        t0 = time.perf_counter()
                        run_job(*delay.call_args.args)
                        ms = (time.perf_counter() - t0) * 1000
                    return request, {'ms': round(ms, 1), 'queries': ctx.count, 'sql_ms': round(ctx.ms, 1), 'kb': 0, 'status': 200}

                request, task = self._rolled_back(job)
                for part, r in ((f'{label} — requête', request), (f'{label} — tâche Celery', task)):
                    self._row(part, r)
                    self.results['writes']['imports'][part] = r
                continue
            r = self._rolled_back(lambda: self._measure(client, headers, 'post', url, data={'file': make(), **extra}))
            self._row(label, r)
            self.results['writes']['imports'][label] = r

    def _scheduled_alerts(self):
        """The Beat task at the busiest minute of the day (06:30 — every feeding slot fires)."""
        from apps.alerts.models import Alert, SmsMessage
        from apps.alerts.services import fire_scheduled_alerts

        self.stdout.write('\n[Celery — check_scheduled_alerts at the busiest minute, rolled back]')
        out = {}
        for hhmm in ('06:30', '12:00'):
            hh, mm = map(int, hhmm.split(':'))
            now = timezone.make_aware(datetime.combine(timezone.localdate(), datetime.min.time()) + timedelta(hours=hh, minutes=mm))

            def go():
                before_sms = SmsMessage.objects.count()
                with _QueryCounter() as ctx:
                    t0 = time.perf_counter()
                    created = fire_scheduled_alerts(now=now)
                    ms = (time.perf_counter() - t0) * 1000
                return {
                    'ms': round(ms, 1), 'queries': ctx.count, 'sql_ms': round(ctx.ms, 1),
                    'kb': 0, 'status': 200, 'alerts': len(created),
                    'sms': SmsMessage.objects.count() - before_sms,
                }

            r = self._rolled_back(go)
            self._row(f'fire_scheduled_alerts @ {hhmm} → {r["alerts"]} alerts, {r["sms"]} SMS', r)
            out[hhmm] = r
        self.results['writes']['scheduled_alerts'] = out
