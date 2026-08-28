# Stock Restructure Implementation Plan

> **For agentic workers:** Execute task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn `/dashboard/stock` into a batch-view-style dashboard (charts + suppliers + a "Mettre à jour le stock" modal), add custom stock categories, a supplier directory, and automatic daily stock consumption driven by the protocol.

**Architecture:** Mirror three patterns that already exist in this codebase: `ProtocolEditModal` (backdrop-blur modal wrapping an existing form, live refetch on save), `ProtocolCategory` + `HouseProtocolForm` "+" tab (custom categories with icon picker), and `_protocol_line_occurrence` (day-range-covers-today check) + `check_low_stock` (StockMovement post_save → LOW_STOCK). New: a static Celery Beat schedule (no `django-celery-beat` dependency) for the daily deduction task.

**Tech Stack:** Django 6.1 + DRF, React 19 + Vite, recharts 3, framer-motion 13, lucide-react, Celery 5 + Redis, PostgreSQL.

**Spec:** the task brief in the session (Parts A–E) — restated per-task below.

## Global Constraints

- Conventional Commits (`feat:` / `fix:` / `chore:`), one commit per Part.
- Transactions where multiple rows are written together (`with transaction.atomic():`).
- Thin views — business logic in `apps/<app>/services.py` or `calculations.py` (see `docs/architecture.md`).
- Python: type hints, early return, no business logic in views. React: functional components + hooks, no business logic in JSX.
- No default farm *data* — structural scaffolding (default categories) is allowed, consistent with `ProtocolCategory` (`apps/houses/signals.py`).
- Do NOT touch Finances (Ventes/Achats/Salaires/Globale) beyond reading existing `StockMovement`/`Expense`.
- Do NOT touch batch action buttons, weighing section, or task assignment.
- Leave `PurchaseOrder.supplier` / `StockMovement.supplier` free-text fields unchanged.
- French user-facing copy; internal enum values stay English.

## Autonomous decisions (also recorded in README / docs/deviations.md)

