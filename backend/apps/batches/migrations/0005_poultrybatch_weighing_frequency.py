from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('batches', '0004_dailylog_eggs_collected'),
    ]

    operations = [
        migrations.AddField(
            model_name='poultrybatch',
            name='weighing_frequency',
            field=models.CharField(
                blank=True, null=True, max_length=8,
                choices=[('DAY', 'Day'), ('WEEK', 'Week'), ('MONTH', 'Month')],
                help_text='Optional "Fréquence de pesée" (2026-08-25) — reuses apps.protocols.models.'
                           'ProtocolUnit\'s three values by string (not a direct FK/import, to avoid a '
                           'protocols->batches model dependency) rather than defining a near-duplicate '
                           'enum. Drives a recurring WEIGHING_REMINDER AlertRule '
                           '(apps.batches.services.sync_weighing_reminder) and the "tâches à effectuer '
                           'maintenant" panel — never restricts when a weight can actually be logged '
                           'through the quick-entry panel, which accepts a weight on any date regardless.',
            ),
        ),
    ]
