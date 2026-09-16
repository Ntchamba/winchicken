# Data model

One section per Django model as actually implemented in `backend/apps/*/models.py`,
cross-checked field-by-field against `farm_management_schema_en.puml` (root of the
repo). Deviations from the puml are called out explicitly in each section; a
consolidated list is also in `docs/deviations.md`.

Field names below are the Django (snake_case) names; the puml uses camelCase for the
same concepts (e.g. `houseCode` in the puml == `house_code` in Django/`houseCode` in
JSON API responses, since DRF's default renderer does not camelCase automatically —
API responses actually use snake_case field names except where a serializer
explicitly renames a field, e.g. `MeSerializer`'s `farm`/`farm_name`, or
`ContactMessage`-style camelCase-in-JSON payloads that are constructed by hand in a
view rather than a `ModelSerializer`).

## core (`apps/core/models.py`)

### Farm
Single-row root of the installation. `name`, `location` (blank-allowed, puml has no
such distinction), `creation_date` (`auto_now_add`, puml: `creationDate`). Matches
the puml 1:1.

### User
Matches the puml's `User` class, with one difference: the puml lists a `password`
attribute directly on `User`; the actual model uses `AbstractBaseUser`, which stores
the hash in an inherited `password` field — not a field declared in
`apps/core/models.py` itself, but present at the DB level via inheritance. Also adds
`is_active`, `is_staff`, `date_joined` (all inherited/added for Django's
auth/admin machinery, not in the puml) and `phone` (in the puml too). `farm` is
nullable at the DB level (the puml shows a mandatory `farm_id`), though no code path
ever leaves it null in practice — see the model docstring for why.

### Role subtypes — Admin, SecondaryAdmin, FarmManager, Farmer, Worker, Technician, Cashier
Class-table inheritance, one row per `User` whose `role` matches, sharing the `User`
row's primary key (`user` `OneToOneField(primary_key=True)`). Matches the puml's
`User ||--o| <Role> : specializes_as` relationships and the `Admin ||--o{ FarmManager
: supervises` / `SecondaryAdmin ||--o{ Farmer : oversees` FKs (`FarmManager.admin`,
`Farmer.secondary_admin`) exactly. `ROLE_PROFILE_MODELS` + `create_role_profile()`
are the code-level mechanism that keeps a `User.role` and its subtype row in sync —
there is no DB constraint enforcing that a `User` has exactly the one matching
subtype row; it's enforced only by every code path going through
`create_role_profile()`.

### ContactMessage, NewsletterSubscriber — **not in the puml at all**
Public landing-page forms (implementation-detail spec section 1.3). `ContactMessage`:
`full_name`, `email`, `phone` (blank-allowed), `subject`, `message`, `created_at`.
`NewsletterSubscriber`: `email` (unique), `created_at`. Added because the
implementation-detail spec's landing-page button inventory requires them even though
neither the puml nor the cahier des charges' endpoint list (section 10) mentions
them.

## houses (`apps/houses/models.py`)

### PoultryHouse
Matches the puml (`houseCode` PK, `farm_id` FK, `name`, `sizeM2` → `size_m2`,
`maxCapacity` → `max_capacity`, `lastDisinfectionDate` → `last_disinfection_date`),
plus `created_at` (`auto_now_add`, not in the puml — used for default ordering).
`house_code` is a `CharField` primary key, server-generated as `H-{farmId}-{seq}`
(`apps.houses.serializers.generate_house_code`) — no form collects it manually.

## protocols (`apps/protocols/models.py`) — **the whole app is absent from the puml**

