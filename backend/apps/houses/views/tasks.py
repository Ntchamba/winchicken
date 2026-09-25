from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.alerts.models import AlertRule, AlertRuleType
from apps.batches.models import PoultryBatch
from apps.batches.services import WEIGHING_RECURRENCE_LABELS
from apps.core.models import User
from apps.core.permissions import CanEditHouseProtocol, IsAdminOrFarmManagerOrFarmerOrWorker
from apps.houses.models import PoultryHouse
from apps.houses.services import compute_tasks_now
from apps.protocols.models import ProtocolTemplate, ProtocolTimeSlot

_TASK_SERIALIZER = inline_serializer('HouseTaskNow', {
    'id': serializers.CharField(),
    'category': serializers.CharField(),
    'icon': serializers.CharField(),
    'what': serializers.CharField(),
    'details': serializers.CharField(),
    'periodDay': serializers.IntegerField(allow_null=True),
    'periodLength': serializers.IntegerField(allow_null=True),
    'recurrence': serializers.CharField(allow_null=True, help_text='Set only for the recurring weighing reminder (2026-08-25) — a human label like "Hebdomadaire," in place of periodDay/periodLength which don\'t apply to a recurring item.'),
    'assignedTo': serializers.ListField(
        child=serializers.IntegerField(),
        help_text='Assignee user ids — empty when unassigned (a list since 2026-09-16, FIX 7).',
    ),
    'assignedToNames': serializers.ListField(child=serializers.CharField()),
    'timeSlotId': serializers.IntegerField(allow_null=True),
    'startTime': serializers.CharField(allow_null=True),
    'endTime': serializers.CharField(allow_null=True),
    'completable': serializers.BooleanField(),
    'done': serializers.BooleanField(help_text='One occurrence, one completion — shared by every assignee since FIX 7.'),
    'completedAt': serializers.DateTimeField(allow_null=True),
    'completedBy': serializers.IntegerField(allow_null=True, help_text='Who closed it, so the other assignees see who did the work.'),
    'completedByName': serializers.CharField(allow_null=True),
}, many=True)


