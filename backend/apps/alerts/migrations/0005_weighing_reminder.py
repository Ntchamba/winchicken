from django.db import migrations, models

RULE_TYPE_CHOICES = [
    ('LOW_STOCK', 'Low stock'),
    ('VACCINE_DUE', 'Vaccine due'),
    ('CONSUMPTION_DEVIATION', 'Consumption deviation'),
    ('PROFITABILITY_THRESHOLD', 'Profitability threshold'),
    ('SANITARY_VOID_END', 'Sanitary void end'),
    ('PROTOCOL_TASK', 'Protocol task'),
    ('WEIGHING_REMINDER', 'Weighing reminder'),
]

FREQUENCY_CHOICES = [
    ('DAILY', 'Daily'),
    ('WEEKLY', 'Weekly'),
    ('MONTHLY', 'Monthly'),
    ('ONE_TIME', 'One time'),
]


class Migration(migrations.Migration):

    dependencies = [
        ('alerts', '0004_alertrule_protocol_task'),
    ]

    operations = [
        migrations.AlterField(
            model_name='alertrule',
            name='rule_type',
            field=models.CharField(choices=RULE_TYPE_CHOICES, max_length=32),
        ),
        migrations.AlterField(
            model_name='notificationpreference',
            name='rule_type',
            field=models.CharField(choices=RULE_TYPE_CHOICES, max_length=32),
        ),
        migrations.AlterField(
            model_name='alertrule',
            name='frequency',
            field=models.CharField(blank=True, choices=FREQUENCY_CHOICES, max_length=16, null=True),
        ),
    ]
