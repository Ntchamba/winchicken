from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('stock', '0007_stockitem_item_type'),
    ]

    operations = [
        migrations.AddField(
            model_name='stockcomposition',
            name='base_output_quantity',
            field=models.FloatField(blank=True, null=True),
        ),
    ]
