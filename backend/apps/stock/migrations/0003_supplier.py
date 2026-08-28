import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('stock', '0002_stockcategory'),
        ('core', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Supplier',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=255)),
                ('contact', models.CharField(blank=True, help_text='Phone number.', max_length=64)),
                ('email', models.EmailField(blank=True, max_length=254)),
                ('farm', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='suppliers', to='core.farm')),
            ],
            options={'ordering': ['name']},
        ),
        migrations.AddField(
            model_name='stockitem',
            name='supplier',
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name='items', to='stock.supplier',
                help_text="Default/primary supplier for this item (2026-08-28). Free-text supplier "
                          "fields on PurchaseOrder/StockMovement are unaffected.",
            ),
        ),
    ]
