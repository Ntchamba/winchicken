"""Business logic for the houses app, kept out of views.py per this project's "thin views"
convention (see docs/architecture.md).
"""
from django.utils import timezone


def _protocol_line_occurrence(line, day_of_cycle):
    """`(period_day, period_length)` if `line` is due on `day_of_cycle` of its batch's cycle, or
    `None` if it isn't — the exact from_day/to_day range check `compute_tasks_now` always used,
    extracted (2026-08-27, docs/deviations.md — calendar bugfix) so `compute_month_schedule` can
    reuse it verbatim instead of a second copy that could drift out of sync (this project has
    already been bitten once by near-identical logic living in two places and diverging, see
    `compute_tasks_now`'s own docstring)."""
    from apps.protocols.services import to_days

    from_day = to_days(line.from_value, line.from_unit)
    if line.until_end:
        if day_of_cycle < from_day:
            return None
        return day_of_cycle - from_day + 1, None
    to_day = to_days(line.to_value or line.from_value, line.to_unit)
    if not (from_day <= day_of_cycle <= to_day):
        return None
    return day_of_cycle - from_day + 1, to_day - from_day + 1


def compute_tasks_now(house):
    """`(day_of_cycle, tasks)` for `house`'s active batch — the "tâches à effectuer maintenant"
    computation, extracted (2026-08-26, docs/deviations.md Part 15) from
    `apps.houses.views.HouseTasksNowView` so `apps.houses.views.MyTasksView` (task assignment's
    "Mes tâches" view, spanning every house) calls the exact same logic instead of a second copy
    that could drift out of sync — this project has already been bitten once by near-identical
    logic living in two places and diverging (the sidebar-staleness bug, docs/deviations.md
    Part 5/6). Returns `(None, [])` if the house has no active batch.

    Each task dict carries `assignedTo`/`assignedToName` (both `None` if unassigned) — resolved
    from `ProtocolTemplate.assigned_to` for a protocol-line task, or from the batch's
    `WEIGHING_REMINDER` `AlertRule.assigned_to` for the recurring weighing task (see those
    fields' docstrings for why assignment lives on two different models).
    """
    from apps.alerts.models import AlertRule, AlertRuleType
    from apps.batches.models import BatchStatus, PoultryBatch
    from apps.batches.services import weighing_reminder_task
    from apps.protocols.models import ProtocolTemplate

    from apps.protocols.models import TaskCompletion

    batch = PoultryBatch.objects.filter(house=house, status=BatchStatus.ACTIVE).first()
    if not batch:
        return None, []

    today = timezone.localdate()
    day_of_cycle = (today - batch.start_date).days

    # Today's completions for this batch, fetched once rather than per line — the panel and
    # "Mes tâches" both render every task, so a per-task query would be N+1 on every poll.
    # Keyed by line id; `time_slot` is null for these panel-level occurrences (see
    # TaskCompletion's uniqueness rule).
    done_by_line = {
        c.protocol_template_id: c
        for c in TaskCompletion.objects.filter(
            batch=batch, date=today, time_slot__isnull=True,
        ).select_related('completed_by')
    }

    tasks = []
    for line in ProtocolTemplate.objects.filter(house=house).select_related('category', 'assigned_to'):
        occurrence = _protocol_line_occurrence(line, day_of_cycle)
        if occurrence is None:
            continue
        period_day, period_length = occurrence
        completion = done_by_line.get(line.id)
        tasks.append({
            'id': str(line.id),
            'category': line.category.label,
            'icon': line.category.icon,
            'what': line.what,
            'details': line.details,
            'periodDay': period_day,
            'periodLength': period_length,
            'recurrence': None,
            'assignedTo': line.assigned_to_id,
            'assignedToName': line.assigned_to.name if line.assigned_to_id else None,
            # Completion state, so a finished task reads as done instead of vanishing.
            # `completable` is False for the weighing reminder below: it is not a
            # ProtocolTemplate row, so the complete endpoint has nothing to record against.
            'completable': True,
            'done': completion is not None,
            'completedAt': completion.completed_at if completion else None,
            'completedByName': (
                completion.completed_by.name if completion and completion.completed_by_id else None
            ),
        })

    weighing_task = weighing_reminder_task(batch, day_of_cycle)
    if weighing_task:
        rule = AlertRule.objects.filter(
            batch=batch, rule_type=AlertRuleType.WEIGHING_REMINDER,
        ).select_related('assigned_to').first()
        weighing_task['assignedTo'] = rule.assigned_to_id if rule else None
        weighing_task['assignedToName'] = rule.assigned_to.name if rule and rule.assigned_to_id else None
        # Not a ProtocolTemplate row — it is satisfied by recording a weighing, not by a
        # "fait" checkbox, so the UI must not offer one.
        weighing_task['completable'] = False
        weighing_task['done'] = False
        weighing_task['completedAt'] = None
        weighing_task['completedByName'] = None
        tasks.append(weighing_task)

    return day_of_cycle, tasks


