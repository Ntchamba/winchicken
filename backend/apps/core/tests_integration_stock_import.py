"""Integration chain 2 — Excel import -> column remapping -> preview (dry run) -> confirmation ->
database state. Real .xlsx files built with openpyxl, posted to the API, checked in the database.

The preview must promise exactly what the confirmation then does, and a malformed file must
change nothing it was not asked to change.
"""
import datetime as dt
import io
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from openpyxl import Workbook
from rest_framework.test import APITestCase

from apps.core.models import Farm, User, UserRole, create_role_profile
from apps.stock.calculations import current_quantity
from apps.stock.models import MovementType, StockCategory, StockItem, StockMovement, Supplier


def xlsx(header, *rows, name='stock.xlsx'):
    wb = Workbook()
    ws = wb.active
    ws.append(list(header))
    for row in rows:
        ws.append(list(row))
    buf = io.BytesIO()
    wb.save(buf)
    return SimpleUploadedFile(name, buf.getvalue(), content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


class StockImportChainTests(APITestCase):
    def setUp(self):
        self.farm = Farm.objects.create(name='Ferme Import')
        admin = User.objects.create_user(email='admin@import.local', password='x', name='A', role=UserRole.ADMIN, farm=self.farm)
        create_role_profile(admin)
        self.client.force_authenticate(user=admin)
        feed = StockCategory.objects.get(farm=self.farm, kind='FEED')
        self.provende = StockItem.objects.create(
            item_code=f'FEE-{self.farm.id}-001', farm=self.farm, category=feed, name='Provende', unit='kg',
            alert_threshold=50, unit_price=Decimal('450'),
        )
        StockMovement.objects.create(item=self.provende, movement_type=MovementType.IN, quantity=300, movement_date=dt.date(2026, 9, 1))
        self.url = f'/api/farms/{self.farm.id}/stock-items/import-xlsx/'

    def post(self, upload, dry_run=False):
        data = {'file': upload}
        if dry_run:
            data['dry_run'] = '1'
        return self.client.post(self.url, data, format='multipart')

    def snapshot(self):
        return (
            sorted(StockItem.objects.filter(farm=self.farm).values_list('name', 'unit', 'alert_threshold', 'unit_price', 'category__label', 'supplier__name')),
            StockCategory.objects.filter(farm=self.farm).count(),
            Supplier.objects.filter(farm=self.farm).count(),
            StockMovement.objects.count(),
        )

    # A file from the farm's own spreadsheet: other header words, other order, an extra column.
    REMAPPED = ('Fournisseur', 'Désignation', 'Famille', 'PU', 'Unité de mesure', 'Seuil mini', 'Observations')

    def remapped_file(self):
        return xlsx(
            self.REMAPPED,
            ('Agrivet SARL', 'Provende', 'Aliment', 475, 'kg', 80, 'hausse de prix'),
            ('Pharmavet', 'Vaccin Newcastle', 'Vétérinaire', 3500, 'flacon', 5, ''),
            ('', 'Copeaux', 'Litière', 1500, 'sac', 10, 'nouvelle catégorie'),
        )

    def test_preview_maps_the_columns_and_writes_nothing(self):
        before = self.snapshot()
        response = self.post(self.remapped_file(), dry_run=True)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(response.data['dryRun'])
        self.assertEqual((response.data['updated'], response.data['created'], response.data['skipped']), (1, 2, []))
        mapped = {m['key']: m['header'] for m in response.data['columns']['matches']}
        self.assertEqual(mapped, {
            'name': 'Désignation', 'category': 'Famille', 'detail': '', 'unit': 'Unité de mesure',
            'alert_threshold': 'Seuil mini', 'unit_price': 'PU', 'supplier': 'Fournisseur',
        })
        self.assertEqual(response.data['columns']['unknownHeaders'], ['Observations'])
        self.assertEqual(self.snapshot(), before)  # no item, category or supplier leaked out of the rollback

    def test_confirmation_does_exactly_what_the_preview_said(self):
        preview = self.post(self.remapped_file(), dry_run=True).data
        result = self.post(self.remapped_file()).data
        self.assertEqual({k: result[k] for k in ('updated', 'created', 'skipped')}, {k: preview[k] for k in ('updated', 'created', 'skipped')})

        provende = StockItem.objects.get(pk=self.provende.pk)
        self.assertEqual((provende.unit_price, provende.alert_threshold, provende.supplier.name), (Decimal('475'), 80, 'Agrivet SARL'))
        self.assertEqual(current_quantity(provende), 300)  # parameters only: the level is untouched
        self.assertEqual(StockMovement.objects.count(), 1)  # and no movement was written
        vaccine = StockItem.objects.get(farm=self.farm, name='Vaccin Newcastle')
        self.assertEqual((vaccine.category.kind, vaccine.unit, current_quantity(vaccine)), ('VETERINARY', 'flacon', 0))
        copeaux = StockItem.objects.get(farm=self.farm, name='Copeaux')
        self.assertEqual((copeaux.category.label, copeaux.supplier), ('Litière', None))

    def test_importing_the_same_file_twice_changes_nothing_the_second_time(self):
        self.post(self.remapped_file())
        after_first = self.snapshot()
        result = self.post(self.remapped_file()).data
        self.assertEqual((result['updated'], result['created']), (3, 0))
        self.assertEqual(self.snapshot(), after_first)

    # --- malformed files ---------------------------------------------------------------------

    def test_a_file_that_is_not_xlsx_is_refused(self):
        response = self.post(SimpleUploadedFile('stock.csv', b'Article;Categorie\n'))
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data['detail'], 'Importez un fichier .xlsx (Excel).')

    def test_a_corrupt_xlsx_is_refused_in_french(self):
        response = self.post(SimpleUploadedFile('stock.xlsx', b'not a zip at all'))
        self.assertEqual(response.status_code, 400)
        self.assertIn('Fichier illisible', response.data['detail'])

    def test_a_missing_required_column_is_pointed_at_in_the_preview_and_refused_on_confirm(self):
        upload = lambda: xlsx(('Article', 'Unité'), ('Provende', 'kg'))  # noqa: E731
        preview = self.post(upload(), dry_run=True).data
        self.assertEqual(preview['columns']['unresolved'], ['Catégorie'])
        before = self.snapshot()
        response = self.post(upload())
        self.assertEqual(response.status_code, 400)
        self.assertIn('« Catégorie »', response.data['detail'])
        self.assertEqual(self.snapshot(), before)

    def test_rows_missing_a_name_or_a_category_are_skipped_with_their_line(self):
        result = self.post(xlsx(
            ('Article', 'Catégorie', 'Unité'),
            ('', 'Aliment', 'kg'), ('Maïs', '', 'kg'), (None, None, None), ('Son de blé', 'Aliment', 'kg'),
        )).data
        self.assertEqual(result['created'], 1)
        self.assertEqual(result['skipped'], [
            {'line': 2, 'reason': "nom de l'article manquant"}, {'line': 3, 'reason': 'catégorie manquante'},
        ])

    def test_a_failed_row_does_not_poison_the_next_row_of_the_same_new_category(self):
        # Row 2 creates the category "Litière" inside its savepoint and then fails (no unit), so
        # the savepoint takes the category away. Row 3 must still import into "Litière".
        result = self.post(xlsx(
            ('Article', 'Catégorie', 'Unité', 'Fournisseur'),
            ('Copeaux', 'Litière', '', 'Scierie Nord'), ('Paille', 'Litière', 'botte', 'Scierie Nord'),
        )).data
        self.assertEqual(result['created'], 1, result)
        self.assertEqual([s['line'] for s in result['skipped']], [2])
        paille = StockItem.objects.get(farm=self.farm, name='Paille')
        self.assertEqual((paille.category.label, paille.supplier.name), ('Litière', 'Scierie Nord'))

    def test_an_unreadable_price_is_reported_not_turned_into_zero(self):
        result = self.post(xlsx(('Article', 'Catégorie', 'Unité', 'Prix unitaire'), ('Provende', 'Aliment', 'kg', 'environ 500'))).data
        self.assertEqual(result['updated'], 0, result)
        [skip] = result['skipped']
        self.assertEqual(skip['line'], 2)
        self.assertIn('environ 500', skip['reason'])
        self.assertEqual(StockItem.objects.get(pk=self.provende.pk).unit_price, Decimal('450'))

    def test_a_price_typed_with_french_thousands_separators_is_read(self):
        # "12 000" (space, no-break space or narrow no-break space) is how FCFA amounts are typed.
        result = self.post(xlsx(
            ('Article', 'Catégorie', 'Unité', 'Prix unitaire'),
            ('Abreuvoir', 'Équipement', 'unité', '12 000'), ('Mangeoire', 'Équipement', 'unité', '8 500'),
            ('Radiant', 'Équipement', 'unité', '1 250,50'),
        )).data
        self.assertEqual((result['created'], result['skipped']), (3, []))
        prices = dict(StockItem.objects.filter(farm=self.farm, name__in=['Abreuvoir', 'Mangeoire', 'Radiant']).values_list('name', 'unit_price'))
        self.assertEqual(prices, {'Abreuvoir': Decimal('12000'), 'Mangeoire': Decimal('8500'), 'Radiant': Decimal('1250.50')})

    def test_without_a_unit_column_an_existing_items_unit_is_kept(self):
        # The column's own preview note promises this: "l'unité d'un article existant n'est pas modifiée".
        result = self.post(xlsx(('Article', 'Catégorie', "Seuil d'alerte"), ('Provende', 'Aliment', 120))).data
        self.assertEqual((result['updated'], result['skipped']), (1, []), result)
        provende = StockItem.objects.get(pk=self.provende.pk)
        self.assertEqual((provende.unit, provende.alert_threshold), ('kg', 120))

    def test_without_a_supplier_column_an_existing_items_supplier_is_kept(self):
        # The column's own preview note: "le fournisseur déjà enregistré sur un article existant est conservé".
        self.provende.supplier = Supplier.objects.create(farm=self.farm, name='Agrivet SARL')
        self.provende.save()
        result = self.post(xlsx(('Article', 'Catégorie', 'Unité'), ('Provende', 'Aliment', 'kg'))).data
        self.assertEqual((result['updated'], result['skipped']), (1, []), result)
        self.assertEqual(StockItem.objects.get(pk=self.provende.pk).supplier.name, 'Agrivet SARL')

    def test_a_new_item_without_a_unit_is_skipped_with_a_clear_reason(self):
        result = self.post(xlsx(('Article', 'Catégorie'), ('Maïs', 'Aliment'))).data
        self.assertEqual(result['skipped'], [{'line': 2, 'reason': 'unité manquante'}])
