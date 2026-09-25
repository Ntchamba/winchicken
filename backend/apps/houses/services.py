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
    # No end = a single day at the start, in the start's unit. (It used to take from_value in
    # to_unit — which defaults to DAY — so "semaine 2" with no end ran from day 14 to day 2 and
    # was due on no day at all.)
    to_day = to_days(line.to_value, line.to_unit) if line.to_value is not None else from_day
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

    Each task dict carries `assignedTo`/`assignedToNames` — parallel lists, empty when nobody is
    assigned (many-to-many since 2026-09-16, FIX 7; they were a single id/name before) — resolved
    from `ProtocolTemplate.assignees` for a protocol-line task, or from the batch's
    `WEIGHING_REMINDER` `AlertRule.assignees` for the recurring weighing task (see those fields'
    docstrings for why assignment lives on two different models). Several assignees share one
    occurrence: the first to complete it closes it for all of them.

    `timeSlotId`/`startTime`/`endTime` (2026-09-14 bugfix): a line with one or more
    `ProtocolTimeSlot` rows is one task *per slot*, each completable on its own; a line with
    none is a single untimed task with all three `None`, exactly as before. This mirrors
    `compute_month_schedule`, which has expanded slots since 2026-08-27 — "maintenant" was the
    one path still collapsing them, so a twice-daily 55 kg feeding line offered one checkbox and
    deducted 55 kg instead of 110. Stock then depleted half as fast in the app as in the barn,
    threshold alerts fired late, feed cost was understated by half, and the evening worker had
    nothing to mark done. `TaskCompletion` has always keyed occurrences on
    `(protocol_template, batch, date, time_slot)` and the complete/uncomplete endpoints have
    always accepted `time_slot_id`; this is the producer catching up with them.
    """
    from apps.alerts.models import AlertRule, AlertRuleType
    from apps.batches.models import BatchStatus, PoultryBatch
    from apps.batches.services import weighing_reminder_task
    from apps.protocols.models import ProtocolTemplate

    from apps.protocols.models import TaskCompletion

    batch = PoultryBatch.objects.filter(house=house, status=BatchStatus.ACTIVE).first()
    if not batch:
        return None, []

    from apps.batches.services import day_of_cycle as cycle_day

    today = timezone.localdate()
    day_of_cycle = cycle_day(batch, today)

    # Today's completions for this batch, fetched once rather than per line — the panel and
    # "Mes tâches" both render every task, so a per-task query would be N+1 on every poll.
    # Keyed by `(line id, time_slot id)`, the same identity TaskCompletion's unique constraint
    # uses; `time_slot_id` is None for an untimed line. The old `time_slot__isnull=True` filter
    # is gone: it hid every per-slot completion from the panel, so a slot marked done would have
    # kept reading as outstanding.
    done_by_occurrence = {
        (c.protocol_template_id, c.time_slot_id): c
        for c in TaskCompletion.objects.filter(
            batch=batch, date=today,
        ).select_related('completed_by')
    }

    tasks = []
    lines = (
        ProtocolTemplate.objects.filter(house=house)
        .select_related('category')
        .prefetch_related('time_slots', 'assignees')
    )
    for line in lines:
        occurrence = _protocol_line_occurrence(line, day_of_cycle)
        if occurrence is None:
            continue
        period_day, period_length = occurrence
        base = {
            # Stays the ProtocolTemplate pk: it is the {taskId} path segment of the
            # complete/uncomplete/assign routes. The slot travels beside it in `timeSlotId`,
            # which the two completion endpoints already read as `time_slot_id`.
            'id': str(line.id),
            'category': line.category.label,
            'icon': line.category.icon,
            'what': line.what,
            'details': line.details,
            'periodDay': period_day,
            'periodLength': period_length,
            'recurrence': None,
            'assignedTo': [user.id for user in line.assignees.all()],
            'assignedToNames': [user.name for user in line.assignees.all()],
            # `completable` is False for the weighing reminder below: it is not a
            # ProtocolTemplate row, so the complete endpoint has nothing to record against.
            'completable': True,
        }
        # `%Hh%M` matches compute_month_schedule and apps.alerts.templates.render_task_reminder,
        # so the same window reads identically in the panel, the calendar and the SMS.
        slots = list(line.time_slots.all()) or [None]
        for slot in slots:
            completion = done_by_occurrence.get((line.id, slot.id if slot else None))
            tasks.append({
                **base,
                'timeSlotId': slot.id if slot else None,
                'startTime': slot.start_time.strftime('%Hh%M') if slot else None,
                'endTime': slot.end_time.strftime('%Hh%M') if slot else None,
                # Completion state, so a finished task reads as done instead of vanishing.
                'done': completion is not None,
                'completedAt': completion.completed_at if completion else None,
                # Who closed it, for the *other* assignees: a line can carry several workers
                # (FIX 7) and the first completion closes the occurrence for all of them, so a
                # row that reads "Fait" in someone else's list must say by whom. The id travels
                # beside the name so the UI can say "vous" without matching on a display name.
                'completedBy': completion.completed_by_id if completion else None,
                'completedByName': (
                    completion.completed_by.name if completion and completion.completed_by_id else None
                ),
            })

    weighing_task = weighing_reminder_task(batch, day_of_cycle)
    if weighing_task:
        rule = AlertRule.objects.filter(
            batch=batch, rule_type=AlertRuleType.WEIGHING_REMINDER,
        ).prefetch_related('assignees').first()
        assignees = list(rule.assignees.all()) if rule else []
        weighing_task['assignedTo'] = [user.id for user in assignees]
        weighing_task['assignedToNames'] = [user.name for user in assignees]
        # Not a ProtocolTemplate row — it is satisfied by recording a weighing, not by a
        # "fait" checkbox, so the UI must not offer one.
        weighing_task['completable'] = False
        weighing_task['done'] = False
        weighing_task['completedAt'] = None
        weighing_task['completedBy'] = None
        weighing_task['completedByName'] = None
        # Same keys as a protocol-line task so consumers never branch on which kind they hold.
        weighing_task['timeSlotId'] = None
        weighing_task['startTime'] = None
        weighing_task['endTime'] = None
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
    from apps.batches.services import day_of_cycle as cycle_day
    from apps.protocols.models import ProtocolTemplate

    entries = []
    batches = list(PoultryBatch.objects.filter(house__farm=farm, status=BatchStatus.ACTIVE).select_related('house'))
    # Every house's lines in one query (plus one for their slots), not one query per house.
    lines_by_house = {}
    for line in (
        ProtocolTemplate.objects.filter(house_id__in={batch.house_id for batch in batches})
        .select_related('category')
        .prefetch_related('time_slots')
        .order_by('house_id', 'pk')
    ):
        lines_by_house.setdefault(line.house_id, []).append(line)
    for batch in batches:
        lines = lines_by_house.get(batch.house_id, [])
        if not lines:
            continue
        # A cycle ends at its planned end date: "jusqu'à la fin du cycle" lines used to run on
        # through every later month (live QA, 2026-09-25). Days already lived still show while a
        # batch stays open past that date — the birds were still there.
        last_day = max(batch.planned_end_date, timezone.localdate()) if batch.planned_end_date else end
        day = start
        while day <= min(end, last_day):
            day_of_cycle = cycle_day(batch, day)
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


def summarize_month_schedule(entries, preview=3):
    """The month grid's view of `compute_month_schedule`'s entries: per day, how many tasks and
    the first `preview` of them (what a grid cell shows), plus every category in first-seen
    order so the grid colours them exactly as it did from the full list.

    The full list was 4.4 MB a month at 50 houses (load test, 2026-09-25) for a grid that shows
    three pills a day; the day's complete list is fetched on tap (`?date=`) instead. Built from
    the same entries, never a second computation of what is due.
    """
    categories = []
    seen = set()
    days = {}
    for entry in entries:
        if entry['category'] not in seen:
            seen.add(entry['category'])
            categories.append(entry['category'])
        day = days.setdefault(entry['date'], {'count': 0, 'preview': []})
        day['count'] += 1
        if len(day['preview']) < preview:
            day['preview'].append({key: entry[key] for key in ('id', 'startTime', 'houseName', 'what', 'category')})
    return {'categories': categories, 'days': days}


def compute_cycle_milestones(house, batch=None, lines=None):
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

    `batch` (the house's active batch) and `lines` (its protocol lines, `category` loaded) may be
    passed in by a caller that already fetched them for every house at once — the farm-wide 48h
    widget, which otherwise cost three queries per house. Left out, both are read here.
    """
    from apps.batches.models import BatchStatus, PoultryBatch
    from apps.protocols.models import ProtocolTemplate
    from apps.protocols.services import to_days

    if batch is None:
        batch = PoultryBatch.objects.filter(house=house, status=BatchStatus.ACTIVE).first()
    if not batch:
        return None, None, []

    from apps.batches.services import day_of_cycle as cycle_day

    day_of_cycle = cycle_day(batch)
    milestones = []
    if lines is None:
        lines = ProtocolTemplate.objects.filter(house=house).select_related('category')
    for line in lines:
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