### ProtocolTemplate
Not present in `farm_management_schema_en.puml` in any form — no class, no note,
no relationship. It *is*, however, listed in the cahier des charges section 10 app
table ("protocols → ProtocolTemplate"), so the puml is simply out of date relative
to the cahier des charges rather than the implementation inventing an undocumented
model. Fields: `house` (FK to `PoultryHouse`), `category` (FK to `ProtocolCategory`),
`from_value` + `from_unit`, `to_value` + `to_unit` (both nullable — ignored when
`until_end` is set), `until_end` (boolean), `what`, `details`, `assignees`
(many-to-many to `User` since 2026-09-16, FIX 7 — it was a single `assigned_to` FK;
several workers can hold one line and the first to complete an occurrence closes it
for all of them),
`stock_item` (nullable FK to `StockItem`) + `quantity_per_day` (nullable float —
optional "this row consumes X units/day of that item", drives
`apps.stock.services.run_daily_consumption`), `time_slots` (reverse FK), `created_at`.

`apps.core.services.is_farm_configured` treats "a house has at least one
ProtocolTemplate line" as "a house has an active protocol" for onboarding purposes,
since neither `ProtocolTemplate` nor `PoultryHouse` has any boolean "active protocol"
flag to check instead (see `docs/deviations.md`).

## batches (`apps/batches/models.py`)

### PoultryBatch
Matches the puml's fields (`batchCode` PK, `houseCode`/`house`, `farmer_id`/`farmer`,
`productionType`/`production_type`, `breed`, `initialCount`/`initial_count`,
`currentCount`/`current_count`, `startDate`/`start_date`,
`plannedEndDate`/`planned_end_date`, `actualEndDate`/`actual_end_date`, `status`)
plus `created_at` (not in the puml). The puml describes the single-ACTIVE-batch rule
only as a text note ("Application-level constraint"); the implementation goes
further and enforces it as an actual database constraint:

```python
constraints = [
    models.UniqueConstraint(fields=['house'], condition=Q(status='ACTIVE'), name='one_active_batch_per_house')
]
```

i.e. a partial unique index on `house` where `status = 'ACTIVE'` — Postgres itself
will reject a second concurrently-ACTIVE batch for the same house, not just the
serializer-level check in `PoultryBatchSerializer.validate_house_code` (which exists
too, to surface a friendlier validation error before hitting the DB constraint).
`batch_code` is server-generated as `BATCH-{year}-{seq}`.

### DailyLog
Matches the puml (`logDate`/`log_date`, `mortality`, `feedConsumedKg`/
`feed_consumed_kg`, `waterConsumedL`/`water_consumed_l`,
`avgSampleWeight`/`avg_sample_weight`, `notes`), plus `created_at`. The puml's
"unique (batchCode, logDate)" note is implemented as an actual
`UniqueConstraint(fields=['batch', 'log_date'], name='one_daily_log_per_batch_per_day')`.

### BatchClosingReport
Matches the puml field-for-field (`batchCode` shared PK, `closingDate`/
`closing_date`, `totalMortalityPct`/`total_mortality_pct`,
`feedConversionRatio`/`feed_conversion_ratio`, `revenue`, `totalVariableCost`/
`total_variable_cost`, `unitCostPrice`/`unit_cost_price`, `totalMargin`/
`total_margin`). Computed by `apps.batches.calculations.build_closing_report` — see
`docs/calculations.md`.

## stock (`apps/stock/models.py`)

