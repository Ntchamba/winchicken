from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0002_contactmessage_newslettersubscriber'),
    ]

    operations = [
        migrations.AddField(
            model_name='farm',
            name='singleton_lock',
            field=models.PositiveSmallIntegerField(default=1, editable=False, unique=True),
        ),
    ]
