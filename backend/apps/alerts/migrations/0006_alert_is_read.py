from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('alerts', '0005_weighing_reminder'),
    ]

    operations = [
        migrations.AddField(
            model_name='alert',
            name='is_read',
            field=models.BooleanField(default=False),
        ),
    ]
