"""The project-wide paginator: DRF's page-number pagination with a stable row order."""
from rest_framework.pagination import PageNumberPagination


class StablePageNumberPagination(PageNumberPagination):
    """Appends the primary key to the queryset's ordering before cutting pages.

    Most lists sort by a column that is not unique — a sale date, a case date, a salary period.
    Postgres returns tied rows in any order it likes, and it may pick a different one for each
    page's LIMIT/OFFSET query, so a row can show up on two pages while another is on none. For a
    screen that reads every page and adds the rows up ("Total du jour" at the till), that is a
    wrong total, not just an odd list. The primary key is unique, so the order becomes total;
    tied rows keep the order they were created in.
    """

    def paginate_queryset(self, queryset, request, view=None):
        if not queryset.query.combinator:  # a union() cannot be re-ordered by a model field
            ordering = list(queryset.query.order_by or (
                queryset.model._meta.ordering if queryset.query.default_ordering else []
            ))
            names = {str(field).lstrip('-') for field in ordering}
            if not names & {'pk', 'id', queryset.model._meta.pk.name}:
                queryset = queryset.order_by(*ordering, 'pk')
        return super().paginate_queryset(queryset, request, view)
