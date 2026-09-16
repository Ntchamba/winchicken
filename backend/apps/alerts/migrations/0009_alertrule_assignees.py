"""A weighing reminder can be assigned to several workers (2026-09-16, FIX 7).

Same add-copy-drop ordering as protocols.0009: the autodetector's RemoveField-first version
would have discarded every existing assignment.
"""
from django.conf import settings
from django.db import migrations, models


def copy_assignment_to_assignees(apps, schema_editor):
    AlertRule = apps.get_model('alerts', 'AlertRule')
    for rule in AlertRule.objects.exclude(assigned_to=None).iterator():
        rule.assignees.add(rule.assigned_to_id)


def keep_the_first_assignee(apps, schema_editor):
    """Reverse: lossy, the lowest-id assignee wins (see protocols.0009)."""
    AlertRule = apps.get_model('alerts', 'AlertRule')
    for rule in AlertRule.objects.all().iterator():
        first = rule.assignees.order_by('id').first()
        if first is not None:
            rule.assigned_to_id = first.id
            rule.save(update_fields=['assigned_to'])


class Migration(migrations.Migration):

    dependencies = [
        ('alerts', '0008_pushsubscription'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='alertrule',
            name='assignees',
            field=models.ManyToManyField(blank=True, help_text='Task-assignment targets (2026-08-26, docs/deviations.md Part 15; many-to-many since 2026-09-16, FIX 7) — only meaningful for WEIGHING_REMINDER rows, which (unlike PROTOCOL_TASK) are stable/persistent rather than pruned each time they\'d fire; see apps.protocols.models.ProtocolTemplate.assignees for the protocol-line equivalent used by every other "tâches à effectuer maintenant" entry. Several workers can share one task: whoever completes it closes it for all of them.', related_name='assigned_alert_rules', to=settings.AUTH_USER_MODEL),
        ),
        migrations.RunPython(copy_assignment_to_assignees, keep_the_first_assignee),
        migrations.RemoveField(
            model_name='alertrule',
            name='assigned_to',
        ),
    ]
