"""The one way this app hands out a sequential, human-readable code (`H-2-003`, `BATCH-2026-004`,
`FEE-2-007`, `FAULT-H-2-001-002`, `CASE-BATCH-2026-001-003`).

Each generator used to be "count the rows, add one". That is only correct while nothing is ever
deleted: remove any row that is not the newest and the count lands on a code still in use, so the
next create hits the primary key (500) — and keeps hitting it, since the count never moves again.
Deleting one house made "Nouveau bâtiment" fail for good (campaign 9, finding B1).

The sequence now follows the highest existing suffix under the prefix, so a deleted code is never
reissued either (an old audit-log line naming it cannot be mistaken for a newer row). Two creates
racing on the same number (a double-tapped submit) are resolved by `create_with_code` retrying.
"""
from django.db import IntegrityError, transaction


def next_sequential_code(model, field: str, prefix: str, width: int = 3) -> str:
    """`prefix` + (highest numeric suffix among `model.field` values starting with `prefix`) + 1,
    zero-padded to `width`. Non-numeric suffixes are ignored; a prefix that merely shares leading
    characters (`H-2-` vs `H-21-`) does not match because the prefix ends with its separator."""
    highest = 0
    for code in model.objects.filter(**{f'{field}__startswith': prefix}).values_list(field, flat=True).iterator():
        suffix = code[len(prefix):]
        if suffix.isdigit():
            highest = max(highest, int(suffix))
    return f'{prefix}{highest + 1:0{width}d}'


def create_with_code(create, attempts: int = 5):
    """Run `create()` — which must compute its code *inside* the call — in a savepoint, retrying on
    `IntegrityError`. A concurrent create that took the same number makes the first attempt fail;
    the retry recomputes past it. Safe inside an outer `transaction.atomic()`."""
    for attempt in range(attempts):
        try:
            with transaction.atomic():
                return create()
        except IntegrityError:
            if attempt == attempts - 1:
                raise
