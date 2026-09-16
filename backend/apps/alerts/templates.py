"""SMS message content.

This module holds the **SCHEDULED task-reminder** template (`render_task_reminder` /
`build_task_reminders`) added 2026-08-27 for personal `PROTOCOL_TASK` reminders generated from
`apps.protocols.models.ProtocolTemplate` lines — "Bonjour Monsieur/Madame X, merci d'effectuer
Y à Z [à HHhMM|aujourd'hui]." targeted at the task's assigned employee, falling back to the
batch's Fermier.

**EVENT-type alert messages** (LOW_STOCK, CONSUMPTION_DEVIATION, ...) are farm-wide observations,
not personal task assignments, and keep their own "Bonjour Monsieur, merci de faire..." framing
out of scope for this task — they stay where they already lived, as inline f-strings in
`apps.alerts.services` (`check_low_stock`, `check_consumption_deviation`), untouched by this
change. See docs/deviations.md for why the two weren't merged into one shared module: moving
the EVENT strings here would touch their existing behavior, which this task was explicitly told
not to do.
"""
from apps.core.models import Civility

CIVILITY_LABELS = {
    Civility.M: 'Monsieur',
    Civility.MME: 'Madame',
}


def _first_name(full_name):
    """`User.name` is a single free-text field (no separate first/last name columns anywhere in
    this codebase — checked, not assumed). Takes the first whitespace-separated token, matching
    the task spec's own example ("Jean Dupont" -> "Bonjour Monsieur Jean")."""

    first, _, _ = full_name.strip().partition(' ')
    return first or full_name


def render_task_reminder(user, task_what, house_name, start_time=None):
    """Renders one personal task-reminder SMS.

    `start_time` is a `datetime.time` (a `ProtocolTimeSlot.start_time`) for a specific
    occurrence, or None for a day-range task with no time slot — rendered as "aujourd'hui"
    instead of a dangling/empty time clause.
    """
    civility = CIVILITY_LABELS[user.civility]
    time_clause = f' à {start_time.strftime("%Hh%M")}' if start_time else ' aujourd\'hui'
    return (
        f"Bonjour {civility} {_first_name(user.name)}, merci d'effectuer {task_what} "
        f'à {house_name}{time_clause}.'
    )


def resolve_task_reminder_recipients(protocol_line, batch):
    """The task's assigned employees (`ProtocolTemplate.assignees`) if any, else the batch's
    Fermier (`PoultryBatch.farmer`) alone. Never broadcasts to every farm employee — returns an
    empty list (caller must not send anything) if neither is set.

    A list since 2026-09-16 (FIX 7): a line can be assigned to several workers, and each of them
    gets their own reminder, addressed to them by name. They still share one occurrence — the
    first to mark it done closes it for everyone.
    """

    assignees = list(protocol_line.assignees.all())
    if assignees:
        return assignees
    return [batch.farmer] if batch.farmer else []


def build_task_reminders(protocol_line, batch):
    """One (recipient, message) pair per `ProtocolTimeSlot` on `protocol_line` **per recipient**,
    or one pair per recipient with no time clause if the line has none — never one message trying
    to list multiple times, and never one message addressed to several people (each is greeted by
    their own name). Returns an empty list if there is no one to notify (see
    `resolve_task_reminder_recipients`).
    """
    recipients = resolve_task_reminder_recipients(protocol_line, batch)
    if not recipients:
        return []

    house_name = batch.house.name
    slots = list(protocol_line.time_slots.all()) or [None]
    return [
        (
            recipient,
            render_task_reminder(
                recipient, protocol_line.what, house_name,
                start_time=slot.start_time if slot else None,
            ),
        )
        for recipient in recipients
        for slot in slots
    ]
