"""Integration chain 2 (protocol side) — Excel import -> parsed rows -> confirmation (the normal
protocol PUT) -> database state -> a completed task survives a re-import.

The protocol import only parses; the form maps the rows and saves them through
PUT /houses/{code}/protocol/, an upsert keyed on line id. The frontend now gives a re-imported
line the id of the existing line it repeats (utils/protocolImportResolve.js); these pin what the
API does with that — and why the id matters.
"""
import datetime as dt
import io
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from openpyxl import Workbook
from rest_framework.test import APITestCase

from apps.batches.models import BatchStatus, PoultryBatch, ProductionType
from apps.core.models import Farm, User, UserRole, create_role_profile
from apps.houses.models import PoultryHouse
from apps.protocols.models import ProtocolCategory, ProtocolTemplate, TaskCompletion
from apps.stock.calculations import current_quantity
from apps.stock.models import MovementType, StockCategory, StockItem, StockMovement

HEADER = ('Action', 'Catégorie', 'De', 'À', 'Consommation', 'Quantité/jour', 'Créneaux')
ROWS = (
    ('Aliment démarrage', 'Alimentation', 1, None, 'Provende', 40, ''),
    ('Vaccin Gumboro', 'Vaccination', 7, 7, '', None, '08:00-09:00;25:00-26:00'),
    ('', 'Vaccination', 3, 3, '', None, ''),
)


def xlsx(header, rows):
    wb = Workbook()
    ws = wb.active
    ws.append(list(header))
    for row in rows:
        ws.append(list(row))
    buf = io.BytesIO()
    wb.save(buf)
    return SimpleUploadedFile('protocole.xlsx', buf.getvalue())


