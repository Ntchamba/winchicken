from datetime import date

from rest_framework import status
from rest_framework.test import APITestCase

from apps.batches.models import PoultryBatch, ProductionType
from apps.core.models import Farm, User, UserRole, create_role_profile
from apps.houses.models import PoultryHouse
from apps.protocols.models import ProtocolCategory, ProtocolTemplate, ProtocolTimeSlot


class ScheduleViewMultiDayTests(APITestCase):
    """GET /api/protocols/schedule/ (Bug 3 fix, 2026-08-27, docs/deviations.md) — a
    ProtocolTemplate line spanning several days must appear on every one of those days in the
    calendar month view, not just the first (the previous implementation read PROTOCOL_TASK
    AlertRule rows, generated for a line's first due day only)."""

    def setUp(self):
        self.farm = Farm.objects.create(name='Ferme Calendrier Test')
        self.user = User.objects.create_user(
            email='admin@calendar-test.local', password='x', name='Admin', role=UserRole.ADMIN, farm=self.farm,
        )
        create_role_profile(self.user)
        self.client.force_authenticate(user=self.user)

        self.house = PoultryHouse.objects.create(house_code='H-CAL-1', farm=self.farm, name='Salle 1', max_capacity=1000)
        self.category = ProtocolCategory.objects.create(house=self.house, label='Alimentation', icon='Soup')
        # Day 1 to day 15 of the cycle — day_of_cycle = (day - start_date).days, so day_of_cycle
        # 1 falls on start_date + 1 (2026-03-02), matching this project's existing convention
        # (see apps.houses.tests.TaskAssignmentTests.setUp's own "day_of_cycle=1" comment).
        # Batch starts 2026-03-01: day 1 = 2026-03-02, day 15 = 2026-03-16.
        ProtocolTemplate.objects.create(
            house=self.house, category=self.category,
            from_value=1, from_unit='DAY', to_value=15, to_unit='DAY', until_end=False,
            what='Aliment démarrage',
        )
        self.batch = PoultryBatch.objects.create(
            batch_code='BATCH-CAL-1', house=self.house, production_type=ProductionType.BROILER,
            initial_count=500, start_date=date(2026, 3, 1),
        )

    def test_multi_day_line_appears_on_every_day_of_its_range(self):
        response = self.client.get('/api/protocols/schedule/', {'month': '2026-03'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        dates = sorted(entry['date'] for entry in response.data)
        expected = [f'2026-03-{day:02d}' for day in range(2, 17)]
        self.assertEqual(dates, expected)

    def test_no_entries_outside_the_line_s_range(self):
        response = self.client.get('/api/protocols/schedule/', {'month': '2026-03'})
        for entry in response.data:
            self.assertLessEqual(entry['date'], '2026-03-16')

    def test_no_entries_in_a_month_before_the_batch_started(self):
        response = self.client.get('/api/protocols/schedule/', {'month': '2026-02'})
        self.assertEqual(response.data, [])

    def test_until_end_line_keeps_appearing_every_day_after_its_start(self):
        ProtocolTemplate.objects.create(
            house=self.house, category=self.category,
            from_value=20, from_unit='DAY', until_end=True, what='Nettoyage quotidien',
        )
        response = self.client.get('/api/protocols/schedule/', {'month': '2026-03'})
        cleaning_dates = sorted(e['date'] for e in response.data if e['what'] == 'Nettoyage quotidien')
        # day_of_cycle 20 = start_date (2026-03-01) + 20 = 2026-03-21, no upper bound — every
        # remaining day of the visible month.
        expected = [f'2026-03-{day:02d}' for day in range(21, 32)]
        self.assertEqual(cleaning_dates, expected)

    def add_second_house(self):
        house = PoultryHouse.objects.create(house_code='H-CAL-2', farm=self.farm, name='Salle 2', max_capacity=1000)
        vaccine = ProtocolCategory.objects.create(house=house, label='Vaccination', icon='Syringe')
        line = ProtocolTemplate.objects.create(
            house=house, category=vaccine, from_value=1, from_unit='DAY', to_value=3, to_unit='DAY',
            until_end=False, what='Vaccin',
        )
        ProtocolTimeSlot.objects.create(protocol_line=line, start_time='06:30', end_time='07:30')
        ProtocolTimeSlot.objects.create(protocol_line=line, start_time='17:00', end_time='18:00')
        PoultryBatch.objects.create(
            batch_code='BATCH-CAL-2', house=house, production_type=ProductionType.BROILER,
            initial_count=500, start_date=date(2026, 3, 1),
        )

    def test_summary_counts_each_day_and_previews_three_from_the_same_entries(self):
        """2026-09-25: the flat month was 4.4 MB at 50 houses for a grid showing 3 pills a day."""
        self.add_second_house()
        full = self.client.get('/api/protocols/schedule/', {'month': '2026-03'}).data
        summary = self.client.get('/api/protocols/schedule/', {'month': '2026-03', 'view': 'summary'}).data

        per_day = {}
        for entry in full:
            per_day.setdefault(entry['date'], []).append(entry)
        self.assertEqual({d: v['count'] for d, v in summary['days'].items()}, {d: len(v) for d, v in per_day.items()})
        self.assertEqual(summary['days']['2026-03-02']['count'], 3)  # 1 feed + 2 vaccine slots
        self.assertEqual(
            [p['id'] for p in summary['days']['2026-03-02']['preview']],
            [e['id'] for e in per_day['2026-03-02'][:3]],
        )
        self.assertEqual(summary['categories'], list(dict.fromkeys(e['category'] for e in full)))

    def test_one_day_is_exactly_that_days_part_of_the_month(self):
        self.add_second_house()
        full = self.client.get('/api/protocols/schedule/', {'month': '2026-03'}).data
        day = self.client.get('/api/protocols/schedule/', {'date': '2026-03-03'}).data
        self.assertEqual(day, [e for e in full if e['date'] == '2026-03-03'])
        self.assertEqual(self.client.get('/api/protocols/schedule/', {'date': '03/03/2026'}).status_code, 400)

    def test_queries_do_not_grow_with_the_number_of_houses(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        with CaptureQueriesContext(connection) as one:
            self.client.get('/api/protocols/schedule/', {'month': '2026-03', 'view': 'summary'})
        self.add_second_house()
        with CaptureQueriesContext(connection) as two:
            self.client.get('/api/protocols/schedule/', {'month': '2026-03', 'view': 'summary'})
        self.assertEqual(len(two.captured_queries), len(one.captured_queries))


class OnboardingTimeSlotTests(APITestCase):
    """POST /api/protocols/onboarding/ also writes `ProtocolTimeSlot` rows (Bug 1 fix,
    2026-08-27, docs/deviations.md) — the "Horaires" section must work from the onboarding
    wizard's protocol step, not just the "Modifier" edit modal/page (same shared
    HouseProtocolForm component, same OnboardingView/HouseProtocolView write path)."""

    def setUp(self):
        self.farm = Farm.objects.create(name='Ferme Onboarding Horaires Test')
        self.admin = User.objects.create_user(
            email='admin@onboarding-slot-test.local', password='x', name='Admin', role=UserRole.ADMIN, farm=self.farm,
        )
        create_role_profile(self.admin)
        self.client.force_authenticate(user=self.admin)

    def test_onboarding_creates_time_slots_for_a_protocol_line(self):
        payload = {
            'house': {'name': 'Bâtiment A', 'maxCapacity': 500},
            'protocolLines': [{
                'categoryIndex': 0, 'from_value': 1, 'from_unit': 'DAY',
                'to_value': None, 'to_unit': 'DAY', 'until_end': True, 'what': 'Nourrissage', 'details': '',
                'time_slots': [{'start_time': '07:00', 'end_time': '09:00'}, {'start_time': '18:00', 'end_time': '20:00'}],
            }],
        }
        response = self.client.post('/api/protocols/onboarding/', payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        line = ProtocolTemplate.objects.get(house__house_code=response.data['house']['houseCode'])
        self.assertEqual(ProtocolTimeSlot.objects.filter(protocol_line=line).count(), 2)
        self.assertEqual(len(response.data['protocolLines'][0]['time_slots']), 2)


class OnboardingBatchNameRequiredTests(APITestCase):
    """Part A: a batch may not be created with a blank / whitespace-only name."""

    def setUp(self):
        self.farm = Farm.objects.create(name='Ferme Batch Name Test')
        self.admin = User.objects.create_user(
            email='admin@batch-name-test.local', password='x', name='Admin', role=UserRole.ADMIN, farm=self.farm,
        )
        create_role_profile(self.admin)
        self.client.force_authenticate(user=self.admin)

    def _payload(self, batch_name):
        return {
            'house': {'name': 'Bâtiment A', 'maxCapacity': 500},
            'batch': {'name': batch_name, 'initialCount': 500, 'productionType': 'BROILER'},
            'protocolLines': [{
                'categoryIndex': 0, 'from_value': 1, 'from_unit': 'DAY', 'to_value': 15, 'to_unit': 'DAY',
                'until_end': False, 'what': 'Nourrissage', 'details': '',
            }],
        }

    def test_blank_batch_name_is_rejected_with_a_field_error(self):
        for bad in ('', '   ', '\t\n'):
            response = self.client.post('/api/protocols/onboarding/', self._payload(bad), format='json')
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
            self.assertIn('name', response.data.get('batch', {}))
            self.assertFalse(PoultryBatch.objects.exists())
            self.assertFalse(PoultryHouse.objects.exists())  # nothing half-created

    def test_valid_batch_name_is_accepted_and_stored_trimmed(self):
        response = self.client.post('/api/protocols/onboarding/', self._payload('  Bande printemps  '), format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(PoultryBatch.objects.get().name, 'Bande printemps')


class ScheduleViewTimeSlotTests(APITestCase):
    """GET /api/protocols/schedule/ showing `ProtocolTimeSlot` windows (calendar time-slot
    display fix, 2026-08-27, docs/deviations.md) — a line with time slots must generate one
    calendar entry per slot, each carrying its own window; a line with none is unaffected."""

    def setUp(self):
        self.farm = Farm.objects.create(name='Ferme Calendrier Horaires Test')
        self.user = User.objects.create_user(
            email='admin@calendar-slot-test.local', password='x', name='Admin', role=UserRole.ADMIN, farm=self.farm,
        )
        create_role_profile(self.user)
        self.client.force_authenticate(user=self.user)
        self.house = PoultryHouse.objects.create(house_code='H-CALSLOT-1', farm=self.farm, name='Salle 1', max_capacity=1000)
        self.category = ProtocolCategory.objects.create(house=self.house, label='Alimentation', icon='Soup')
        self.batch = PoultryBatch.objects.create(
            batch_code='BATCH-CALSLOT-1', house=self.house, production_type=ProductionType.BROILER,
            initial_count=500, start_date=date(2026, 3, 1),
        )

    def test_line_with_two_slots_produces_two_entries_with_their_own_times(self):
        line = ProtocolTemplate.objects.create(
            house=self.house, category=self.category, from_value=1, until_end=True, what='Nourrissage',
        )
        ProtocolTimeSlot.objects.create(protocol_line=line, start_time='07:00', end_time='09:00')
        ProtocolTimeSlot.objects.create(protocol_line=line, start_time='18:00', end_time='20:00')

        response = self.client.get('/api/protocols/schedule/', {'month': '2026-03'})
        entries = [e for e in response.data if e['date'] == '2026-03-02']  # day_of_cycle=1
        self.assertEqual(len(entries), 2)
        windows = sorted((e['startTime'], e['endTime']) for e in entries)
        self.assertEqual(windows, [('07h00', '09h00'), ('18h00', '20h00')])
        self.assertEqual(len({e['id'] for e in entries}), 2)  # distinct ids, not deduped/collided

    def test_line_with_no_slots_produces_one_entry_with_null_times(self):
        ProtocolTemplate.objects.create(
            house=self.house, category=self.category, from_value=1, to_value=5, what='Nettoyage',
        )
        response = self.client.get('/api/protocols/schedule/', {'month': '2026-03'})
        entries = [e for e in response.data if e['date'] == '2026-03-02']
        self.assertEqual(len(entries), 1)
        self.assertIsNone(entries[0]['startTime'])
        self.assertIsNone(entries[0]['endTime'])


class ProtocolXlsxImportTests(APITestCase):
    """Parser + endpoints for the "Importer un fichier Excel" feature (docs/excel-import.md)."""

    def setUp(self):
        self.farm = Farm.objects.create(name='Ferme Import')
        self.admin = User.objects.create_user(
            email='admin@import-test.local', password='x', name='Admin', role=UserRole.ADMIN, farm=self.farm,
        )
        create_role_profile(self.admin)
        self.client.force_authenticate(user=self.admin)

    @staticmethod
    def _xlsx(rows, headers=None):
        from io import BytesIO

        from openpyxl import Workbook
        wb = Workbook()
        ws = wb.active
        ws.append(headers or ['Catégorie', 'De', 'À', 'Action', 'Détails', 'Consommation', 'Quantité/jour'])
        for r in rows:
            ws.append(r)
        buf = BytesIO()
        wb.save(buf)
        buf.seek(0)
        buf.name = 'import.xlsx'
        return buf

    def _upload(self, buf):
        return self.client.post('/api/protocols/import-xlsx/', {'file': buf}, format='multipart')

    def test_template_download_is_a_valid_xlsx_and_needs_no_auth(self):
        self.client.force_authenticate(user=None)
        resp = self.client.get('/api/protocols/import-template.xlsx')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('spreadsheetml', resp['Content-Type'])
        self.assertIn('attachment', resp['Content-Disposition'])
        from io import BytesIO

        from apps.protocols.xlsx_import import parse_protocol_rows
        parsed = parse_protocol_rows(BytesIO(resp.content))
        self.assertEqual(parsed['imported'], 3)  # the template's example rows round-trip

    def test_valid_rows_parse_with_consumption_and_until_end(self):
        buf = self._xlsx([
            ['Alimentation', 1, 15, 'Aliment démarrage', '3000 kcal', 'Provende', 40],
            ['Nettoyage', 1, '', 'Ajout de litière', '', '', ''],  # blank À -> until end of cycle
        ])
        resp = self._upload(buf)
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(resp.data['imported'], 2)
        self.assertEqual(resp.data['skipped'], [])
        r0, r1 = resp.data['rows']
        self.assertEqual((r0['category'], r0['fromValue'], r0['toValue'], r0['what']),
                         ('Alimentation', 1.0, 15.0, 'Aliment démarrage'))
        self.assertEqual((r0['consumption'], r0['quantityPerDay']), ('Provende', 40.0))
        self.assertTrue(r1['untilEnd'])
        self.assertIsNone(r1['toValue'])

    def test_bad_rows_are_skipped_with_specific_reasons_not_a_whole_import_failure(self):
        buf = self._xlsx([
            ['Alimentation', 1, 15, 'OK row', '', '', ''],   # line 2 — fine
            ['Alimentation', 5, '', '', '', '', ''],          # line 3 — action manquante
            ['Alimentation', '', 10, 'No De', '', '', ''],    # line 4 — De manquant
            ['Alimentation', 20, 10, 'A before De', '', '', ''],  # line 5 — À < De
            ['', 1, 2, 'No category', '', '', ''],            # line 6 — catégorie manquante
            ['', '', '', '', '', '', ''],                     # line 7 — fully empty, ignored silently
        ])
        resp = self._upload(buf)
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(resp.data['imported'], 1)
        reasons = {s['line']: s['reason'] for s in resp.data['skipped']}
        self.assertEqual(set(reasons), {3, 4, 5, 6})
        self.assertIn('action', reasons[3].lower())
        self.assertIn('de', reasons[4].lower())
        self.assertIn('inférieur', reasons[5].lower())
        self.assertIn('catégorie', reasons[6].lower())

    def test_quantity_without_consumption_is_dropped_but_row_still_imports(self):
        buf = self._xlsx([['Alimentation', 1, 5, 'Action', '', '', 40]])
        resp = self._upload(buf)
        self.assertEqual(resp.data['imported'], 1)
        self.assertIsNone(resp.data['rows'][0]['consumption'])
        self.assertIsNone(resp.data['rows'][0]['quantityPerDay'])

    def test_headers_matched_by_name_not_position(self):
        buf = self._xlsx(
            [['Aliment démarrage', 'Alimentation', 1, 15]],
            headers=['Action', 'Catégorie', 'De', 'À'],
        )
        resp = self._upload(buf)
        self.assertEqual(resp.data['imported'], 1)
        self.assertEqual(resp.data['rows'][0]['what'], 'Aliment démarrage')
        self.assertEqual(resp.data['rows'][0]['category'], 'Alimentation')

    def test_missing_required_header_column_is_a_clear_400(self):
        buf = self._xlsx([['Alimentation', 1, 'x']], headers=['Catégorie', 'De', 'Détails'])
        resp = self._upload(buf)
        self.assertEqual(resp.status_code, 400)
        self.assertIn('Action', resp.data['detail'])

    def test_non_xlsx_upload_is_rejected(self):
        from io import BytesIO
        f = BytesIO(b'category,de\n')
        f.name = 'protocol.csv'
        resp = self.client.post('/api/protocols/import-xlsx/', {'file': f}, format='multipart')
        self.assertEqual(resp.status_code, 400)

    def test_import_requires_authentication(self):
        self.client.force_authenticate(user=None)
        resp = self._upload(self._xlsx([['Alimentation', 1, 2, 'A', '', '', '']]))
        self.assertEqual(resp.status_code, 401)

    # --- Unité + Créneaux columns (2026-09-02) ---
    _H9 = ['Catégorie', 'De', 'À', 'Action', 'Détails', 'Consommation', 'Unité', 'Quantité/jour', 'Créneaux']

    def test_two_time_windows_in_one_cell_parse_to_two_slots(self):
        buf = self._xlsx([['Alimentation', 1, 15, 'Nourrissage', '', 'Provende', 'kg', 40, '06:30-07:30;18:30-19:30']],
                         headers=self._H9)
        resp = self._upload(buf)
        self.assertEqual(resp.status_code, 200, resp.data)
        row = resp.data['rows'][0]
        self.assertEqual(row['unit'], 'kg')
        self.assertEqual(row['timeSlots'], [
            {'startTime': '06:30', 'endTime': '07:30'},
            {'startTime': '18:30', 'endTime': '19:30'},
        ])
        self.assertEqual(resp.data['warnings'], [])

    def test_malformed_creneau_segment_is_dropped_row_still_imports_with_a_warning(self):
        buf = self._xlsx([
            ['Alimentation', 1, 5, 'Ok row', '', '', '', '', '06h30-07h30;18:00-19:00'],  # 1st seg malformed
            ['Alimentation', 6, 10, 'End before start', '', '', '', '', '19:00-08:00'],    # end <= start
        ], headers=self._H9)
        resp = self._upload(buf)
        self.assertEqual(resp.data['imported'], 2)          # both rows still imported
        self.assertEqual(resp.data['skipped'], [])
        # line 2: only the good window survives
        self.assertEqual(resp.data['rows'][0]['timeSlots'], [{'startTime': '18:00', 'endTime': '19:00'}])
        # line 3: no slot at all
        self.assertEqual(resp.data['rows'][1]['timeSlots'], [])
        warns = {w['line']: w['reason'] for w in resp.data['warnings']}
        self.assertIn(2, warns)
        self.assertIn('06h30-07h30', warns[2])
        self.assertIn('mal formé', warns[2])
        self.assertIn(3, warns)
        self.assertIn('19:00-08:00', warns[3])

    def test_unit_is_returned_per_row_for_new_resource_creation(self):
        buf = self._xlsx([['Vaccination', 1, 1, 'Vaccin', '', 'Sérum X', 'flacon', 2, '']], headers=self._H9)
        resp = self._upload(buf)
        self.assertEqual(resp.data['rows'][0]['unit'], 'flacon')
        self.assertEqual(resp.data['rows'][0]['consumption'], 'Sérum X')
        self.assertEqual(resp.data['rows'][0]['quantityPerDay'], 2.0)


class ColumnMatchingUnitTests(APITestCase):
    """The matcher itself — pure functions, no file, no database (apps/core/column_matching.py)."""

    def test_normalize_folds_accents_case_punctuation_and_spacing(self):
        from apps.core.column_matching import normalize
        self.assertEqual(normalize('  Qté / Jour '), 'qte jour')
        self.assertEqual(normalize("Seuil d'alerte"), 'seuil d alerte')
        self.assertEqual(normalize('CATÉGORIE'), 'categorie')
        self.assertEqual(normalize(None), '')

    def test_exact_match_wins_and_reports_full_confidence(self):
        from apps.core.column_matching import match_columns
        from apps.protocols.import_columns import COLUMNS
        report = match_columns(['Catégorie', 'De', 'Action'], COLUMNS)
        by_key = {m.key: m for m in report.matches}
        self.assertEqual(by_key['category'].method, 'exact')
        self.assertEqual(by_key['category'].confidence, 1.0)
        self.assertEqual(report.index['category'], 0)

    def test_accent_and_case_variants_are_exact_not_fuzzy(self):
        from apps.core.column_matching import match_columns
        from apps.protocols.import_columns import COLUMNS
        report = match_columns(['  CATEGORIE  ', 'de', 'ACTION'], COLUMNS)
        self.assertEqual({m.key: m.method for m in report.matches}['category'], 'exact')

    def test_listed_synonyms_resolve_to_the_canonical_column(self):
        from apps.core.column_matching import match_columns
        from apps.protocols.import_columns import COLUMNS
        report = match_columns(['Rubrique', 'Jour début', 'Jour fin', 'Tâche', 'Horaires'], COLUMNS)
        by_key = {m.key: m for m in report.matches}
        self.assertEqual(by_key['category'].header, 'Rubrique')
        self.assertEqual(by_key['from_value'].header, 'Jour début')
        self.assertEqual(by_key['to_value'].header, 'Jour fin')
        self.assertEqual(by_key['what'].header, 'Tâche')
        self.assertEqual(by_key['time_slots'].header, 'Horaires')

    def test_a_typo_is_recovered_by_edit_distance_and_flagged_as_approximate(self):
        from apps.core.column_matching import match_columns
        from apps.protocols.import_columns import COLUMNS
        report = match_columns(['Catgorie', 'De', 'Acton', 'Consomation'], COLUMNS)
        by_key = {m.key: m for m in report.matches}
        self.assertEqual(by_key['category'].header, 'Catgorie')
        self.assertEqual(by_key['category'].method, 'fuzzy')
        self.assertLess(by_key['category'].confidence, 1.0)
        self.assertEqual(by_key['what'].header, 'Acton')
        self.assertEqual(by_key['consumption'].header, 'Consomation')

    def test_an_unrelated_column_is_left_unknown_rather_than_force_matched(self):
        from apps.core.column_matching import match_columns
        from apps.protocols.import_columns import COLUMNS
        report = match_columns(['Catégorie', 'De', 'Action', 'Numéro de facture'], COLUMNS)
        self.assertIn('Numéro de facture', report.unknown_headers)
        self.assertNotIn('Numéro de facture', [m.header for m in report.matches])

    def test_one_file_column_is_never_claimed_by_two_canonical_columns(self):
        from apps.core.column_matching import match_columns
        from apps.protocols.import_columns import COLUMNS
        report = match_columns(['Catégorie', 'De', 'À', 'Action'], COLUMNS)
        used = [m.index for m in report.matches if m.index is not None]
        self.assertEqual(len(used), len(set(used)))

    def test_absent_optional_column_reports_its_existing_default(self):
        from apps.core.column_matching import match_columns
        from apps.protocols.import_columns import COLUMNS
        report = match_columns(['Catégorie', 'De', 'Action'], COLUMNS)
        by_key = {m.key: m for m in report.matches}
        self.assertEqual(by_key['unit'].method, 'default')
        self.assertIn('kg', by_key['unit'].note)
        self.assertEqual(by_key['details'].method, 'default')

    def test_absent_required_column_is_unresolved_and_blocks(self):
        from apps.core.column_matching import match_columns
        from apps.protocols.import_columns import COLUMNS
        report = match_columns(['De', 'Action'], COLUMNS)
        self.assertEqual([m.label for m in report.unresolved], ['Catégorie'])

    def test_short_headers_must_match_exactly_no_fuzzy_guessing(self):
        # "De"/"À" are too short for edit distance to mean anything — a 2-letter header must
        # not be pulled onto some other column by a single edit.
        from apps.core.column_matching import match_columns
        from apps.protocols.import_columns import COLUMNS
        report = match_columns(['Catégorie', 'De', 'Action', 'Xy'], COLUMNS)
        self.assertIn('Xy', report.unknown_headers)

    def test_matching_is_deterministic_same_input_same_output(self):
        from apps.core.column_matching import match_columns
        from apps.protocols.import_columns import COLUMNS
        headers = ['Rubrique', 'Jour début', 'Jour fin', 'Tâche', 'Conso', 'Qté/jour']
        first = match_columns(headers, COLUMNS).as_dict()
        for _ in range(5):
            self.assertEqual(match_columns(headers, COLUMNS).as_dict(), first)


class ProtocolImportRemappingTests(ProtocolXlsxImportTests):
    """End-to-end: a file whose headers don't match the template still imports (Prompt 2)."""

    def test_file_with_completely_different_wording_imports_correctly(self):
        buf = self._xlsx(
            [['Alimentation', 1, 15, 'Aliment démarrage', '3000 kcal', 'Provende', 40]],
            headers=['Rubrique', 'Jour début', 'Jour fin', 'Tâche', 'Commentaire', 'Ressource', 'Ration journalière'],
        )
        resp = self._upload(buf)
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(resp.data['imported'], 1)
        row = resp.data['rows'][0]
        self.assertEqual(row['category'], 'Alimentation')
        self.assertEqual(row['fromValue'], 1.0)
        self.assertEqual(row['toValue'], 15.0)
        self.assertEqual(row['what'], 'Aliment démarrage')
        self.assertEqual(row['details'], '3000 kcal')
        self.assertEqual(row['consumption'], 'Provende')
        self.assertEqual(row['quantityPerDay'], 40.0)

    def test_response_carries_the_mapping_report_for_the_preview_screen(self):
        buf = self._xlsx(
            [['Alimentation', 1, 15, 'Aliment démarrage', '', 'Provende', 40]],
            headers=['Rubrique', 'Jour début', 'Jour fin', 'Tâche', 'Commentaire', 'Ressource', 'Ration journalière'],
        )
        resp = self._upload(buf)
        by_key = {m['key']: m for m in resp.data['columns']['matches']}
        self.assertEqual(by_key['category']['header'], 'Rubrique')
        self.assertEqual(by_key['category']['method'], 'exact')  # 'rubrique' is a listed synonym
        self.assertEqual(by_key['unit']['method'], 'default')    # absent from this file
        self.assertEqual(resp.data['columns']['unresolved'], [])

    def test_unmatched_required_column_still_returns_a_clear_400(self):
        buf = self._xlsx(
            [['x', 1, 'Action']],
            headers=['Numéro de facture', 'Montant', 'Référence'],
        )
        resp = self._upload(buf)
        self.assertEqual(resp.status_code, 400)
        self.assertIn('Catégorie', str(resp.data))
