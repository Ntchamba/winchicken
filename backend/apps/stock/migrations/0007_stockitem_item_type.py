from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('stock', '0006_stockcomposition_stockcompositioningredient'),
    ]

    operations = [
        migrations.AddField(
            model_name='stockitem',
            name='item_type',
            field=models.CharField(blank=True, default='', max_length=64),
        ),
    ]
