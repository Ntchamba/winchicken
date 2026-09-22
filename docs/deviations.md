# Deviations from the spec documents

Every point below where the implementation differs from
`winchicken-cahier-des-charges.docx` and/or `winchicken-spec-implementation-detaillee.docx`,
or from `farm_management_schema_en.puml`. Grouped by topic; kept up to date as
the authoritative log whenever a deviation is introduced, discovered, or resolved.

## Endpoints added beyond the spec's list

- **`GET /api/health/`** — liveness probe, absent from the cahier des charges
  endpoint list (`apps/core/urls.py` + `apps/core/views.py:HealthCheckView`).
- **`POST /api/contact/` and `POST /api/newsletter/`** — public (`AllowAny`)
  landing-page forms, absent from cahier des charges section 10, present in
  the implementation-detail spec section 1.3. `POST /api/contact/` and
  `POST /api/newsletter/` currently have no frontend caller (see "Landing
  page v2" below) but are kept as small, generic, publicly-safe endpoints.
- **`PATCH /api/purchase-orders/{orderCode}/`** — implements "receiving a
  purchase order generates a `StockMovement` of type `IN`"
  (`apps/finance/serializers.py:PurchaseOrderSerializer.update`); the cahier
  des charges section 10 table lists only `GET`/`POST /api/purchase-orders/`.

## Server-generated codes

`houseCode`/`batchCode`/`itemCode`/`orderCode`/`faultCode`/`caseCode` are all
server-generated, never client-writable:
`apps/houses/serializers.py:generate_house_code` (`H-{farmId}-{seq}`),
`apps/batches/serializers.py:generate_batch_code` (`BATCH-{year}-{seq}`),
`apps/stock/serializers.py:generate_item_code` (`{CAT3}-{farmId}-{seq}`),
`apps/finance/serializers.py:PurchaseOrderSerializer.create`
(`PO-{farmId}-{seq:04d}`), `apps/maintenance/serializers.py:EquipmentFaultSerializer.create`
(`FAULT-{houseCode}-{seq}`), `apps/maintenance/serializers.py:UnusualCaseSerializer.create`
(`CASE-{batchCode}-{seq}`).

## `roiForecastPct`

`total_investment` = sum of `RECEIVED` `EQUIPMENT`-category `PurchaseOrder`s
over the period; stays `null` until one exists
(`apps/finance/calculations.py:roi_forecast_pct`). The spec also allows a
manually-entered investment value when none is recorded yet (section 5.4) —
not implemented, since the schema has no investment/capex field to hold a
manual entry.

## SMS provider

SMS sending defaults to a `console` provider
(`SMS_PROVIDER=console` in `config/settings.py` / `.env.example`;
`apps/alerts/providers/console.py:ConsoleSmsProvider` logs instead of
sending). `apps/alerts/providers/twilio.py` implements a real Twilio
integration (see `docs/architecture.md`); any other `SMS_PROVIDER` value
raises `NotImplementedError` in `apps/alerts/providers/__init__.py:get_sms_provider`.

## Landing page

Landing page (`/`) is a single welcome screen (superseding cahier des
charges §6 / implementation-detail spec §1, both updated to match): a
`.brand-mark` logo, "Welcome from Winchicken" heading, a "Voir une démo"
button opening a modal video player
(`frontend/src/components/DemoVideoModal.jsx`), and "Se connecter", routed by
`GET /api/farm/exists/`. `frontend/public/demo.mp4` is a placeholder path —
no video file is committed; drop the real file at that path to wire up the
button. `/demo` (`frontend/src/demo/DemoPage.jsx`) is a separate,
interactive client-side demo against fixture data — kept alongside the video,
not replaced by it. Landing page imagery uses CSS gradient placeholder
blocks, no image assets.

## Finance access matrix

`GET /api/finance/summary/` is `IsAuthenticated`-gated with a role-branched
response (implements cahier des charges §8 / implementation-detail spec
§4.3+§8): Admin / Farm Manager get `access: "full"` plus the full payload
(`months`, `cashOnHand`, `pendingPayables`, `roiForecastPct`); every other
role gets `access: "restricted"` plus only `revenueTrend`/`expenseTrend`
(`"up"`/`"down"`/`"flat"`, from
`apps.finance.calculations.finance_trend_direction`) — no monetary figures.
`FinanceExpenseCategoriesView` and `FinanceTransactionsView` remain
`IsAdminOrFarmManager`-only (exact amounts, per-transaction detail).
Test coverage: `apps/finance/tests.py` (`FinanceAccessTests`).

## Protocol categories & batch naming

- `ProtocolCategory` is a real model (`id`, `house` FK, `label`, `icon`,
  `sort_order`), not the old fixed 5-value enum. Deleting a category cascades
  to its `ProtocolTemplate` lines (`on_delete=CASCADE`).
- Five default categories (Alimentation/Température/Santé et
  soins/Vaccination/Nettoyage) are seeded on every new `PoultryHouse` via a
  `post_save` signal (`apps/houses/signals.py`).
- Custom categories: name + icon, from a 12-icon fixed list
  (`apps/protocols/models.py:CUSTOM_CATEGORY_ICON_CHOICES`, mirrored by hand
  in `HouseProtocolForm.jsx`'s `ICON_OPTIONS` — kept in sync manually, a
  maintenance risk if one changes without the other).
- During onboarding, protocol lines reference their category by array
  position (`categoryIndex`: 0-4 the five defaults in seed order, 5+ walking
  `customCategories` in supplied order) since the house doesn't exist yet
  server-side. Category deletion (the × control) is therefore management-mode
  only, not available during onboarding — deleting a default category
  mid-onboarding would shift later positions and misfile lines. See
  `docs/protocol-configuration.md`.
- `PoultryBatch.name` — required by the onboarding form, `blank=True` at the
  model level, only persisted from the onboarding flow. The protocol-edit
  screen for an existing house displays the field but doesn't persist it
  (consistent with the other 3 header fields on that screen, none of which
  persist from there either).
- `HouseProtocolView`'s `PUT` validates that every submitted line's category
  actually belongs to the target house (previously any valid category id was
  accepted regardless of owning house/farm, since DRF's default
  `PrimaryKeyRelatedField` only checks existence).

## Data model — puml vs. implementation

- **`ProtocolTemplate` (and the whole `apps.protocols` app)** is absent from
  `farm_management_schema_en.puml` — no class, relationship, or note — but
  is listed in the cahier des charges section 10 app table, so this is the
  puml being out of date, not an undocumented addition. See
  `docs/data-model.md`. (`docs/data-model.md`'s own `ProtocolTemplate`
  section still describes the old fixed 5-value enum and needs a refresh —
  flagged, not yet updated.)
- `User.farm` is nullable at the DB level (puml shows a mandatory `farm_id`),
  though no code path ever leaves it null in practice.
- `PoultryBatch`'s single-ACTIVE-batch-per-house rule is enforced as an
  actual partial unique DB constraint (`UniqueConstraint(fields=['house'],
  condition=Q(status='ACTIVE'))`), not just an application-level check — the
  puml describes it only as a text note.
- `DailyLog`'s "unique (batchCode, logDate)" note is a real
  `UniqueConstraint`.
- `Vaccination`'s "reconstitutionTime + 2h = strict expiry" note is not
  enforced anywhere in code — no constraint, no alert, no view logic reads
  it; documented convention only.
- `NotificationPreference` adds a `UniqueConstraint(user, rule_type)` not
  shown in the puml, matching the described "one preference per user per
  alert type" intent.
- `ContactMessage`/`NewsletterSubscriber` are not in the puml at all
  (implementation-detail spec section 1.3 landing-page forms).

## Alerts & scheduling

- `AlertRule` supports `EVENT` and `SCHEDULED` trigger modes; a Celery Beat
  schedule (`config/celery.py`) evaluates `SCHEDULED` rules
  (`trigger_time`/`frequency`/`active_days`) on a periodic task, alongside
  the two `EVENT`-mode rules wired to Django signals (`LOW_STOCK` on
  `StockMovement.post_save`, `CONSUMPTION_DEVIATION` on `DailyLog.post_save`,
  both in `apps/alerts/signals.py`).
- `ProtocolTemplate` lines generate `AlertRule` rows at batch creation,
  offset from `PoultryBatch.startDate` (cahier des charges §4.6), covering
  `VACCINE_DUE` and `SANITARY_VOID_END` alert types. See
  `apps/protocols/services.py:expand_protocol_to_alert_rules` and
  `apps/batches/signals.py`.
- `PROFITABILITY_THRESHOLD` remains defined as a valid `AlertRuleType` but
  has no evaluator — there is no profitability-per-batch computation wired
  to trigger it yet.
- `Alert.status` transitions via `PATCH /api/alerts/{id}/` (`NEW` →
  `SENT`/`RESOLVED`), used by `AlertsListPage.jsx` to let a user acknowledge
  an alert.

## Maintenance endpoints

`EquipmentFault` and `UnusualCase` support status transitions:
`PATCH /api/equipment-faults/{faultCode}/` sets `status`/`repaired_date`;
`PATCH /api/unusual-cases/{caseCode}/` edits a submitted case. Both are
restricted to the roles the cahier des charges section 8 permission matrix
assigns to maintenance actions (Technician / assigned Worker for faults;
Farmer/Worker for case reporting) via `get_permissions()` overrides on
`VaccinationListCreateView` and `UnusualCaseListCreateView`, matching every
other write endpoint in the project.

## Finance calculations wired to endpoints

`apps.finance.calculations.break_even_quantity` and `safety_margin_pct`, and
`apps.batches.calculations.bfr_estimate`, are exposed via
`GET /api/finance/working-capital/` and `GET /api/finance/break-even/`
(both `IsAdminOrFarmManager`), rather than being dead code reachable only
from unit-level calls.

## API field-naming convention

Every endpoint returns **snake_case** JSON field names
(`house_code`, `total_amount`, `feed_conversion_ratio`, ...), including the
hand-built endpoints that previously mixed in camelCase keys
(`weekly_kpi`, `finance_summary`, `expense_category_breakdown`,
`FinanceTransactionsView`, the new `FinanceBreakEvenView`/
`FinanceWorkingCapitalView`), and `AlertSerializer` (`ruleType` renamed to
`rule_type`).

**One deliberate exception**: `apps.protocols.views.OnboardingView`'s
request *and* response both stay camelCase
(`protocolLines`, `categoryIndex`, `customCategories`, `houseCode`,
`batchCode`, ...), matching the implementation-detail spec's section 11
examples verbatim. This is the one endpoint in the API where the
transaction shape is complex enough (id-less `categoryIndex` resolution
during onboarding, documented at length in
`docs/protocol-configuration.md`) that changing its wire format on both
sides carries real regression risk for a low readability payoff — every
other endpoint's camelCase was fixed instead. See `docs/api-reference.md`
for the current shape of every response.

## Fixed defects (kept here for traceability)

- **SMS body**: `apps/alerts/tasks.py:send_sms_task` now sends
  `sms.alert.message` (the actual alert text) to the provider, not
  `sms.idempotency_key` (a 40-character hash) — the idempotency key is used
  only for the `get_or_create` dedup key in
  `apps.alerts.services.trigger_alert`.
- **House type icon**: `DashboardShell.jsx` derives each house's `type` from
  its active batch's `production_type` (fetching `GET /api/batches/`
  alongside `GET /api/houses/`), instead of hardcoding `"Broiler"`.
