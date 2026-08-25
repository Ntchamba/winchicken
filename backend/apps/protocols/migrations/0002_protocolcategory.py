import django.db.models.deletion
from django.db import migrations, models

DEFAULT_CATEGORIES = [
    {'label': 'Alimentation', 'icon': 'Soup'},
    {'label': 'Température', 'icon': 'Thermometer'},
    {'label': 'Santé et soins', 'icon': 'Stethoscope'},
    {'label': 'Vaccination', 'icon': 'Syringe'},
    {'label': 'Nettoyage', 'icon': 'SprayCan'},
]

# Old TextChoices value -> new default category label, for converting existing
# ProtocolTemplate rows from the fixed enum to the new FK.
OLD_VALUE_TO_LABEL = {
    'FEEDING': 'Alimentation',
    'TEMPERATURE': 'Température',
    'HEALTH': 'Santé et soins',
    'VACCINATION': 'Vaccination',
    'CLEANING': 'Nettoyage',
}


def seed_categories_and_migrate_lines(apps, schema_editor):
    PoultryHouse = apps.get_model('houses', 'PoultryHouse')
    ProtocolCategory = apps.get_model('protocols', 'ProtocolCategory')
    ProtocolTemplate = apps.get_model('protocols', 'ProtocolTemplate')

    for house in PoultryHouse.objects.all():
        label_to_category = {}
        for i, cat in enumerate(DEFAULT_CATEGORIES):
            category = ProtocolCategory.objects.create(
                house=house, label=cat['label'], icon=cat['icon'], sort_order=i,
            )
            label_to_category[cat['label']] = category

        for line in ProtocolTemplate.objects.filter(house=house):
            label = OLD_VALUE_TO_LABEL.get(line.category)
            line.category_new = label_to_category.get(label)
            line.save(update_fields=['category_new'])


def noop_reverse(apps, schema_editor):
    # Not reversible in any meaningful way (custom categories added after this migration
    # would have no enum value to fall back to) — forward-only, matches this being a
    # pre-production dev-stage project (see docs/deviations.md).
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('houses', '0001_initial'),
        ('protocols', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='ProtocolCategory',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('label', models.CharField(max_length=100)),
                ('icon', models.CharField(help_text='A lucide-react icon component name (e.g. "Soup").', max_length=50)),
                ('sort_order', models.PositiveIntegerField(default=0)),
                ('house', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='protocol_categories', to='houses.poultryhouse')),
            ],
            options={
                'verbose_name_plural': 'protocol categories',
                'ordering': ['sort_order', 'id'],
            },
        ),
        migrations.AddField(
            model_name='protocoltemplate',
            name='category_new',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='protocol_lines', to='protocols.protocolcategory'),
        ),
        migrations.RunPython(seed_categories_and_migrate_lines, noop_reverse),
        migrations.RemoveField(
            model_name='protocoltemplate',
            name='category',
        ),
        migrations.RenameField(
            model_name='protocoltemplate',
            old_name='category_new',
            new_name='category',
        ),
        migrations.AlterField(
            model_name='protocoltemplate',
            name='category',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='protocol_lines', to='protocols.protocolcategory'),
        ),
        migrations.AlterModelOptions(
            name='protocoltemplate',
            options={'ordering': ['category__sort_order', 'from_value']},
        ),
    ]
