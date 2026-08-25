from datetime import timedelta

from django.db import transaction
from drf_spectacular.utils import OpenApiExample, extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.batches.models import BatchStatus, PoultryBatch
from apps.batches.serializers import generate_batch_code
from apps.houses.models import PoultryHouse
from apps.houses.serializers import generate_house_code
from apps.protocols.models import ProtocolCategory, ProtocolTemplate
from apps.protocols.serializers import ProtocolCategorySerializer, ProtocolTemplateSerializer

UNIT_TO_DAYS = {'DAY': 1, 'WEEK': 7, 'MONTH': 30}


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
            ProtocolTemplate.objects.bulk_create(
                [ProtocolTemplate(house=house, **line) for line in line_serializer.validated_data]
            )

            batch = None
            if batch_data.get('initialCount'):
                from django.utils.dateparse import parse_date
                from django.utils import timezone

                start_date = parse_date(batch_data.get('startDate', '')) or timezone.now().date()
                cycle_value = int(batch_data.get('growthCycleValue', 0) or 0)
                cycle_unit = batch_data.get('growthCycleUnit', 'DAY')
                planned_end_date = (
                    start_date + timedelta(days=cycle_value * UNIT_TO_DAYS.get(cycle_unit, 1))
                    if cycle_value else None
                )
                batch = PoultryBatch.objects.create(
                    batch_code=generate_batch_code(farm.id),
                    name=batch_data.get('name', ''),
                    house=house,
                    farmer=request.user if request.user.role == 'FARMER' else None,
                    production_type=batch_data.get('productionType', 'BROILER'),
                    breed=batch_data.get('breed', ''),
                    initial_count=batch_data['initialCount'],
                    current_count=batch_data['initialCount'],
                    start_date=start_date,
                    planned_end_date=planned_end_date,
                    status=BatchStatus.ACTIVE,
                )

        return Response(
            {
                'house': {'houseCode': house.house_code, 'name': house.name},
                'batch': {'batchCode': batch.batch_code, 'name': batch.name} if batch else None,
                'categories': ProtocolCategorySerializer(ordered_categories, many=True).data,
                'protocolLines': ProtocolTemplateSerializer(ProtocolTemplate.objects.filter(house=house), many=True).data,
            },
            status=status.HTTP_201_CREATED,
        )