@extend_schema(
    responses=inline_serializer('HouseTasksNowResponse', {
        'dayOfCycle': serializers.IntegerField(allow_null=True),
        'tasks': _TASK_SERIALIZER,
    }),
)
class HouseTasksNowView(APIView):
    """GET /api/houses/{houseCode}/tasks-now/ — "Tâches à effectuer maintenant" panel
    (2026-08-25): live, uncached computation from the house's *current* ProtocolTemplate rows
    and its active batch's `start_date` (`apps.houses.services.compute_tasks_now`). Never
    persisted anywhere — every request recomputes `dayOfCycle` from `today - start_date` and
    re-filters ProtocolTemplate fresh, so a protocol edit is reflected on the very next load
    with no cache/invalidation to manage (unlike the PROTOCOL_TASK AlertRule rows, which *are*
    persisted and need apps.protocols.services.expand_protocol_to_alert_rules to be kept in
    sync — see that function's docstring).

    Returns `dayOfCycle: null, tasks: []` if the house has no active batch — there is nothing
    "now" to compute without a start date.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, house_code):
        house = get_object_or_404(PoultryHouse, house_code=house_code, farm=request.user.farm)
        day_of_cycle, tasks = compute_tasks_now(house)
        return Response({'dayOfCycle': day_of_cycle, 'tasks': tasks})


@extend_schema(
    request=inline_serializer('HouseTaskAssignRequest', {
        'assignees': serializers.ListField(child=serializers.IntegerField(), allow_empty=True),
    }),
    responses=inline_serializer('HouseTaskAssignResponse', {
        'assignedTo': serializers.ListField(child=serializers.IntegerField()),
        'assignedToNames': serializers.ListField(child=serializers.CharField()),
    }),
)
class HouseTaskAssignView(APIView):
    """PATCH /api/houses/{houseCode}/tasks-now/{taskId}/assign/ — sets or clears one task's
    assignee (2026-08-26, docs/deviations.md Part 15, Part E). `taskId` is whatever id
    `HouseTasksNowView`/`compute_tasks_now` gave that task: a plain `ProtocolTemplate` pk for a
    protocol-line task, or `weighing-{batchCode}` for the recurring weighing reminder — resolved
    back to the underlying row here (`ProtocolTemplate.assignees` or the batch's
    `WEIGHING_REMINDER` `AlertRule.assignees`, respectively). Reserved to Admin/Farm
    Manager/Farmer (`CanEditHouseProtocol`, the same role set that edits the protocol these
    tasks are generated from) — Ouvrier/Technicien can see assignment (via `HouseTasksNowView`)
    but not set it.

    Takes the **whole** assignee set (`{"assignees": [id, ...]}`, many-to-many since 2026-09-16,
    FIX 7); `[]` clears it. `set()` rather than add/remove so the request is idempotent and the
    admin UI can send exactly what the multi-select shows. Purely additive either way — an
    unassigned task keeps showing normally for anyone with access to the house.
    """

    permission_classes = [CanEditHouseProtocol]

    def patch(self, request, house_code, task_id):
        house = get_object_or_404(PoultryHouse, house_code=house_code, farm=request.user.farm)
        user_ids = request.data.get('assignees')
        if not isinstance(user_ids, list):
            return Response(
                {'detail': 'Le champ « assignees » doit être une liste d’identifiants.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        # Farm-scoped on purpose: an id from another farm must 404, not silently assign.
        assignees = [get_object_or_404(User, pk=user_id, farm=request.user.farm) for user_id in user_ids]

        if task_id.startswith('weighing-'):
            batch = get_object_or_404(PoultryBatch, batch_code=task_id.removeprefix('weighing-'), house=house)
            row = get_object_or_404(AlertRule, batch=batch, rule_type=AlertRuleType.WEIGHING_REMINDER)
        else:
            row = get_object_or_404(ProtocolTemplate, pk=task_id, house=house)
        row.assignees.set(assignees)

        return Response({
            'assignedTo': [user.id for user in assignees],
            'assignedToNames': [user.name for user in assignees],
        })


@extend_schema(
    request=inline_serializer('HouseTaskCompleteRequest', {
        'date': serializers.DateField(required=False),
        'time_slot_id': serializers.IntegerField(required=False, allow_null=True),
        'force': serializers.BooleanField(required=False),
    }),
    responses=inline_serializer('HouseTaskCompleteResponse', {
        'status': serializers.ChoiceField(['done', 'already_done', 'insufficient_stock']),
        'completedAt': serializers.DateTimeField(allow_null=True),
        'movement': inline_serializer('HouseTaskCompleteMovement', {
            'id': serializers.IntegerField(), 'itemCode': serializers.CharField(),
            'quantity': serializers.FloatField(),
        }, allow_null=True),
        'shortfall': serializers.DictField(allow_null=True),
    }),
)
class HouseTaskCompleteView(APIView):
    """POST /api/houses/{houseCode}/tasks-now/{taskId}/complete/ — "Marquer comme fait" for one
    occurrence of a protocol-line task (2026-08-31). `taskId` is the `ProtocolTemplate` pk (as
    `compute_tasks_now` emits it). Body: optional `date` (default today), optional
    `time_slot_id`, optional `force`.

    Runs the validation-time insufficient-stock check first: if the linked resource is short
    and `force` is not set, responds `{status: 'insufficient_stock', shortfall: {...}}` and
    writes nothing — the frontend shows a prominent warning and re-POSTs with `force: true`
    (non-blocking, the user may have sourced it elsewhere). Otherwise records a `TaskCompletion`
    and, if the row links a `stock_item` + quantity, creates the `OUT` `StockMovement`.
    Idempotent — re-marking the same occurrence returns `{status: 'already_done'}` and creates
    no second movement.
    """

    permission_classes = [IsAdminOrFarmManagerOrFarmerOrWorker]

    def post(self, request, house_code, task_id):
        from apps.batches.models import BatchStatus
        from apps.stock.consumption import complete_task_occurrence

        house = get_object_or_404(PoultryHouse, house_code=house_code, farm=request.user.farm)
        line = get_object_or_404(ProtocolTemplate, pk=task_id, house=house)
        batch = PoultryBatch.objects.filter(house=house, status=BatchStatus.ACTIVE).first()
        if batch is None:
            return Response({'detail': "Ce bâtiment n'a pas de bande active."}, status=400)

        slot_id = request.data.get('time_slot_id')
        time_slot = get_object_or_404(ProtocolTimeSlot, pk=slot_id, protocol_line=line) if slot_id else None
        when = None
        if request.data.get('date'):
            import datetime as _dt

            from django.utils import timezone as _tz
            from django.utils.dateparse import parse_date

            d = parse_date(request.data['date'])
            if d is None:
                return Response({'detail': 'date invalide (attendu YYYY-MM-DD).'}, status=400)
            when = _tz.make_aware(_dt.datetime.combine(d, _dt.time(12, 0)))  # noon — only .date() is used

        # The endpoint takes any date, but only a day the line is actually due on is an occurrence:
        # a day-7 vaccine "done" on day 1 deducted its stock for a task that did not exist.
        from apps.batches.services import day_of_cycle
        from apps.houses.services import _protocol_line_occurrence

        cycle_day = day_of_cycle(batch, timezone.localdate(when) if when else timezone.localdate())
        if _protocol_line_occurrence(line, cycle_day) is None:
            return Response(
                {'detail': f"Cette tâche n'est pas prévue ce jour-là (jour {cycle_day} du cycle)."}, status=400,
            )
        # A timed line is one occurrence per slot. Without the slot, a third, untimed occurrence
        # was filed and deducted while both real ones stayed outstanding.
        if time_slot is None and line.time_slots.exists():
            return Response({'detail': 'Précisez le créneau : cette tâche a plusieurs horaires dans la journée.'}, status=400)

        result = complete_task_occurrence(
            line, batch, when=when, time_slot=time_slot, user=request.user,
            force=bool(request.data.get('force')),
        )

        if result.get('needs_confirmation'):
            return Response({'status': 'insufficient_stock', 'shortfall': result['shortfall'],
                             'completedAt': None, 'movement': None})

        completion = result['completion']
        mv = result['movement']
        return Response({
            'status': 'already_done' if result['already_done'] else 'done',
            'completedAt': completion.completed_at,
            'movement': None if mv is None else {
                'id': mv.id, 'itemCode': mv.item_id, 'quantity': mv.quantity,
            },
            'shortfall': None,
        }, status=200 if result['already_done'] else 201)


class HouseTaskUncompleteView(APIView):
    """POST /api/houses/{houseCode}/tasks-now/{taskId}/uncomplete/ — undo "Marquer comme fait".

    Deletes the `TaskCompletion` and the `OUT` `StockMovement` it created, restoring the
    article's quantity. Body: optional `date` (default today), optional `time_slot_id`.

    Undoing something that was never completed returns `{status: 'not_done'}` rather than a
    404: two taps racing on a phone should not surface an error the user can do nothing with.
    Same permissions as completing — whoever can mark a task done can correct it.
    """

    permission_classes = [IsAdminOrFarmManagerOrFarmerOrWorker]

    def post(self, request, house_code, task_id):
        from apps.batches.models import BatchStatus
        from apps.stock.consumption import uncomplete_task_occurrence

        house = get_object_or_404(PoultryHouse, house_code=house_code, farm=request.user.farm)
        line = get_object_or_404(ProtocolTemplate, pk=task_id, house=house)
        batch = PoultryBatch.objects.filter(house=house, status=BatchStatus.ACTIVE).first()
        if batch is None:
            return Response({'detail': "Ce bâtiment n'a pas de bande active."}, status=400)

        slot_id = request.data.get('time_slot_id')
        time_slot = get_object_or_404(ProtocolTimeSlot, pk=slot_id, protocol_line=line) if slot_id else None
        when = None
        if request.data.get('date'):
            import datetime as _dt

            from django.utils import timezone as _tz
            from django.utils.dateparse import parse_date

            d = parse_date(request.data['date'])
            if d is None:
                return Response({'detail': 'date invalide (attendu YYYY-MM-DD).'}, status=400)
            when = _tz.make_aware(_dt.datetime.combine(d, _dt.time(12, 0)))

        result = uncomplete_task_occurrence(line, batch, when=when, time_slot=time_slot)
        return Response({
            'status': 'undone' if result['undone'] else 'not_done',
            'restored': result['restored'],
        })


@extend_schema(responses=inline_serializer('AssignableUser', {
    'id': serializers.IntegerField(), 'name': serializers.CharField(), 'role': serializers.CharField(),
}, many=True))
class AssignableUsersView(APIView):
    """GET /api/tasks/assignable-users/ — every user account on the farm, for the assignee
    `<select>` in `TasksNowPanel.jsx` (2026-08-27 bugfix, docs/deviations.md). Previously that
    dropdown reused `GET /api/employees/` (`EmployeeListCreateView`), which (a) is gated to
    Admin/Secondary Admin only — a Farm Manager or Farmer performing the assignment (both
    allowed to, per `CanEditHouseProtocol`/`HouseTaskAssignView`) got a 403 and an empty
    dropdown — and (b) excludes the requesting user's own account (`EmployeeListCreateView.
    get_queryset`'s `.exclude(pk=self.request.user.pk)`, correct for *that* view's "manage
    everyone but yourself" purpose, wrong here), so an Admin could never assign a task to
    themselves. Same permission as who can actually perform an assignment
    (`HouseTaskAssignView`), deliberately not reusing the employee-management endpoint's
    Admin/Secondary-Admin-only gate — this is task-assignee visibility, not account management.
    Every role (including the requester) is listed; nothing here restricts *who can be chosen*
    as an assignee.

    Optional `?q=` (name contains, case-insensitive) and `?limit=` (capped at
    `ASSIGNABLE_USERS_MAX`): the picker searches as the user types instead of downloading every
    account — 1 MB and 390 ms at 20 000 staff in the 2026-09-25 load test. Without either
    parameter the full list comes back, unchanged.
    """

    permission_classes = [CanEditHouseProtocol]
    ASSIGNABLE_USERS_MAX = 100

    def get(self, request):
        users = User.objects.filter(farm=request.user.farm).order_by('name', 'id')
        query = (request.query_params.get('q') or '').strip()
        if query:
            users = users.filter(name__icontains=query)
        limit = request.query_params.get('limit')
        if limit is not None:
            try:
                limit = int(limit)
            except ValueError:
                return Response({'limit': 'Nombre entier attendu.'}, status=status.HTTP_400_BAD_REQUEST)
            users = users[:max(1, min(limit, self.ASSIGNABLE_USERS_MAX))]
        return Response(list(users.values('id', 'name', 'role')))


@extend_schema(responses=inline_serializer('MyTasksResponse', {}, many=False))
class MyTasksView(APIView):
    """GET /api/tasks/mine/ — every task assigned to the requesting user, across every house in
    the farm (2026-08-26, "Mes tâches", docs/deviations.md Part 15). Same task shape as
    `HouseTasksNowView`'s `tasks` entries, plus `houseCode`/`houseName` since results span
    houses. Reuses `apps.houses.services.compute_tasks_now` per house with an active batch — see
    that function's docstring for why this must not be a second, independent computation."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        results = []
        # Only houses where this user holds an assignment can yield a task for them — the two
        # places an assignment lives are the ones `compute_tasks_now` reads `assignedTo` from.
        # Computing every other house's full task list just to discard it cost ~5 queries per
        # house on every poll of this screen.
        # Two IN-subqueries, not an OR across both joins: that multiplied every assignee row of
        # every line by every rule row (~400 000 rows at 20 000 employees) before filtering.
        houses = PoultryHouse.objects.filter(farm=request.user.farm).filter(
            Q(house_code__in=ProtocolTemplate.objects.filter(assignees=request.user).values('house_id'))
            | Q(house_code__in=AlertRule.objects.filter(
                assignees=request.user, rule_type=AlertRuleType.WEIGHING_REMINDER,
            ).values('batch__house_id')),
        )
        for house in houses:
            _, tasks = compute_tasks_now(house)
            for task in tasks:
                # `assignedTo` is a list since FIX 7 — the same occurrence appears for every
                # assignee, and whoever completes it closes it for all of them (`done` and
                # `completedByName` come from the single TaskCompletion row).
                if request.user.id in task['assignedTo']:
                    results.append({**task, 'houseCode': house.house_code, 'houseName': house.name})
        return Response(results)


_ASSIGNMENT_SERIALIZER = inline_serializer('HouseAssignment', {
    'id': serializers.CharField(help_text='The same task id the assign endpoint takes.'),
    'what': serializers.CharField(),
    'category': serializers.CharField(),
    'assignedTo': serializers.ListField(child=serializers.IntegerField()),
    'assignedToNames': serializers.ListField(child=serializers.CharField()),
    'activeToday': serializers.BooleanField(),
    'periodLabel': serializers.CharField(allow_null=True),
}, many=True)


@extend_schema(responses=_ASSIGNMENT_SERIALIZER)
class HouseAssignmentsView(APIView):
    """GET /api/houses/{houseCode}/assignments/ — every assignment this house currently carries,
    whether or not the task is due today (2026-09-15, FIX 4).

    `HouseTasksNowView` only ever lists what is due *now*, and assignment display was hung off
    that list. So the moment a task stopped being due — the day after a weekly weighing, or the
    day a protocol line's range ended — its assignment disappeared from the panel and from
    `/api/tasks/mine/` while the assignment sat in the database with no way to see or clear it.
    The row had not expired: a weekly reminder is due again six days later. The filter was too
    narrow, so this is the wider read rather than a cleanup that would throw the assignment away.

    `activeToday` comes from `compute_tasks_now` itself, not from a second "is it due" rule —
    the two must never be able to disagree (see that function's docstring).
    """

    permission_classes = [CanEditHouseProtocol]

    def get(self, request, house_code):
        house = get_object_or_404(PoultryHouse, house_code=house_code, farm=request.user.farm)
        _, tasks = compute_tasks_now(house)
        due_ids = {str(task['id']) for task in tasks}

        rows = []
        lines = (
            ProtocolTemplate.objects
            .filter(house=house, assignees__isnull=False)
            .distinct()
            .select_related('category')
            .prefetch_related('assignees')
        )
        for line in lines:
            if line.until_end:
                period = f'À partir du jour {line.from_value}'
            else:
                period = f'Jours {line.from_value} à {line.to_value}'
            rows.append({
                'id': str(line.id),
                'what': line.what,
                'category': line.category.label,
                'assignedTo': [user.id for user in line.assignees.all()],
                'assignedToNames': [user.name for user in line.assignees.all()],
                'activeToday': str(line.id) in due_ids,
                'periodLabel': period,
            })

        rules = (
            AlertRule.objects
            .filter(batch__house=house, rule_type=AlertRuleType.WEIGHING_REMINDER, assignees__isnull=False)
            .distinct()
            .select_related('batch')
            .prefetch_related('assignees')
        )
        for rule in rules:
            task_id = f'weighing-{rule.batch.batch_code}'
            rows.append({
                'id': task_id,
                'what': 'Peser un échantillon de la bande',
                'category': 'Pesée',
                'assignedTo': [user.id for user in rule.assignees.all()],
                'assignedToNames': [user.name for user in rule.assignees.all()],
                'activeToday': task_id in due_ids,
                'periodLabel': WEIGHING_RECURRENCE_LABELS.get(rule.batch.weighing_frequency),
            })

        return Response(rows)
