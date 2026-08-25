from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('batches', '0002_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='poultrybatch',
            name='name',
            field=models.CharField(
                blank=True, max_length=255,
                help_text='Human-friendly name (e.g. "Bande printemps 2026") — required by the '
                           'protocol form when starting a batch, but blank=True at the model '
                           "level so existing rows from before this field (none in this "
                           "project's history) and any other creation path stay valid without "
                           'a forced default.',
            ),
        ),
    ]