1. **Celery Beat schedule mechanism:** static `app.conf.beat_schedule` in `config/celery.py` with `crontab(hour=0, minute=0)` — no `django-celery-beat` dependency added. A `run_stock_consumption` management command wraps the same service function for manual/testing runs. Only this one task is wired; the pre-existing unfired SCHEDULED AlertRule types (`PROTOCOL_TASK`, `WEIGHING_REMINDER`, …) stay out of scope.
2. **`StockCategory.kind`** (`FEED|VETERINARY|EQUIPMENT|BEDDING|CUSTOM`, default `CUSTOM`) — a small divergence from the pure `ProtocolCategory` mirror. `StockItem.feed_stage` / `cold_chain_required` semantics must survive a category label rename, so the seeded defaults carry a stable `kind`; the form shows the feed-stage dropdown only for `kind==FEED` rows and the cold-chain toggle only for `kind==VETERINARY`. Custom categories show neither.
3. **`StockMovement.protocol_line`** (FK, nullable, `SET_NULL`) — added so the daily task is idempotent *per batch per protocol row per day* (the spec's exact requirement) and so auto-generated movements are distinguishable from manual ones. `PurchaseOrder`/`StockMovement.supplier` free-text fields still untouched.
4. **Insufficient-stock warning heuristic:** `GET /api/stock-items/{itemCode}/coverage/?quantity_per_day=<n>&days=<span>` returns `{currentQuantity, dailyRate, daysRemaining, daysNeeded, sufficient}`. `dailyRate` = this row's rate + sum of `quantity_per_day` of every *other* `ProtocolTemplate` row across the farm linked to the same item (whether or not its range currently covers today — a planning figure). Non-blocking, warning only.
5. **"Réinitialiser" button** added to `StockParametersForm`'s management save-bar (restores `data` to `initialData`) so the modal offers Save / Cancel (X, backdrop, Esc) / Réinitialiser as the brief asks. The `ProtocolEditModal` pattern being reused has no Réinitialiser; this is additive.
6. **Chart date range:** first `StockMovement.movement_date` for the farm → today, calendar dates (not day-of-cycle — stock is farm-scoped). "All items" overview overlays one line per item (like `GrowthCurves`). Per-item view adds a `ReferenceLine` at `alert_threshold`.
7. **Stock category icons:** curated lucide list `STOCK_CATEGORY_ICON_CHOICES`, defaults Aliment→`Wheat`, Vétérinaire→`Stethoscope`, Équipement→`Wrench`, Litière→`Layers`; frontend `iconFor` falls back to `Package` if a name is absent in the installed lucide build.

---

## Task 1 — Part C: `StockCategory` model + FK migration + seeding + API

**Files:**
- Modify: `backend/apps/stock/models.py` — add `StockCategory`, `StockCategoryKind`, `DEFAULT_STOCK_CATEGORIES`, `STOCK_CATEGORY_ICON_CHOICES`; change `StockItem.category` from `CharField(choices=ItemCategory)` to `ForeignKey(StockCategory)`.
- Modify: `backend/apps/stock/serializers.py` — `StockCategorySerializer`; `StockItemSerializer.category` → PK FK, add `category_label`/`category_kind` read fields; `generate_item_code` takes the category's `kind` (or `CUS`) for the 3-letter prefix.
- Modify: `backend/apps/stock/views.py` — `FarmStockCategoriesView` (GET list / POST create), `StockCategoryDetailView` (DELETE); `FarmStockItemsView.put` resolves `category` id per item; `StockItemsLowCountView` unchanged (works off `current_quantity`).
- Modify: `backend/apps/stock/urls.py` — `farms/<farm_id>/stock-categories/`, `stock-categories/<pk>/`.
- Create: `backend/apps/stock/signals.py` — `seed_default_stock_categories` on `Farm` post_save (mirror `apps/houses/signals.py`).
- Modify: `backend/apps/stock/apps.py` — `ready()` imports `signals`.
- Create migration: `backend/apps/stock/migrations/0002_stockcategory.py` — create `StockCategory`; then a `RunPython` that, for every existing `Farm`, creates the 4 defaults and remaps each `StockItem.category` string → the matching `StockCategory` row (by `kind`); then alter `StockItem.category` to the FK. (Split into 2–3 migration ops as Django requires: add nullable FK `category_new`, data-migrate, remove old `category`, rename.)
- Modify: `backend/apps/finance/calculations.py` — `_ITEM_CATEGORY_TO_EXPENSE_CATEGORY` lookups now key off `item.category.kind` not `item.category`. Grep `purchases_evolution` + any `.item.category` reader.
- Modify: `backend/apps/finance/serializers.py` / `apps/stock` — grep every `ItemCategory` / `.category` reference on `StockItem` (PurchaseOrder serializer, Vaccination flows) and adjust to `.category.kind` or the FK.
- Test: `backend/apps/stock/tests.py` — seeding on farm create; add/delete category endpoints; permission (Admin/FarmManager/Farmer only for write); item code prefix; PUT items with a custom category id.

**Interfaces:**
- Produces: `StockCategory(id, farm, label, icon, sort_order, kind)`; `GET/POST /api/farms/{farmId}/stock-categories/` (`{id,label,icon,sort_order,kind}`); `DELETE /api/stock-categories/{id}/`; `StockItemSerializer` now emits `category` (int id), `category_label`, `category_kind`.

- [ ] **Step 1 — failing test:** `test_new_farm_seeds_four_stock_categories` — create a `Farm`, assert `StockCategory.objects.filter(farm=farm).count() == 4` and kinds == `{FEED,VETERINARY,EQUIPMENT,BEDDING}`.
- [ ] **Step 2 — run, expect fail** (`StockCategory` undefined): `pytest apps/stock/tests.py -k seeds_four -v`
- [ ] **Step 3 — implement** model + `DEFAULT_STOCK_CATEGORIES` + `signals.py` + `apps.py` `ready()`.
- [ ] **Step 4 — migration:** write `0002_stockcategory.py` (create model + `RunPython` forward: for each farm `bulk_create` the 4 defaults; backward: no-op). Add the `StockItem.category` FK transition ops.
- [ ] **Step 5 — run migrations + test:** `python manage.py makemigrations --check --dry-run` then `pytest apps/stock -q` → seeding test passes.
- [ ] **Step 6 — API:** `StockCategorySerializer`, `FarmStockCategoriesView`, `StockCategoryDetailView`, urls. Icon validated against `STOCK_CATEGORY_ICON_CHOICES`. `perform_create` sets `sort_order = max+1`, `kind = CUSTOM`. Delete cascades to items? No — `StockItem.category` is `on_delete=PROTECT` would block; use `on_delete=CASCADE` to match `ProtocolCategory` (deleting a category deletes its items) OR `SET_NULL`. **Decision:** `CASCADE` + the frontend confirm dialog states it (mirrors `ProtocolCategory`). Add test `test_delete_category_cascades_items`.
- [ ] **Step 7 — tests:** add/delete/permission/PUT-items-with-custom-category; `pytest apps/stock apps/finance -q`.
- [ ] **Step 8 — full backend run:** `pytest -q` (fix fallout in finance/batches from the enum→FK change).
- [ ] **Step 9 — commit:** `git add backend/apps/stock backend/apps/finance && git commit -m "feat: custom stock categories (StockCategory FK, per-farm seeding, +/- API)"`

## Task 2 — Part D: `Supplier` model + `StockItem.supplier` + directory API

**Files:**
- Modify: `backend/apps/stock/models.py` — `Supplier(farm, name, contact, email)`; `StockItem.supplier = FK(Supplier, null=True, on_delete=SET_NULL, related_name='items')`.
- Modify: `backend/apps/stock/serializers.py` — `SupplierSerializer` (+ `item_names` SerializerMethodField = `[i.name for i in obj.items.all()]`); `StockItemSerializer` add `supplier` (PK, `allow_null`) + `supplier_name` read.
- Modify: `backend/apps/stock/views.py` — `FarmSuppliersView` (GET/POST), `SupplierDetailView` (GET/PUT/DELETE), all `IsAdminOrFarmManagerOrFarmer` for writes; `FarmStockItemsView.put` sets `supplier_id` per item.
- Modify: `backend/apps/stock/urls.py` — `farms/<farm_id>/suppliers/`, `suppliers/<pk>/`.
- Migration: `0003_supplier.py`.
- Test: `backend/apps/stock/tests.py` — supplier CRUD, `item_names` derivation, linking a supplier via PUT items, permissions.

**Interfaces:**
- Produces: `GET/POST /api/farms/{farmId}/suppliers/`, `GET/PUT/DELETE /api/suppliers/{id}/` → `{id,name,contact,email,item_names}`.

- [ ] Step 1 — failing test `test_supplier_crud_and_item_link`.
- [ ] Step 2 — run, expect fail.
- [ ] Step 3 — model + migration.
- [ ] Step 4 — serializer + views + urls.
- [ ] Step 5 — `FarmStockItemsView.put` handles `supplier`.
- [ ] Step 6 — `pytest apps/stock -q`.
- [ ] Step 7 — commit: `feat: supplier directory (Supplier model, StockItem.supplier FK, CRUD API)`

## Task 3 — Part E: protocol-driven daily stock consumption

**Files:**
- Modify: `backend/apps/protocols/models.py` — `ProtocolTemplate.stock_item = FK('stock.StockItem', null=True, on_delete=SET_NULL, related_name='protocol_lines')`, `quantity_per_day = FloatField(null=True, blank=True)`.
- Modify: `backend/apps/protocols/serializers.py` — add both fields to `ProtocolTemplateSerializer.Meta.fields` (+ help_text). Both write paths (`HouseProtocolView.put`, `OnboardingView.post`) spread `**line` → new fields flow automatically; verify `time_slots` pop still fine.
- Modify: `backend/apps/stock/models.py` — `StockMovement.protocol_line = FK('protocols.ProtocolTemplate', null=True, blank=True, on_delete=SET_NULL, related_name='stock_movements')`.
- Create: `backend/apps/stock/services.py` — `run_daily_consumption(today=None) -> list[StockMovement]`: iterate `PoultryBatch.objects.filter(status=ACTIVE)`, `day_of_cycle = (today - batch.start_date).days`, for each `ProtocolTemplate` of `batch.house` with `stock_item_id` and `quantity_per_day`, if `_protocol_line_occurrence(line, day_of_cycle)` not None and not `StockMovement.objects.filter(item=line.stock_item, batch=batch, protocol_line=line, movement_date=today, movement_type=OUT).exists()` → create `StockMovement(OUT, quantity=quantity_per_day, movement_date=today, batch=batch, protocol_line=line)`. One `transaction.atomic()`. Import `_protocol_line_occurrence` from `apps.houses.services`.
- Create: `backend/apps/stock/coverage.py` (or in `calculations.py`) — `coverage_for(item, quantity_per_day, days) -> dict`.
- Create: `backend/apps/stock/tasks.py` — `@shared_task deduct_daily_stock_consumption()` → calls `run_daily_consumption()`.
- Modify: `backend/config/celery.py` — `from celery.schedules import crontab`; `app.conf.beat_schedule = {'daily-stock-consumption': {'task': 'apps.stock.tasks.deduct_daily_stock_consumption', 'schedule': crontab(hour=0, minute=0)}}`.
- Create: `backend/apps/stock/management/commands/run_stock_consumption.py` — calls `run_daily_consumption()`, prints count.
- Modify: `backend/apps/stock/views.py` — `StockItemCoverageView` GET `stock-items/<item_code>/coverage/`.
- Modify: `backend/apps/stock/urls.py`.
- Migration: `0004_protocolline_consumption.py` (protocols) + `0005_stockmovement_protocol_line.py` (stock) — or one each per app.
- Tests: `backend/apps/stock/tests.py` — `run_daily_consumption` creates one OUT per matching row; **idempotent** on second run same day; range boundary (not due → nothing); LOW_STOCK fires when the new OUT crosses `alert_threshold` (assert an `Alert` with `rule_type=LOW_STOCK`); coverage endpoint math. `backend/apps/protocols/tests.py` — protocol PUT round-trips `stock_item`/`quantity_per_day`.

**Interfaces:**
- Consumes: `apps.houses.services._protocol_line_occurrence`, `apps.stock.calculations.current_quantity`, `apps.alerts.services.check_low_stock` (via existing `StockMovement` post_save signal — no new wiring).
- Produces: `run_daily_consumption(today=None)`, `coverage_for(item, quantity_per_day, days)`, `GET /api/stock-items/{code}/coverage/`.

- [ ] Step 1 — failing test `test_daily_consumption_creates_one_out_per_row`.
- [ ] Step 2 — failing test `test_daily_consumption_is_idempotent_same_day`.
- [ ] Step 3 — failing test `test_daily_consumption_triggers_low_stock_alert`.
- [ ] Step 4 — run, expect all fail.
- [ ] Step 5 — models + migrations + serializer fields.
- [ ] Step 6 — `services.run_daily_consumption` + `tasks.py` + `celery.py` beat + management command.
- [ ] Step 7 — `coverage_for` + `StockItemCoverageView` + url + coverage test.
- [ ] Step 8 — `pytest apps/stock apps/protocols apps/alerts -q`, then `pytest -q`.
- [ ] Step 9 — commit: `feat: automatic daily stock consumption from protocol (beat task + coverage warning)`

## Task 4 — Part B: stock evolution chart API

**Files:**
- Modify: `backend/apps/stock/calculations.py` — `stock_evolution(farm) -> list[dict]`: `[{itemCode, name, unit, alertThreshold, points: [{date, quantity}]}]`, running balance of `StockMovement` (IN +, OUT −) ordered by `movement_date`, one point per date a movement exists (carry-forward handled client-side or emit daily — **decision:** emit one point per distinct movement date, cumulative; front draws a step/line).
- Modify: `backend/apps/stock/views.py` — `FarmStockEvolutionView` GET `farms/<farm_id>/stock-evolution/`.
- Modify: `backend/apps/stock/urls.py`.
- Test: `backend/apps/stock/tests.py` — running balance correct across IN/OUT; threshold echoed; empty when no movements.

**Interfaces:**
- Produces: `GET /api/farms/{farmId}/stock-evolution/` → `[{itemCode,name,unit,alertThreshold,points:[{date,quantity}]}]`.

- [ ] Step 1 — failing test `test_stock_evolution_running_balance`.
- [ ] Step 2 — run, expect fail.
- [ ] Step 3 — implement calc + view + url.
- [ ] Step 4 — `pytest apps/stock -q`.
- [ ] Step 5 — commit: `feat: stock evolution series endpoint (running StockMovement balance by calendar date)`

## Task 5 — Part A + C/D/E frontend

**Files:**
- Modify: `frontend/src/api/endpoints.js` — `stockApi`: `categories(farmId)`, `addCategory(farmId,payload)`, `removeCategory(id)`, `suppliers(farmId)`, `addSupplier(farmId,payload)`, `updateSupplier(id,payload)`, `removeSupplier(id)`, `evolution(farmId)`, `coverage(itemCode, params)`.
- Create: `frontend/src/components/StockParametersModal.jsx` — mirror `ProtocolEditModal.jsx`: `motion` backdrop `blur(6px)`, `.protocol-modal-*` classes, focus trap, Esc, dirty capture, `onSaved` refetch; wraps `<StockParametersForm mode="management" .../>`; fetches items+categories+suppliers, on save calls `stockApi.putItems`, then `onClose()` + `onSaved()`.
- Rewrite: `frontend/src/pages/dashboard/StockPage.jsx` — dashboard layout: `<StockEvolutionChart/>`, `<SuppliersSection/>`, a "Mettre à jour le stock" button that opens `<StockParametersModal/>`; `onSaved` refetches chart + suppliers. Keep `tabifyItems` shape but key tabs by category id, not the fixed map.
- Create: `frontend/src/components/StockEvolutionChart.jsx` — recharts `LineChart`; item `<select>` + "Tous les articles" option; `ReferenceLine y={alertThreshold}` (per-item view only); X = `date`, Y = `quantity`. Empty state when no points.
- Create: `frontend/src/components/SuppliersSection.jsx` — list `name / contact / email / item_names`; add/edit/delete inline (role-gated via `useAuth().user.role in ['ADMIN','FARM_MANAGER','FARMER']`).
- Rewrite: `frontend/src/components/StockParametersForm.jsx` — replace hardcoded `TABS`/`CATEGORY_BY_TAB`/`PANEL_META` with dynamic categories (`initialCategories` prop, `[{id,label,icon,kind}]`); add the "+" tab + icon-picker + delete-confirm from `HouseProtocolForm` (management persists via `stockApi.addCategory/removeCategory`, onboarding local-only); "Détail" column: feed-stage `<select>` when `activeCategory.kind==='FEED'`, cold-chain `<select>` when `'VETERINARY'`, hidden otherwise; add supplier `<select>` per row with inline "+ Nouveau fournisseur"; add "Réinitialiser" button (management save-bar). `buildPayload().items[]` gains `category` (id), `supplier` (id|null).
- Modify: `frontend/src/pages/onboarding/OnboardingStockPage.jsx` + `frontend/src/context/OnboardingContext.jsx` — pass `initialCategories` (fetch `stockApi.categories(farm)` — they're seeded at farm creation), thread `customCategories` through onboarding submit if any; supplier select optional here (can defer suppliers to management — **decision:** onboarding shows no supplier column, management does).
- Modify: `frontend/src/components/HouseProtocolForm.jsx` — each protocol row gets "Article de stock consommé" `<select>` (options from `stockApi.categories`? no — from stock items; needs an items fetch) + "Quantité/jour" number input; when both set, debounced `stockApi.coverage(itemCode,{quantity_per_day,days})` → inline warning text when `!sufficient`. `makeRow` gains `stockItemCode:null`, `quantityPerDay:""`. `buildPayload` protocol lines gain `stock_item`, `quantity_per_day`.
- Modify: `frontend/src/components/ProtocolEditModal.jsx` — `buildSchedules` maps `line.stock_item`/`line.quantity_per_day` into row shape; fetch stock items list to pass to the form.
- Modify: `frontend/src/demo/DemoPage.jsx` — pass a static `DEMO_STOCK_CATEGORIES` so the demo form still renders.
- Modify: `frontend/src/styles/dashboard-theme.css` (or a new `stock-page.css`) — layout for the new dashboard sections.
- Tests: `frontend/src/components/__tests__/StockParametersModal.test.jsx` (opens form, save → onClose+onSaved), `StockEvolutionChart.test.jsx` (renders lines + reference line), and update any snapshot/behaviour tests touching `StockParametersForm`/`StockPage`.

- [ ] Step 1 — `endpoints.js` additions.
- [ ] Step 2 — `StockParametersForm.jsx` rewrite to dynamic categories + supplier select + Réinitialiser; run `npm test -- StockParametersForm` / add coverage.
- [ ] Step 3 — `StockParametersModal.jsx` + test.
- [ ] Step 4 — `StockEvolutionChart.jsx` + `SuppliersSection.jsx` + tests.
- [ ] Step 5 — `StockPage.jsx` rewrite wiring all three + modal.
- [ ] Step 6 — onboarding + demo adjustments.
- [ ] Step 7 — `HouseProtocolForm.jsx` + `ProtocolEditModal.jsx` consumption fields + coverage warning.
- [ ] Step 8 — `npm run test` + `npm run build` (or `npx vite build`) green.
- [ ] Step 9 — commit: `feat: stock dashboard (charts + suppliers + update-stock modal), protocol consumption fields`

## Task 6 — Schema + docs

**Files:**
- Modify: `farm_management_schema_en.puml` — add `StockCategory`, `Supplier`; `StockItem.category : int <<FK>>` + `supplier_id : int <<FK>>`; `ProtocolTemplate.stockItem_id` + `quantityPerDay`; `StockMovement.protocolLine_id`; relationship lines (`Farm ||--o{ StockCategory`, `Farm ||--o{ Supplier`, `StockCategory ||--o{ StockItem`, `Supplier ||--o{ StockItem`, `StockItem ||--o{ ProtocolTemplate`, `ProtocolTemplate ||--o{ StockMovement`).
- Modify: `README.md` — "Autonomous decisions" list: the 7 decisions above.
- Modify: `docs/deviations.md` — new numbered Part: daily-task scheduling mechanism (static beat schedule, only this task wired), `StockCategory.kind` divergence, `StockMovement.protocol_line` addition, coverage heuristic, and the `PurchaseOrder`/`StockMovement` free-text `supplier` migration deferral (future task could FK them to `Supplier`).
- Modify: `docs/data-model.md` / `docs/api-reference.md` if they enumerate stock endpoints/models (grep first).

- [ ] Step 1 — puml edits.
- [ ] Step 2 — README + deviations.
- [ ] Step 3 — data-model / api-reference if present.
- [ ] Step 4 — commit: `docs: schema + deviations for stock restructure`

## Verification (from the brief)

1. `/dashboard/stock` shows charts + Fournisseurs by default; parameter form only opens via "Mettre à jour le stock"; on save the modal closes and charts refresh.
2. Add a custom stock category via "+" → persists (reload).
3. Add a supplier, link it to a stock item → appears in Fournisseurs with the item listed.
4. Link a feeding protocol row to a stock item with a daily qty exceeding current stock before period end → inline warning shows, save still allowed.
5. Run `python manage.py run_stock_consumption` twice same day → one `StockMovement` OUT per matching row, no duplicate on the 2nd run; a `LOW_STOCK` `Alert` appears once quantity crosses `alert_threshold`.
6. `pytest -q` and `npm run test` green; `npm run build` succeeds.

## Self-review notes

- Spec coverage: A→Task 5; B→Task 4 + Task 5 chart; C→Task 1 + Task 5 form; D→Task 2 + Task 5 section/select; E→Task 3 + Task 5 form warning; schema/docs→Task 6. ✓
- Enum→FK ripple (Task 1) is the highest-risk step — `grep -rn "ItemCategory\|\.category" backend/apps/{stock,finance,batches}` before editing; run the full backend suite at Step 8.
- `StockMovement` post_save already calls `check_low_stock` — Task 3 needs NO new signal, only a test proving it still fires for task-created movements.
