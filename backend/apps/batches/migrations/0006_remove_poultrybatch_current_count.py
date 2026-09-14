from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('batches', '0005_poultrybatch_weighing_frequency'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='poultrybatch',
            name='current_count',
        ),
    ]
