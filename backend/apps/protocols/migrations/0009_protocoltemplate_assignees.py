"""A protocol line can be assigned to several workers (2026-09-16, FIX 7).

Add-copy-drop, in that order: Django's autodetector wrote the RemoveField first, which would
have thrown every existing assignment away. `assigned_to` is read into the new table before the
column goes.
"""
from django.conf import settings
from django.db import migrations, models


def copy_assignment_to_assignees(apps, schema_editor):
    ProtocolTemplate = apps.get_model('protocols', 'ProtocolTemplate')
    for line in ProtocolTemplate.objects.exclude(assigned_to=None).iterator():
        line.assignees.add(line.assigned_to_id)


def keep_the_first_assignee(apps, schema_editor):
    """Reverse: a single FK cannot hold a set, so the lowest-id assignee wins and the rest are
    dropped. Lossy on purpose — it is the only shape the old column has."""
    ProtocolTemplate = apps.get_model('protocols', 'ProtocolTemplate')
    for line in ProtocolTemplate.objects.all().iterator():
        first = line.assignees.order_by('id').first()
        if first is not None:
            line.assigned_to_id = first.id
            line.save(update_fields=['assigned_to'])


class Migration(migrations.Migration):

    dependencies = [
        ('protocols', '0008_taskcompletion'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='protocoltemplate',
            name='assignees',
            field=models.ManyToManyField(blank=True, related_name='assigned_protocol_tasks', to=settings.AUTH_USER_MODEL),
        ),
        migrations.RunPython(copy_assignment_to_assignees, keep_the_first_assignee),
        migrations.RemoveField(
            model_name='protocoltemplate',
            name='assigned_to',
        ),
    ]