- **`/api/schema/` and `/api/docs/` authentication**: both endpoints require
  a JWT (`SPECTACULAR_SETTINGS['SERVE_PERMISSIONS'] =
  ['rest_framework.permissions.IsAuthenticated']`) — `drf-spectacular`'s
  views default their own `permission_classes` to `AllowAny` internally,
  silently overriding `REST_FRAMEWORK['DEFAULT_PERMISSION_CLASSES']` unless
  set explicitly.
- **`POST /api/sales/` 500 error**: `apps.finance.models.Sale.save()` now
  computes `total_amount` as `Decimal(str(self.quantity)) *
  self.unit_price`, avoiding the `TypeError` from multiplying a `FloatField`
  by a `DecimalField` directly.
- **`GET /api/finance/break-even/` 500 error**: `batch_break_even`'s
  `unit_sale_price` averaging hit the same `FloatField` × `DecimalField`
  `TypeError` as the `Sale.save()` bug above (`Sale.unit_price` is a
  `DecimalField`, `Sale.quantity` a `FloatField`) — caught by the test added
  alongside this endpoint (`FinanceAccessTests.test_break_even_endpoint_reserved_to_admin_and_farm_manager`),
  not by `manage.py check`. Fixed the same way: `Decimal(str(quantity))`
  before multiplying.
