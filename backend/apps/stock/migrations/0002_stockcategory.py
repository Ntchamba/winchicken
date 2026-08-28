import django.db.models.deletion
from django.db import migrations, models

DEFAULTS = [
    ('Aliment', 'Wheat', 'FEED'),
    ('Vétérinaire', 'Stethoscope', 'VETERINARY'),
    ('Équipement', 'Wrench', 'EQUIPMENT'),
    ('Litière', 'Layers', 'BEDDING'),
]


def forwards(apps, schema_editor):
    Farm = apps.get_model('core', 'Farm')
    StockCategory = apps.get_model('stock', 'StockCategory')
    StockItem = apps.get_model('stock', 'StockItem')

    for farm in Farm.objects.all():
        by_kind = {}
        for i, (label, icon, kind) in enumerate(DEFAULTS):
            cat, _ = StockCategory.objects.get_or_create(
                farm=farm, kind=kind, defaults={'label': label, 'icon': icon, 'sort_order': i}
            )
            by_kind[kind] = cat
        for item in StockItem.objects.filter(farm=farm):
            item.category_new = by_kind.get(item.category) or by_kind['FEED']
            item.save(update_fields=['category_new'])


def backwards(apps, schema_editor):
    StockItem = apps.get_model('stock', 'StockItem')
    for item in StockItem.objects.select_related('category_new').all():
        item.category = item.category_new.kind if item.category_new else 'FEED'
        item.save(update_fields=['category'])


class Migration(migrations.Migration):

    dependencies = [
        ('stock', '0001_initial'),
        ('core', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='StockCategory',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('label', models.CharField(max_length=100)),
                ('icon', models.CharField(help_text='A lucide-react icon component name (e.g. "Wheat").', max_length=50)),
                ('sort_order', models.PositiveIntegerField(default=0)),
                ('kind', models.CharField(
                    choices=[('FEED', 'Feed'), ('VETERINARY', 'Veterinary'), ('EQUIPMENT', 'Equipment'),
                             ('BEDDING', 'Bedding'), ('CUSTOM', 'Custom')],
                    default='CUSTOM',
                    help_text='Discriminator for the four seeded defaults; user-added categories are CUSTOM.',
                    max_length=16,
                )),
                ('farm', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='stock_categories', to='core.farm')),
            ],
            options={'verbose_name_plural': 'stock categories', 'ordering': ['sort_order', 'id']},
        ),
        migrations.AddField(
            model_name='stockitem',
            name='category_new',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='items', to='stock.stockcategory'),
        ),
        migrations.RunPython(forwards, backwards),
        migrations.RemoveField(model_name='stockitem', name='category'),
        migrations.RenameField(model_name='stockitem', old_name='category_new', new_name='category'),
        migrations.AlterField(
            model_name='stockitem',
            name='category',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='items', to='stock.stockcategory'),
        ),
        migrations.AlterModelOptions(name='stockitem', options={'ordering': ['category__sort_order', 'name']}),
    ]