class ProtocolImportChainTests(APITestCase):
    def setUp(self):
        self.farm = Farm.objects.create(name='Ferme Protocole')
        self.admin = User.objects.create_user(email='admin@proto.local', password='x', name='A', role=UserRole.ADMIN, farm=self.farm)
        create_role_profile(self.admin)
        self.client.force_authenticate(user=self.admin)
        self.house = PoultryHouse.objects.create(house_code=f'H-{self.farm.id}-001', farm=self.farm, name='B1', max_capacity=500)
        today = timezone.localdate()
        PoultryBatch.objects.create(
            batch_code=f'B-{self.farm.id}', house=self.house, production_type=ProductionType.BROILER, initial_count=500,
            start_date=today - dt.timedelta(days=1), status=BatchStatus.ACTIVE,
        )
        self.item = StockItem.objects.create(
            item_code=f'FEE-{self.farm.id}-001', farm=self.farm, category=StockCategory.objects.get(farm=self.farm, kind='FEED'),
            name='Provende', unit='kg', unit_price=Decimal('450'),
        )
        StockMovement.objects.create(item=self.item, movement_type=MovementType.IN, quantity=500, movement_date=today)
        self.categories = {c.label: c.id for c in ProtocolCategory.objects.filter(house=self.house)}

    def parse(self, upload, preview=False):
        data = {'file': upload, **({'preview': '1'} if preview else {})}
        return self.client.post('/api/protocols/import-xlsx/', data, format='multipart')

    def to_lines(self, rows, keep_ids=False):
        """What the form sends after an import: category label -> id, consumption name -> item
        code, and (since the fix) the id of the existing line a row repeats."""
        existing = {(l.category_id, l.what.lower(), l.from_value, None if l.until_end else l.to_value): l.id
                    for l in ProtocolTemplate.objects.filter(house=self.house)} if keep_ids else {}
        lines = []
        for r in rows:
            category = self.categories[r['category']]
            line = {
                'category': category, 'from_value': r['fromValue'], 'from_unit': 'DAY',
                'to_value': None if r['untilEnd'] else r['toValue'], 'to_unit': 'DAY', 'until_end': r['untilEnd'],
                'what': r['what'], 'details': r['details'],
                'time_slots': [{'start_time': s['startTime'], 'end_time': s['endTime']} for s in r['timeSlots']],
                'stock_item': self.item.item_code if r['consumption'] == 'Provende' else None,
                'quantity_per_day': r['quantityPerDay'],
            }
            key = (category, r['what'].lower(), r['fromValue'], None if r['untilEnd'] else r['toValue'])
            if key in existing:
                line['id'] = existing[key]
            lines.append(line)
        return lines

    def save(self, lines):
        response = self.client.put(f'/api/houses/{self.house.house_code}/protocol/', {'lines': lines}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        return response.data

    def complete_feeding(self):
        line = ProtocolTemplate.objects.get(house=self.house, what='Aliment démarrage')
        return self.client.post(f'/api/houses/{self.house.house_code}/tasks-now/{line.id}/complete/', {}, format='json')

    def test_parse_reports_rows_skips_and_slot_warnings(self):
        data = self.parse(xlsx(HEADER, ROWS)).data
        self.assertEqual(data['imported'], 2)
        self.assertEqual(data['skipped'], [{'line': 4, 'reason': 'action manquante'}])
        self.assertEqual([w['line'] for w in data['warnings']], [3])  # 25:00-26:00 dropped, row kept
        self.assertEqual(data['rows'][1]['timeSlots'], [{'startTime': '08:00', 'endTime': '09:00'}])

    def test_confirming_writes_the_protocol_and_the_tasks_appear(self):
        rows = self.parse(xlsx(HEADER, ROWS)).data['rows']
        self.save(self.to_lines(rows))
        lines = {l.what: l for l in ProtocolTemplate.objects.filter(house=self.house).prefetch_related('time_slots')}
        self.assertEqual(set(lines), {'Aliment démarrage', 'Vaccin Gumboro'})
        self.assertEqual((lines['Aliment démarrage'].stock_item_id, lines['Aliment démarrage'].quantity_per_day), (self.item.item_code, 40))
        self.assertEqual([str(s.start_time) for s in lines['Vaccin Gumboro'].time_slots.all()], ['08:00:00'])
        tasks = self.client.get(f'/api/houses/{self.house.house_code}/tasks-now/').data['tasks']
        self.assertIn('Aliment démarrage', [t.get('what') or t.get('title') for t in tasks])

    def test_a_reimport_that_keeps_ids_keeps_todays_completion_and_deducts_once(self):
        rows = self.parse(xlsx(HEADER, ROWS)).data['rows']
        self.save(self.to_lines(rows))
        self.assertEqual(self.complete_feeding().status_code, 201)

        rows = self.parse(xlsx(HEADER, ROWS)).data['rows']
        self.save(self.to_lines(rows, keep_ids=True))

        self.assertEqual(TaskCompletion.objects.count(), 1)
        self.assertEqual(self.complete_feeding().data['status'], 'already_done')
        self.assertEqual(current_quantity(self.item), 460)

    def test_why_the_ids_matter_a_reimport_without_them_loses_the_completion(self):
        # The API's documented upsert semantics: a line not sent back is deleted, with its
        # completions (CASCADE). This is what every re-import did before the frontend fix.
        rows = self.parse(xlsx(HEADER, ROWS)).data['rows']
        self.save(self.to_lines(rows))
        self.complete_feeding()
        self.save(self.to_lines(self.parse(xlsx(HEADER, ROWS)).data['rows']))
        self.assertEqual(TaskCompletion.objects.count(), 0)
        self.assertEqual(self.complete_feeding().data['status'], 'done')
        self.assertEqual(current_quantity(self.item), 420)  # deducted twice for one day

    def test_a_missing_required_column_previews_the_gap_and_is_refused_otherwise(self):
        upload = lambda: xlsx(('Action', 'De'), [('Aliment', 1)])  # noqa: E731
        preview = self.parse(upload(), preview=True).data
        self.assertEqual(preview['columns']['unresolved'], ['Catégorie'])
        self.assertEqual(preview['rows'], [])
        response = self.parse(upload())
        self.assertEqual(response.status_code, 400)
        self.assertIn('Catégorie', response.data['detail'])

    def test_a_file_with_no_usable_row_changes_nothing(self):
        self.save(self.to_lines(self.parse(xlsx(HEADER, ROWS)).data['rows']))
        data = self.parse(xlsx(HEADER, [('', 'Vaccination', 3, 3, '', None, '')])).data
        self.assertEqual(data['rows'], [])  # the form keeps the existing protocol (resolver returns null)
        self.assertEqual(ProtocolTemplate.objects.filter(house=self.house).count(), 2)

    def test_not_an_xlsx_is_refused(self):
        response = self.parse(SimpleUploadedFile('protocole.csv', b'a;b'))
        self.assertEqual(response.status_code, 400)
        self.assertIn('.xlsx', response.data['detail'])
