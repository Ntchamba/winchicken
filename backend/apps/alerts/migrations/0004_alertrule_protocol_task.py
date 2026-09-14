import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('alerts', '0003_initial'),
        ('batches', '0001_initial'),
        ('protocols', '0002_protocolcategory'),
    ]

    operations = [
        migrations.AlterField(
            model_name='alertrule',
            name='rule_type',
            field=models.CharField(
                choices=[
                    ('LOW_STOCK', 'Low stock'),
                    ('VACCINE_DUE', 'Vaccine due'),
                    ('CONSUMPTION_DEVIATION', 'Consumption deviation'),
                    ('PROFITABILITY_THRESHOLD', 'Profitability threshold'),
                    ('SANITARY_VOID_END', 'Sanitary void end'),
                    ('PROTOCOL_TASK', 'Protocol task'),
                ],
                max_length=32,
            ),
        ),
        migrations.AlterField(
            model_name='notificationpreference',
            name='rule_type',
            field=models.CharField(
                choices=[
                    ('LOW_STOCK', 'Low stock'),
                    ('VACCINE_DUE', 'Vaccine due'),
                    ('CONSUMPTION_DEVIATION', 'Consumption deviation'),
                    ('PROFITABILITY_THRESHOLD', 'Profitability threshold'),
                    ('SANITARY_VOID_END', 'Sanitary void end'),
                    ('PROTOCOL_TASK', 'Protocol task'),
                ],
                max_length=32,
            ),
        ),
        migrations.AddField(
            model_name='alertrule',
            name='batch',
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.CASCADE,
                related_name='alert_rules', to='batches.poultrybatch',
                help_text="Set only for PROTOCOL_TASK rules generated from this batch's protocol.",
            ),
        ),
        migrations.AddField(
            model_name='alertrule',
            name='protocol_line',
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.CASCADE,
                related_name='generated_alert_rules', to='protocols.protocoltemplate',
                help_text='The ProtocolTemplate row this PROTOCOL_TASK rule was expanded from.',
            ),
        ),
        migrations.AddField(
            model_name='alertrule',
            name='scheduled_date',
            field=models.DateField(
                blank=True, null=True,
                help_text='Calendar date this ONE_TIME PROTOCOL_TASK rule fires on — '
                           'batch.start_date + protocol_line.from_value converted to days.',
            ),
        ),
    ]
