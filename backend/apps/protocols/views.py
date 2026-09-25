from calendar import monthrange
from datetime import date, timedelta

from django.db import transaction
from django.http import HttpResponse
from drf_spectacular.utils import OpenApiExample, extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.batches.models import BatchStatus, PoultryBatch
from apps.batches.serializers import generate_batch_code
from apps.houses.models import PoultryHouse
from apps.houses.serializers import generate_house_code
from apps.protocols.models import ProtocolCategory, ProtocolTemplate, ProtocolTimeSlot
from apps.protocols.serializers import ProtocolCategorySerializer, ProtocolTemplateSerializer
from apps.batches.services import sync_weighing_reminder
from apps.houses.services import compute_month_schedule, summarize_month_schedule
from apps.protocols.services import UNIT_TO_DAYS, expand_protocol_to_alert_rules
from apps.protocols.xlsx_import import ImportError as XlsxImportError
from apps.protocols.xlsx_import import build_template_workbook, parse_protocol_rows


@extend_schema(
    request=inline_serializer(
        'OnboardingRequest',
        {
            'house': inline_serializer('OnboardingHouse', {
                'name': serializers.CharField(required=False),
                'sizeM2': serializers.IntegerField(required=False),
                'maxCapacity': serializers.IntegerField(required=False),
            }),
            'batch': inline_serializer('OnboardingBatch', {
                'name': serializers.CharField(required=False, help_text='"Nom de la bande" — required by the frontend form, but this endpoint only requires it when initialCount is present (no name needed for a house with no batch yet).'),
                'initialCount': serializers.IntegerField(required=False, help_text='Omit to create the house without starting a batch.'),
                'startDate': serializers.DateField(required=False),
                'productionType': serializers.CharField(required=False, help_text='BROILER | PULLET | LAYER'),
                'breed': serializers.CharField(required=False),
                'growthCycleValue': serializers.IntegerField(required=False),
                'growthCycleUnit': serializers.CharField(required=False, help_text='DAY | WEEK | MONTH'),
            }),
            'customCategories': inline_serializer('OnboardingCustomCategory', {
                'label': serializers.CharField(), 'icon': serializers.CharField(),
            }, many=True, required=False, help_text='Extra categories beyond the 5 auto-seeded defaults, in display order.'),
            'protocolLines': inline_serializer('OnboardingProtocolLine', {
                'categoryIndex': serializers.IntegerField(help_text='0-4 = the 5 default categories in their fixed order (Alimentation/Température/Santé et soins/Vaccination/Nettoyage); 5+ = customCategories, in the order supplied.'),
                'from_value': serializers.IntegerField(), 'from_unit': serializers.CharField(),
                'to_value': serializers.IntegerField(required=False, allow_null=True), 'to_unit': serializers.CharField(),
                'until_end': serializers.BooleanField(), 'what': serializers.CharField(), 'details': serializers.CharField(required=False),
            }, many=True),
        },
    ),
    responses=inline_serializer(
        'OnboardingResponse',
        {
            'house': inline_serializer('OnboardingResponseHouse', {'houseCode': serializers.CharField(), 'name': serializers.CharField()}),
            'batch': inline_serializer('OnboardingResponseBatch', {'batchCode': serializers.CharField(), 'name': serializers.CharField()}, required=False, allow_null=True),
            'categories': ProtocolCategorySerializer(many=True),
            'protocolLines': ProtocolTemplateSerializer(many=True),
        },
    ),
    examples=[OpenApiExample(
        'Minimal onboarding request',
        value={
            'house': {'name': 'House A', 'maxCapacity': 500},
            'batch': {'name': 'Bande printemps 2026', 'initialCount': 500, 'startDate': '2026-08-25', 'productionType': 'BROILER'},
            'protocolLines': [
                {'categoryIndex': 0, 'from_value': 1, 'from_unit': 'DAY', 'to_value': 15, 'to_unit': 'DAY', 'until_end': False, 'what': 'Starter feed', 'details': ''}
            ],
        },
        request_only=True,
    )],
)
class OnboardingView(APIView):
    """POST /api/protocols/onboarding/ — creates PoultryHouse (+ its 5 default
    ProtocolCategory rows, seeded automatically by apps.houses.signals) + any custom
    categories + ProtocolTemplate lines (+ PoultryBatch if `batch.initialCount` is provided)
    in one transaction.

    Used by onboarding step 1 (new farm, cahier des charges 5.5) and by the dashboard sidebar's
    "+ Nouveau bâtiment" action (adding a further house later reuses the same endpoint).
    At least one protocol line is required; the request is rejected with 400 otherwise.

    Protocol lines reference their category by position (`categoryIndex`) rather than a real id,
    since custom categories don't have one yet at request time — the house (and its default
    categories) doesn't exist until this same request creates it. `categoryIndex` 0-4 are the 5
    defaults in their fixed seed order; 5+ walk through `customCategories` in the order supplied.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        farm = request.user.farm
        house_data = request.data.get('house', {})
        batch_data = request.data.get('batch', {})
        custom_categories_data = request.data.get('customCategories', [])
        protocol_lines_data = request.data.get('protocolLines', [])

        if not protocol_lines_data:
            return Response({'detail': 'Au moins une ligne de protocole est requise.'}, status=status.HTTP_400_BAD_REQUEST)

        # A batch is created only when initialCount is present; when it is, its name is required
        # (checked before the transaction opens so nothing is half-created on rejection).
        if batch_data.get('initialCount') and not str(batch_data.get('name') or '').strip():
            return Response(
                {'batch': {'name': ['Le nom de la bande est requis.']}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        category_serializer = ProtocolCategorySerializer(data=custom_categories_data, many=True)
        category_serializer.is_valid(raise_exception=True)

        with transaction.atomic():
            house = PoultryHouse.objects.create(
                house_code=generate_house_code(farm.id),
                farm=farm,
                name=house_data.get('name', 'Untitled house'),
                size_m2=house_data.get('sizeM2'),
                max_capacity=house_data.get('maxCapacity') or batch_data.get('initialCount', 0),
                last_disinfection_date=None,
            )

            # The 5 defaults now exist (apps.houses.signals, fired synchronously by .create()
            # above, inside this same transaction) — append any custom categories after them.
            next_sort_order = ProtocolCategory.objects.filter(house=house).count()
            for i, cat in enumerate(category_serializer.validated_data):
                ProtocolCategory.objects.create(house=house, sort_order=next_sort_order + i, **cat)
            ordered_categories = list(ProtocolCategory.objects.filter(house=house).order_by('sort_order'))

            resolved_lines = []
            for line in protocol_lines_data:
                index = line.get('categoryIndex')
                if index is None or not (0 <= index < len(ordered_categories)):
                    return Response(
                        {'detail': f'categoryIndex invalide : {index!r}.'}, status=status.HTTP_400_BAD_REQUEST
                    )
                resolved_lines.append({**line, 'category': ordered_categories[index].id})

            line_serializer = ProtocolTemplateSerializer(data=resolved_lines, many=True)
            line_serializer.is_valid(raise_exception=True)
            # `time_slots` isn't a real ProtocolTemplate field/constructor kwarg (it's the
            # reverse FK to ProtocolTimeSlot) — popped per line before bulk_create, then created
            # against the real pks bulk_create returns (Bug 1 fix, 2026-08-27, docs/deviations.md).
            lines_data = list(line_serializer.validated_data)
            time_slots_per_line = [line.pop('time_slots', []) for line in lines_data]
            # `id` is writable on the serializer so HouseProtocolView.put can match a line to the
            # row it edits. Onboarding only ever creates, on a house that has just been made, so
            # any id in the payload is meaningless here — dropped rather than passed to the
            # constructor as an explicit primary key.
            for line in lines_data:
                line.pop('id', None)
            created_lines = ProtocolTemplate.objects.bulk_create(
                [ProtocolTemplate(house=house, **line) for line in lines_data]
            )
            ProtocolTimeSlot.objects.bulk_create([
                ProtocolTimeSlot(protocol_line=line_obj, **slot)
                for line_obj, slots in zip(created_lines, time_slots_per_line)
                for slot in slots
            ])

            batch = None
            if batch_data.get('initialCount'):
                from django.utils.dateparse import parse_date
                from django.utils import timezone

                start_date = parse_date(batch_data.get('startDate', '')) or timezone.localdate()
                cycle_value = int(batch_data.get('growthCycleValue', 0) or 0)
                cycle_unit = batch_data.get('growthCycleUnit', 'DAY')
                planned_end_date = (
                    start_date + timedelta(days=cycle_value * UNIT_TO_DAYS.get(cycle_unit, 1))
                    if cycle_value else None
                )
                batch = PoultryBatch.objects.create(
                    batch_code=generate_batch_code(farm.id),
                    name=str(batch_data.get('name') or '').strip(),
                    house=house,
                    farmer=request.user if request.user.role == 'FARMER' else None,
                    production_type=batch_data.get('productionType', 'BROILER'),
                    breed=batch_data.get('breed', ''),
                    initial_count=batch_data['initialCount'],
                    start_date=start_date,
                    planned_end_date=planned_end_date,
                    weighing_frequency=batch_data.get('weighingFrequency') or None,
                    status=BatchStatus.ACTIVE,
                )
                expand_protocol_to_alert_rules(batch)
                sync_weighing_reminder(batch)

        return Response(
            {
                'house': {'houseCode': house.house_code, 'name': house.name},
                'batch': {'batchCode': batch.batch_code, 'name': batch.name} if batch else None,
                'categories': ProtocolCategorySerializer(ordered_categories, many=True).data,
                'protocolLines': ProtocolTemplateSerializer(
                    ProtocolTemplate.objects.filter(house=house).prefetch_related('time_slots'), many=True
                ).data,
            },
            status=status.HTTP_201_CREATED,
        )


class ScheduleView(APIView):
    """GET /api/protocols/schedule/?month=YYYY-MM — sidebar "Calendrier" month-grid view.

    Farm-wide, across every house/batch: every `ProtocolTemplate` line due on any day of the
    given month, per that house's active batch (`apps.houses.services.compute_month_schedule` —
    2026-08-27 bugfix, docs/deviations.md; previously read `PROTOCOL_TASK` `AlertRule` rows,
    which are only ever generated for a line's *first* due day, so a multi-day line like day
    1-15 was invisible on the calendar for days 2-15 — see that function's docstring). `month`
    defaults to the current month. Open to any authenticated user of the farm (like
    HouseTasksNowView), not Admin/Farm-Manager-only like AlertRuleListCreateView — this is task
    visibility, not rule management.

    Two lighter forms for the month grid (2026-09-25 — the flat list was 4.4 MB at 50 houses):
    `?month=YYYY-MM&view=summary` returns `{categories, days: {date: {count, preview}}}`
    (`summarize_month_schedule`), and `?date=YYYY-MM-DD` returns the flat list for that one day,
    fetched when a day is opened.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        day_param = request.query_params.get('date')
        if day_param:
            try:
                day = date.fromisoformat(day_param)
            except ValueError:
                return Response({'detail': 'date must be formatted YYYY-MM-DD'}, status=status.HTTP_400_BAD_REQUEST)
            return Response(compute_month_schedule(request.user.farm, day, day))

        month_param = request.query_params.get('month')
        try:
            if month_param:
                year, month = (int(part) for part in month_param.split('-', 1))
            else:
                today = timezone.localdate()
                year, month = today.year, today.month
            start = date(year, month, 1)
        except ValueError:
            return Response({'detail': 'month must be formatted YYYY-MM'}, status=status.HTTP_400_BAD_REQUEST)

        end = date(year, month, monthrange(year, month)[1])

        entries = compute_month_schedule(request.user.farm, start, end)
        if request.query_params.get('view') == 'summary':
            return Response(summarize_month_schedule(entries))
        return Response(entries)


