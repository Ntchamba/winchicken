from django.db.models import Q
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.batches.models import PoultryBatch
from apps.houses.models import PoultryHouse
from apps.stock.models import StockItem

RESULT_LIMIT = 6


class SearchView(APIView):
    """GET /api/search/?q=... — sidebar quick-search across houses, batches, and stock items,
    farm-scoped like every other endpoint (request.user.farm). Matches PoultryHouse.name,
    PoultryBatch.name, StockItem.name via icontains, capped at 6 results per group. Returns only
    names/codes — no financial or other role-restricted data — so no extra role scoping beyond
    IsAuthenticated is needed here."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        query = request.query_params.get('q', '').strip()
        farm = request.user.farm
        if not query or not farm:
            return Response({'houses': [], 'batches': [], 'stockItems': []})

        houses = PoultryHouse.objects.filter(farm=farm, name__icontains=query)[:RESULT_LIMIT]
        batches = (
            PoultryBatch.objects.select_related('house')
            .filter(Q(house__farm=farm) & Q(name__icontains=query))[:RESULT_LIMIT]
        )
        stock_items = StockItem.objects.filter(farm=farm, name__icontains=query)[:RESULT_LIMIT]

        return Response({
            'houses': [{'houseCode': h.house_code, 'name': h.name} for h in houses],
            'batches': [
                {
                    'batchCode': b.batch_code,
                    'name': b.name,
                    'houseCode': b.house_id,
                    'houseName': b.house.name,
                }
                for b in batches
            ],
            'stockItems': [{'itemCode': s.item_code, 'name': s.name} for s in stock_items],
        })
