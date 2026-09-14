from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('batches', '0003_poultrybatch_name'),
    ]

    operations = [
        migrations.AddField(
            model_name='dailylog',
            name='eggs_collected',
            field=models.PositiveIntegerField(
                blank=True, null=True,
                help_text='Eggs collected that day, farm-wide quick-entry field (2026-08-25). Nullable '
                           'since most batches are broilers with no laying to record; a dedicated '
                           'laying-rate chart is deferred to a later iteration — this field only '
                           'captures the raw data point for now.',
            ),
        ),
    ]
