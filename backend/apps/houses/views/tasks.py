from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers
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
    'assignedTo': serializers.IntegerField(allow_null=True, help_text='Assignee user id, or null if unassigned (2026-08-26).'),
    'assignedToName': serializers.CharField(allow_null=True),
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
    request=inline_serializer('HouseTaskAssignRequest', {'assigned_to': serializers.IntegerField(allow_null=True)}),
    responses=inline_serializer('HouseTaskAssignResponse', {
        'assignedTo': serializers.IntegerField(allow_null=True),
        'assignedToName': serializers.CharField(allow_null=True),
    }),
)
class HouseTaskAssignView(APIView):
    """PATCH /api/houses/{houseCode}/tasks-now/{taskId}/assign/ — sets or clears one task's
    assignee (2026-08-26, docs/deviations.md Part 15, Part E). `taskId` is whatever id
    `HouseTasksNowView`/`compute_tasks_now` gave that task: a plain `ProtocolTemplate` pk for a
    protocol-line task, or `weighing-{batchCode}` for the recurring weighing reminder — resolved
    back to the underlying row here (`ProtocolTemplate.assigned_to` or the batch's
    `WEIGHING_REMINDER` `AlertRule.assigned_to`, respectively). Reserved to Admin/Farm
    Manager/Farmer (`CanEditHouseProtocol`, the same role set that edits the protocol these
    tasks are generated from) — Ouvrier/Technicien can see assignment (via `HouseTasksNowView`)
    but not set it. `assigned_to: null` clears it; purely additive either way, an unassigned
    task keeps showing normally for anyone with access to the house.
    """

    permission_classes = [CanEditHouseProtocol]

    def patch(self, request, house_code, task_id):
        house = get_object_or_404(PoultryHouse, house_code=house_code, farm=request.user.farm)
        user_id = request.data.get('assigned_to')
        assignee = get_object_or_404(User, pk=user_id, farm=request.user.farm) if user_id is not None else None

        if task_id.startswith('weighing-'):
            batch = get_object_or_404(PoultryBatch, batch_code=task_id.removeprefix('weighing-'), house=house)
            rule = get_object_or_404(AlertRule, batch=batch, rule_type=AlertRuleType.WEIGHING_REMINDER)
            rule.assigned_to = assignee
            rule.save(update_fields=['assigned_to'])
        else:
            line = get_object_or_404(ProtocolTemplate, pk=task_id, house=house)
            line.assigned_to = assignee
            line.save(update_fields=['assigned_to'])

        return Response({
            'assignedTo': assignee.id if assignee else None,
            'assignedToName': assignee.name if assignee else None,
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
    """

    permission_classes = [CanEditHouseProtocol]

    def get(self, request):
        users = User.objects.filter(farm=request.user.farm).order_by('name')
        return Response([{'id': u.id, 'name': u.name, 'role': u.role} for u in users])


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
        for house in PoultryHouse.objects.filter(farm=request.user.farm):
            _, tasks = compute_tasks_now(house)
            for task in tasks:
                if task['assignedTo'] == request.user.id:
                    results.append({**task, 'houseCode': house.house_code, 'houseName': house.name})
        return Response(results)


_ASSIGNMENT_SERIALIZER = inline_serializer('HouseAssignment', {
    'id': serializers.CharField(help_text='The same task id the assign endpoint takes.'),
    'what': serializers.CharField(),
    'category': serializers.CharField(),
    'assignedTo': serializers.IntegerField(),
    'assignedToName': serializers.CharField(),
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
    `/api/tasks/mine/` while `assigned_to` sat in the database with no way to see or clear it.
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
            .filter(house=house, assigned_to__isnull=False)
            .select_related('assigned_to', 'category')
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
                'assignedTo': line.assigned_to_id,
                'assignedToName': line.assigned_to.name,
                'activeToday': str(line.id) in due_ids,
                'periodLabel': period,
            })

        rules = (
            AlertRule.objects
            .filter(batch__house=house, rule_type=AlertRuleType.WEIGHING_REMINDER, assigned_to__isnull=False)
            .select_related('assigned_to', 'batch')
        )
        for rule in rules:
            task_id = f'weighing-{rule.batch.batch_code}'
            rows.append({
                'id': task_id,
                'what': 'Peser un échantillon de la bande',
                'category': 'Pesée',
                'assignedTo': rule.assigned_to_id,
                'assignedToName': rule.assigned_to.name,
                'activeToday': task_id in due_ids,
                'periodLabel': WEIGHING_RECURRENCE_LABELS.get(rule.batch.weighing_frequency),
            })

        return Response(rows)