CONTENT_TYPE_XLSX = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'


class ProtocolImportTemplateView(APIView):
    """GET /api/protocols/import-template.xlsx — the ready-to-fill Excel template (headers +
    example rows). Static content only, no farm data, so it is `AllowAny`: the frontend can
    offer it as a plain download link without threading the bearer token through an <a href>."""

    permission_classes = [AllowAny]

    def get(self, request):
        resp = HttpResponse(build_template_workbook(), content_type=CONTENT_TYPE_XLSX)
        resp['Content-Disposition'] = 'attachment; filename="modele-protocole.xlsx"'
        return resp


class ProtocolImportView(APIView):
    """POST /api/protocols/import-xlsx/ (multipart, field `file`) — parse an uploaded .xlsx into
    protocol rows for the form. Parse-only: nothing is written here, the frontend merges the
    rows into `HouseProtocolForm` for the user to review before the normal save. Farm-agnostic
    on purpose — onboarding uploads this before the house exists.

    Returns `{rows: [...], imported: int, skipped: [{line, reason}]}`. Same editor roles as the
    protocol itself (Admin / Farm Manager / Farmer)."""

    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    throttle_scope = 'import'  # security review 2026-09-26 HIGH-2

    def post(self, request):
        upload = request.FILES.get('file')
        if upload is None:
            return Response({'detail': 'Aucun fichier reçu.'}, status=status.HTTP_400_BAD_REQUEST)
        if not upload.name.lower().endswith('.xlsx'):
            return Response(
                {'detail': 'Format non pris en charge. Importez un fichier .xlsx (Excel).'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        from apps.core.xlsx import WorkbookError, check_upload_size
        try:  # security review 2026-09-26: refuse a memory bomb up front
            check_upload_size(upload)
        except WorkbookError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        # `preview=1` (the batch-creation Excel screen) wants the column mapping back even when
        # a required column couldn't be resolved, so it can show which one needs attention and
        # keep the confirm button disabled. Without the flag a file like that is still a 400,
        # which is what the protocol form's own import button has always done.
        preview = str(request.data.get('preview', '')).lower() in ('1', 'true', 'oui')
        try:
            result = parse_protocol_rows(upload, strict=not preview)
        except XlsxImportError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(result)