- **Feed-stage dropdown pre-fill**: `StockPage.jsx` and
  `OnboardingStockPage.jsx` now map a loaded item's `feed_stage` (backend
  enum, e.g. `"STARTER"`) through `FEED_STAGE_LABELS` before setting
  `StockParametersForm.jsx`'s `detail` field, matching the `<select>`'s
  capitalized option values (e.g. `"Starter"`).

## Translation & localization

- `config/settings.py`'s `LANGUAGE_CODE` is `'fr'`, so Django/DRF's built-in
  user-facing messages (password validators, required-field errors,
  login-failure text, permission-denied text) render in French without
  per-string translation.
- Every UI string is in French; raw backend enum values shown to the user go
  through French label maps (`CATEGORY_LABELS`, `TREND_LABELS`,
  `BATCH_STATUS_LABELS`, `ALERT_STATUS_LABELS`, `ROLE_LABELS`,
  `HOUSE_TYPE_LABELS`, `UNIT_LABELS`, `FEED_STAGE_LABELS`) rather than
  displayed directly — values that round-trip into a backend `TextChoices`
  enum stay in English internally with a separate label map for display, so
  translating the label never sends an invalid enum value to the API.
- Custom backend error strings are translated
  (`apps/core/serializers.py`, `apps/core/views.py`, `apps/houses/views.py`,
  `apps/stock/views.py`, `apps/batches/views.py`,
  `apps/batches/serializers.py`, `apps/stock/serializers.py`) along with the
  two alert-message templates in `apps/alerts/services.py`.

## No seeded data

No management command, fixture, data migration, or hardcoded credential
seeds a `User`/`Farm` anywhere in the repository — verified by grepping
`backend/` and `frontend/` for
`seed_demo|seed_data|demo_user|test123|createsuperuser|initial_data|fixtures?/`
and every migration file for `RunPython`/`bulk_create`/`.objects.create(`.
`docker-compose.yml`/`backend/.env(.example)` contain only local-dev infra
placeholders (`DB_PASSWORD=winchicken`,
`SECRET_KEY=dev-secret-key-change-in-production`), not application account
credentials — see `docs/architecture.md` for the production requirement that
`SECRET_KEY` be set explicitly with no insecure default.
