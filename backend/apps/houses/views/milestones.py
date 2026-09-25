from collections import defaultdict

from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.batches.models import PoultryBatch
from apps.houses.models import PoultryHouse
from apps.houses.services import compute_cycle_milestones
from apps.protocols.models import ProtocolTemplate


@extend_schema(
    responses=inline_serializer('HouseMilestonesResponse', {
        'cycleLength': serializers.IntegerField(allow_null=True),
        'dayOfCycle': serializers.IntegerField(allow_null=True),
        'milestones': inline_serializer('CycleMilestone', {
            'id': serializers.CharField(), 'category': serializers.CharField(), 'icon': serializers.CharField(),
            'what': serializers.CharField(), 'details': serializers.CharField(),
            'day': serializers.IntegerField(), 'isPast': serializers.BooleanField(),
        }, many=True),
    }),
)
class HouseMilestonesView(APIView):
    """GET /api/houses/{houseCode}/milestones/ — cycle timeline data for the per-house view
    (2026-08-26, docs/deviations.md Part 16, Part B): every `ProtocolTemplate`-derived milestone
    for the house's active batch, projected across the whole remaining cycle — see
    `apps.houses.services.compute_cycle_milestones` for the computation (shared with
    `Upcoming48hView` below, so the global 48h widget and this per-house timeline can never
    disagree about where a milestone falls)."""

    permission_classes = [IsAuthenticated]

    def get(self, request, house_code):
        house = get_object_or_404(PoultryHouse, house_code=house_code, farm=request.user.farm)
        cycle_length, day_of_cycle, milestones = compute_cycle_milestones(house)
        return Response({'cycleLength': cycle_length, 'dayOfCycle': day_of_cycle, 'milestones': milestones})


@extend_schema(
    responses=inline_serializer('Upcoming48hResponse', {
        'houseCode': serializers.CharField(), 'houseName': serializers.CharField(),
        'batchName': serializers.CharField(allow_null=True),
        'category': serializers.CharField(), 'icon': serializers.CharField(), 'what': serializers.CharField(),
        'when': serializers.CharField(help_text='"aujourd\'hui", "demain", or an ISO date for anything further out (shouldn\'t normally happen within a 48h window).'),
    }, many=True),
)
class Upcoming48hView(APIView):
    """GET /api/tasks/upcoming/ — the next 3-4 scheduled tasks across every house/batch within
    the next 48 hours (2026-08-26, docs/deviations.md Part 16, Part C), for the global view's
    "Prochaines 48h" widget. Built from the exact same `compute_cycle_milestones` as the
    per-house timeline (`HouseMilestonesView`) — filtered to `dayOfCycle <= day <=
    dayOfCycle + 2` rather than a separate query, per this task's own "reuse... not a separate
    calculation" instruction. No `ProtocolTimeSlot`/time-of-day concept exists anywhere in this
    codebase (checked before assuming otherwise) — every entry is a day-level "aujourd'hui" /
    "demain" label, not an exact time window.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        farm = request.user.farm
        # Every house's active batch and protocol lines in two queries, handed to the shared
        # helper — it used to look both up again for each house (three queries per house).
        batches = {b.house_id: b for b in PoultryBatch.objects.filter(house__farm=farm, status='ACTIVE')}
        lines = defaultdict(list)
        for line in ProtocolTemplate.objects.filter(house__farm=farm).select_related('category'):
            lines[line.house_id].append(line)
        results = []
        for house in PoultryHouse.objects.filter(farm=farm):
            batch = batches.get(house.house_code)
            if batch is None:
                continue
            _, day_of_cycle, milestones = compute_cycle_milestones(house, batch=batch, lines=lines[house.house_code])
            for m in milestones:
                offset = m['day'] - day_of_cycle
                if not (0 <= offset <= 2):
                    continue
                when = 'aujourd\'hui' if offset == 0 else 'demain' if offset == 1 else f'dans {offset} jours'
                results.append({
                    'houseCode': house.house_code, 'houseName': house.name,
                    'batchName': batch.name if batch else None,
                    'category': m['category'], 'icon': m['icon'], 'what': m['what'], 'when': when,
                })
        results.sort(key=lambda r: r['when'] != 'aujourd\'hui')  # today's entries first, stable otherwise
        return Response(results[:4])