def compute_month_schedule(farm, start, end):
    """Every `ProtocolTemplate`-derived task due on any day in `[start, end]` (inclusive) across
    every house on `farm` with an active batch — the sidebar "Calendrier" month grid (2026-08-27
    bugfix, docs/deviations.md). Reuses `_protocol_line_occurrence`, the exact same day-in-range
    check `compute_tasks_now` uses for "today," evaluated once per calendar day instead of only
    today, so a line is never shown on just its first due day.

    Replaces `apps.protocols.views.ScheduleView`'s previous read of `PROTOCOL_TASK` `AlertRule`
    rows: `apps.protocols.services.expand_protocol_to_alert_rules` only ever creates *one* row
    per line, dated its first due day (`batch.start_date + from_value`) — a line spanning day 1
    to day 15 was only ever visible on day 1. This function computes the calendar directly from
    `ProtocolTemplate` + the batch's `start_date`, the same source `compute_tasks_now` already
    reads, instead of a second, AlertRule-derived representation that could (and did) fall out
    of sync with it.

    Returns a flat list of dicts, one per (house, day, protocol line, time slot) — the shape
    `CalendarPage.jsx` already expects from `GET /api/protocols/schedule/`.

    `startTime`/`endTime` (2026-08-27 bugfix, docs/deviations.md) — a line with one or more
    `ProtocolTimeSlot` rows generates one entry per slot for that day, each carrying its own
    window (`"%Hh%M"`, matching `apps.alerts.templates.render_task_reminder`'s own formatting —
    the one place in this codebase that already renders a slot time); a line with none generates
    a single entry with both `None`, exactly as before this fix (no regression for time-agnostic
    tasks like a multi-day cleaning range).
    """
    from datetime import timedelta

    from apps.batches.models import BatchStatus, PoultryBatch
    from apps.protocols.models import ProtocolTemplate

    entries = []
    batches = PoultryBatch.objects.filter(house__farm=farm, status=BatchStatus.ACTIVE).select_related('house')
    for batch in batches:
        lines = list(
            ProtocolTemplate.objects.filter(house=batch.house)
            .select_related('category')
            .prefetch_related('time_slots')
        )
        if not lines:
            continue
        day = start
        while day <= end:
            day_of_cycle = (day - batch.start_date).days
            for line in lines:
                if _protocol_line_occurrence(line, day_of_cycle) is None:
                    continue
                base = {
                    'date': day.isoformat(),
                    'houseCode': batch.house_id,
                    'houseName': batch.house.name,
                    'batchCode': batch.batch_code,
                    'batchName': batch.name,
                    'category': line.category.label,
                    'icon': line.category.icon,
                    'what': line.what,
                    'details': line.details,
                }
                slots = list(line.time_slots.all())
                if not slots:
                    entries.append({
                        'id': f'{line.id}-{day.isoformat()}', 'startTime': None, 'endTime': None, **base,
                    })
                else:
                    for slot in slots:
                        entries.append({
                            'id': f'{line.id}-{day.isoformat()}-{slot.id}',
                            'startTime': slot.start_time.strftime('%Hh%M'),
                            'endTime': slot.end_time.strftime('%Hh%M'),
                            **base,
                        })
            day += timedelta(days=1)
    return entries


def compute_cycle_milestones(house):
    """`(cycle_length, day_of_cycle, milestones)` for `house`'s active batch — every
    `ProtocolTemplate` line's start day projected across the *whole* remaining cycle, not just
    "is it due today" (2026-08-26, docs/deviations.md Part 16, Part B). Deliberately scoped to
    `ProtocolTemplate`-derived milestones only, per that task's own wording ("every upcoming
    `ProtocolTemplate`-derived milestone") — the recurring weighing reminder
    (`PoultryBatch.weighing_frequency`) is a different, non-protocol-line mechanism and is left
    out of this projection rather than folded in for completeness that wasn't asked for.

    Reuses `apps.protocols.services.to_days` for the exact same from_value/from_unit → day
    conversion `compute_tasks_now` already uses, so a milestone's day here always agrees with
    when `compute_tasks_now` will actually surface it as "due" — no separate calculation to
    drift out of sync. `until_end` lines get one milestone at their start day (`from_value`) —
    they have no defined end to also mark.

    `cycle_length` is `planned_end_date - start_date` when set, else the furthest milestone day
    (or `day_of_cycle` itself if there are none) — this project's batches aren't required to set
    `planned_end_date` (see `PoultryBatch` model), so the timeline still has *some* sensible
    length to render even without it, rather than crashing or rendering a zero-width bar.

    Returns `(None, None, [])` if the house has no active batch.
    """
    from apps.batches.models import BatchStatus, PoultryBatch
    from apps.protocols.models import ProtocolTemplate
    from apps.protocols.services import to_days

    batch = PoultryBatch.objects.filter(house=house, status=BatchStatus.ACTIVE).first()
    if not batch:
        return None, None, []

    day_of_cycle = (timezone.localdate() - batch.start_date).days
    milestones = []
    for line in ProtocolTemplate.objects.filter(house=house).select_related('category'):
        from_day = to_days(line.from_value, line.from_unit)
        milestones.append({
            'id': str(line.id),
            'category': line.category.label,
            'icon': line.category.icon,
            'what': line.what,
            'details': line.details,
            'day': from_day,
            'isPast': from_day < day_of_cycle,
        })
    milestones.sort(key=lambda m: m['day'])

    if batch.planned_end_date:
        cycle_length = (batch.planned_end_date - batch.start_date).days
    elif milestones:
        cycle_length = max(day_of_cycle, milestones[-1]['day'])
    else:
        cycle_length = day_of_cycle

    return cycle_length, day_of_cycle, milestones
