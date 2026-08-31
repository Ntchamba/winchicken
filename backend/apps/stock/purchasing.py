"""Manual "Ajouter du stock" cost tracking (2026-08-31).

A manual IN `StockMovement` on its own carries no monetary value, so it can never show up in
Finance. When the "Prix total payé" field is filled, `record_manual_purchase_expense` writes
the matching `Expense` — that (not a separate mechanism) is what makes the purchase appear in
Achats and Globale.
"""


def _expense_category_for(item):
    """Which `ExpenseCategory` a purchase of `item` belongs to.

    Prefer a keyword match on the item's free-text `item_type` — so "chaise (équipement)" lands
    in DEPRECIATION and a plain "éponge" in MISC even when both sit under one CUSTOM stock
    category. When `item_type` is blank or matches nothing, fall back to the stock-category-kind
    map (`_ITEM_CATEGORY_TO_EXPENSE_CATEGORY`) the RECEIVED-PurchaseOrder aggregation uses:
    FEED→FEED, VETERINARY→VETERINARY, EQUIPMENT→DEPRECIATION, BEDDING/CUSTOM→MISC.
    """
    from apps.finance.calculations import _ITEM_CATEGORY_TO_EXPENSE_CATEGORY
    from apps.finance.models import ExpenseCategory

    keywords = (
        (('aliment', 'provende', 'grain', 'maïs', 'mais', 'son', 'tourteau', 'concentré'), ExpenseCategory.FEED),
        (('médic', 'medic', 'vaccin', 'vétérin', 'veterin', 'antibio', 'vitamine', 'traitement'), ExpenseCategory.VETERINARY),
        (('équipement', 'equipement', 'matériel', 'materiel', 'outil', 'machine', 'mangeoire', 'abreuvoir'), ExpenseCategory.DEPRECIATION),
    )
    label = (item.item_type or '').strip().lower()
    if label:
        for needles, category in keywords:
            if any(n in label for n in needles):
                return category
    return _ITEM_CATEGORY_TO_EXPENSE_CATEGORY.get(item.category.kind, ExpenseCategory.MISC)


def record_manual_purchase_expense(movement, total_price):
    """Create the `Expense` for a manual stock IN.

      category      ← `_expense_category_for(item)` — a keyword match on the item's free-text
                      `item_type` first, else the item's stock-category kind via the same
                      `apps.finance.calculations._ITEM_CATEGORY_TO_EXPENSE_CATEGORY` map the
                      RECEIVED-PurchaseOrder aggregation already uses (FEED→FEED,
                      VETERINARY→VETERINARY, EQUIPMENT→DEPRECIATION, BEDDING/CUSTOM→MISC) —
                      reused for consistency with that flow rather than the simpler
                      "everything but feed/vet → MISC" (see README).
      amount        ← total_price (the amount actually paid this time, editable, may differ
                      from the item's reference unit_price).
      expense_date  ← the movement's date.
      batch         ← null (general farm stock, not batch-specific).
      supplier      ← the item's linked `Supplier` name if one is set, else blank.
    """
    from apps.finance.models import Expense

    item = movement.item
    category = _expense_category_for(item)
    return Expense.objects.create(
        farm=item.farm,
        batch=None,
        category=category,
        amount=total_price,
        expense_date=movement.movement_date,
        supplier=(item.supplier.name if item.supplier_id else ''),
    )