### StockCategory
`farm` FK, `label`, `icon` (lucide-react name), `sort_order`, `kind`
(`FEED|VETERINARY|EQUIPMENT|BEDDING|CUSTOM`). Same shape as `ProtocolCategory`; the
four defaults (Aliment/Vétérinaire/Équipement/Litière) are seeded per `Farm` by
`apps/stock/signals.py`. Deleting one cascades to its `StockItem` rows. `kind` is the
stable discriminator behind the feed-stage / cold-chain UI and the finance
`PurchaseOrder` breakdown mapping, so those survive a label rename (`ItemCategory`
enum is now this field's choices, not `StockItem.category` itself).

### Supplier
`farm` FK, `name`, `contact` (phone), `email`. Directory table (2026-08-28), kept
separate from the free-text `PurchaseOrder.supplier` / `StockMovement.supplier`
fields, which are unchanged.

### StockItem
`itemCode` PK, `farm_id`, `category` (**FK to `StockCategory`**, `on_delete=CASCADE`),
`supplier` (FK to `Supplier`, nullable, `on_delete=SET_NULL`), `name`, `unit`,
`feed_stage`, `cold_chain_required`, `alert_threshold`, `unit_price`, `created_at`.
`item_code` is server-generated as `{PREFIX}-{farmId}-{seq}` where `PREFIX` is the
category's `kind` 3-letter code (`FEE`/`VET`/`EQU`/`BED`/`CUS`). Current on-hand
quantity is *not* a field — always computed from `StockMovement` rows (see
`docs/calculations.md`).

### StockMovement
`item`/`itemCode`, `batch`/`batchCode` (nullable, `SET_NULL`), `protocol_line`
(nullable FK to `ProtocolTemplate`, `SET_NULL` — set only on rows generated by the
daily automatic consumption task, `apps.stock.services.run_daily_consumption`, and
its idempotency key), `movement_type`, `quantity`, `movement_date`,
`supplier_batch_number`, `supplier` (free text, unchanged), `created_at`.

### Vaccination
Matches the puml (`batchCode`/`batch`, `itemCode`/`item`, `scheduledDate`/
`scheduled_date`, `administeredDate`/`administered_date`,
`reconstitutionTime`/`reconstitution_time`, `dosesUsed`/`doses_used`, `status`). The
puml's note "dosesUsed >= batch currentCount" is enforced in
`apps.stock.serializers.VaccinationSerializer.validate` (application-level — not a
DB `CheckConstraint`, since it depends on a different row's current state). The
"reconstitutionTime + 2h = strict expiry" note is **not enforced anywhere in code** —
no constraint, no alert, no view logic reads it; it exists purely as a documented
convention. `status` is a plain `CharField` (default `'SCHEDULED'`), not an enum
class, unlike the puml's implicit suggestion of a fixed status set.

## maintenance (`apps/maintenance/models.py`)

### EquipmentFault
Matches the puml (`faultCode` PK, `technician_id`/`technician`, `houseCode`/`house`,
`itemCode`/`item`, `faultDescription`/`fault_description`, `reportedDate`/
`reported_date` (`auto_now_add` — always "today", cannot be backdated on create,
unlike a plain writable date field), `repairedDate`/`repaired_date`, `status`).
`fault_code` is server-generated as `FAULT-{houseCode}-{seq}`. `status` is a plain
`CharField` (default `'REPORTED'`), not a `TextChoices` enum. There is no endpoint to
transition `status`/set `repaired_date` after creation (see `docs/deviations.md`).

### UnusualCase
Matches the puml (`caseCode` PK, `batchCode`/`batch`, `farmer_id`/`farmer`,
`worker_id`/`worker`, `caseDescription`/`case_description`, `caseDate`/`case_date`,
`auto_now_add`). `case_code` is server-generated as `CASE-{batchCode}-{seq}`.

## finance (`apps/finance/models.py`)

### Expense
Matches the puml (`farm_id`, `batchCode`/`batch`, `category`, `amount`,
`expenseDate`/`expense_date`, `supplier`), plus `created_at`. `batch` is nullable —
matches the puml's optional `PoultryBatch ||--o{ Expense : allocated_to`.

### Sale
Matches the puml (`farm_id`, `batchCode`/`batch`, `cashier_id`/`cashier`,
`productType`/`product_type`, `quantity`, `unitPrice`/`unit_price`,
`totalAmount`/`total_amount`, `saleDate`/`sale_date`, `customer`), plus
`created_at`. `total_amount` is always recomputed server-side from
`quantity * unit_price` in an overridden `save()` — client-submitted values for it
are ignored (the serializer also marks it `read_only`).

### PurchaseOrder
Matches the puml (`orderCode` PK, `farm_id`, `cashier_id`/`cashier`, `itemCode`/
`item`, `supplier`, `quantity`, `amount`, `orderDate`/`order_date` (`auto_now_add`),
`status`). `order_code` is server-generated as `PO-{farmId}-{seq}` (4-digit
sequence, unlike the other 3-digit codes). The puml's note "Receiving it generates a
StockMovement of type IN" is implemented in
`apps.finance.serializers.PurchaseOrderSerializer.update`, triggered by
`PATCH /api/purchase-orders/{orderCode}/` — an endpoint the cahier des charges'
section 10 table does not list at all (only `GET`/`POST /api/purchase-orders/` are
listed there), added specifically so this rule has somewhere to run (see
`docs/deviations.md`).

## alerts (`apps/alerts/models.py`)

### AlertRule
Matches the puml (`farm_id`, `ruleType`/`rule_type`, `triggerMode`/`trigger_mode`,
`threshold`, `frequency`, `triggerTime`/`trigger_time`, `activeDays`/`active_days`,
`active`). Only `LOW_STOCK` and `CONSUMPTION_DEVIATION` (both `EVENT`-mode) are ever
actually created and fired by code (`apps.alerts.services.trigger_alert`, invoked
from `apps.alerts.signals`); `VACCINE_DUE`, `PROFITABILITY_THRESHOLD` and
`SANITARY_VOID_END` exist as valid `AlertRuleType` choices and can be created
through `POST /api/alert-rules/`, but nothing evaluates them, and there is no Celery
Beat schedule anywhere in the project to drive `SCHEDULED`-mode rules at all — see
`docs/deviations.md`.

### Alert
Matches the puml (`rule_id`/`rule`, `batchCode`/`batch`, `triggeredAt`/
`triggered_at`, `status`), plus `message` and `severity` (both absent from the puml,
but required by the frontend's `HomeDashboard.jsx` alert feed and the
implementation-detail spec's alert card design). `status` defaults to `NEW` and
nothing in the codebase ever transitions it to `SENT`/`RESOLVED` — there's no PATCH
endpoint on `Alert` at all.

### SmsMessage
Matches the puml (`alert_id`/`alert`, `recipient`, `idempotencyKey`/
`idempotency_key` (unique), `providerStatus`/`provider_status`, `provider`,
`retryCount`/`retry_count`, `nextRetryAt`/`next_retry_at`, `sentAt`/`sent_at`), plus
`created_at`.

### NotificationPreference
Matches the puml (`user_id`/`user`, `ruleType`/`rule_type`, `preferredChannel`/
`preferred_channel`, `active`). The puml doesn't show a uniqueness constraint; the
implementation adds `UniqueConstraint(fields=['user', 'rule_type'],
name='one_preference_per_user_per_rule_type')` — one preference row per user per
alert type, matching the described intent ("Per-user, per-alert-type volume
control") even though the puml only states it in a note, not as a schema constraint.

## Enums summary

All `TextChoices` enums (`UserRole`, `ProductionType`, `BatchStatus`,
`ItemCategory`, `FeedStage`, `MovementType`, `ExpenseCategory`, `ProductType`,
`OrderStatus`, `AlertRuleType`, `TriggerMode`, `ScheduleFrequency`, `AlertStatus`,
`SmsStatus`, `NotificationChannel`) match the puml's enum value sets exactly, except
`ItemCategory` gained `CUSTOM` (2026-08-28) and is now the `kind` field on
`StockCategory` rather than `StockItem.category` (which became an FK). One further
addition not in the puml: `ProtocolCategory`
(FEEDING/TEMPERATURE/HEALTH/VACCINATION/CLEANING) and `ProtocolUnit`
(DAY/WEEK/MONTH) in `apps/protocols/models.py`, since the whole `protocols` app is
absent from the puml (see above).
