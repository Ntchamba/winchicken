# Deviations from the spec documents

Every point below where the implementation differs from
`winchicken-cahier-des-charges.docx` and/or `winchicken-spec-implementation-detaillee.docx`.
Part 1 re-verifies the root `README.md`'s "Autonomous decisions made during this build"
list against the current code (all still hold). Part 2 lists further deviations found
during this documentation pass (schema/docstring review) that weren't already in the
README.

## Part 1 — README's "Autonomous decisions", re-verified against current code

1. **`HomeDashboard.jsx` / `dashboard-theme.css` authored from scratch, wired to real
   API data.** Confirmed: `frontend/src/components/HomeDashboard.jsx` and
   `frontend/src/styles/dashboard-theme.css` both exist; `HomeDashboard` takes
   `houses`/`alerts`/`stats` as props from real API shapes (see its JSDoc block) rather
   than any hardcoded data.

2. **`HouseProtocolForm.jsx` re-themed to the light design system; starter template
   moved behind an explicit button, never auto-loaded.** Confirmed:
   `frontend/src/components/HouseProtocolForm.jsx` imports
   `../styles/house-protocol-theme-light.css` only, and `STARTER_TEMPLATE` is applied
   exclusively by `loadStarterTemplate()`, wired to an explicit "Load starter template"
   button — the form's initial state is always `EMPTY_SCHEDULES` unless
   `initialSchedules` is passed in by the caller (real data when editing an existing
   house).

3. **Fixed/superseded since first written.** Full containerization
   (`docker-compose.yml`: db + redis + web + worker + frontend) added mid-build;
   Docker access was initially blocked (no `docker` group membership, no sudo). Since
   resolved without root by installing a **rootless** Docker daemon (the
   `docker-ce-rootless-extras` package was already present) — see the root
   `README.md`'s "If `docker compose up` fails with a permission error" section. The
   full stack has since been built and run live: all 5 containers healthy, migrations
   applied, and the entire flow (farm creation → 409 rejection → onboarding →
   `is_configured` flip → employee login → daily logs → sales/expenses → finance
   summary → PO receiving → batch closing → double-close rejection) exercised directly
   against the running API and confirmed correct, then the database flushed back to
   empty. Two frontend files (`DashboardLayout.jsx`, `sidebar-theme.css`) also turned
   out to have restrictive `600` permissions left over from their original copy, which
   rootless Docker's UID-namespace remapping turned into `EACCES` errors reading them
   from inside the `frontend` container — fixed with `chmod 664` on both.

4. **`is_configured` = farm has ≥1 `PoultryHouse` with ≥1 `ProtocolTemplate` line AND
   ≥1 `StockItem`.** Confirmed verbatim in `apps/core/services.py:is_farm_configured`.

5. **`houseCode`/`batchCode`/`itemCode`/`orderCode`/`faultCode`/`caseCode` are all
   server-generated.** Confirmed: `apps/houses/serializers.py:generate_house_code`
   (`H-{farmId}-{seq}`), `apps/batches/serializers.py:generate_batch_code`
   (`BATCH-{year}-{seq}`), `apps/stock/serializers.py:generate_item_code`
   (`{CAT3}-{farmId}-{seq}`), `apps/finance/serializers.py:PurchaseOrderSerializer.create`
   (`PO-{farmId}-{seq:04d}`), `apps/maintenance/serializers.py:EquipmentFaultSerializer.create`
   (`FAULT-{houseCode}-{seq}`), `apps/maintenance/serializers.py:UnusualCaseSerializer.create`
   (`CASE-{batchCode}-{seq}`). None of these are writable client-submitted fields.

6. **`GET /api/health/` added, not in the cahier des charges endpoint list.** Confirmed:
   `apps/core/urls.py` + `apps/core/views.py:HealthCheckView`; absent from cahier des
   charges section 10.

7. **`POST /api/contact/` and `POST /api/newsletter/` added.** Confirmed: both public
   (`AllowAny`), absent from cahier des charges section 10, present as buttons on
   `frontend/src/pages/LandingPage.jsx`, matching implementation-detail spec 1.3.

8. **`PATCH /api/purchase-orders/{orderCode}/` added to implement "receiving generates a
   StockMovement IN".** Confirmed: `apps/finance/urls.py` + `PurchaseOrderDetailView`;
   the side effect is in `apps/finance/serializers.py:PurchaseOrderSerializer.update`.
   Also confirmed absent from cahier des charges section 10 (which lists only
   `GET`/`POST /api/purchase-orders/`).

9. **`roiForecastPct`'s `total_investment` = sum of `RECEIVED` `EQUIPMENT`-category
   `PurchaseOrder`s over the period; stays `null` until one exists.** Confirmed in
   `apps/finance/calculations.py:roi_forecast_pct` — matches the README's description
   exactly, including the missing "or a manually entered value" fallback the spec
   allows (see spec section 5.4; no field/table exists for a manual entry).

10. **SMS sending defaults to a `console` provider.** Confirmed:
    `SMS_PROVIDER=console` default in `config/settings.py` and `.env.example`;
    `apps/alerts/providers/console.py:ConsoleSmsProvider` logs instead of sending;
    `apps/alerts/providers/__init__.py:get_sms_provider` raises `NotImplementedError`
    for any other `SMS_PROVIDER` value (no second provider is implemented yet).

11. **Landing page product imagery is CSS gradient placeholder blocks.** Confirmed:
    `frontend/src/pages/LandingPage.jsx` uses `linear-gradient(...)` inline styles for
    its imagery blocks; no image assets are referenced there.

12. **Dashboard overview's "weekly mortality" stat shows "—" (not computed
    farm-wide); per-batch weekly mortality is fully computed via
    `kpi/weekly/`.** Confirmed: `HomeDashboard.jsx` renders
    `weeklyMortalityPct != null ? ... : "—"` and there is indeed no farm-wide
    weekly-mortality aggregate endpoint anywhere in `apps/batches` — only the
    per-batch `GET /api/batches/{batchCode}/kpi/weekly/`.

13. **Employee edit/delete actions on `/dashboard/employees` (pencil/trash icons,
    confirm-before-delete).** Confirmed in
    `frontend/src/pages/dashboard/EmployeesPage.jsx`: `Pencil`/`Trash2` icons,
    `confirmDeleteId` state gating a "Confirm"/"Cancel" step before
    `employeesApi.remove`.

## Part 2 — further deviations found during this documentation pass

14. **`ProtocolTemplate` (and the whole `apps.protocols` app) is entirely absent from
    `farm_management_schema_en.puml`** — no class, no relationship, no note anywhere in
    the puml file. It *is* listed in the cahier des charges section 10 app table
    ("protocols → ProtocolTemplate"), so this is the puml being out of date relative to
    the cahier des charges, not an undocumented addition. See `docs/data-model.md`.

15. **No Celery Beat schedule is configured anywhere in the project**
    (`backend/config/celery.py` has no `beat_schedule`, and no other file registers
    one). Consequence: `AlertRule.trigger_mode = SCHEDULED` rows (feeding-time
    reminders, scheduled vaccinations per the puml's own note on `AlertRule`) can be
    created through `POST /api/alert-rules/` but nothing ever evaluates their
    `trigger_time`/`frequency`/`active_days` fields — they never actually fire. Only
    the two `EVENT`-mode rule types with a wired Django signal (`LOW_STOCK` via
    `StockMovement.post_save`, `CONSUMPTION_DEVIATION` via `DailyLog.post_save`, both in
    `apps/alerts/signals.py`) ever produce a real `Alert`.

16. **`VACCINE_DUE`, `PROFITABILITY_THRESHOLD`, `SANITARY_VOID_END` alert types are
    defined but never triggered by any code path** — valid `AlertRuleType` choices,
    creatable via the API, but no service function or signal ever calls
    `trigger_alert(rule_type=...)` with any of these three values. Only `LOW_STOCK` and
    `CONSUMPTION_DEVIATION` are wired (see #15).

17. **`Alert.status` never transitions past its default `NEW`** — there is no
    `PATCH`/`PUT` endpoint on `Alert` anywhere in `apps/alerts/urls.py`
    (`AlertListView` is `ListAPIView`, read-only). Nothing in the codebase ever sets a
    status of `SENT` or `RESOLVED`, despite `AlertStatus` defining both.

18. **`EquipmentFault` and `UnusualCase` have no update endpoint** — both
    `apps/maintenance/urls.py` routes are `ListCreateAPIView` only. There is no way to
    set `EquipmentFault.repaired_date`/advance its `status` past the default
    `"REPORTED"`, or to edit a submitted `UnusualCase`, through the API. This leaves
    the cahier des charges section 8 permission-matrix row "Valider une tâche de
    maintenance" (Technician / assigned Worker) with no corresponding endpoint to
    apply that permission to.

19. **`GET/POST /api/vaccinations/` and `GET/POST /api/unusual-cases/` have no role
    restriction beyond `IsAuthenticated`** — `VaccinationListCreateView` and
    `UnusualCaseListCreateView` both omit any `get_permissions()`/role-specific
    `permission_classes` override, unlike almost every other write endpoint in the
    project. Any authenticated user of the farm can create a vaccination event or an
    unusual-case report, even though the cahier des charges section 8 permission matrix
    implies these are role-specific actions (e.g. case reporting: Farmer/Worker).

20. **`apps.finance.calculations.bfr_estimate`, `break_even_quantity`, and
    `safety_margin_pct` are implemented per the spec's formulas but never called from
    any view, serializer, or URL** — dead code as far as the API surface is concerned.
    No endpoint exposes working-capital-requirement (`bfr_estimate`), break-even
    quantity, or safety-margin figures, despite all three being fully implemented in
    `apps/batches/calculations.py` and `apps/finance/calculations.py`. See
    `docs/calculations.md`.

21. **Fixed since first written.** The SMS body sent to the provider was the
    idempotency key, not the alert's message text — `apps/alerts/tasks.py:send_sms_task`
    called `provider.send(sms.recipient, sms.idempotency_key)` instead of
    `sms.alert.message`. A real SMS gateway would have sent a meaningless 40-character
    hash to the recipient's phone instead of the intended alert text (e.g. "Starter feed
    below threshold..."). Now reads `provider.send(sms.recipient, sms.alert.message)`;
    `idempotency_key` still does its actual job (the uniqueness constraint /
    `get_or_create` dedup key in `apps.alerts.services.trigger_alert`), it's just no
    longer conflated with the message body.

22. **Fixed since first written.** `DashboardShell.jsx` hardcoded every house's `type` to
    `"Broiler"` regardless of its actual `PoultryBatch.production_type`
    (BROILER/PULLET/LAYER), so the `Bird`/`Egg` icon selection in `DashboardLayout.jsx`
    (sidebar) and `HomeDashboard.jsx` (house list) could never render `Egg` even for a
    house whose active batch is a LAYER batch. `DashboardShell.jsx` now also fetches
    `GET /api/batches/` alongside `GET /api/houses/` and derives each house's `type` from
    its active batch's `production_type` (defaulting to `"Broiler"` only for a house with
    no active batch, e.g. an empty sanitary void) before passing `houses` down through
    `<Outlet context={{ houses }} />`.

23. **The API's JSON field-naming convention is inconsistent, both across and within
    endpoints.** Every `ModelSerializer`-backed endpoint (houses, batches, daily-logs,
    stock items, movements, vaccinations, faults, cases, expenses, sales, purchase
    orders, alert rules, alerts, sms-messages, notification-preferences) returns
    **snake_case** field names by default (DRF's default, e.g. `house_code`,
    `total_amount`, `feed_conversion_ratio`), matching what the frontend actually
    expects (see `frontend/src/api/endpoints.js` and the `buildPayload()` functions in
    `HouseProtocolForm.jsx`/`StockParametersForm.jsx`, which all send snake_case keys).
    A handful of hand-built-dict endpoints instead return **camelCase** keys throughout
    — `weekly_kpi`, `finance_summary`, `expense_category_breakdown`, `OnboardingView`'s
    response, and `FinanceTransactionsView`'s merged transaction rows — matching the
    implementation-detail spec's section 11 examples literally. And at least one
    `ModelSerializer`-backed endpoint mixes both conventions in the same response:
    `AlertSerializer` (`GET /api/alerts/`) declares
    `ruleType = serializers.CharField(source='rule.rule_type', read_only=True)`
    alongside otherwise-snake_case fields (`triggered_at`, `batch`, ...), so a single
    `Alert` JSON object has both `triggered_at` and `ruleType` side by side. The
    `PATCH /api/batches/{batchCode}/close/` response is the clearest cross-endpoint
    example: the spec's section 11.4 example shows camelCase
    (`totalMortalityPct`, `feedConversionRatio`, ...), but the real
    `BatchClosingReportSerializer` (a `ModelSerializer`) returns snake_case
    (`total_mortality_pct`, `feed_conversion_ratio`, ...) — the *values*/formulas match
    the spec exactly, but the literal JSON key casing does not. See
    `docs/api-reference.md` for the concrete example.

24. **Fixed since first written.** `/api/schema/` and `/api/docs/` were reachable
    **unauthenticated** despite `config/settings.py`'s comment and `config/urls.py`'s
    comment both asserting they inherit the project's default `IsAuthenticated`
    permission. Caught by live testing against the running Docker stack: both endpoints
    returned `200` with no `Authorization` header. Root cause: `SpectacularAPIView` and
    `SpectacularSwaggerView` default their own `permission_classes` to `AllowAny`
    internally, which silently overrides `REST_FRAMEWORK['DEFAULT_PERMISSION_CLASSES']`
    — neither view actually looks at that global default. Fixed by adding
    `SPECTACULAR_SETTINGS['SERVE_PERMISSIONS'] = ['rest_framework.permissions.IsAuthenticated']`;
    both endpoints now correctly return `401` unauthenticated (verified live).

25. **Fixed since first written.** `POST /api/sales/` returned a `500` for every request.
    `apps.finance.models.Sale.save()` computed `self.total_amount = self.quantity *
    self.unit_price`, but `quantity` is a `FloatField` and `unit_price` a
    `DecimalField` — Python raises `TypeError: unsupported operand type(s) for *:
    'float' and 'decimal.Decimal'` rather than silently coercing. Caught by live
    testing (recording a sale against the running stack), not by `manage.py check` or
    the OpenAPI schema generation, since it's a runtime error in model logic, not a
    startup-time or schema-introspection error. Fixed by multiplying
    `Decimal(str(self.quantity))` instead; verified live (`POST /api/sales/` now
    returns `201` with the correct `total_amount`, and it flows through correctly into
    `GET /api/finance/summary/`, `GET /api/finance/transactions/`, and
    `BatchClosingReport.revenue` on batch closing).

## Part 3 — Landing page v2 / login routing verification / Finance access restriction (2026-08-25)

26. **Landing page (`/`) replaced with a single welcome screen**, superseding cahier des
    charges §6 and implementation-detail spec §1 (both updated in place, not just here).
    Removed entirely, not hidden with CSS: the navbar, Contact section, technical-specs
    section, Features section, old CTA section, newsletter bar, and footer — along with
    their dead React state/handlers (`contactForm`/`newsletterEmail`,
    `submitContact`/`submitNewsletter`) from `LandingPage.jsx`. New content: a
    `.brand-mark` logo, "Welcome from Winchicken" heading, one-line subtext, a "Voir une
    démo" button opening a modal video player (`frontend/src/components/DemoVideoModal.jsx`
    — controls visible, closable via Escape or backdrop click), and a "Se connecter"
    button as the page's only navigation, routed by `GET /api/farm/exists/` exactly as
    before. Framer Motion fade-up applies to the logo/heading/subtext/buttons only, no
    scroll-triggered animation (the screen doesn't scroll). `frontend/public/demo.mp4` is
    a **placeholder path, not a committed file** — no real product video exists yet; drop
    the actual file at that path to wire up the button (noted in root `README.md`). `/demo`
    (the interactive client-side demo — `frontend/src/demo/DemoPage.jsx`) is **kept**, not
    replaced: it exercises real `HomeDashboard`/`HouseProtocolForm`/`StockParametersForm`
    components against fixture data, which a video walkthrough can't substitute for — the
    two are additive (video for a quick look, `/demo` for hands-on exploration), not
    redundant. `frontend/src/api/endpoints.js`'s `publicApi` (the `contact`/`newsletter`
    wrappers) was removed as dead code along with the sections that called it. Backend
    `POST /api/contact/` and `POST /api/newsletter/` (deviation #7 above) are **left in
    place** despite now having no frontend caller — they're small, generic,
    `AllowAny`-public endpoints with no other coupling to the landing page's markup, so
    removing them wasn't judged worth the churn versus simply noting here that they're
    presently unreferenced from the UI.

27. **Login routing straight to `/dashboard` (no intermediate screen) — verified already
    correct, no code change needed.** `LoginPage.jsx`'s `handleSubmit` already navigates
    on the *login response itself* (`data.is_configured`, returned directly by
    `WinchickenTokenObtainPairSerializer.validate`), not a second round-trip — so there's
    no separate confirmation step between a successful login and the dashboard render, for
    any role. `ProtectedRoute.jsx` independently enforces the same rule
    (`!user.is_configured` → `/onboarding/protocol`) for direct URL access. Confirmed live
    against the running stack: `POST /api/auth/login/` for both an Admin and a freshly
    created Farmer employee on the same (already-configured) farm each returned
    `is_configured: true` directly in the login payload, with `GET /api/auth/me/`
    corroborating it — exactly the condition `LoginPage.jsx` checks before calling
    `navigate("/dashboard", { replace: true })`.

28. **`GET /api/finance/summary/` restructured to a role-branched payload** implementing
    the Finance access matrix (cahier des charges §8 / implementation-detail spec §4.3+§8,
    both updated in place): the view's `permission_classes` changed from
    `IsAdminOrFarmManager` to `IsAuthenticated`, and its response now always includes an
    `access` field. Admin / Farm Manager get `access: "full"` plus the original payload
    (`months`, `cashOnHand`, `pendingPayables`, `roiForecastPct`) unchanged; every other
    role gets `access: "restricted"` plus only `revenueTrend`/`expenseTrend` (`"up"` /
    `"down"` / `"flat"`, from `apps.finance.calculations.finance_trend_direction` —
    comparing the two most recent months in the window) — no monetary figures at all.
    `FinanceExpenseCategoriesView` and `FinanceTransactionsView` are **unchanged**
    (`IsAdminOrFarmManager`, still `403` for every other role) since those two carry exact
    amounts and per-transaction detail that the restricted view must never expose, even to
    a direct API call. `frontend/src/pages/dashboard/FinancePage.jsx` renders either shape
    (skipping the expense-categories/transactions fetches entirely when
    `summary.access !== "full"`, rather than firing them and discarding a `403`), and
    `DashboardShell.jsx`'s `canSeeFinance` prop was dropped so the sidebar link falls back
    to `DashboardLayout`'s `true` default for every role — the link itself is no longer
    role-gated, only its content is, per the updated permission-matrix rows. Verified live
    against the running stack: an Admin's `GET /api/finance/summary/` returned
    `access: "full"` with `cashOnHand`; a Farmer employee's returned
    `access: "restricted"` with only `revenueTrend`/`expenseTrend`, and that same Farmer's
    `GET /api/finance/expense-categories/` and `GET /api/finance/transactions/` both
    returned `403`. Backend coverage added in `apps/finance/tests.py`
    (`FinanceAccessTests`, 6 cases, all passing) — none of the other seven apps had any
    tests before this (all `tests.py` files were empty Django stubs), so this is the first
    real test module in the project.

30. **Audit pass (2026-08-25, same day as #26–28): `/dashboard/finance` was correctly, not
    mistakenly, touched by deviation #28 above.** `/` (`frontend/src/pages/LandingPage.jsx`)
    and `/dashboard/finance` (`frontend/src/pages/dashboard/FinancePage.jsx`) are separate
    routes rendering separate components (`frontend/src/App.jsx` lines 31 and 50) with no
    aliasing or shared file — re-confirmed by direct inspection, not by trusting the prior
    session's own account. `LandingPage.jsx`/`landing.css` already matched the "single
    welcome screen" spec exactly (verified bullet-by-bullet: no navbar/Contact/specs/
    Features/old-CTA/newsletter/footer present; welcome heading, subtext, `.brand-mark`,
    "Voir une démo" modal, "Se connecter" routed by `GET /api/farm/exists/`, fade-up-only
    animation), so no landing-page changes were needed this pass. The Finance changes were
    re-checked against the spec independently (not assumed correct) and confirmed legitimate
    Part C work: `FinanceSummaryView` is `IsAuthenticated`-gated with server-side role
    branching (`access: "full"` for Admin/Farm Manager, `"restricted"` otherwise — no
    monetary fields in the restricted branch), and `FinanceExpenseCategoriesView`/
    `FinanceTransactionsView` remain `IsAdminOrFarmManager`-only. One real defect found and
    fixed: `apps/finance/tests.py`'s `_user()` helper passed a hardcoded literal password
    (`'pw12345!'`) to `create_user()` that was never actually used for authentication (the
    tests authenticate via `RefreshToken.for_user()` directly, bypassing password login
    entirely) — removed; `create_user()` now runs with no password argument (defaults to an
    unusable one), tests re-verified passing. A repo-wide grep
    (`seed_demo|seed_data|demo_user|test123|createsuperuser|initial_data|fixtures?/`,
    plus a broader `password\s*[:=]\s*['"]...` sweep, backend `management/commands/` and
    every migration file for `RunPython`/`bulk_create`/`.objects.create(`) found nothing
    else — no seed command, no fixture, no data migration, no other hardcoded credential
    anywhere in `backend/` or `frontend/`. `docker-compose.yml`/`backend/.env(.example)`
    contain only pre-existing local-dev infra placeholders (`DB_PASSWORD=winchicken`,
    `SECRET_KEY=dev-secret-key-change-in-production`) — not application account
    credentials, not touched by any prior session, out of scope for the "no seeded
    User/Farm accounts" rule this audit was checking. The prior session *did* leave two
    pieces of runtime-only state in the shared dev database (never in source): it reset
    the existing dev admin's password via `manage.py shell` to run a live verification
    call, and created one test `FARMER` employee through the real `POST /api/employees/`
    endpoint — both disclosed in that session's own final report, neither ever written to
    a repo file. Cleared with `python manage.py flush --no-input` (confirmed `Farm.objects.count() == 0`
    and `User.objects.count() == 0` immediately after). Re-verified Parts B and C end to
    end from that clean slate using only the real flows — `POST /api/farm/create/` for a
    fresh admin, `POST /api/protocols/onboarding/` + `PUT
    /api/farms/{id}/stock-items/` to flip `is_configured`, `POST /api/employees/` for a
    fresh Farmer and a fresh Cashier — with every password generated per-run by `openssl
    rand` in the shell and never written to disk. All confirmed live: admin's `POST
    /api/auth/login/` returned `is_configured: true` directly (no intermediate screen);
    the Farmer employee's login on the same already-configured farm did too; the Farmer's
    `GET /api/finance/summary/` returned `access: "restricted"` with no monetary fields,
    and both detail endpoints `403`'d; the Cashier's summary was likewise `restricted` while
    `POST /api/sales/` still returned `201`. Database flushed back to zero rows again as
    the final state.

## Part 4 — Full French-language pass (2026-08-25)

31. **"POULET À VOIE" does not exist anywhere in the codebase.** A follow-up task asked
    to fix a login-card eyebrow label reading "POULET À VOIE" — grepped the whole
    frontend for that string and any variant; zero matches. Every eyebrow label
    (`LoginPage.jsx`, `CreateFarmPage.jsx`, `DashboardLayout.jsx`, and five page-header
    instances) already read "WINCHICKEN". No change made; reported rather than
    fabricating a fix for a bug that isn't there.

32. **Every remaining English UI string translated to French**, across `/`, `/login`,
    `/create-farm`, onboarding steps 1–3, `/dashboard` and all its sub-screens, the
    sidebar, and `/demo` — roughly 25 frontend files touched. Terminology kept consistent
    with the cahier des charges and with wording already established elsewhere in the
    app (role names: Fermier, Ouvrier, Technicien, Caissier, Gérant de ferme,
    Administrateur, Administrateur secondaire; "Se connecter", "Créer la ferme",
    "Suivant", "Retour", "Sauter", "Ajouter une ligne", "Ajouter un article",
    "Enregistrer"). Layout, routing, and behavior untouched — text only.

33. **Raw backend enum values that were being displayed directly to the user are now
    routed through French label maps**, per this task's explicit rule (enum values stay
    English in the database; display goes through a translation). Found and fixed:
    `FinancePage.jsx`'s transactions table showed `row.category` raw (`FEED`, `BIRD`,
    ...) and the restricted-view trend badges showed `summary.revenueTrend`/
    `expenseTrend` raw (`up`/`down`/`flat`) — both now go through label maps
    (`CATEGORY_LABELS`, `TREND_LABELS`). `HouseDetailPage.jsx`'s status chip showed
    `batch.status` raw (`ACTIVE`/`CLOSED`) — now `BATCH_STATUS_LABELS`.
    `AlertsListPage.jsx` showed `alert.status` raw (`NEW`/`SENT`/`RESOLVED`) — now
    `ALERT_STATUS_LABELS`. `CashierPage.jsx`'s sales table showed `s.product_type` raw
    — now looked up through the already-French `PRODUCT_TYPES` list.
    `SettingsPage.jsx` showed `user.role` raw (`GET /api/auth/me/` returns the bare
    enum, not a label) — now a local `ROLE_LABELS` map, matching `DashboardShell.jsx`'s
    existing one. `HomeDashboard.jsx`'s house sub-line showed `house.type` — this one
    stays English internally (`"Broiler"/"Pullet"/"Layer"`, produced by
    `DashboardShell.jsx`'s `TYPE_LABELS` and also used for icon-selection string
    comparisons in `DashboardLayout.jsx`) with a new `HOUSE_TYPE_LABELS` map added only
    at the one point it's rendered as text, so the icon-selection logic elsewhere was
    never touched.

34. **Values that round-trip into a backend `TextChoices` enum were deliberately left in
    English internally, with a separate French label map for display** — translating the
    stored value itself would have sent invalid enum values to the API. Two cases:
    `HouseProtocolForm.jsx`'s `UNITS` (`"Day"/"Week"/"Month"`, `.toUpperCase()`'d
    straight into `ProtocolTemplate.from_unit`/`to_unit`) got `UNIT_LABELS`/
    `UNIT_LABELS_PLURAL`. `StockParametersForm.jsx`'s `DETAIL_OPTIONS.feed`
    (`"Starter"/"Grower"/"Finisher"/"Pullet"/"Layer"`, `.toUpperCase()`'d into
    `StockItem.feed_stage`) got `FEED_STAGE_LABELS`. Every other `DETAIL_OPTIONS` tab
    (veterinary/equipment/bedding) and the stock `UNITS` list (`kg`/`L`/`dose`/...) are
    **not** backend enums (`StockItem.unit` is a free-text `CharField`, confirmed by
    reading the model before touching it) — those were translated directly with no
    label-map indirection needed.

35. **Pre-existing bug noticed, not fixed (out of scope — text-only task).**
    `StockPage.jsx` and `OnboardingStockPage.jsx` both set a loaded feed item's `detail`
    directly from `item.feed_stage`, which the backend returns as the raw uppercase
    `FeedStage` enum (`"STARTER"`) — but `StockParametersForm.jsx`'s `<select>` expects
    one of `DETAIL_OPTIONS.feed`'s capitalized values (`"Starter"`). The mismatch means
    the feed-stage dropdown doesn't show the correct pre-selected value when editing an
    existing feed item — this predates this pass; the translation work (adding
    `FEED_STAGE_LABELS`) didn't create it or make it worse, just surfaced it while
    reading the code. Worth a real (behavioral) fix in a follow-up.

36. **`config/settings.py`'s `LANGUAGE_CODE` changed from `'en-us'` to `'fr'`** — this
    turned out to be the highest-leverage fix in this pass: Django/DRF's own built-in
    user-facing messages (password validators, "this field is required", login-failure
    text, generic permission-denied text) were all still English regardless of any
    hand-translated custom strings, since they come from Django's own bundled message
    catalog keyed off the process's active language. Verified live against the running
    stack after the change: a weak-password `POST /api/farm/create/` now returns *"Ce
    mot de passe est trop court. Il doit contenir au minimum 8 caractères."*; a missing
    required field returns *"Ce champ est obligatoire."*; bad login credentials return
    *"Aucun compte actif n'a été trouvé avec les identifiants fournis"*; a role-denied
    request returns *"Vous n'avez pas la permission d'effectuer cette action."* — all
    automatic, no per-string translation needed. Full test suite (6/6) and `manage.py
    check` still pass after the change.

37. **Custom backend error strings also translated** (the ones not covered by
    `LANGUAGE_CODE`, since they're this codebase's own text, not Django/DRF's):
    `apps/core/serializers.py` ("Un compte utilise déjà cet email.", the admin-creation
    guard), `apps/core/views.py` (farm-already-exists 409 — though the frontend doesn't
    actually read this message, it hardcodes its own; translated anyway for API
    consistency), `apps/houses/views.py` + `apps/stock/views.py` (403 guard),
    `apps/batches/views.py` (batch-already-closed 400), `apps/batches/serializers.py`
    (active-batch-exists and mortality-exceeds-count validation), `apps/stock/
    serializers.py` (doses-used validation). **Left in English, deliberately:**
    `apps/core/views.py`'s `ContactMessageView`/`NewsletterSubscribeView` messages
    (`/api/contact/`, `/api/newsletter/`) — confirmed these have no frontend caller at
    all since the landing-page rewrite removed `publicApi` (deviation #26), so nothing
    currently routes these strings to a user; translate them if/when something calls
    those endpoints again.

38. **`apps/alerts/services.py`'s two alert-message templates translated** — these
    generate the literal `Alert.message` text rendered in `HomeDashboard.jsx`'s alert
    feed and `AlertsListPage.jsx`. `check_low_stock`: *"{item} below threshold
    (...)"* → *"{item} sous le seuil (...)"*. `check_consumption_deviation`: *"Water/feed
    ratio ... outside 1.6-2.2 norm"* → *"Ratio eau/aliment ... hors norme 1,6-2,2"*. The
    item/batch-code interpolations themselves are untouched (user-entered or
    server-generated codes, not translatable content).

39. **Translation calls worth a second look, flagged for review rather than silently
    decided alone:** `HouseProtocolForm.jsx`'s protocol-line table header "What" →
    "Action" (could also read as "Description" — picked "Action" since a protocol line
    is fundamentally a care action taken, but it's a judgment call, not a term the spec
    docs use verbatim). `HomeDashboard.jsx`'s pre-existing "1 house configured — start a
    batch to see it here." empty-state text, shown when `houses.length === 0`, reads
    oddly in either language (says "1" with zero houses) — translated literally
    ("1 bâtiment configuré...") rather than silently fixing what looks like a
    pre-existing content bug, since this pass is text-only, not behavior.

## Part 5 — Custom protocol categories, batch naming, protocol documentation (2026-08-25)

40. **Schema:** `ProtocolCategory` (`id`, `house` FK, `label`, `icon`, `sort_order`)
    replaces the fixed 5-value `ProtocolCategory` TextChoices enum that used to live on
    `ProtocolTemplate.category` — that field is now a real FK
    (`on_delete=CASCADE`, so deleting a category deletes its lines with it, enforced at
    the DB level, not just a frontend confirm dialog). Migration `protocols/0002` is a
    single self-contained migration (add nullable FK → `RunPython` seeds 5 default
    categories per existing house and remaps each existing line's old string value to
    the matching new category → drop the old field → rename/tighten the new one) —
    applied and verified against this environment's live data (2 houses, 8 lines, all
    correctly remapped by label match). `PoultryBatch.name` added the same way
    (`batches/0003`, no data to migrate — 0 existing batches). Both migrations are
    exactly what `manage.py makemigrations --check` independently generates from the
    final model state, confirmed before writing this note.

41. **Default categories seeded via a `post_save` signal on `PoultryHouse`**
    (`apps/houses/signals.py`, registered in `HousesConfig.ready()`, same pattern as
    `apps.alerts.signals`) rather than in each view that creates a house — there are two
    such views (`HouseListCreateView`/`PoultryHouseSerializer.create()` and
    `OnboardingView`, which creates `PoultryHouse` directly, not through that
    serializer) and a signal covers both without duplicating the seed list. Confirmed
    `POST /api/houses/` has no frontend caller at all currently (grepped — only
    `OnboardingView`'s direct creation is ever exercised), so the signal's second
    trigger point is currently latent but correct or when someone eventually wires that
    endpoint up.

42. **Icon set for the picker** (`apps/protocols/models.py`
    `CUSTOM_CATEGORY_ICON_CHOICES`, mirrored by hand in
    `HouseProtocolForm.jsx`'s `ICON_OPTIONS` — the two lists are **not** shared/
    generated from one source, kept in sync manually, flagged as a maintenance risk if
    one changes without the other): `Soup`, `Thermometer`, `Stethoscope`, `Syringe`,
    `SprayCan` (the 5 defaults' own icons — reused, not excluded, since nothing stops a
    custom category from picking the same icon as a default), plus `ShieldCheck`,
    `Droplets`, `Wind`, `Egg`, `Bug`, `ClipboardList`, `Package` — chosen for having an
    obvious, farm-relevant reading (biosécurité, eau, ventilation, œufs/production,
    nuisibles, inspection/checklist, matériel/fournitures) rather than being generic UI
    icons. Backend validates the icon name against this exact list on category create
    (400 if not in the list); the frontend picker only ever offers these 12, so an
    invalid icon shouldn't reach the API in normal use — the backend check exists for
    direct API calls, not as the only line of defense.

43. **Category deletion is management-mode only, not available during onboarding** —
    the biggest deliberate scope decision in this pass, documented at length in
    `docs/protocol-configuration.md` §"Suppression d'une catégorie": during onboarding
    the house doesn't exist yet, so protocol lines reference their category by array
    position (`categoryIndex`, resolved server-side once the house — and its 5
    signal-seeded defaults — actually exist) rather than a real id. Deleting a default
    category mid-onboarding would shift every later category's position and silently
    misfile lines to the wrong category. Rather than build index-stable deletion (e.g.
    tombstoning a slot) for a control most users won't need before the house is even
    saved, the delete control (× on hover) simply isn't rendered when `mode !==
    "management"`. Adding a category during onboarding has no such issue (always
    appended) and works normally in both modes.

44. **`OnboardingView`'s request shape changed**: `protocolLines` entries now carry
    `categoryIndex` (position in an implicit combined list: 0-4 are the 5 defaults in
    their fixed seed order, 5+ walk `customCategories` in the order supplied) instead of
    a `category` enum string; a new optional `customCategories: [{label, icon}]` field
    lets onboarding create categories beyond the 5 defaults in the same request/
    transaction as the house. The response now also includes the full `categories` list
    (real ids, for the frontend to keep local state in sync after the id-less
    `categoryIndex` phase ends) and `batch.name`. `HouseProtocolView`'s `PUT` (existing
    houses) gained a check that every submitted line's `category` actually belongs to
    the target house — previously any valid `ProtocolCategory` id would have been
    silently accepted regardless of which house (or farm) it belonged to, since DRF's
    default `PrimaryKeyRelatedField` only validates that the id *exists*, not that it's
    the caller's to use.

45. **`PoultryBatch.name` is required by the frontend form (always, both modes — it's
    the same header card used for onboarding and management) but `blank=True` at the
    model level, and only actually wired to persist in onboarding** — `HouseProtocolPage`
    (management: editing an existing house's protocol) only ever `PUT`s
    `protocolLines`, exactly as before this change; it doesn't fetch or update house/
    batch fields at all, which was already true for the other 3 header fields (building
    name, chicks placed, growth cycle) before this pass — none of them persist from that
    screen either. Adding "Nom de la bande" as a 4th field there is consistent with the
    existing 3 (displayed, editable, not saved by that particular screen) rather than a
    new gap — see `docs/protocol-configuration.md` §"Nom de la bande" for the full
    reasoning. Displayed wherever a batch appears in the UI: grepped the whole frontend
    for `batch_code`/`batchCode` display sites first — there is exactly **one**
    (`HouseDetailPage.jsx`; no batch list screen, and the Finance transactions
    endpoint/table has no batch reference at all to begin with) — updated to show the
    name as the primary label with the code as a small parenthetical, falling back to
    the code alone if a batch predates this field (none currently do, but the model
    allows a blank name).

46. **In-app help panel doubles as the source for the PDF/Markdown examples** — the "?"
    button's popover, `docs/protocol-configuration.md`, and the generated PDF all show
    the same one-example-per-default-category table, reusing
    `STARTER_TEMPLATE`'s reference content (display-only in the help panel — confirmed
    it is never written into the real form, only "Charger un modèle de départ" does
    that). `helpDocUrl` defaults to `/docs/protocol-configuration.md`; since
    `docs/protocol-configuration.md` lives at the repo root and isn't otherwise served
    by the frontend, a copy was placed in `frontend/public/docs/` purely so the in-app
    link resolves to something real rather than a dead link — the two copies are
    **not** auto-synced by any build step, kept in sync by hand (re-copy after editing
    either).

47. **The cahier des charges section 4.6 already documented "ProtocolTemplate expands
    into `AlertRule` rows at batch creation, offset from `PoultryBatch.startDate`"** —
    checked before writing `docs/protocol-configuration.md`'s note about this, since the
    task description characterized it as "the existing design already documented in the
    cahier des charges." That part is accurate — the spec really does say this. What's
    not accurate (confirmed by grepping `apps/protocols` and `apps/batches` for any
    `AlertRule` reference — none) is that this was ever implemented: no code path
    creates an `AlertRule` from a `ProtocolTemplate` line, at batch creation or anywhere
    else. This isn't new information — `docs/deviations.md` #16 already flagged
    `VACCINE_DUE`/`SANITARY_VOID_END` as defined-but-never-triggered before this pass —
    but it's directly relevant to documenting "how the protocol relates to
    `PoultryBatch`," so `docs/protocol-configuration.md` describes the spec's intent
    *and* states plainly that it isn't built, rather than either fabricating that the
    connection exists or silently omitting a real (pre-existing, spec-documented) gap.

48. **Not touched, flagged for a follow-up pass:** `docs/data-model.md`'s
    `ProtocolTemplate` section still describes the old 5-value fixed enum — the task's
    explicit deliverable list named the two spec `.docx` files and the puml, not this
    generated doc, so it was left alone rather than treated as in-scope; noted here so
    it isn't mistaken for having been checked and found fine. `apps/protocols/tests.py`
    remains an empty stub — no tests were added for the new category CRUD endpoints or
    the onboarding `categoryIndex` resolution in this pass (everything below was
    verified live against the running stack instead, matching this project's existing
    near-total absence of a test suite going into this pass — see deviation #28's note
    that `apps/finance/tests.py` was "the first real test module in the project").

49. **PDF usage guide** (`docs/protocol-configuration-usage-guide.pdf`) generated from a
    purpose-written HTML file (not a literal export of the Markdown reference — the
    Markdown is technical/implementation-facing, with internal notes like the
    `categoryIndex` wire format and the `AlertRule` gap; the PDF is written for an
    end-user reading it to learn the feature, shorter and step-by-step) via
    `google-chrome --headless --print-to-pdf`. Verified by reading the rendered PDF back
    (not just checking the file existed/had a plausible size) — an earlier attempt at
    exact-height page sizing produced a bad page break (a sliver of the cover bleeding
    onto a near-blank second page); caught by actually looking at the rendered output,
    fixed by leaving more safety margin in the cover's height rather than chasing exact
    millimeter precision against Chrome's print margins.

## Part 6 — Live growth curves, quick daily entry, live task propagation, protocol-edit modal (2026-08-25)

50. **The `ProtocolTemplate` → `AlertRule` expansion this task's Part C asked to "reuse
    ... rather than duplicating it, refactor into a shared function ... if it currently
    only exists inline in the creation path" did not exist anywhere at all** —
    confirmed again by grep before writing any code, consistent with #16/#47 above. This
    task is the first real implementation of it: `apps/protocols/services.py`'s new
    `expand_protocol_to_alert_rules(batch)` is the single shared function, called from
    three sites — `OnboardingView` (batch created during onboarding),
    `PoultryBatchListCreateView.perform_create` (a further batch added to an
    already-protocoled house — this path existed before but never called it either), and
    `HouseProtocolView.put` (a protocol edit, only when the house has an active batch).
    A new `AlertRuleType.PROTOCOL_TASK` choice and three new nullable `AlertRule` fields
    (`batch`, `protocol_line` — `on_delete=CASCADE`, `scheduled_date`) carry these rows;
    every pre-existing rule type leaves all three null, unaffected.

51. **These generated rows are exactly as inert as the project's existing `SCHEDULED`
    rules** (see `AlertRule`'s own docstring, and #16) — there is still no Celery Beat
    schedule anywhere in this project, so nothing ever evaluates `scheduled_date` to
    actually fire an `Alert`/SMS. This task's scope was "regenerate the schedule rows
    correctly on every protocol edit," not "build the Beat wiring to fire them" — the
    task's own verification steps only ask to confirm the rows are created/regenerated/
    left alone-when-past, never to confirm an SMS goes out, so this is treated as
    consistent with the task's actual ask rather than a shortfall to silently work around
    by inventing a Beat schedule that wasn't requested.

52. **"Regenerate ... delete rows that have not yet triggered"** is implemented as:
    delete every `PROTOCOL_TASK` `AlertRule` for this batch with `scheduled_date >=
    today`, then recreate one row per current `ProtocolTemplate` line whose computed
    date (`batch.start_date + from_value`, converted to days) is today or later. Rows
    already in the past are left untouched — nothing in this codebase ever marks these
    rows "sent" (no Beat evaluates them, per #51), so a past `scheduled_date` is the only
    available signal for "this already happened"; there is no `Alert`/`SmsMessage`
    history for `PROTOCOL_TASK` rows yet to accidentally delete, since nothing has fired
    one. Wrapped in one `transaction.atomic()` block per the task's requirement.

53. **`DailyLog.eggs_collected`** (nullable `PositiveIntegerField`) added exactly as the
    task specified — a raw data point only, no laying-rate calculation reads it yet
    (explicitly deferred by the task itself).

54. **Quick-entry upsert** (`PUT /api/batches/{batchCode}/daily-logs/quick-entry/`,
    `DailyLogQuickEntryView`) is a new, separate view from the existing `POST
    /daily-logs/` — that one stays a strict one-row-per-day create (used by the fuller
    daily-log entry flow elsewhere), this one always upserts and only ever touches
    `mortality`/`eggs_collected`, leaving any `feed_consumed_kg`/`water_consumed_l`/
    `avg_sample_weight`/`notes` already on that day's row untouched. `current_count` is
    adjusted by the *delta* between the new and previous mortality value (not the raw
    new value), so correcting an already-logged day's mortality doesn't double-decrement
    the flock size — verified live: submitting mortality=5 then mortality=8 for the same
    date against a 1000-bird batch left `current_count` at 992, one `DailyLog` row, not
    987 / two rows.

55. **`growth_curve(batch)`** (`apps/batches/calculations.py`) is a new day-of-cycle
    series (`dayOfCycle = log_date - start_date`), separate from the existing
    week-indexed `weekly_kpi` (left untouched — still powers the FCR/mortality charts on
    the house page, unrelated to this task). `GET /api/batches/growth-curves/` returns
    it for every active batch by default, or one batch via `?batch_code=`/`?house_code=`
    — one endpoint for both the global view's overlaid multi-batch chart and the
    per-house view's single-line chart, per the task's explicit "reuse the exact same
    chart component ... not a separate implementation" instruction (the frontend mirrors
    this: `GrowthCurves.jsx` takes a `series` array and a `scope` prop, nothing else
    differs between the two call sites).

56. **`GET /api/houses/{houseCode}/tasks-now/`** (`HouseTasksNowView`) recomputes
    `dayOfCycle` and re-filters `ProtocolTemplate` from scratch on every request —
    deliberately nothing is cached or persisted, per the task's explicit requirement.
    Verified live: editing a protocol line's date range via `PUT
    /api/houses/{houseCode}/protocol/` changed this endpoint's response on the very next
    call, with no intervening cache to invalidate.

57. **`ProtocolEditModal.jsx`** (added mid-task, on explicit follow-up request) replaces
    full-page navigation to `/dashboard/houses/{houseCode}/protocol` for both "Modifier"
    entry points (global-view batch list, per-house header) with a centered modal —
    same backdrop-blur/scale-fade language as the landing page's `DemoVideoModal`
    (reused, not reinvented). Decisions made without being asked:
    - **The route itself stays working**, rendering the same full-page `HouseProtocolForm`
      it always has (now navigating to the house-detail page on save so that page's own
      refetch picks up the change) — kept as a direct/shareable link rather than teaching
      `DashboardShell` to open a modal from a URL, which would need two reconciled
      "source of truth" mechanisms (route vs. modal state) for no real benefit here.
    - **"Unsaved changes" tracking** is a capture-phase `input`/`change` listener on the
      modal panel, not a prop threaded into `HouseProtocolForm` — the task said not to
      change the form's internals, and this achieves the same confirm-before-discard
      behavior (a plain `window.confirm`, since no such pattern existed anywhere else in
      the app yet) without touching it at all.
    - **Focus trap** is hand-rolled (query focusable elements in the panel, cycle
      Tab/Shift+Tab at the ends, restore focus to the triggering button on close) since
      no focus-trap utility already existed in this project's dependencies and adding one
      for a single modal seemed like more than this warranted.
    - On successful save the modal calls the caller's `onSaved` (refetch growth
      curves/tasks-now) and then closes itself, rather than expecting the caller to close
      it — one less thing for each of the two call sites to get right identically.

58. **"Signaler un cas inhabituel"** (per-house view) is a minimal inline textarea + submit
    button, not a new page/route — `POST /api/unusual-cases/` already existed
    (`apps/maintenance`) with zero frontend usage anywhere before this task; the task
    asked for "a link to report" one, not a full case-management screen, so this stays
    proportional to that ask. `farmer`/`worker` on the payload are set from the logged-in
    user's own id based on their role (whichever doesn't apply is left null), matching
    how the model itself allows either.

59. **Verification method, disclosed:** the browser extension was not connected this
    session (checked via `tabs_context_mcp`, which returned "extension not connected"),
    so the modal's actual on-screen appearance, blur, animation, and keyboard focus-trap
    behavior were **not** visually confirmed — only verified by code review against the
    same pattern `DemoVideoModal` already uses successfully. Everything server-side
    **was** verified live against the running stack: created a temporary protocol line
    and batch on the real `H-1-001` house, confirmed `expand_protocol_to_alert_rules`
    generated the correct `AlertRule` row at batch creation, edited the protocol via
    `PUT /protocol/` and confirmed the old rule was deleted and a new one regenerated
    with the updated `scheduled_date`, confirmed `tasks-now` reflected the edited range
    immediately, exercised the quick-entry upsert/delta logic directly (see #54), then
    deleted all of this temporary data afterward (`H-1-001` is back to zero protocol
    lines and batches, matching its state before this task started).

## Part 7 — Five bugs in the batch-edit flow and sidebar, found by testing Part 6 (2026-08-25)

60. **Bug 1 root cause (batch rename silently discarded):** `ProtocolEditModal`'s
    `handleSave` only ever called `PUT /api/houses/{houseCode}/protocol/`
    (`protocolLines` only) — the "Nom de la bande" field's value
    (`payload.batchName`) was built by `HouseProtocolForm` but never sent anywhere.
    Worse, **no endpoint existed to persist it even if it had been sent** —
    `PoultryBatch.name` had a model column and a form field since the earlier task that
    added it, but no view ever wrote to it outside of batch *creation*
    (`OnboardingView`, `PoultryBatchListCreateView`). Fix: new `PATCH
    /api/batches/{batchCode}/` (`PoultryBatchDetailView`, `name`-only via a dedicated
    `PoultryBatchNameUpdateSerializer` — deliberately not a general batch editor, see
    that serializer's docstring), called from `ProtocolEditModal.handleSave` alongside
    the protocol PUT whenever the name actually changed.

61. **Bug 1 root cause (sidebar not refetching):** `DashboardShell.jsx`'s `houses` state
    (the sidebar's data source, via outlet context) only refetched on
    `location.pathname` change — the protocol-edit modal is an overlay that never
    navigates, so a save there had nothing to trigger a sidebar refresh. Fix: extracted
    the fetch into a `refreshHouses` callback, still run on route change as before, and
    also exposed via `<Outlet context={{ houses, refreshHouses }}>` so
    `DashboardHomePage`/`HouseDetailPage` can call it from `ProtocolEditModal`'s
    `onSaved` alongside their own existing refetches (growth curves, tasks-now, the
    page's own batch list).

62. **Bug 2 root cause:** the mortality field was a plain small `<input type="number">`
    with no severity signal of any kind — there was nothing to "make more visible," it
    simply hadn't been designed with any visual weight. Fix: `QuickEntryPanel`'s
    mortality input is now large (22px, bold) with a background/border color scaled to
    severity (`.mortality-neutral`/`.mortality-warning`/`.mortality-danger`, all reusing
    the existing `--warning`/`--danger` tokens, no new colors introduced) — gray at 0,
    amber for any non-zero count before its cumulative effect is known, red once the
    *cumulative* mortality (returned by the quick-entry endpoint's new
    `cumulativeMortalityPct`, reusing `apps.batches.calculations.mortality_pct` — not
    recomputed client-side) exceeds `MORTALITY_REFERENCE_RANGE`'s upper bound. A summary
    line under the field restates the count and cumulative percentage after each save.
    Applied once, in the one shared `QuickEntryPanel` component — it already appears in
    both the global and per-house views, so both get the fix from one change; there is
    no other place in the app that currently displays a per-day mortality figure.

63. **Bug 3 audit result: does not reproduce in the current code.** Grepped
    `apps/batches/` and `apps/protocols/` for any `PoultryHouse`-writing code reachable
    from batch closing — none exists; `BatchCloseView.patch()` only ever touches
    `PoultryBatch.status`/`actual_end_date` and creates a `BatchClosingReport`.
    `HouseDetailPage.jsx`'s close-confirmation dialog has never rendered a name-bound
    input, so there is no shared-state path either. Read as a preemptive check tied to
    Bug 1's fix rather than an existing regression — verified live instead: created a
    batch on `H-1-001` (whose `PoultryHouse.name` happens to be an empty string),
    renamed it via the new `PATCH /api/batches/{batchCode}/`, then closed it, checking
    `GET /api/houses/H-1-001/` before and after both steps — `name` stayed `''`
    throughout. The new endpoint only ever writes to `PoultryBatch` (see #60); nothing
    added by Bug 1's fix touches `PoultryHouse` either.

64. **Bug 4:** `DashboardLayout.jsx`'s sidebar rendered `house.name` (the house
    identifier) unconditionally. Fix: `DashboardShell.refreshHouses` now also resolves
    each house's active batch and includes `activeBatchName`; the sidebar shows that as
    the primary label with the house identifier demoted to a small secondary line
    underneath (new `.sidebar-link-label`/`-primary`/`-secondary` CSS) when present,
    falling back to the house name alone for a house with no active batch (sanitary
    void) — exactly the task's specified fallback.

65. **Bug 5.1 root cause:** `ProtocolEditModal` fetched and correctly pre-filled the
    protocol categories/lines (`initialCategories`/`initialSchedules`), but never passed
    `initialHeader` to `HouseProtocolForm` at all — every header field, including "Nom
    de la bande," silently defaulted to empty regardless of the batch's real data. Fix:
    the modal now also fetches the house (`GET /api/houses/{houseCode}/`) and the active
    batch (`GET /api/batches/?house_code=`), and derives `initialHeader` from them
    (`buildingName` from the house, `chicksPlaced`/`batchName` from the batch,
    `growthCycle` from `planned_end_date - start_date` in days where available).

66. **Bug 5.2 audit result: does not reproduce — `HouseProtocolForm` never renders
    wizard chrome in management mode.** Read the component in full: the "Suivant" button,
    any stepper, and the Stock/Employees steps live entirely in `OnboardingLayout.jsx`
    and the three `/onboarding/*` pages, a completely separate component tree that
    `ProtocolEditModal` never touches. `HouseProtocolForm`'s own save bar renders
    `mode === "onboarding" ? "Suivant" : "Enregistrer le protocole"` — `ProtocolEditModal`
    hardcodes `mode="management"`. The most likely real cause of this observation is
    Bug 5.1: an empty, unlabeled-feeling form (no pre-filled batch name, "Charger le
    modèle de départ" button visible, same layout copy as onboarding step 1) reasonably
    *reads* like a wizard step even though no stepper/Suivant-to-Stock code path exists.
    No changes were needed here beyond the Bug 5.1 fix; noted rather than silently
    assumed identical to onboarding.

67. **Bug 5.3 audit result: no leftover "go to home" button exists, confirmed rather
    than assumed.** Grepped `ProtocolEditModal.jsx` and `HouseProtocolForm.jsx` for any
    such control — the modal has exactly one close affordance (the top-right X;
    backdrop-click and Escape also close it, from the earlier modal task), which returns
    cleanly to the dashboard screen underneath since the modal is an overlay on the same
    route, never a navigation away from it. No fix needed; documented per the task's own
    instruction to confirm rather than assume.

68. **Verification method, disclosed:** browser extension still not connected this
    session, so the sidebar/badge/modal *visuals* were not screenshotted — verified by
    code review plus live API checks: PATCHed a batch's name and confirmed it persisted
    and `PoultryHouse.name` was untouched; computed `mortality_pct` directly for a
    60/1000 mortality scenario and confirmed it exceeds `MORTALITY_REFERENCE_RANGE`
    (6.0% > 5%, would render red); closed a batch and confirmed the house name was
    identical before and after. All temporary batches/logs created for this were deleted
    afterward — `H-1-001` is back to exactly its prior state (one pre-existing user
    batch on `H-1-003`, untouched throughout, is unrelated to any of this).

## Part 8 — Branding/polish pass: sidebar background, favicon, per-route titles (2026-08-25)

69. **Part A audit result: `.sidebar` had a hardcoded `background:#fff`** in
    `sidebar-theme.css`, independent of `--bg` (also `#ffffff` today, but able to drift)
    — fixed to `background:var(--bg)`. Audited the rest of `sidebar-theme.css` for other
    hardcoded colors not reading from a shared variable — the mobile-drawer state's
    `box-shadow:0 0 0 1px var(--line)` already reads the shared `--line` token (it's a
    1px outline substituting for the border on a floating overlay, not an elevation
    shadow), so it was left as-is; nothing else in the file hardcodes a color that has a
    token equivalent.

70. **Part B audit result: the "Vite + React" title / Vite-logo-favicon premise was
    already false** — `index.html`'s `<title>` was already "Winchicken" and there was no
    `vite.svg` anywhere in `public/` (both presumably fixed in an earlier pass this
    session, before this task). What *was* real and off-brand: the existing
    `favicon.svg` was a leftover purple abstract mark completely unrelated to
    Winchicken's actual mint-globe "W" logo — replaced with PNGs
    (`favicon-16x16.png`/`favicon-32x32.png`/`apple-touch-icon.png`) generated from
    `frontend/public/logo-mark.png` (already the correct, already-integrated brand mark
    — confirmed by opening both `Images/image_20.png`, the wordmark source the task
    named, and `logo-mark.png` side by side: the latter is that same mark, already
    cropped to a transparent-background icon, i.e. already the right favicon source
    with no extraction work needed). Generated by padding the mark to a square canvas
    (avoids squashing at small sizes) with Python/Pillow; the apple-touch-icon is
    flattened onto the brand's dark navy (`#0d1b29`, matching `AnimatedBackground`'s
    gradient) since Apple touch icons are expected opaque. `icons.svg` (unused, in the
    same folder) was left alone — unlike the old `favicon.svg` it isn't actively wrong-
    branded, just unwired, and isn't a Vite artifact, so removing it wasn't clearly
    in scope.

71. **Part B — route-aware titles:** new `frontend/src/hooks/useDocumentTitle.js`,
    called from every top-level route component (`LandingPage`, `LoginPage`,
    `CreateFarmPage`, `DemoPage`, `OnboardingLayout` — one shared title for all three
    onboarding steps, since they're one flow — and each `/dashboard/*` sub-page
    individually, including `HouseDetailPage` using the house's own name when known).
    No cleanup/restore on unmount: React Router only ever mounts one top-level route
    component at a time, and the next route's mount sets its own title anyway.

72. **Part C — added:** `<meta name="description">`, `<meta name="theme-color"
    content="#0b8f68">` (the `--mint` token, the more consistently-named "brand mint"
    versus the more saturated `--mint-fill` used for CTAs), Open Graph tags
    (`og:type`/`og:site_name`/`og:title`/`og:description`/`og:image`), and `lang="fr"`
    on `<html>` (was `"en"`). `og:image` points at `/logo-mark.png` as a root-relative
    path rather than a full absolute URL — this project has no configured production
    domain/site-URL anywhere (no env var for one), so a real absolute URL isn't
    honestly available yet; noted here rather than fabricating a domain.

73. **Verification method, disclosed:** browser extension not connected this session
    (as with the prior two tasks) — the favicon/title/sidebar-background changes were
    not visually screenshotted, only verified by reading the generated PNGs back via
    the Read tool (confirmed the mint mark renders correctly at 32x32 and 180x180) and
    by a clean `oxlint`/production `vite build` pass confirming no import/reference
    errors from the new hook or the removed `favicon.svg`.

## Part 9 — Sidebar-staleness root-cause fix, batch deletion, backend/frontend reorg, mandatory self-test (2026-08-25)

74. **The real root cause, traced (not guessed) per this task's explicit instructions:**
    the previous pass's fix (`refreshHouses` threaded through `DashboardShell` →
    `<Outlet context>` → each page's own `onSaved` handler) was structurally correct
    and, once re-traced end to end, does work — confirmed live: `PATCH
    /api/batches/{batchCode}/` persists and `GET /api/houses/` +
    `GET /api/batches/` (what the sidebar reads) reflect it immediately afterward.
    What was **fragile**, not broken: the sidebar refresh depended on every page that
    opens the protocol modal remembering to wire `onSaved` to a refresh call — an easy
    thing to get right once and forget on a third call site. That fragility is now
    eliminated at the root: `frontend/src/hooks/useHouses.js` (`{houses, loading,
    error, refetch}`) is the single fetch point, shared via a new
    `frontend/src/context/HousesContext.jsx` (`HousesProvider`/`useHousesContext`)
    wrapping the whole `/dashboard/*` tree from `DashboardShell`. `ProtocolEditModal`
    now calls `useHousesContext().refetch()` **itself**, directly, after every
    successful save — independent of whatever any given page's `onSaved` callback
    does. A future third "Modifier" entry point gets this for free.

75. **A second, real, previously-silent bug found and fixed while tracing:**
    `ProtocolEditModal.handleSave` had no `catch` — a failed save (permission,
    validation, network) left the user with zero feedback: the spinner just stopped
    and the modal sat there with nothing visibly wrong, which could plausibly read as
    "appears to save, but nothing happened." Fixed by wrapping the save in try/catch,
    surfacing a visible red error banner (`.protocol-modal-error`) inside the modal on
    failure, and re-throwing so `HouseProtocolForm`'s own success message doesn't show
    a false "Enregistré" on top of a failed save.

76. **Batch deletion:** `DELETE /api/batches/{batchCode}/` added to the existing
    `PoultryBatchDetailView` (now `RetrieveUpdateDestroyAPIView`), permission
    `IsAdminOrFarmManager` — stricter than the PATCH permission (any protocol-editing
    role), since deleting is materially more destructive/irreversible than renaming.
    Cascades through every `on_delete=CASCADE` `batch` FK (`DailyLog`, `Alert`,
    `AlertRule`, `UnusualCase`, `Vaccination`, `StockMovement`, `Expense`, `Sale`,
    `BatchClosingReport`) — verified live (item 81 below): all six of the checked
    related-row counts went from populated to exactly zero, and the house immediately
    became eligible for a new batch again (the single-active-batch validation that
    previously rejected a second batch on the same house). Frontend: a "Supprimer la
    bande" button + confirm dialog on `HouseDetailPage`, reusing the new
    `ConfirmDialog` component (see item 78) rather than a third copy of the
    inline-card-with-two-buttons pattern.

77. **Backend reorg** (`apps/batches/`, the app most directly touched by this task —
    per the addendum's own scoping rule, no other app was restructured): `views.py`
    split into a `views/` package (`batches.py`, `daily_logs.py`, `kpi.py`) with
    `views/__init__.py` re-exporting everything so `urls.py`'s existing `from
    apps.batches import views` / `views.XxxView` pattern needed zero changes. New
    `services.py` holds the two pieces of real multi-step orchestration that were
    previously inline in views (`finalize_new_batch`, `record_quick_entry`) — the
    quick-entry view now only parses the request and turns the service's return value
    into the right HTTP response. `PoultryBatchNameUpdateSerializer` moved from
    views.py into `serializers.py` where it belonged (shape/validation only, no
    business logic) — a pre-existing misplacement from the previous task, fixed
    opportunistically while touching this exact file, per the addendum's explicit
    allowance for that.

78. **Frontend reorg:** `HouseDetailPage.jsx` (was 256 lines, several responsibilities)
    split into itself (182 lines) plus four new single-purpose files:
    `ConfirmDialog.jsx` (the destructive-action confirm card, now shared by "Clôturer
    la bande," "Supprimer la bande," and — not touched this pass, but a clear future
    candidate — `HouseProtocolForm`'s category-delete confirm), `TasksNowPanel.jsx`,
    `WeeklyKpiCharts.jsx`, `UnusualCaseReportForm.jsx`. `HouseProtocolForm.jsx` (570
    lines, several mixed responsibilities) was deliberately **not** touched — explicitly
    out of scope per this task's own rules ("don't go on a separate cleanup spree");
    noted here as a known follow-up candidate for a future pass that's actually
    scoped to it.

79. **A dedicated `code-architect` subagent** (`.claude/agents/code-architect.md`,
    committed to the repo) was created per this task's own instructions, to review
    every file this task touched against the standards above before considering the
    task done. Its first invocation in this session failed (`Agent type 'code-architect'
    not found` — a freshly-written `.claude/agents/*.md` file isn't hot-loaded into an
    already-running session's agent list), so the review ran via `general-purpose`
    with the same standards and file list embedded in the prompt instead — functionally
    equivalent for this one pass, and the committed subagent file is available to
    future sessions as intended. Result: no violations found, no fixes needed (see the
    agent's own report for the specifics it checked — the `views.py`→`views/` package
    re-export path in particular, since that's the kind of thing that looks fine to a
    human skim but silently breaks imports if done wrong).

80. **A genuine, real bug turned up by the mandatory self-test that neither the code
    review nor `manage.py check` caught:** `DELETE /api/batches/{batchCode}/` returned
    405 against the live dev server, even though the view code was correct and `manage.py
    check` (a fresh process each invocation) reported no issues. Root cause: this
    project's `web` container had been running continuously for ~20 hours across many
    prior tasks in this session; converting `apps/batches/views.py` (a file) into
    `apps/batches/views/` (a package with the same import path) is an edge case Django's
    autoreloader apparently didn't handle cleanly on this long-running process — a stale
    `views.cpython-312.pyc` for the deleted single-file module was found in
    `__pycache__`, and the live server was still serving the pre-split view (no DELETE
    method) despite every fresh `docker compose exec` process picking up the new package
    correctly. **This is a dev-environment artifact, not a code bug** — a real deploy
    always starts a fresh process — but it's exactly the kind of thing "run
    `manage.py check` and call it verified" misses and only exercising the live,
    already-running server catches, which is the whole point of this task's mandatory
    self-test practice. Fixed with `docker compose restart web`; re-verified DELETE
    returns 204 and the cascade is correct (item 76) immediately after.

81. **Self-test coherence, checked by hand against the raw API responses (not just
    "did it render"):** created a real farm/admin via `POST /api/farm/create/`
    (singleton-locked — see item 82), onboarded one house with protocol lines across
    Alimentation/Température/Vaccination, a named batch (`initialCount=1000`,
    `startDate=2026-08-18`), one stock item per category, two employees (a Farmer, a
    Cashier). Logged 4 days via the full `POST /daily-logs/` (mortality 3/2/1/4, feed
    15/16/17/18kg, weights .045/.05/.06/.075kg) plus one day via quick-entry
    (mortality 2, then corrected to 3 — delta-tested). Hand-computed vs. actual API
    response, all matched exactly: cumulative mortality 13/1000 = **1.3%**; FCR =
    66kg ÷ (987 × 0.075kg) = **0.89**; `current_count` **987** after the correction
    (not 982 — confirms the delta logic, not a double-decrement); growth-curve
    `dayOfCycle` values **0,1,2,3,7** with survival **99.7/99.5/99.4/99.0/98.7%**, all
    exact. Edited the protocol (pushed a line's range from day 0-15 to day 10-20) and
    renamed the batch through the exact two calls `ProtocolEditModal` makes: `tasks-now`
    immediately stopped showing the now-out-of-range line, the old `AlertRule` was
    deleted and two new ones appeared with correctly recalculated `scheduled_date`s
    (`start_date + from_value`), and the rename persisted — all confirming item 74's fix
    end-to-end, not just at the unit level. Logged one `UnusualCase`, one
    `EquipmentFault` (no photo — that feature doesn't exist yet, see the still-queued
    six-part task), one `Expense` (277.20 FEED) and one `Sale` (50 × 1.50 = **75.00**,
    server-computed). Finance summary as Admin: revenue **75.0**, expenses **277.2**,
    `cashOnHand` **-202.2** — all exact. Finance summary as the Cashier employee: raw
    response was `{"access":"restricted","revenueTrend":"up","expenseTrend":"up"}` —
    confirmed server-side, not just UI-hidden, that no monetary figure is present at all
    for that role. No coherence bug found anywhere in this pass beyond item 80.

82. **A pre-existing single-farm constraint (`Farm.singleton_lock`, from before this
    session) meant the self-test's own Step 2 — "create one test farm ... through the
    actual `/create-farm` flow" — was impossible without first freeing that slot.**
    Since the user's own confirmed cleanup plan for this self-test was a full wipe to
    zero rows anyway, the wipe was moved to the *start* of the self-test instead of only
    the end (same authorized outcome, resequenced so the real creation flow could
    actually be exercised) — flagged explicitly before doing it, not silently assumed.
    Two full `python manage.py flush --noinput` passes: one immediately before creating
    the test farm, one after the self-test finished. **Before either flush, this
    session explicitly confirmed with the user which cleanup was wanted** — the first
    proposed answer ("targeted deletion," preserving real pre-existing data from earlier
    in this session) conflicted with a follow-up instruction demanding zero rows
    afterward, and rather than silently picking one, both were surfaced as an explicit
    either/or question; "full wipe to zero" was the confirmed answer. Final state,
    verified: `GET /api/farm/exists/` → `false`; `Farm`/`User`/`PoultryHouse`/
    `PoultryBatch` row counts → `0`/`0`/`0`/`0`.

83. **Standing practice going forward (per this task's explicit instruction, not a
    one-off):** after implementing a feature, (1) delegate a `code-architect` review of
    the changed files before considering it done, and (2) actually exercise the change
    against the live running stack via the real API/UI — not just `manage.py check`/
    `oxlint`/a unit test — with hand-computed expected values checked against real
    responses, and full cleanup of anything created for the test afterward. Item 80 is
    the concrete example of why step (2) matters even when step (1) and static checks
    both pass clean.

## Part 10 — Weight entry / sparse growth curve / weighing reminder, then a `current_count` audit fix (2026-08-25)

84. **Weight added to quick-entry, upsert kept non-clobbering:** `QuickEntryPanel`'s
    existing `date` field now covers weight too (any date, not forced to today).
    `mortality`/`eggsCollected`/`avgSampleWeight` are each sent as `null` when left
    blank; the backend (`apps.batches.services.record_quick_entry`) only writes fields
    it actually receives to `DailyLog.objects.update_or_create`'s `defaults`, so a
    weight-only submission leaves mortality/eggs on that date untouched and vice versa.
    This also fixed a **pre-existing gap in mortality's own handling**, not just weight's
    — the old code always forced `mortality: 0` into `defaults` when the field was left
    blank, which would have silently zeroed out an existing mortality entry the moment
    someone tried a weight-only submission; not previously reachable since weight didn't
    exist yet, but a real latent bug this task's own "don't clobber" requirement exposed
    and required fixing (the task's "don't touch mortality/eggs logic beyond what's
    needed" carve-out explicitly allows this).

85. **Growth curve empty state is per-chart, not all-or-nothing:** `GrowthCurves.jsx`
    already used `connectNulls` and already omitted (not zeroed) days without a weight —
    that part worked correctly already. What was missing: a batch with `DailyLog` rows
    (mortality logged) but zero weight entries yet rendered a technically-correct-but-
    visually-empty weight chart instead of a message. Added a `hasAnyWeight` check
    gating the weight chart specifically — the survival chart (which has data whenever
    any `DailyLog` exists) is unaffected either way.

86. **"Fréquence de pesée"** added as a 5th `HouseProtocolForm` header field (not a
    Health & treatment tab addition — the header already holds the other batch-level
    settings, e.g. growth cycle, so it's the more consistent home), `PoultryBatch.
    weighing_frequency` (nullable, reusing `apps.protocols.models.ProtocolUnit`'s three
    string values rather than a new near-duplicate enum, referenced by string not FK to
    avoid a protocols→batches model dependency). Drives a recurring `WEIGHING_REMINDER`
    `AlertRule` (new rule type; `ScheduleFrequency` gained `MONTHLY`, which didn't exist
    before) via `apps.batches.services.sync_weighing_reminder` — reuses the `AlertRule`
    mechanism exactly as instructed, shaped differently from `PROTOCOL_TASK` because it's
    genuinely recurring (one row, `frequency` set, no `scheduled_date`) rather than a
    single-date one-shot. Same "created correctly, nothing fires it" caveat as every
    other `SCHEDULED` rule in this project (no Celery Beat). Also surfaced live in
    "tâches à effectuer maintenant" (`apps.batches.services.weighing_reminder_task`,
    due when `day_of_cycle % cadence_days == 0`) — the in-app notification center from
    an earlier task request was never actually built, so that half of the surfacing
    instruction doesn't apply yet.

87. **`current_count` audit, requested separately, done as its own clean pass:** traced
    both real write paths (`DailyLogListCreateView.perform_create`, `record_quick_entry`)
    and confirmed both correctly handled creation *and* delta-correction of an
    already-logged day — not stale in the app's own two endpoints. The **real** gap:
    Django admin (`/admin/batches/dailylog/`) edits `DailyLog` directly via `.save()`,
    bypassing both code paths entirely — a mortality correction made there would have
    left `current_count` silently wrong. Fixed per the task's stated preference:
    `current_count` is now a computed `@property` (`initial_count` minus
    `Sum(daily_logs.mortality)`, clamped at 0) instead of a stored column — verified live
    that this also simplified `record_quick_entry` (no more delta-tracking write needed)
    and confirmed by directly editing a `DailyLog.mortality` value in a shell (bypassing
    every view/service) that `current_count` still came back correct on the next read.
    No DB constraint or raw SQL referenced the old column, so the "keep it stored, sync
    via a signal" fallback wasn't needed. Verified against a temporary test house added
    to the farm's real, already-in-use `Farm` row (a genuine farm/house/batch/worker now
    exist from the user's own use of the live app between sessions — untouched; the
    verification house/batch were deleted afterward, cascade-confirmed).

## Part 11 — Weighing entry split into its own section (2026-08-25)

88. **Three follow-up messages described this same change at three different stages of
    completion ("remove a leftover bug," "reposition an existing section") that didn't
    actually exist yet** — verified the real state of `QuickEntryPanel.jsx` before
    acting each time rather than assuming any of the described intermediate states were
    real, per this session's standing practice. Synthesized all three into one direct
    build of the final described state, rather than implementing and then re-doing
    fictional intermediate ones.

89. **New `WeighingSection.jsx`** — separate card from `QuickEntryPanel`, own date +
    weight fields, upserts via the same `PUT .../quick-entry/` endpoint with
    `mortality`/`eggsCollected` sent as `null` (untouched, per the existing no-clobber
    contract — no backend change needed for this task at all, purely a frontend
    reorganization). Positioned directly below the growth/survival curves and above the
    mortality/eggs panel on both dashboard locations, per the final message's explicit
    order. `QuickEntryPanel` had its weight field/state fully removed and reverted to
    mortality/eggs only — its date field was kept flexible (not forced back to
    today-only) since it predates the weight feature and forcing it would have been an
    actual regression to already-working backdating behavior, which every version of
    this task explicitly prohibited.

90. **Global view requires an explicit house/batch choice before logging a weight** —
    reuses the same `<select>` pattern already on `QuickEntryPanel` (confirmed that
    pattern exists before reusing it, per the task's own instruction to check rather
    than copy a possibly-broken one). Recent-weighings list groups by house name on the
    global view (`activeBatchList`'s existing `houseName`/`houseCode` fields, already
    present from the Part 6 dashboard rework — no new data needed) and stays a flat list
    on the per-house view, where grouping would be meaningless (exactly one house).

## Part 12 — Farm-wide factory reset, Administrateur only (2026-08-26)

91. **A single `farm.delete()` is the entire wipe** — audited every app's `models.py`
    for its FK chain back to `Farm` before writing anything: `PoultryHouse`/`StockItem`/
    `Expense`/`Sale`/`PurchaseOrder`/`AlertRule` FK `Farm` directly; `PoultryBatch` FKs
    `PoultryHouse`; `DailyLog`/`BatchClosingReport`/`Vaccination`/`UnusualCase` FK
    `PoultryBatch`; `StockMovement` FKs `StockItem`; `EquipmentFault` FKs `PoultryHouse`;
    `Alert`/`SmsMessage` FK `AlertRule`/`Alert`; `ProtocolCategory`/`ProtocolTemplate`
    FK `PoultryHouse`; `User` (and every role-subtype row, via a `CASCADE` `OneToOne`)
    FKs `Farm` directly; `NotificationPreference` FKs `User`. Every single one of those
    FKs is `on_delete=CASCADE` — none is `SET_NULL`/`PROTECT`/`DO_NOTHING` on the path
    back to `Farm` (the `SET_NULL`s that do exist, e.g. `EquipmentFault.technician`,
    `Sale.cashier`, are all on FKs to `User` that don't matter once the row carrying them
    is itself cascade-deleted via a different path). Confirmed the two tables genuinely
    *not* wiped, `ContactMessage`/`NewsletterSubscriber`, have no FK to `Farm` at all —
    they're the public landing-page contact form and newsletter opt-in, not farm data,
    and aren't in `farm_management_schema_en.puml`. This meant no per-app deletion pass,
    no signal, no explicit list of models to walk — `apps.core.services.
    factory_reset_farm` is a two-line function (log, then `farm.delete()` in a
    transaction).

92. **No `rest_framework_simplejwt.token_blacklist` app added, deliberately** — the task
    asked for "invalidate all JWT tokens currently issued." Adding the blacklist app
    would mean a new `INSTALLED_APPS` entry, a new migration, and a table that itself
    lives in the database being wiped (meaning the reset would have to remember to
    special-case blacklisting-then-wiping its own blacklist table). Reasoned through
    what actually happens instead: `JWTAuthentication.get_user()` does a real
    `User.objects.get(pk=...)` on every authenticated request; once `factory_reset_farm`
    deletes every `User` row, every already-issued access token 401s on its very next
    use, full stop. A refresh token can still be exchanged for a *new* access token
    afterward (`TokenRefreshView` only checks the token's own signature/expiry, never
    the `User` table) — but that new access token then 401s the moment it's actually
    used for anything, for the exact same reason. End state is identical to a real
    blacklist (every session rejected) without adding a table this feature would have
    to carve out an exception for.

93. **That same "refresh still works, but the token it hands back is dead on arrival"
    behavior turned out to be a real, separate frontend bug** — traced what the
    existing axios interceptor (`frontend/src/api/client.js`) actually does when a
    retried request comes back 401 a second time: `try { ...; return client(original);
    } catch (refreshError) { ...; window.location.href = "/login"; }` — a `return`ed
    promise's later rejection is not caught by the `try` block's own `catch` (plain JS
    async/await semantics, not React- or this-project-specific), so a second 401 after
    a "successful" refresh silently rejected the original caller's promise with **no
    redirect at all** — the tab would just sit there with failed requests. Confirmed
    this by tracing the code, not by reproducing it against the running dev stack (see
    item 96). Fixed by awaiting the retry (`return await client(original)`) so its
    rejection reaches the existing `catch`.

94. **Redirect target changed from `/login` to `/`, everywhere this interceptor
    redirects, not just for the reset case** — `/login` has no farm-existence check and
    would show a normal-looking login form for a farm that no longer exists;
    `LandingPage.jsx` already calls `GET /api/farm/exists/` on mount and switches its
    primary CTA to "Créer la ferme" once it's `false`. Since the fixed retry-then-401
    path (item 93) is the *only* code path that can actually reach this reset scenario
    from a stale second tab, and it shares the exact same redirect line as ordinary
    token-expiry, changing the one line covers the reset case for free instead of
    adding a reset-specific branch — at the cost of one extra click ("Se connecter") for
    the ordinary expired-session case, judged an acceptable trade against not needing a
    second code path to keep correct.

95. **Confirmation flow built as two screens, not four separate clicks** — the task's
    steps 1 ("explain what's deleted") and 2–4 (type farm name, re-enter password,
    button enables) group naturally into "read the irreversible consequences" and
    "prove it's really you, twice"; a `FactoryResetModal` with an `explain` → `confirm`
    internal step reuses `ProtocolEditModal`'s exact backdrop/panel/focus-trap/Escape
    chrome (`protocol-edit-modal.css`) rather than inventing a fourth modal shell.
    "Match" in the task's "only when both match does the confirm button become enabled"
    is read as the *typed farm name* matching `Farm.name` — the only one of the two
    fields that can be compared client-side at all; password correctness has nothing to
    check it against on the frontend and can only be verified by the request actually
    reaching the server, so the button enables on (name match + non-empty password) and
    a wrong password comes back as a request-level error shown inline, exactly as the
    task's own verification steps describe ("type the correct name but wrong password →
    blocked" — blocked by the server rejecting it, not by a disabled button that could
    never have known).

96. **Verified against Django's real, isolated test database, not the running dev
    stack** — `backend/apps/core/tests.py` (`FactoryResetTests`,
    `FactoryResetLoggingTests`) creates one row of every farm-scoped model (`PoultryHouse`
    — whose creation itself signal-seeds `ProtocolCategory` rows, proving the cascade
    reaches two hops deep, not just direct FKs), calls the real endpoint, and asserts
    every table is empty afterward, `GET /api/farm/exists/` is `false`, a wrong password
    is rejected with nothing deleted, a non-Administrateur caller gets 403, an
    unauthenticated caller is rejected, and the external log file gained a line
    containing the right farm name and admin email. All 5 pass. Deliberately **not**
    exercised by clicking through the actually-running dev stack the way this project's
    own standing practice (Part 9 item 83) otherwise calls for: that stack's database
    holds the user's own genuine farm/house/batch/worker data from real use between
    sessions (first noted in Part 10 item 87), this specific action is irreversible and
    deletes literally everything including whoever's logged in, and there is no way to
    stand up a second, disposable farm to click through instead — this deployment allows
    exactly one `Farm` row, enforced by `Farm.singleton_lock`'s DB constraint. The
    frontend's visual/interaction correctness (modal steps, disabled-until-both-match
    button, danger-zone styling) was checked by code review and a clean `oxlint` + `vite
    build` pass only, not by clicking through the running app as an Administrateur, for
    the same reason: doing so would require either the real farm's actual admin
    password or creating a second Administrateur account, and the latter isn't even
    possible through this project's own API (`EmployeeSerializer.validate_role`
    explicitly rejects `role=ADMIN` — by design, there is exactly one Administrateur per
    farm, created only through `POST /api/farm/create/`).

## Part 13 — Outage root cause, specific error messages, dashboard polish, Help link (2026-08-26)

97. **Audited before touching anything, per Step 0's explicit instruction, and the actual
    finding was neither of the two hypotheses the task offered** — not a validation
    error hiding behind a generic message, not a broken/partial migration, not a
    partially-run factory reset. `docker compose ps` showed `web` as `unhealthy`;
    `docker compose logs web` showed a `PermissionError: [Errno 13] Permission denied:
    '/app/logs'` raised from `backend/config/settings.py`'s `LOGS_DIR.mkdir(exist_ok=True)`
    (added the previous session, for the factory-reset audit log — Part 12), which
    Django's `runserver` autoreloader had hit and crash-looped on the moment it picked
    up that settings change, at a point in this session's own history *before* this
    task ever started (traced via `docker compose logs --timestamps`). The backend had
    been completely unreachable since — not just `/farm/create/`, everything. Confirmed
    `python manage.py showmigrations` had every migration applied (ruling out
    hypothesis 3 outright) before even looking at the logs, per Step 0's order of
    operations.

98. **`GET /api/farm/exists/` → `true`, confirmed once the server was actually
    reachable** — ruling out "a partially-run factory reset left the DB
    inconsistent" and confirming the real farm/user data from between-session use
    (Part 10 item 87, Part 12 item 96) was completely untouched. This made the
    fix a pure infrastructure/deployment problem, not a data-recovery one — Step 2's
    `docker compose down -v` recovery path was read, judged unnecessary, and not run:
    there was a clean, targeted fix (below), and running it would have destroyed real
    data over a bug that never touched the database at all.

99. **Root cause, precisely: a host/container filesystem-permission mismatch on the
    bind-mounted `./backend:/app` volume, not the reset feature's application logic** —
    `docker compose exec web chown -R appuser:appuser /app/logs` (done ad hoc last
    session to unblock that session's own test run) fixed the directory for *new*
    processes started after that command, but the `web` service's long-running
    `runserver` process had already crashed in its autoreload thread at the moment the
    permission problem first appeared and never recovered on its own (`restart:
    unless-stopped` doesn't help here — the container's own top-level process didn't
    exit, only an internal thread did). A manual chown is also not a fix that survives
    a fresh clone/`docker compose up` on any other machine or CI runner, so it was
    never going to be the real answer even before this incident proved it insufficient.

100. **Fix: `/app/logs` moved to a Docker-managed named volume, seeded with correct
     ownership at image-build time** — first tried a bare named volume
     (`winchicken_backend_logs:/app/logs` in `docker-compose.yml`) on its own; that
     *also* crashed the same way, because Docker initializes a fresh named volume as
     `root:root` by default unless the image already has content at that path when the
     volume is first attached, in which case Docker seeds the volume from the image
     layer (files *and* ownership). Fixed by adding `RUN mkdir -p /app/logs && chown
     appuser:appuser /app/logs` to `backend/Dockerfile` (before `USER appuser`), then
     rebuilding the image and recreating the volume so it re-seeded from the corrected
     layer. This is now robust for any machine: no host-side permissions to get right,
     no manual chown step, works the same on a fresh clone. Added the same volume to
     `worker` too, even though `worker` hadn't crashed (Celery has no autoreload, so it
     was still running on the settings module as originally imported, before the
     `LOGGING` change) — it would hit the identical crash on its own next restart
     otherwise.

101. **The generic "Vérifiez les champs." / "Impossible de créer la ferme." messages
     were a real, separate bug in their own right, not just a symptom of the outage
     above** — traced `CreateFarmPage.jsx`'s catch block: `err.response?.data?.email
     ?.[0] || "Impossible de créer la ferme. Vérifiez les champs."` only ever reads the
     `email` field's error and falls back to the hardcoded sentence for *any* other
     case — a weak password, a missing farm name, and (critically) a request that never
     reached the server at all, since `err.response` is `undefined` for a network
     failure and the optional-chain silently resolves to the fallback. That fallback
     text is *exactly* what the user reported seeing during this session's actual
     outage — confirming the outage (item 97) explains why the symptom was reported at
     all, while this parsing bug explains why the message gave no useful signal once it
     happened. The identical `err.response?.data?.<one hardcoded field>?.[0] ||
     "<generic>"` pattern was found copy-pasted into three more forms
     (`EmployeesPage.jsx`, `OnboardingEmployeesPage.jsx`, `HouseProtocolForm.jsx`'s
     category-add handler) via a repo-wide grep for the pattern, not by guessing where
     else it might be — all four fixed the same way.

102. **Fix: one shared parser, not four different hand-rolled fallbacks** —
     `frontend/src/api/errors.js` (`getFieldErrors`, `getServerErrorMessage`)
     distinguishes three DRF response shapes a form can actually receive: no
     `err.response` at all (server unreachable — a message that says so, not
     "incorrect password" or "check your fields"), `{detail: "..."}` (a view-level
     rejection — 409 farm-exists, 403, SimpleJWT's own already-specific login-failure
     message), and `{field: ["...", ...]}` (serializer validation — surfaced per-field
     where the form already has a slot for it, `CreateFarmPage`/`LoginPage`; as a
     single banner via the first field where it doesn't, the other three forms, left as
     a scoped fix rather than restructuring their layouts). `CreateFarmPage.jsx` also
     gained the two missing `{errors.admin_name}`/`{errors.farm_name}` display slots —
     the JSX only ever rendered `errors.email`/`errors.password`, so even a correctly
     -extracted error for either of the other two fields had nowhere to show before
     this.

103. **Sidebar dark theme: navy sampled directly from the pixel data of
     `welcome-bg.jpg`** (`PIL.Image.getpixel` at three flat-background points, all
     `rgb(13,27,40)`) rather than approximated by eye or reused from
     `AnimatedBackground.css`'s scrim color (`rgba(7,15,21,.3)`, which is a
     *translucent overlay* drawn on top of the image, not the image's own base tone).
     Applied as a flat color on `.sidebar` directly — not by mounting
     `AnimatedBackground` inside the sidebar column, which the task itself flagged as
     unnecessary ("no need to animate it... or a still frame if that's simpler") and
     which would in practice look wrong: that component's Ken Burns pan/zoom and cursor
     parallax are tuned for a full-bleed hero, and confined to a 264px-wide column would
     just read as visual noise, not the same "welcome screen" association the task is
     going for. Scoped every new hover/active/text color rule to `.sidebar` specifically
     (`.sidebar .sidebar-link`, `.sidebar .sidebar-link-ghost`) rather than editing the
     bare `.sidebar-link`/`.sidebar-link-ghost` classes directly, after checking where
     else those class names are used: `.sidebar-link-ghost` is reused by the mobile
     sidebar-toggle button, which renders as a sibling of `<aside class="sidebar">`,
     positioned over the still-light main content area — giving it the sidebar's new
     dark colors unscoped would have made it invisible/wrong against a light
     background. (That toggle button turns out to be permanently hidden already, via an
     inline `display:"none"` with no CSS override at any breakpoint reviving it — a
     pre-existing dead-code condition unrelated to this task, left alone rather than
     fixed since nothing here asked for a working mobile nav.)

104. **Help link: exactly one document, after actually reading all three candidates,
     not assumed from filenames** — unzipped and read the opening text of both `.docx`
     files in the repo root: `winchicken-cahier-des-charges.docx` opens "Document de
     référence pour l'implémentation (Claude Code / équipe de développement)" and
     `winchicken-spec-implementation-detaillee.docx` opens "Complément à
     winchicken-cahier-des-charges.docx — à donner à Claude Code avec ce dernier" —
     both explicitly self-describe as build-time specification documents for the dev
     team, not end-user material, confirming they should stay unlinked rather than
     guessing from the "cahier des charges" / "spec-implementation" names alone. The
     third candidate, `docs/protocol-configuration-usage-guide.pdf` (a 3-page PDF,
     distinct from the already-public `frontend/public/docs/protocol-configuration.md`
     it's based on) existed only in the repo's dev-facing `docs/` folder, not in
     `frontend/public/`, so nothing had ever actually served it to the running app —
     copied to `frontend/public/docs/` and confirmed served (`curl` returns
     `200 application/pdf`) before wiring the link. Single link, not the
     "small menu/panel" the task described for the multiple-relevant-docs case, since
     exactly one document qualified once the other two were excluded.

## Part 14 — Sidebar: search, notification bell, calendar, incident shortcut, count badges, version (2026-08-26)

105. **Audit result for Part B (notification bell) and Part C (calendar): both
     genuinely missing, not stale/broken.** `DashboardLayout.jsx` had no bell icon, no
     badge, no panel anywhere near the brand mark before this task, and no
     `/dashboard/calendar` route/link existed in `App.jsx`/`DashboardLayout.jsx` either
     — confirmed by reading both files in full before writing any code, not assumed.
     Both built from scratch per the task's own spec. The calendar's hard part (per-day
     scheduled tasks derived from `ProtocolTemplate`) turned out to already exist:
     `AlertRule` rows with `rule_type=PROTOCOL_TASK` (see `apps.protocols.services.
     expand_protocol_to_alert_rules`, Part 6 above) already carry `scheduled_date` per
     house/batch/protocol-line — the new `GET /api/protocols/schedule/?month=YYYY-MM`
     (`apps/protocols/views.py:ScheduleView`) just exposes those for a month range;
     no new scheduling logic was needed on either side.

106. **Search** (`GET /api/search/?q=`, new `apps.search` app) matches
     `PoultryHouse.name`, `PoultryBatch.name`, `StockItem.name` via `icontains`,
     capped at 6 results/group, farm-scoped via `request.user.farm` like every other
     endpoint in this project. Returns only names/codes — no financial or otherwise
     restricted data — so no role scoping beyond the global `IsAuthenticated` default
     was added; there's nothing restricted in scope to leak. A batch result navigates
     to its house's detail page (`/dashboard/houses/{houseCode}`) — there's no
     standalone batch-detail route to send it to instead.

107. **Notification bell read-state: new `Alert.is_read` field, deliberately separate
     from `Alert.status`.** `status` (NEW/SENT/RESOLVED) already exists but — per
     deviation #17 above — never actually transitions anywhere in this codebase; reusing
     it for "seen in the bell dropdown" would have meant marking something read also
     silently claimed the underlying issue was resolved, which isn't true. `is_read` is
     one shared boolean (not per-user) — this app has no existing per-user relation on
     `Alert` to hang a per-user read state off, and the farm is a single shared team, not
     a multi-tenant one, per `apps/core/serializers.py`'s "whole deployment is
     single-farm" note. New endpoints: `POST /api/alerts/{id}/mark-read/`,
     `POST /api/alerts/mark-all-read/`, `GET /api/alerts/unread-count/`, all farm-scoped
     (`rule__farm=request.user.farm`) like `AlertListView`. `AlertSerializer` gained
     `houseCode`/`houseName`/`batchName` (via `batch.house`, `null` when `batch` is
     unset) so the bell can show house/batch context without a second round-trip, and
     `is_read`. Rule-type labels (`RULE_TYPE_LABELS` in the new `NotificationBell.jsx`)
     follow `AlertsListPage.jsx`'s existing `ALERT_STATUS_LABELS` convention — raw
     `AlertRuleType` enum values are never shown to the user directly.

108. **Incident shortcut reuses `UnusualCaseReportForm.jsx` exactly, plus one new
     backward-compatible prop.** The new `IncidentShortcut.jsx` (its own
     visually-separated, `--danger`-adjacent button/card in the sidebar, not a plain nav
     link — matching the "bigger, more visible" treatment that component's own button
     already got, see its docstring) picks a house, resolves that house's `ACTIVE`
     batch via `GET /api/batches/?house_code=` (a house with no active batch — sanitary
     void — shows "Aucune bande active dans ce bâtiment" instead, since `UnusualCase.batch`
     is required and there's nothing to attach the report to), then renders
     `UnusualCaseReportForm` unmodified except for one new optional prop:
     `startOpen` (default `false`). Without it, the sidebar flow would be house-pick →
     click again to reveal the form's own collapsed-by-default textarea → fill → submit —
     three clicks deep before typing anything, on top of already being reachable from
     anywhere in the app. `startOpen` skips straight to the textarea once a batch is
     resolved. `HouseDetailPage.jsx`'s existing per-house call site is unaffected
     (prop defaults to its old behavior).

109. **Stock/Finance badges reuse the existing calculations, not new ones.**
     `GET /api/stock-items/low-count/` (new) counts items where
     `apps.stock.calculations.current_quantity(item) <= item.alert_threshold` — the
     same function `StockItem`'s low-stock alert and stock page already use, not a
     second IN-minus-OUT implementation. `GET /api/purchase-orders/pending-count/`
     (new) counts `PurchaseOrder.objects.filter(status='PENDING')`, gated by the
     existing `IsAdminOrFarmManager` permission class — the same Finance-access role
     set `FinanceSummaryView`'s `access: "full"` branch already uses (deviation #28
     above), so the badge can't leak a count to a role that can't see full Finance
     figures either. Both badges hide entirely at 0 (no "0" pill) per the task's own
     rule, and both are colored via the existing `--danger`/`--warning` tokens — this
     project already had them (`house-protocol-theme-light.css`), unlike what the task
     brief assumed needed introducing.

110. **One new shared refresh mechanism (`useSidebarNotifications`), not three.**
     The sidebar's house list doesn't poll — `useHouses`/`HousesContext` fetch once and
     refetch on `location.pathname` change (`DashboardShellContent`'s existing
     `useEffect`) or on-demand after a write. `useSidebarNotifications` (unread count +
     both badge counts) rides that exact same `useEffect`, not a separate interval —
     `refetchCounts()` is called right alongside the existing `refetch()` for houses.
     `financePendingCount` is only ever fetched for `ADMIN`/`FARM_MANAGER`
     (`canSeeFinancePendingCount` in `DashboardShellContent`) — the same
     fire-the-request-and-discard-a-403 anti-pattern `FinancePage.jsx` already avoids
     for `summary.access !== "full"`.

111. **Version string sourced from `frontend/package.json`** (bumped `0.0.0` → `1.0.0`),
     imported directly in `DashboardLayout.jsx` (`import packageJson from
     "../../package.json"`) rather than a Django settings constant + endpoint — it's a
     static frontend build artifact; a network round-trip for it would be pure waste.
     Rendered as `.sidebar-version`, 10.5px, `rgba(255,255,255,.25)` on the dark
     sidebar — deliberately low-contrast, below the user chip, per the task's own
     "not fighting for attention" instruction.

112. **Verification method, disclosed (same situation as deviation #59 above): the
     browser extension was not connected this session** (`tabs_context_mcp` returned
     "extension not connected"), so none of this task's new UI — the search dropdown,
     the bell panel, the calendar grid, the incident-shortcut modal, the badges — was
     visually confirmed on screen. What **was** verified: every new backend endpoint
     live against the running Docker stack's real data (1 farm, houses/batches/stock
     items already in the live dev DB) using JWTs minted via `RefreshToken.for_user()`
     for the farm's existing accounts (no password touched, matching deviation #30's
     precedent) — search returned the real seeded house; the schedule endpoint
     returned real `PROTOCOL_TASK` rows with correct house/batch/category context;
     stock low-count and finance pending-count returned correct live figures, and the
     Finance endpoint correctly `403`'d a non-Finance role; a temporary `Alert` was
     created to exercise unread-count → mark-read → mark-all-read end to end, then
     deleted (`Alert`/`AlertRule` test rows both removed immediately after, disclosed
     here rather than left silently in the shared dev database). The full existing
     backend test suite (15/15) still passes after the `Alert.is_read` migration. On
     the frontend: a clean `vite build` (2900 modules, no errors) and `oxlint` (no new
     warning categories beyond the `set-state-in-effect` pattern already present
     throughout this codebase, e.g. `useHouses.js`) — but not an actual rendered
     screenshot. Flagged for a human/browser-connected pass before this ships.

113. **Not committed.** The working tree already had ~75 files of unrelated
     in-progress changes (landing page, onboarding, protocol editing, weighing, etc.)
     before this task started — not this task's to fold into a commit alongside a
     six-feature sidebar change. This task's own files were left staged-ready but
     uncommitted so a human can review and commit deliberately, rather than mixing two
     unrelated bodies of work into one git history event.

## Part 15 — Backups, a real test suite + CI, an internal audit log, a richer Cashier screen, employee task assignment (2026-08-26)

Five independent additions requested together — reliability infrastructure (backups,
tests, audit log) plus two feature completions (Cashier, task assignment). Documented
as one part since they landed in one task, but each stands alone; cross-references
below say which item covers which.

### Backups (items 114–119)

114. **`pg_dump -Fc` (custom format), not plain SQL** — compressed, and the only
     format `pg_restore --clean` can selectively drop-and-recreate objects from before
     reloading. `backend/apps/core/management/commands/backup_db.py` shells out via
     `subprocess`, reading connection params from `settings.DATABASES['default']`
     (never hardcoded) — the same values Django itself already uses, so there's
     nothing to keep in sync separately. Deletes a dump immediately if `pg_dump`
     exits non-zero, so a failed/truncated attempt is never silently counted toward
     retention or left looking like a valid backup.

115. **`postgresql-client` had to be added to `backend/Dockerfile`** — the runtime
     image only had `libpq5` (the C runtime library `psycopg2` links against), not the
     client *binaries* (`pg_dump`/`pg_restore`/`psql`), since nothing needed them
     before this task. Installed the generic Debian `postgresql-client` meta-package
     rather than pinning `postgresql-client-16` to exactly match the `db` service's
     Postgres 16 image — confirmed after building that this resolves to client tools
     from Postgres 17 (`pg_dump --version` in the built image), one major version
     ahead of the server. Left as-is rather than adding the official PostgreSQL apt
     repo just to pin an exact match: `pg_dump`/`pg_restore` are documented as
     forward-compatible with older server major versions for this direction (newer
     client, older server), and a live round-trip backup+restore test (item 119)
     confirmed it actually works end-to-end against this project's real Postgres 16 —
     not just assumed compatible.

116. **Retention default 7, read via `python-decouple`'s `config()`** (same library
     `backend/config/settings.py` already uses for every other env-driven setting),
     not a Django setting — `backup_db.py` is a standalone script-like command with no
     other reason to touch `settings.py`, so reading the env var directly where it's
     used keeps the change smaller. `BACKUP_RETENTION_COUNT`/`BACKUP_INTERVAL_SECONDS`
     both documented in `backend/.env.example`.

117. **Scheduling: a new `backup` service running a `sh -c 'while true; do ...;
     sleep ...; done'` loop, not cron inside `web`/`worker`, and not Celery Beat** —
     three options existed. Celery Beat was rejected first: this project already has
     Celery+Redis running, and Beat is even documented as a "Key Command" in the
     project's own config notes, but `docs/deviations.md` has repeatedly noted (Part
     6 item ~46, Part 10 item 86) that *no* Beat schedule has ever actually been wired
     up anywhere in this codebase — making backups the very first thing to depend on
     it would be a bigger, riskier change than the task asked for, for a feature (SMS
     alert scheduling) this task has nothing to do with. Real cron inside a container
     needs a foreground-process wrapper (supervisor, or a cron daemon started as PID 1
     with proper signal handling) to behave correctly under Docker — meaningful extra
     complexity for "run one command roughly once a day." A plain shell loop, reusing
     the exact same `web`/`worker` image (already has `pg_dump` after item 115), is
     the smallest correct thing that satisfies the task's own "or a small additional
     lightweight cron container/service" alternative. Interval-since-container-start
     instead of calendar-time ("2am nightly") is a deliberate simplification: nothing
     in this app cares what time of day a backup runs, only that one runs roughly
     daily and old ones are pruned.

118. **The base image's `HEALTHCHECK` (curls `:8000/api/health/`) had to be disabled
     for this service** (`healthcheck: disable: true` in `docker-compose.yml`) — the
     `backup` service never serves HTTP, so the inherited check would report
     permanently unhealthy for a container that's actually working correctly. Same
     reasoning `worker` already applies (it overrides the check with a Celery-specific
     one instead) — `backup` has nothing analogous to check at the container level
     ("did the last loop iteration's backup succeed" isn't expressible as a
     healthcheck), so verification is `ls backend/backups/`, documented in the README,
     rather than a fake always-true check.

119. **Verified with real `pg_dump`/`pg_restore` subprocess calls, including a full
     round-trip restore, against Django's isolated test database — never the real dev
     database** (same caution as the factory-reset feature's own tests, Part 12 item
     96): `BackupRestoreTests` (`TransactionTestCase`, not `TestCase` — `pg_dump`
     connects as its own separate process and only sees *committed* data, which
     `TestCase`'s always-rolled-back per-test transaction would hide) creates a `Farm`
     row, backs up, deletes it via the ORM, restores from the dump, and asserts the
     row is back. Also manually triggered a real backup against the actual running
     dev stack (`docker compose exec web python manage.py backup_db` and via the new
     `backup` service itself) and confirmed with `pg_restore --list` that the dump is
     a genuine, complete 317-table-object archive — not just that the command exited
     0.

### Tests + CI (items 120–125)

120. **`pytest` + `pytest-django` added specifically because the task named `pytest`**
     — the existing test suite (this project's own, from Parts 12–13) already used
     Django's/DRF's `TestCase`/`APITestCase` via `manage.py test`, which is a
     legitimate, un-migrated-away-from convention, not something to rewrite into
     pytest-style function tests just to match the letter of the request.
     `pytest-django` runs the *exact same* `TestCase`/`APITestCase` classes unchanged
     under `pytest` (confirmed: `pytest` collected and ran all pre-existing +new tests
     with zero test-file changes needed) — the smallest change that makes `pytest`
     work as asked without a disruptive rewrite. `backend/pytest.ini` points
     `DJANGO_SETTINGS_MODULE` at `config.settings`.

121. **Six new backend test files/classes, one per named regression-prone area** —
     `LoginTests` (admin + employee login, `is_configured` reflecting real farm
     state), `SingleActiveBatchConstraintTests` (asserts the DB constraint itself, not
     just a view), `CurrentCountTests` (including the "edit an already-logged day"
     correction case that motivated the computed-property switch in Part 10 item 87),
     `ProtocolSaveAlertRuleRegenerationTests` (built a *past*, already-fired
     `AlertRule`+`Alert`+`SmsMessage` directly via the ORM alongside a *future*
     protocol line, edited the protocol through the real `PUT` endpoint, and asserted
     the future row regenerated with a new schedule while the past row/Alert/SmsMessage
     were completely untouched — the literal scenario this task described as having
     broken before), `AuditLogTests`, `TaskAssignmentTests`. `FinanceAccessTests`
     (restricted vs. full payload shape) already existed from earlier work — checked
     before writing a duplicate, per this session's standing practice.

122. **`FeedConversionRatioTests` asserts what the codebase actually does, not what
     the task assumed it does** — the task's Part B item 6 said "Feed conversion
     ratio computed from `StockMovement`, not from any deprecated field." Checked
     `apps/batches/calculations.py::feed_conversion_ratio` before writing anything:
     it computes `SUM(DailyLog.feed_consumed_kg) / (current_count * latest
     avg_sample_weight)`, per implementation-detail spec 5.1 — there is no
     `StockMovement`-based FCR calculation anywhere in this codebase, and
     `feed_consumed_kg` is not deprecated; it's the one and only spec-mandated
     source. Writing a test (or, worse, new production code) around the task's
     `StockMovement` premise would have been a real regression against the documented
     spec to satisfy a wrong assumption. The test asserts the actual, correct,
     already-spec-compliant behavior instead, and this discrepancy is called out
     explicitly in the test's own docstring so a future reader isn't confused about
     why the test doesn't mention `StockMovement` at all.

123. **Frontend testing didn't exist at all — checked first, per the task's own
     instruction, before adding anything.** `frontend/package.json` had no test
     script and no `@testing-library`/`vitest`/`jest` dependency anywhere. Added
     Vitest + React Testing Library + `@testing-library/user-event` +
     `@testing-library/jest-dom` + `jsdom` — the standard pairing for a Vite project
     specifically (Vitest reads the same `vite.config.js`, no separate config file,
     no separate bundler to keep in sync). Installed via the host's own `node`/`npm`
     (v24, confirmed present), not inside the `frontend` Docker container — the
     container's `node_modules` is a *named volume*, separate from the bind-mounted
     source tree, so a container-side `npm install` wouldn't have been visible to the
     container anyway without a rebuild; host-side install is also simply how this
     session already had oxlint/vite build working throughout every prior task.

124. **A real, narrow Vitest/Vite-version bug found and fixed, not routed around** —
     every rendered test failed with `ReferenceError: React is not defined`,
     including inside *source* files (`HouseProtocolForm.jsx`, `ProtocolEditModal.jsx`,
     `OnboardingEmployeesPage.jsx`) that have never needed a `React` import and build
     fine under real `vite build`/`vite dev` throughout this entire session — proving
     this wasn't a mistake in the new test files, but Vitest's own (separate,
     esbuild-based) transform not correctly inheriting `@vitejs/plugin-react`'s
     automatic-JSX-runtime setting from this project's Vite 8 (rolldown-based) build
     pipeline. Fixed once, centrally, with `esbuild: { jsx: 'automatic' }` in
     `vite.config.js`'s top level (read by both Vite's real build and Vitest) — not
     by adding a `React` import to every source file under test, which would have
     been a much wider, backwards-looking change to files that are otherwise correct.

125. **The three requested regression tests, against what's actually real, not
     assumed:**
     - *Sidebar staleness* (`ProtocolEditModal.test.jsx`) — mocks `HouseProtocolForm`
       (a large, separately-tested surface; the regression lives in
       `ProtocolEditModal`'s own save-handling, not the form's internals) and asserts
       `useHousesContext().refetch()` is called after a save. **Sanity-checked live**,
       per the task's explicit verification step: commented out the `refetchHouses()`
       call, reran the test, watched it fail with a real timeout/assertion error, then
       reverted and reran to confirm it passes again.
     - *Suivant/Sauter enable-disable* — checked which button actually has
       data-dependent disabling before writing assertions: `HouseProtocolForm`'s save
       button (labeled "Suivant" in onboarding mode) is `disabled={saving || totalRows
       === 0}` — genuinely data-gated, tested by clicking the real "Charger le modèle
       de départ" button and observing it flip from disabled to enabled.
       `OnboardingEmployeesPage`'s own Suivant/Sauter are gated only on `saving`, not
       on entered data (this step is deliberately skippable, per its own on-screen
       "Facultatif" copy) — tested that reality instead of fabricating a data-gate
       that doesn't exist there, and separately tested the page's one genuinely
       data-dependent behavior, the "Ajouter un autre employé" validation (rejects an
       incomplete entry rather than silently accepting it).
     - *"Modifier" modal* — grepped `HouseProtocolForm.jsx` and `ProtocolEditModal.jsx`
       for "Réinitialiser" before writing an assertion about it: it doesn't exist
       anywhere in this codebase. The two "Annuler" buttons found are for unrelated
       sub-flows (canceling add-category, canceling delete-category), not a
       form-level cancel/reset. What's real and tested instead: management mode shows
       "Enregistrer le protocole" and never the onboarding-only "Suivant" button, and
       loads with the `initialHeader`/`initialCategories`/`initialSchedules` it's
       given rather than blank fields (`getByDisplayValue` on the pre-filled
       building/batch names and a protocol line's own label).

126. **`.github/workflows/ci.yml`** — two independent jobs (backend/frontend) rather
     than one sequential job, so a frontend lint failure doesn't hide the backend
     job's result or vice versa. Backend job runs against a real `postgres:16`
     service container (not sqlite) — this suite exercises real DB-level constraints
     (`one_active_batch_per_house`, `Farm.singleton_lock`) and `BackupRestoreTests`
     shells out to real `pg_dump`/`pg_restore`, neither of which sqlite could stand in
     for.

### Audit log (items 127–130)

127. **`AuditLogEntry` gained a `farm` FK the task's own field list didn't
     mention** — every other farm-scoped model in this codebase (`StockItem`,
     `AlertRule`, `Expense`, ...) has one, and without it `/dashboard/audit`'s
     queryset would have no way to scope results to the requesting farm at all
     (single-farm-per-install or not, the model layer's own convention is to scope
     explicitly, not rely on there only ever being one farm row). `on_delete=CASCADE`
     like everything else — meaning this internal log is deliberately wiped by a
     factory reset along with the data it describes, which is exactly why the task
     asked for it "in addition to," not "instead of," the reset's own external
     plain-text log file: this table covers "while the data still exists," the
     external file covers "after." The `farm.reset` action is logged via this same
     `record_audit_log()` call for consistency, immediately before `farm.delete()`
     cascades it away — it exists for the length of one transaction and is never
     actually readable afterward, which is expected, not a bug.

128. **One shared service function, not a decorator** — the task offered either
     ("a small reusable decorator/service function"). A decorator would need to
     either introspect the view/serializer to build a human-readable
     `target_description` (fragile, magic) or take a static description template with
     no access to the object that was actually created/edited/deleted (useless for
     "Bande Printemps 2026"-style specificity). `apps.core.services.record_audit_log
     (user, action, target_description)` is called explicitly, one line, right after
     each real mutation succeeds — the caller already has the created/updated/deleted
     object in scope at exactly that point, so building an accurate description costs
     nothing extra.

129. **Wired into `perform_create`/`perform_update`/`perform_destroy` overrides on
     existing DRF generic views wherever possible** (batches, employees), a plain
     call after the transaction in hand-written views otherwise (protocol PUT, stock
     PUT, factory reset) — never a new abstraction layer, matching how audit-adjacent
     logic already lives in this codebase (e.g. `record_quick_entry`,
     `expand_protocol_to_alert_rules`). Thirteen call sites total: batch
     created/updated/deleted/closed, protocol updated, employee
     created/updated/deleted, stock updated, expense/sale/purchase-order created,
     farm reset.

130. **`/dashboard/audit` filters server-side (`?action=&date_from=&date_to=`), not
     client-side** — this table has no natural upper bound on how large it grows over
     a farm's lifetime, and DRF's project-wide default pagination (`PAGE_SIZE=20`)
     already caps any single response; filtering after the fact client-side would
     silently only ever filter within whatever one page happened to load.

### Cashier screen (items 131–133)

131. **"Ventes du jour" already existed** (a farm-wide, not per-cashier, list of
     today's sales, auto-refreching via the existing `load()` call after every
     submit) — this task's actual gap was a running total and receipts, so that's all
     that was added; the existing list/refresh discipline was reused unchanged and
     confirmed, not rebuilt.

132. **No PDF library anywhere in this codebase, checked before choosing an
     approach** — `BatchClosingReport` (the only other "report" concept here) is a
     `ModelSerializer` returning JSON, consumed nowhere in the frontend at all
     (grepped `frontend/src/` for any reference — none exist); there was no existing
     "PDF approach" to reuse as the task suggested there might be. `ReceiptModal.jsx`
     uses the browser's own `window.print()` instead of adding a PDF-generation
     dependency (WeasyPrint needs Pango/Cairo system libraries baked into
     `backend/Dockerfile` for a single low-traffic feature; `reportlab` would be
     backend-only and this data is already sitting client-side from the sales list,
     no new endpoint needed) — the task explicitly allowed "a clean print-styled
     view" as the alternative. "Downloadable" is covered by the print dialog's own
     "Save as PDF" destination.

133. **`@media print` scoped to `.receipt-print-area` only** (`styles/receipt.css`) —
     hides everything else on the page (modal backdrop, close button, the dashboard
     behind it) via `body * { visibility: hidden }` + a visibility override on just
     that one subtree, so printing a receipt never leaks surrounding app chrome onto
     paper. No backend endpoint added: the `Sale` row is already in hand from the
     "Ventes du jour" list that renders the "Reçu" button.

### Employee task assignment (items 134–138)

134. **Assignment split across two different models, deliberately, per the task's own
     "and/or"** — `ProtocolTemplate.assigned_to` for ordinary protocol-line tasks,
     `AlertRule.assigned_to` for the recurring weighing reminder specifically. Traced
     why before writing either: the "tâches à effectuer maintenant" panel's
     protocol-line entries are computed live every request from `ProtocolTemplate`
     rows re-filtered by day-of-cycle — `line.id` is the one stable, persisted
     identity a task actually has across the days it's visible, so that's where
     assignment lives. The matching `PROTOCOL_TASK` `AlertRule` rows are the *wrong*
     attachment point for this: `expand_protocol_to_alert_rules` deletes and
     recreates them only for lines whose `scheduled_date` is today-or-future, so a
     task already underway (past its start day, still showing in the panel) usually
     has **no** backing `AlertRule` row left to attach anything to at all — confirmed
     by reading that function's own deletion filter before assuming it would work.
     The weighing reminder is different: its `AlertRule` row (`WEIGHING_REMINDER`) is
     explicitly documented as stable/persistent, replaced only when the frequency
     setting itself changes (`sync_weighing_reminder`'s docstring) — not pruned daily
     like `PROTOCOL_TASK` rows — so it's a reliable attachment point, and there's no
     `ProtocolTemplate` row backing this particular task anyway (it's derived from
     `PoultryBatch.weighing_frequency`, not a protocol line).

135. **Known, accepted limitation: assignment is lost on the next protocol save** —
     `HouseProtocolView.put` does a full delete-and-recreate of a house's
     `ProtocolTemplate` rows on *every* save (documented behavior since before this
     task), so editing even one unrelated line wipes every line's `id` — and with it,
     every line's `assigned_to`. Not engineered around (e.g. by matching old-to-new
     lines heuristically on content) — the task's own framing ("assignment is
     optional... additive, not a restriction") supports treating it as a best-effort
     layer, and the existing full-replace semantics are a pre-existing, independently
     load-bearing design decision from earlier work, not something to compromise for
     this feature. Documented directly in `ProtocolTemplate.assigned_to`'s own
     docstring so it's visible at the point someone would next touch this code.

136. **One assign endpoint, not two** — `PATCH /api/houses/{houseCode}/tasks-now/
     {taskId}/assign/` accepts either task-id shape `HouseTasksNowView` already
     returns (a bare `ProtocolTemplate` pk, or `weighing-{batchCode}`) and resolves to
     the right underlying row internally, rather than exposing two differently-shaped
     endpoints the frontend would need to choose between. Reserved to
     `CanEditHouseProtocol` (Admin/Farm Manager/Farmer) — reusing the exact permission
     class already gating protocol edits, per the task's own role list, rather than
     defining a new one.

137. **`compute_tasks_now` extracted into a new `apps/houses/services.py`, used by
     both `HouseTasksNowView` and the new `MyTasksView`** — this project has already
     been bitten once by near-identical logic living in two places and drifting out
     of sync (the sidebar-staleness bug, Parts 5–6, and the regression test in item
     125 above pins exactly that class of bug down). Rather than writing "Mes
     tâches" as a second, hand-rolled query, it iterates every house with an active
     batch and calls the exact same function the per-house panel calls, then filters
     to the requesting user — the only new logic is the filter and the
     houseCode/houseName tagging, not a parallel computation.

138. **Verified live against Django's real, isolated test database**
     (`TaskAssignmentTests`) — an Admin assigns a protocol-line task to a Worker,
     confirmed the Worker's `GET /api/tasks/mine/` returns exactly that task with the
     correct house context, confirmed a *different* employee's "mine" stays empty
     while the task still appears in the ordinary per-house panel (additive, not a
     restriction — Part E item 4), confirmed a Worker gets 403 attempting to assign,
     and confirmed clearing an assignment (`assigned_to: null`) works. One real bug
     surfaced and fixed during this: the first version of this test's own fixture set
     the batch's `start_date` to today, giving `day_of_cycle=0` — one day *before*
     the test's `from_value=1` protocol line was due, so the task correctly didn't
     appear yet. Not a bug in the feature; a fixture off-by-one, caught by the test
     failing exactly as it should, fixed in the fixture.

## Part 16 — Farm health score, cycle timeline with milestones, upcoming-48h widget, prominent "Cas signalés" (2026-08-26)

Four additive dashboard features requested together. `lean-scope` was named in the
task but isn't an installed skill (checked via tool search before assuming
otherwise) — its evident intent (no file bloat, no scope beyond what's described)
was applied by hand instead: one new backend service function shared by two
features (item 141), CSS consolidated into the existing `dashboard-theme.css`
rather than four new stylesheets, and every model/serializer/view change kept to
exactly what each part needed.

### Farm health score (items 139–142)

139. **Two premises checked against the real codebase before writing anything, both
     wrong, both corrected rather than worked around silently** — `AlertRuleType` has
     no `MORTALITY_SPIKE`/`WEIGHT_DEVIATION` (grepped the enum; the real,
     automatically-fired types are only `LOW_STOCK` and `CONSUMPTION_DEVIATION` — see
     that enum's own docstring, already documented in an earlier part of this file).
     Rather than inventing those alert types just to satisfy the task's example, the
     mortality/FCR breach signals are computed directly from `weekly_kpi`/
     `feed_conversion_ratio` — which is exactly what the task's own item 1 already
     asked for as the first two signals, independent of the alert-type example in
     item 2.

140. **The mortality-breach formula reuses `WeeklyKpiCharts.jsx`'s own red-bar-week
     logic to the letter, not just in spirit** — that component (untouched by this
     task, per the "don't touch the growth/survival/IC curves" rule) colors a week's
     bar red when `w.mortalityPct > 5 / weeks.length`. `farm_health_score`
     (`apps/batches/calculations.py`) applies the identical formula to
     `weekly_kpi(batch)`'s own latest week, but writes `MORTALITY_REFERENCE_RANGE[1]`
     instead of a bare `5` — the same module-level constant `weekly_kpi`'s own
     `referenceRange.mortalityPct` is already built from, so the frontend chart and
     this new backend signal can never drift to different literal thresholds even if
     `MORTALITY_REFERENCE_RANGE` is ever tuned.

141. **Tier rules deliberately simple and stated as a literal, auditable table** (see
     `farm_health_score`'s docstring and the README's "Farm health score" section,
     word-for-word the same rules in both places) — 2+ breaches or any open
     danger-severity alert is Critique; exactly 1 breach or any open alert at all is
     À surveiller; otherwise Bonne. `Alert.severity` is free-text (not an enum), but
     in practice only `'warning'`/`'danger'` are ever written (`apps.alerts.services`
     — `LOW_STOCK` always fires at `'danger'`, `CONSUMPTION_DEVIATION` at
     `'warning'`), so "any open danger alert" in practice means "any open low-stock
     alert" — stated honestly in the docstring rather than implying a richer severity
     model exists.

142. **Verified the exact scenario the task's own verification section asked for**:
     `FarmHealthScoreTests.test_open_danger_alert_forces_critical_and_resolving_
     reverts_to_good` calls the real `apps.alerts.services.trigger_alert` (not a
     hand-built `Alert` row) with `rule_type='LOW_STOCK'`, confirms the badge reads
     `critical`, sets the alert's `status` to `RESOLVED`, and confirms the badge
     reverts to `good` on the next request — no caching anywhere in this endpoint to
     invalidate, it's computed fresh every call, same as `compute_tasks_now`.

### Cycle timeline + upcoming-48h widget (items 143–146)

143. **One shared computation, `apps.houses.services.compute_cycle_milestones`, not
     two** — the per-house timeline needs every milestone across the whole cycle; the
     global 48h widget needs the same milestones filtered to `dayOfCycle <= day <=
     dayOfCycle + 2` across every house. Rather than writing the 48h widget as its
     own query, `Upcoming48hView` calls the identical function `HouseMilestonesView`
     calls, per house, and filters the result — per this task's own explicit "reuse
     existing live-computation logic... rather than writing parallel calculations for
     the same underlying data" instruction, and to avoid this project's own
     documented history of near-identical logic drifting apart when it's written
     twice (the sidebar-staleness bug, cited again in Part 15 item 137 for the
     identical reason).

144. **Deliberately scoped to `ProtocolTemplate`-derived milestones only — the
     recurring weighing reminder is left out of this projection**, even though it's
     already surfaced in `compute_tasks_now`. The task's own Part B wording is
     specific ("every upcoming `ProtocolTemplate`-derived milestone"); the weighing
     reminder is a different, non-protocol-line mechanism (`PoultryBatch.
     weighing_frequency`, recurring), and folding it into the same list would need
     its own recurrence-expansion logic (every Nth day up to the cycle end) that
     wasn't asked for — left out rather than added speculatively, per the `lean-scope`
     intent (item above).

145. **No `ProtocolTimeSlot`/time-of-day concept exists anywhere in this codebase** —
     grepped `apps/protocols/models.py` and the calendar view (`apps.protocols.
     views.ScheduleView`) before assuming otherwise; the calendar itself only ever
     reads a plain `AlertRule.scheduled_date` (no time component). Every
     `Upcoming48hView` entry is therefore a day-level `"aujourd'hui"`/`"demain"`/`"dans
     N jours"` label, never an exact time window — the task's Part C item 2 offered
     that as a conditional ("if set"), so this isn't a shortfall against what was
     asked, just confirmation that the condition never triggers in this codebase.

146. **`cycle_length` falls back gracefully when `PoultryBatch.planned_end_date` is
     unset** — that field is nullable at the model level (existing behavior, not
     changed here) and not every batch in this project's own history has it set.
     `compute_cycle_milestones` falls back to the furthest projected milestone's day
     (or `day_of_cycle` itself with zero milestones) rather than a hardcoded default
     or a crash, so the timeline always has *some* sensible width to render.

### "Cas signalés" (items 147–151)

147. **`UnusualCase` had no resolution concept at all before this task — checked, not
     assumed** — grepped the model and its serializer/views; only `EquipmentFault`
     had a free-text `status` field (default `"REPORTED"`), and even that had no
     endpoint to ever change it (already documented as a known gap in that model's
     own pre-existing docstring, referencing the cahier des charges section 8
     "Valider une tâche de maintenance" permission-matrix row). Added `UnusualCase.
     resolved`/`resolved_at` (a plain boolean + timestamp, matching the task's own
     "e.g. a status field update" suggestion) and a `PATCH`-equivalent `POST .../
     resolve/` action for both models — dedicated action endpoints, not a generic
     `PATCH`, matching this codebase's existing convention for state-transition
     actions (`AlertMarkReadView`/`AlertMarkAllReadView`, not a generic alert `PATCH`).

148. **No photo field exists anywhere on either model — checked, not assumed** —
     grepped the whole backend for `photo`/`ImageField`/`image` and the frontend for
     any camera/photo UI; found nothing on `UnusualCase`, `EquipmentFault`, or
     anywhere else. The task's "photo if one was attached, per the earlier
     photo-attachment feature" describes a feature that was never actually built in
     this codebase's history — omitted from the incident card rather than
     represented with a fake placeholder or a broken image reference.

149. **"Time since reported" is day-granularity, not hours/minutes** — `case_date`/
     `reported_date` are both plain `DateField`s with no time component (existing
     schema, unchanged) — this task didn't add a `DateTimeField` just to get finer
     precision for one display string, since that would touch the reporting flow's
     own data shape for a cosmetic gain nobody asked for explicitly. `daysAgoLabel`
     (`IncidentsPanel.jsx`) renders `"Aujourd'hui"` / `"Il y a 1 jour"` / `"Il y a N
     jours"` — the best precision the real data actually supports.

150. **Resolve permissions differ between the two models, deliberately** — reporting
     an `EquipmentFault` is already `IsAdminOrTechnician`-only, so resolving one
     reuses that same role set. Reporting a `UnusualCase` is open to *any*
     authenticated farm user (existing behavior, unchanged) — but resolving one
     (judging a health/safety observation as handled) was scoped narrower, to
     `IsAdminOrFarmManagerOrFarmer`, so a Worker who files a case can't also be the
     one who marks it resolved with no second set of eyes. Not specified by the task;
     a reasonable, disclosed judgment call.

151. **`IncidentsPanel.jsx` is one component reused verbatim on both views, not a
     styled-alike pair** — `houseCode` omitted (global view, farm-wide) or set
     (per-house view, `?house_code=` passed to both list endpoints server-side) is
     the only difference in how it's invoked; the task's own instruction ("consistent
     styling... just filtered") is satisfied by literally sharing the component
     rather than two implementations kept in sync by hand. Verified live against
     Django's isolated test database (`MaintenanceIncidentTests`): reported a case and
     a fault, confirmed both appear in the open-filtered list, resolved one, confirmed
     it disappears from the `?resolved=false`/`?status=OPEN` filter, confirmed the row
     still exists in the database (`UnusualCase.objects.filter(...).exists()` still
     `True`) and that its resolve action produced a real `/api/audit-log/` entry —
     the exact "disappears from this view but remains in the audit log" behavior the
     task's verification section asked for.

### Civility field & personal task-reminder SMS (items 152–156)

152. **`User.civility` given a model-level default (`M`) rather than left nullable** —
     the task's own instructions offered two options for pre-existing accounts:
     prompt once on next login, or default to a placeholder requiring an admin fix
     via `/dashboard/employees`. Neither `M` nor `MME` is a neutral "placeholder"
     value, and a login-prompt flow would mean building a new UI/gate for a
     one-time, likely-empty local dev database (no real user base to migrate). Went
     with `default='M'` at the DB level: the migration backfills every existing row
     to a concrete, non-null value (so `apps.alerts.templates.render_task_reminder`
     never crashes or silently drops the civility clause), and both creation forms
     (`FarmCreateSerializer`, `EmployeeSerializer`) mark the field `required=True`
     regardless, so every *new* account picks a real value explicitly. An admin can
     still correct a backfilled account's civility via the existing employee-edit
     form — no separate "fix this" flow was built since one already existed.

153. **`{name}` in the reminder template uses the first whitespace-separated token
     of `User.name`, not the whole name** — checked, not assumed: `User.name` is a
     single free-text `CharField` everywhere in this codebase, no separate
     first/last-name columns. The task's own worked example ("Bonjour Monsieur
     Jean, ..." from a user presumably named "Jean Dupont" or similar) implies a
     first-name-only greeting, so `apps.alerts.templates._first_name` splits on the
     first space. Falls back to the full string unchanged for a single-word name.

154. **EVENT-type alert templates were *not* moved into the new `templates.py`
     module** — the task both asked to "centralize this template alongside the
     existing EVENT-type templates... in the same `templates.py` module" and,
     separately, explicitly forbade touching "the EVENT-type alert templates or
     their triggering logic." Checked the codebase for that "earlier Twilio task":
     no `templates.py` exists anywhere, and the EVENT messages (`LOW_STOCK`,
     `CONSUMPTION_DEVIATION` — the only two EVENT rules actually wired to a
     signal, see `AlertRuleType`'s own docstring) are inline f-strings in
     `apps.alerts.services.check_low_stock`/`check_consumption_deviation`. Moving
     them into a new module to satisfy "centralize" would be an edit to their
     existing code, which the "don't touch" rule takes precedence over. Resolution:
     created `apps.alerts.templates` holding only the new SCHEDULED task-reminder
     template, with a module docstring explaining exactly where the EVENT strings
     still live and why they weren't moved.

155. **`ProtocolTimeSlot` is a new model — it did not exist anywhere in this
     codebase before this task** — checked, not assumed: grepped the whole backend
     and the puml for `TimeSlot`/`start_time`/`startTime`, found nothing.
     `apps.protocols.services.expand_protocol_to_alert_rules` generates exactly one
     `AlertRule` per `ProtocolTemplate` line with a hardcoded `trigger_time='08:00'`
     — no per-line multi-time-slot concept existed for the reminder template to key
     off. Added `ProtocolTimeSlot` (FK to `ProtocolTemplate`, one `start_time` each)
     so `apps.alerts.templates.build_task_reminders` can generate one correctly-
     timed reminder per slot, or a single no-time-clause reminder ("...aujourd'hui")
     for a line with none. **No frontend UI manages these yet** — out of this
     task's stated scope (template content + recipient resolution, not the
     protocol-editor UI) and a meaningful multi-time-slot editor for
     `HouseProtocolForm.jsx` is a separate feature in its own right. Slots can be
     created/edited via `/admin/` in the meantime (`apps.protocols.admin`).

156. **The task-reminder template/recipient logic is implemented as pure,
     unit-tested functions (`apps.alerts.templates.build_task_reminders` /
     `render_task_reminder` / `resolve_task_reminder_recipient`), not wired into an
     actual SMS dispatch path** — per this task's own rule ("don't touch the SMS
     sending/retry/idempotency mechanism itself"), and per the pre-existing
     documented fact that no `SCHEDULED` `AlertRule` (which `PROTOCOL_TASK` rows
     always are) ever actually fires in this codebase: there is no Celery Beat
     schedule configured anywhere (`config/celery.py` has no `beat_schedule`), a
     gap already called out in `AlertRule`'s own docstring and in earlier
     deviations. Building a Beat-triggered dispatch task for this reminder type
     would mean building the very SCHEDULED-firing mechanism this task didn't ask
     for and its rules said not to touch. `apps.alerts.tests.TaskReminderTemplateTests`
     exercises the three Verification-section scenarios directly against these
     functions (two time slots → two correctly-timed messages, no time slot →
     "...aujourd'hui", no assignee → falls back to the batch's Fermier, and an
     added case: no assignee *and* no Fermier → no reminder sent to anyone).

### Bug fixes from live testing feedback (items 157–166)

157. **Bug 1 ("Horaires" missing) root cause — two-fold, exactly as the task
     suspected, not a re-application of anything already done** — investigated
     fresh: (1) `python manage.py showmigrations` confirmed `protocols.
     0004_protocoltimeslot` was both written *and applied*, so the model/migration
     were never the problem; (2) `ProtocolTemplateSerializer` never had a
     `time_slots` field at all — `GET/PUT /api/houses/{houseCode}/protocol/`
     genuinely never sent or accepted them; (3) grepped the whole frontend for
     `time_slot`/`TimeSlot`/`Horaires` and found nothing — the shared
     `HouseProtocolForm.jsx` row component (confirmed literally shared between
     `OnboardingProtocolPage.jsx` and both "Modifier" entry points —
     `ProtocolEditModal.jsx` and the standalone `HouseProtocolPage.jsx` route, the
     latter easy to miss since it's not the modal) never rendered a "Horaires"
     section. All three were fixed: serializer + views wired end-to-end, and the
     UI added to the one shared row component so it appears in both onboarding and
     both "Modifier" entry points.

158. **`ProtocolTimeSlot` gained an `end_time` field — a deliberate change from
     the earlier task's single-point `start_time`-only design** — the earlier SMS-
     reminder task modeled a slot as one instant ("feeding at 07h00"); this task's
     own UI spec explicitly wants a *window* per slot (chip reading "07h00–09h00",
     two time pickers, "validating end-after-start"). Added `end_time` (new
     migration, zero existing rows confirmed before writing it as a straight
     `NOT NULL` add) and a `ProtocolTimeSlotSerializer.validate` rejecting
     end-before-start. `apps.alerts.templates.render_task_reminder` (the SMS
     template) is unchanged and still only reads `start_time` — the reminder still
     fires "à {start_time}", not a range — per this task's own "don't touch SMS/
     notification logic" rule; the window is a UI/scheduling concept the reminder
     text doesn't need.

159. **Time slots are a full-replace, not a merge, on every protocol save** —
     matches the existing `ProtocolTemplate` convention exactly
     (`HouseProtocolView.put`/`OnboardingView.post` already delete-and-recreate a
     house's whole protocol on every save): `time_slots` is popped out of each
     validated line dict before `ProtocolTemplate.objects.bulk_create` (it isn't a
     real model field, it's the reverse FK), then `ProtocolTimeSlot` rows are
     created against the real pks `bulk_create` returns. A row's `id` in the API
     response is informational only — the frontend never sends an existing slot's
     id back to "update" it in place, consistent with how `ProtocolTemplate` rows
     themselves already work.

160. **Bug 2 root cause — `IsFarmerOrWorker` on `DailyLogQuickEntryView`/
     `DailyLogListCreateView`, a genuine role-check regression, not an intentional
     restriction** — confirmed by grep: `IsFarmerOrWorker` (`role_permission(FARMER,
     WORKER)`) was used in exactly those two spots and nowhere else, so narrowing
     the fix to just those two call sites carried no risk of loosening an
     unrelated, intentionally-narrow check (protocol editing's `CanEditHouseProtocol`
     and finance's `IsAdminOrFarmManager`/`IsAdminOrCashier` were never touched).
     Replaced with a new `IsAdminOrFarmManagerOrFarmerOrWorker` (deleted the now-
     unused `IsFarmerOrWorker` rather than leave dead code). Technician/Cashier
     access to weighing/mortality entry: **left excluded** — a judgment call, not
     specified by the task; husbandry data entry doesn't fit either role's own
     section-8 responsibilities (equipment faults / finance, respectively), and
     nothing in the bug report asked for them. Verified with a new
     `DailyLogQuickEntryPermissionTests` covering all 6 roles, so a future
     accidental re-narrowing is caught by CI, not just manual QA.

161. **Bug 3 root cause — the calendar read `PROTOCOL_TASK` `AlertRule` rows,
     which are only ever generated for a line's *first* due day** —
     `apps.protocols.services.expand_protocol_to_alert_rules` creates exactly one
     `AlertRule` per `ProtocolTemplate` line, dated `batch.start_date + from_value`
     — never one per day of a multi-day range. `ScheduleView` (`GET /api/protocols/
     schedule/`) read those rows directly, so a day-1-to-15 line was only ever
     visible on day 1. Fixed by computing the month view directly from
     `ProtocolTemplate` + each house's active batch (`apps.houses.services.
     compute_month_schedule`), reusing the *exact* day-in-range check
     `compute_tasks_now` already uses for "today" — extracted into a shared
     `_protocol_line_occurrence` helper so the two can never drift apart again
     (this project has already been bitten once by near-identical logic living in
     two places and diverging, per `compute_tasks_now`'s own docstring). Verified
     with `ScheduleViewMultiDayTests`: a day-1-to-15 line now appears on all 15
     days, an `until_end` line keeps appearing for the rest of the visible month,
     and nothing appears in a month before the batch started.

162. **`expand_protocol_to_alert_rules`/`PROTOCOL_TASK` `AlertRule` generation was
     deliberately left untouched, even though it's now redundant for calendar
     purposes** — after the Bug 3 fix, nothing reads these rows for the calendar
     anymore (nothing ever read them for "tâches à effectuer maintenant" either —
     that panel always computed straight from `ProtocolTemplate`). Removing the
     generation entirely would mean editing `apps.protocols.services`/the
     `apps.alerts` models — adjacent to "notification logic," which this task's
     rules said not to touch, for a cleanup that wasn't asked for. Left as
     harmless, inert leftover plumbing rather than risk touching out-of-scope code.

163. **Feature 4 root cause — the assignee dropdown reused `GET /api/employees/`,
     which is Admin/Secondary-Admin-only and self-excluding** — `TasksNowPanel.jsx`
     called `employeesApi.list()` to populate the `<select>`, but that endpoint
     (`EmployeeListCreateView`) is gated to `IsAdminOrSecondaryAdmin` — a Farm
     Manager or Farmer performing the assignment (both allowed to, per
     `HouseTaskAssignView`'s own `CanEditHouseProtocol`) got a silent 403 and an
     empty dropdown, and `.exclude(pk=self.request.user.pk)` (correct for that
     endpoint's own "manage everyone but yourself" purpose) meant an Admin could
     never assign a task to themselves. Fixed with a new, purpose-built `GET
     /api/tasks/assignable-users/` (`AssignableUsersView`, gated to
     `CanEditHouseProtocol` — the same role set that can actually perform an
     assignment), returning every farm user with no role or self filter — not by
     loosening `/api/employees/` itself, which stays Admin/Secondary-Admin-only for
     its own (unrelated) account-management purpose. Who can *perform* an
     assignment is unchanged (`CAN_ASSIGN_ROLES` in `TasksNowPanel.jsx`, still
     Admin/Farm Manager/Farmer).

164. **Feature 5 — "never resolved by default" required no fix** — audited both
     `UnusualCase.resolved` (`default=False`) and `EquipmentFault.status`
     (`default='REPORTED'`, not `'RESOLVED'`): both already correct. Added
     `test_new_case_is_never_resolved_by_default` to `apps.maintenance.tests` to
     assert it going forward rather than leaving it as an unverified assumption.

165. **`UnusualCaseResolveView` narrowed from Admin/Farm Manager/Farmer to
     Admin/Farm Manager only; `EquipmentFaultResolveView` deliberately left at
     Technician/Admin — the two resolve permissions differ on purpose, and did
     even before this task** (see item 150, this file). The task's wording ("Only
     Administrateur and Gérant de ferme... consistent with who else has
     validation-style authority") most directly describes narrowing `UnusualCase`'s
     existing `IsAdminOrFarmManagerOrFarmer` by dropping Farmer — which also
     structurally satisfies "never triggerable by the reporter themselves" for the
     Farmer/Worker roles a case is normally filed by, with no extra same-user check
     needed. Extending that same narrowing to `EquipmentFault` would remove
     Technician's ability to resolve faults — but the cahier des charges section 8
     permission matrix explicitly assigns "Valider une tâche de maintenance" to
     Technician (see `EquipmentFault`'s own docstring, unchanged from the earlier
     task), and the task's Verification section only exercises one generic "test
     incident," not specifically an equipment fault. Judgment call, disclosed here
     rather than silently picking one reading: `EquipmentFaultResolveView` keeps
     `IsAdminOrTechnician`.

166. **`resolved_by` (new FK, both models) + a "Historique" tab added directly
     inside `IncidentsPanel.jsx`, not a separate route** — neither model recorded
     *who* resolved a case before this task (`UnusualCase.resolved_at` existed,
     but no user reference; `EquipmentFault.repaired_date` same story) — added
     `resolved_by` (`SET_NULL`, migration confirmed against zero existing resolved
     rows) to both, set only by the two resolve views, exposed as `resolvedByName`.
     The history view reuses the *same* `IncidentsPanel` component with a tab
     toggle (`resolved=true`/`status=RESOLVED` instead of `false`/`OPEN`) rather
     than a new `/dashboard/incidents/history` route — the task offered both as
     options, and reusing the component keeps the existing global/per-house reuse
     (item 151, this file) intact for free instead of duplicating it. Resolved
     cards are read-only (no Résolu button) and show "Résolu par {name} — {when}"
     in place of it. `EquipmentFaultListCreateView`'s `?status=` filter was
     generalized (previously only special-cased `OPEN`) so `?status=RESOLVED`
     works the same way `?resolved=true` already did for `UnusualCase`.

### Calendar time-slot display (items 167–168)

167. **Root cause was both stated candidates, confirmed by re-reading the actual
     code, not assumed** — `apps.houses.services.compute_month_schedule` neither
     fetched `ProtocolTimeSlot` (no `prefetch_related`, no time fields in the
     entry dict) nor expanded one entry per slot; `CalendarPage.jsx`'s day-
     expansion card template had no markup for a time at all. Fixed both: the
     backend now emits one entry per slot (each with `startTime`/`endTime`
     formatted `"%Hh%M"`, matching `apps.alerts.templates.render_task_reminder`'s
     own format) when a line has any, and a single entry with both `null` when it
     doesn't (no change for time-agnostic tasks); the frontend card now shows
     "07h00–09h00 — Catégorie — quoi" when present. **Correction to this task's
     own premise**: it stated this was "already specified... same treatment [as
     the tasks-now panel]" — checked (grepped `apps/houses/services.py`,
     `apps/houses/views/tasks.py`, `TasksNowPanel.jsx` for any existing time
     formatting), and the tasks-now panel does not display slot times anywhere;
     that panel was never actually updated to do so. Not fixed here — outside
     this task's stated deliverable (calendar only) — disclosed instead of
     silently expanding scope or silently trusting the false premise.

168. **Month-grid pills also got a time prefix — a small addition beyond the
     stated deliverable, added after live-verifying the fix exposed a real,
     visible issue** — splitting one calendar entry into one-per-slot means a
     day with a 2-window feeding task now produces two `salle_1 · alimenationriche`
     pills in the compact month-grid view with nothing to tell them apart
     (confirmed via a live screenshot against the user's own real configured
     data, not hypothesized). The task's deliverables only mentioned the day-
     expansion card, but leaving two identical-looking pills was a direct,
     visible side effect of this exact fix, not a pre-existing issue — addressed
     it (`"{startTime} · {houseName} · {what}"` when a slot has a time) rather
     than leave a self-introduced rough edge for a future "reported fixed, still
     broken" report. Re-verified live after the change: pills now read
     "07h10 · salle_1 · alimenationriche" / "18h30 · salle_1 · alimenationriche" —
     distinct.

### Calendar deeper diagnosis: Sunday clipped by a CSS grid overflow bug (item 169)

169. **Bug 1 re-diagnosed: it does not reproduce with current code — inspected
     the raw API response (`curl .../api/protocols/schedule/?month=2026-08`)
     before touching any React component and confirmed `startTime`/`endTime`
     ("07h10"/"07h49" etc.) are genuinely present on the wire, then confirmed
     the day-expansion modal renders them correctly, live, in a fresh browser
     session (screenshot evidence, not code reasoning). Both checks passed on
     the first try — no frontend/backend bug found in the time-slot path
     itself this round.** Found a real, different bug instead while looking:
     `.calendar-grid` (`grid-template-columns:repeat(7,1fr); overflow:hidden`)
     — a bare `1fr` track defaults to `minmax(auto,1fr)`, i.e. its minimum
     width is content-based, not zero. `.calendar-day` (a grid item that's
     also a flex column container for its own pills) had no `min-width:0`
     override, so a day cell with a long `white-space:nowrap` pill — which is
     exactly what a time-slotted task produces, e.g. "18h30 · salle_1 ·
     alimenationriche" — could force its whole grid column wider than its fair
     1/7 share. With `overflow:hidden` on the grid (not a scrollbar), the
     excess silently clipped the *rightmost* column — Sunday — off screen
     entirely, confirmed live via screenshot (only Lun-Sam visible, Dim
     missing) both before and, working correctly, after adding `min-width:0`
     to `.calendar-day`/`.calendar-weekday`. **Working theory connecting the
     two bug reports, disclosed as a theory, not asserted as fact**: a
     time-slotted task is the specific trigger that widens a column, so if the
     user's own test happened to land on a day in a squeezed/clipped column
     (Sunday, or worse on a narrower real-world screen than the 1400px window
     used here), the entire day — data, rendering, everything — would be
     invisible, which looks identical to "time slots aren't showing" without
     being a data or rendering-logic bug at all. Re-verified after the CSS fix
     by clicking directly into the previously-invisible Sunday (Aug 30, 2026)
     and confirming both time-slotted entries render correctly there too.

### Rename, alert pulse, and phrasing audit (items 170–174)

170. **"+ Nouveau bâtiment" → "+ Nouvelle bande" resolved a real, pre-existing
     terminology inconsistency, not just a label preference** — checked before
     renaming: `HomeDashboard.jsx`'s `QUICK_ACTIONS` already had its own
     "Nouvelle bande" entry (`path: "new-batch"`), and `DashboardHomePage.jsx`
     routes that same path to `/onboarding/protocol` — the *exact* route the
     sidebar button already linked to under its old label. Two different labels
     for the identical action. Renaming the sidebar button makes both agree;
     no route/logic touched (confirmed: only the button's own JSX text and one
     JSDoc line changed).

171. **Part B's third target ("the sidebar's 'Cas signalés' count badge") did
     not exist — built it, didn't skip it** — checked (grepped
     `DashboardLayout.jsx`/`DashboardShell.jsx` for any cas-signalés badge
     count): none. `IncidentShortcut.jsx`'s "Signaler un cas" is a *report a
     new case* action, not a count indicator. Since this was one of three
     explicit deliverable targets, added `openCasesCount` to
     `useSidebarNotifications.js` (sums the same two farm-wide, unresolved-only
     queries `IncidentsPanel.jsx` already makes — `?resolved=false` /
     `?status=OPEN` — no new backend endpoint, staying within this task's
     frontend-only framing) and rendered it as a badge on "Signaler un cas",
     matching the existing Stock/Finance sidebar badge pattern exactly.

172. **Pulse, not strobe — the accessibility distinction the task called out is
     real and was followed, not just acknowledged.** Rapid flashing above ~3Hz
     is a documented seizure trigger for photosensitive users (photosensitive
     epilepsy) — this is a WCAG 2.3.1 "three flashes" concern, not a style
     preference to skip for a "cooler" effect. Implemented one shared
     `.pulse-alert` CSS class (`dashboard-theme.css`): a smooth opacity
     (100%→60%→100%) + glow `box-shadow` cycle at **1.3s per cycle (~0.77Hz)**,
     nowhere near the hazard threshold, applied only to the small badge/icon
     itself (bell badge, "Cas signalés" count badge + header icon, sidebar case
     badge) — never a large area or the whole screen. `prefers-reduced-motion:
     reduce` swaps the animation for a **static** highlighted ring
     (`box-shadow`, no animation at all) via a dedicated media-query override —
     verified via `getComputedStyle` in a real headless-Chrome session with
     `--force-prefers-reduced-motion`: `animationName` came back `"none"` with
     the animation disabled, versus `"pulse-alert"` with a live 1.3s/infinite
     cycle normally. Every pulsing element only renders/pulses while its count
     is actually > 0 — resolving the underlying alert/case removes the element
     entirely (existing conditional-render logic, unchanged), so there is no
     separate "stop pulsing" code path to get wrong.

173. **Phrasing audit — swept every screen listed in the task (landing, login,
     create-farm, onboarding steps 1–3, dashboard home + every sub-screen,
     sidebar, settings); confirmed no `bande`/`lot` inconsistency exists
     anywhere** (grepped for `lot`/`lots` as whole words — zero matches, this
     codebase was already consistent). Found and fixed 4 genuine issues (full
     before/after list in the PR description; the two most notable):
     `StockParametersForm.jsx`'s and `OnboardingContext.jsx`'s default
     warehouse-name state were both the literal English string `"Main store"`
     — pre-filled the "Nom de l'entrepôt" field (and its own header) with
     English text on first load, the same class of leftover-placeholder issue
     as the earlier "POULET À VOIE" fix, just not screen-visible until a user
     actually reached that step; changed to "Entrepôt principal". Also found a
     factual bug, not just awkward phrasing: `HomeDashboard.jsx`'s zero-houses
     empty state read "**1** bâtiment configuré — démarrez une bande pour le
     voir ici" while rendering exactly when there are **zero** houses — fixed
     to "Aucun bâtiment configuré," matching the sidebar's own existing,
     already-correct copy for the identical state.

174. **The existing error-message discipline (specific messages, not one
     generic fallback) was checked project-wide, not assumed to hold beyond
     `/create-farm`** — read `api/errors.js`'s `getServerErrorMessage`
     (network-unreachable case → `detail` → first field error → caller-
     supplied fallback, in that order) and every catch block that calls it or
     builds its own message across the swept screens. Every one already
     supplies its own specific, context-appropriate fallback string (e.g.
     "Impossible d'enregistrer la pesée.", "Mot de passe incorrect.") rather
     than relying on the generic last-resort default — the discipline holds
     consistently, not just on the one screen the earlier fix touched.

### "+ Nouvelle bande" wizard-shell leakage, deeper diagnosis + multi-batch onboarding (items 175–177)

175. **Root cause, confirmed live before writing any fix (not re-diagnosed from
     reading the code): `OnboardingLayout.jsx` — the shell every `/onboarding/*`
     route renders inside — had zero awareness of `isAddingHouse`.** That flag
     already existed, but only inside `OnboardingProtocolPage.jsx` (decides
     where to navigate *after* saving); the shell wrapping it always rendered
     the full 3-step progress bar ("1. Bâtiments / 2. Stock / 3. Employés",
     steps this flow never visits) and "Retour à l'accueil" pointing at `/`,
     the marketing landing page, for a user who is already logged in and
     already on their dashboard. Captured the actual broken rendered output
     first, headless-browser, before touching anything (`progress steps
     shown: ['1. Bâtiments', '2. Stock', '3. Employés']`, `back link: ("Retour
     à l'accueil", ".../")`) — then fixed `OnboardingLayout.jsx` to read
     `user.is_configured` (the same condition `OnboardingProtocolPage` already
     keys off) and, when true, render neither the step list nor the old back
     link — just "Retour au tableau de bord" → `/dashboard`. Re-verified live
     after the fix: `progress steps shown: []`, back link now `("Retour au
     tableau de bord", ".../dashboard")`.

176. **The save button's own label was a second, related instance of the same
     class of bug ("label describes behavior that no longer applies")** — in
     add-house mode this button was still captioned "Suivant" ("Next") despite
     going straight back to the dashboard, no wizard step following it.
     `HouseProtocolForm` gained an optional `submitLabel` prop (falls back to
     the existing "Suivant"/"Enregistrer le protocole" logic when omitted —
     every other call site unaffected, confirmed by the full existing test
     suite still passing unchanged); `OnboardingProtocolPage` passes
     `submitLabel="Créer la bande"` only when `isAddingHouse`. Verified live:
     button now reads "Créer la bande".

177. **Multi-batch creation during true first-time onboarding — new capability,
     scoped to reuse the existing single-house submission endpoint rather than
     changing its contract.** `POST /api/protocols/onboarding/` already
     creates exactly one house(+batch) per call — that's how the add-house
     shortcut has always worked — so "add several houses during signup" is
     implemented as calling it multiple times before moving to the Stock step,
     not a new bulk endpoint. `HouseProtocolForm` gained an optional
     `onAddAnother` prop (onboarding mode only): when provided, a second
     button "Ajouter ce bâtiment et en configurer un autre" submits the
     current house via the same payload `onSave` gets, without advancing.
     `OnboardingProtocolPage` (only when `!isAddingHouse`) tracks the houses
     added this way, shows them as a running list with a "Continuer sans
     ajouter d'autre bâtiment" escape hatch (jumps straight to `/onboarding/
     stock` without requiring one more, possibly-unwanted house), and remounts
     `HouseProtocolForm` (a bumped `key`) after each addition so its internal
     category/schedule state actually resets to the same blank-with-5-defaults
     state the page starts with — changing its `initial*` props alone
     wouldn't, since those only seed a `useState` once. The add-house
     shortcut (`isAddingHouse`) deliberately does **not** get this button —
     it stays a single-house action, matching its own singular name. **Not
     verified against the live dev stack**: this project is single-farm
     (`Farm.singleton_lock`), so a genuinely `is_configured:false` user only
     exists before that one farm's real signup — the farm currently running
     already carries real manually-entered test data (incident reports, etc.)
     a factory reset would destroy purely to manufacture that state. Verified
     instead with `OnboardingProtocolPage.test.jsx`, exercising the real
     component tree (real `HouseProtocolForm`, a real "Charger le modèle de
     départ" click to populate a real row) with only the network/router/
     context boundaries mocked, matching this project's existing
     `HouseProtocolForm.test.jsx` "real button, real interaction" convention.

### Purchase orders: creation, receiving, and its link to stock (items 178–184)

178. **More backend already existed than the task assumed — checked, not
     assumed, before building anything.** `PurchaseOrder`/`PurchaseOrderSerializer`/
     `PurchaseOrderListCreateView`/`PurchaseOrderDetailView` were all already
     implemented (an earlier task, per their own docstrings), including the
     RECEIVED→StockMovement side effect. No frontend existed at all (grepped
     the whole frontend for `PurchaseOrder`/`purchase-order` — only a stray
     audit-log label). Rather than rebuild the backend from the task's spec,
     audited what was there against every one of this task's explicit
     requirements and fixed the real gaps found (items 179–182), then built
     the missing frontend on top of the corrected API.

179. **Role gap: creation/receiving were Admin/Cashier-only, missing Farm
     Manager** — this task's own role list is Caissier/Administrateur/Gérant
     de ferme; the existing `IsAdminOrCashier` was missing the third. Added a
     new `IsAdminOrFarmManagerOrCashier` permission rather than widening
     `IsAdminOrCashier` in place, since that one is also used by
     `SaleListCreateView` — explicitly out of this task's scope ("don't touch
     ... sales").

180. **Real bug: the StockMovement's `movement_date` was set to the order's
     `order_date`, not the actual receiving date** — this task explicitly
     calls out that the two can differ ("the actual receiving date, which may
     differ from orderDate"); the pre-existing code silently backdated every
     receipt to when the order was placed. Fixed to `timezone.now().date()`.
     Verified live: backdated `order_date` to 2020-01-01, received the order
     today, confirmed the generated movement's date was today, not 2020.

181. **Finality wasn't enforced at all** — a RECEIVED order could be PATCHed
     to CANCELLED (or back to RECEIVED again, generating a *second*
     StockMovement for the same order) with nothing stopping it. Added a
     `validate()` check rejecting any status change once an order is no
     longer PENDING — this task's own Part B item 5 ("no un-receiving, no
     un-cancelling... visible in the audit log," not silently reversible).
     The RECEIVED-transition side effect is also now wrapped in
     `transaction.atomic()` (this task's own rule), which the pre-existing
     code wasn't.

182. **`order_date` genuinely cannot be "editable," and this task's own rules
     say why not — disclosed, not silently ignored.** Part A asks for an
     editable "Date de commande" field defaulting to today; the model has
     `order_date = models.DateField(auto_now_add=True)` — Django enforces
     `auto_now_add` at the model level regardless of what a serializer
     accepts, so no server-side change (short of the schema change this
     task's own rules forbid) could make it editable. Resolution: the
     creation form shows "Date de commande" as a disabled field pre-filled
     with today, honest about what it actually is rather than fake-editable.

183. **`supplierBatchNumber` at receiving time: added, low-friction** — a
     single optional text input in the receive-confirmation dialog, wired as
     a `write_only`, non-model serializer field (`supplierBatchNumber`,
     popped out before it ever reaches `ModelSerializer`'s own create/update)
     that only takes effect on the RECEIVED-transition StockMovement it's
     tied to. Verified live: entered "LOT-SEL-001" at receiving, confirmed
     the created `StockMovement.supplier_batch_number` held that exact value.

184. **Screen location: standalone `/dashboard/purchase-orders` route, not a
     Stock tab** — `StockParametersForm.jsx` (the existing `/dashboard/stock`
     content) is already a complex, self-contained item-configuration editor
     with its own internal category tabs; nesting an unrelated
     order-tracking list/form *inside* it would conflate "define what items
     exist and their thresholds" with "track supplier orders against those
     items," and would mean restructuring an already-large component for a
     feature that doesn't touch its own concerns. A standalone route matches
     how every other transactional/list-heavy feature in this app already
     gets its own route (Calendar, Employees, Audit Log, Cashier) rather than
     living as a tab bolted onto an unrelated page. Sidebar link gated to the
     same Admin/Farm Manager/Cashier role set that can act on orders — the
     list itself stays open to any authenticated user server-side (unchanged
     `IsAuthenticated` on GET), so a direct link still works for a role that
     can view but not manage.

     **Item picker: no existing pattern to reuse — checked, not assumed**
     (task said "reuse the pattern already used elsewhere"; grepped the whole
     frontend for any StockItem-select UI — `StockParametersForm.jsx` edits
     item rows directly, `SidebarSearch.jsx` is a farm-wide fuzzy search, and
     neither is "pick one existing item for a form field"). Built a small,
     self-contained combobox over the farm's already-loaded item catalog (no
     server-side search needed — a farm's own stock list is small), reusing
     `SidebarSearch`'s dropdown-*panel* look but not its dark-sidebar-styled
     input, which would read wrong on this page's light cards.

     Verified the full loop live, end to end, not just per-piece: created an
     order as Admin (item picker → real farm item, supplier/quantity/amount)
     → appeared PENDING in the list; received it with a supplier batch number
     → status flipped to RECEIVED, `StockMovement` confirmed via shell (IN,
     correct item/quantity/supplier/batch-number, `batch_id` None,
     `movement_date` today) and `current_quantity` confirmed to reflect the
     +50 increase; created a second order and cancelled it → CANCELLED, zero
     new `StockMovement` rows; logged in as a Farmer → sidebar link absent,
     direct-URL visit shows the list but no create/manage controls (403 on
     the actual write endpoints separately confirmed by
     `PurchaseOrderTests.test_other_roles_forbidden_from_creating`). Test
     data (2 orders, 1 movement, 1 temporary Farmer account) removed after
     verification — not left in the farm's real data.

185. **Finances restructured into a single page; "Salaires" payroll module
     added.** "Finance" became "Finances" everywhere, and the sidebar link
     turned into an accordion (`DashboardLayout.jsx`) revealing four
     sub-items — Ventes / Achats / Salaires / Globale — that all live on one
     route, `/dashboard/finances`. Clicking a sub-item navigates to
     `/dashboard/finances#<section>` and `FinancesPage.jsx` turns that hash
     into a smooth `scrollIntoView`, not a route change (react-router treats
     a hash-only URL as the same route, so `location.pathname` never
     changes) — this satisfies the requirement literally ("the URL must not
     change route when switching sections") with a standard, bookmarkable
     mechanism rather than inventing a custom tab system. The old
     `FinancePage.jsx` (the existing revenue/expense-trend dashboard) moved
     into this page's "Globale" section verbatim, unchanged in behavior —
     it's just repositioned, per the task's own instruction.

     **Premise correction, checked not assumed:** the task's Part D asked to
     make `Expense.batch` nullable "so a null-batch expense isn't included in
     any batch's unit cost." Read the model first — it already was
     (`null=True, blank=True`, with a docstring already covering the exact
     farm-wide-expense semantics the task wanted). No migration made for
     this; noted here instead of silently proceeding as if a change had
     happened.

186. **Ventes / Achats sections: bucketed evolution endpoints, not a repeat
     of the existing monthly-summary logic.** Added
     `GET /api/finance/sales-evolution/` and
     `GET /api/finance/purchases-evolution/` (`apps.finance.calculations`),
     each accepting `?period=week|month|year` and returning a bucketed
     series (8 weeks / 12 months / 5 years, always ending at the current
     bucket) plus period totals and a category/product-type breakdown. Same
     full-vs-restricted access split as the existing `FinanceSummaryView`
     (Admin/Farm Manager get exact figures; every other role gets a
     direction-only trend badge, enforced server-side — the two new
     `SalesEvolutionView`/`PurchasesEvolutionView` both 403 the underlying
     data query for a restricted role, they just compute a `series_trend()`
     instead). Achats is explicitly **read-only aggregation**, per the task's
     own Part C — it reads RECEIVED `PurchaseOrder` rows and `Expense` rows,
     with no new data-entry surface of its own.

     **Judgment call, disclosed:** `PurchaseOrder.item.category` uses Stock's
     `ItemCategory` (FEED/VETERINARY/EQUIPMENT/BEDDING) — a different enum
     from `Expense.category`'s `ExpenseCategory` (FEED/VETERINARY/MISC/
     DEPRECIATION/LABOR). The task's own Achats breakdown list
     ("Aliment/Vétérinaire/Divers/Amortissement… Main-d'œuvre") matches
     `ExpenseCategory`'s labels, so a received purchase order's item category
     is folded onto that same axis for one unified breakdown: FEED/
     VETERINARY map 1:1 (identical concept); EQUIPMENT → DEPRECIATION
     (capital equipment purchases are exactly what this codebase's existing
     `roi_forecast_pct` already treats as "investment" — the closest
     precedent for classifying them); BEDDING → MISC (no direct
     `ExpenseCategory` equivalent). See `_ITEM_CATEGORY_TO_EXPENSE_CATEGORY`
     in `apps/finance/calculations.py`.

187. **Cashier gap closed: "Enregistrer une dépense."** The task pointed out
     there was no way to record a general (non-purchase-order) expense from
     the Caisse module — `/dashboard/cashier` could only record sales.
     Added a second small form to that same page (category — Aliment/
     Vétérinaire/Amortissement/Divers, deliberately excluding Main-d'œuvre,
     which is system-generated only from a paid `SalaryPayment` — /amount/
     supplier/date) that posts to the already-existing `POST /api/expenses/`
     (its permission was widened from Admin/Farm-Manager-only to also allow
     Cashier — `ExpenseListCreateView.get_permissions()` — the same role set
     already allowed to record a sale on that screen). This is an addition
     beyond the pre-existing Cashier screen, flagged explicitly per the
     task's own "note it in the README" instruction, not silently folded in.

188. **Salaires (payroll) module — schema, calculation, and the on-demand
     decision.** New `User.hourly_rate` (nullable — not every role is paid
     hourly, e.g. Admin/Farm Manager; a user with no rate set is skipped by
     the monthly calculation, not treated as a 0-rate employee), new
     `WorkHoursEntry` (user, date, hours_worked, optional note), and new
     `SalaryPayment` (user, period_month/period_year, total_hours and
     hourly_rate_snapshot — both snapshotted at calculation time so a later
     rate change never retroactively alters a past payment — amount, status
     PENDING/PAID, paid_date). `apps.finance.services.calculate_salaries`
     sums a month's `WorkHoursEntry` rows per employee and
     `update_or_create`s a PENDING `SalaryPayment`, but **never touches an
     already-PAID payment for that period** even if more hours get logged
     afterward — same finality precedent this codebase already established
     for `PurchaseOrder` (RECEIVED/CANCELLED, no further transition).

     **On-demand, not scheduled — and why:** the task left this as an open
     choice ("either... or... user's call, note the decision"). This
     codebase has no Celery Beat schedule configured anywhere (a pre-existing
     gap, already noted elsewhere in this log) — adding the first-ever
     scheduled task for one feature would be a much larger, riskier change
     than the feature itself, for a monthly action a human is going to
     review and act on anyway ("Marquer comme payé" is a manual, deliberate
     step regardless of how the PENDING row was produced). "Calculer les
     salaires du mois" is a plain button (`SalairesSection.jsx`, Admin/Farm
     Manager only), calling `POST /api/salary-payments/calculate/`.

     **Hours-logging ownership model:** self-report is the default —
     `MyHoursShortcut.jsx`, a small sidebar entry point ("Mes heures") open
     to every role, always posts with no `user` field, so the backend
     defaults it to the requester (`WorkHoursEntrySerializer.validate`).
     Admin and Farm Manager can additionally log or correct hours **on
     behalf of any employee** — a second form in `SalairesSection.jsx`
     ("Enregistrer des heures pour un employé") that posts the same endpoint
     with an explicit `user`. Listing follows the same split: a regular
     employee's `GET /api/work-hours/` only ever returns their own entries;
     Admin/Farm Manager see everyone's, needed to review before calculating.

     **"Marquer comme payé":** Admin/Farm Manager only, sets status=PAID,
     paid_date=today, and — inside the same `transaction.atomic()` block —
     creates the matching `Expense` (category=LABOR, batch=null,
     amount=payment.amount, expense_date=paid_date, supplier=employee's
     name — a disclosed judgment call for the one free-text field on an
     otherwise fully system-generated expense row) which is what feeds
     "Main-d'œuvre" into Achats/Globale. Once PAID, a second call is
     rejected (400), matching `PurchaseOrder`'s own finality pattern.

     **Section fully hidden, not just a restricted view, and this needed
     fixing twice:** unlike Ventes/Achats/Globale, Salaires has no
     restricted summary for other roles — it's meant to not exist for them
     at all. The four salary/payroll endpoints
     (`SalaryPaymentListView`/`SalaryCalculateView`/`SalaryPaymentPayView`/
     `EmployeePayrollListView`) are all `IsAdminOrFarmManager` server-side,
     which was right from the start. But live verification (see below)
     caught that the *sidebar* "Salaires" sub-item was still rendering for
     every role — `DashboardLayout.jsx`'s `FINANCES_SECTIONS` list was
     static, unfiltered by role, so a Cashier account saw a "Salaires" link
     in the menu that scrolled to nothing. Fixed by adding a `canSeeSalaires`
     prop (computed in `DashboardShell.jsx` the same way every other
     `canSee*` prop already is, default `false` like `canSeeAudit`) and
     filtering that one sub-item out when it's false — confirmed live with a
     throwaway Cashier account (menu now shows only Ventes/Achats/Globale)
     and a throwaway Farm Manager account (sees all four, and confirmed
     separately that Farm Manager still has no `/dashboard/employees` access
     — see below).

     **Farm Manager rate-editing, resolved:** the task says rates are set
     "from /dashboard/employees" — true for Admin, who already has that
     page. Farm Manager does not (`canSeeEmployees` stays Admin/Secondary-
     Admin only, unchanged elsewhere in this codebase — checked, not
     assumed, and confirmed live: a Farm Manager account has no "Employés"
     sidebar link). Rather than widen that page's access (which would also
     expose role/password/email editing Farm Manager isn't meant to touch,
     since the general employee endpoints stay `IsAdminOrSecondaryAdmin`),
     rate editing is additionally surfaced inside `SalairesSection.jsx`
     itself — the one place both allowed roles already land — backed by a
     new narrow read endpoint, `GET /api/employees/payroll/`
     (`EmployeePayrollListView`/`EmployeePayrollSerializer`,
     `IsAdminOrFarmManager`, id/name/hourly_rate only, no
     email/phone/role/is_active), and the existing
     `PATCH /api/employees/{id}/hourly-rate/`. Admin also gets the same
     field inline in `EmployeesPage.jsx`'s existing employee rows (not the
     create/update form itself — `hourly_rate` is read-only on
     `EmployeeSerializer` by design, so it can't be silently ignored by a
     PUT there).

189. **Cross-section staleness found during live verification, and fixed.**
     All four Finances sections mount together on one page and each fetches
     its own data once; a hash-only navigation between them (Part A's whole
     point) never remounts anything. Verified live: recorded a sale and an
     expense via Cashier, confirmed both in Ventes/Achats; set an hourly
     rate, logged hours, calculated, and marked a salary paid — the created
     LABOR `Expense` was correctly present in `GET
     /api/finance/purchases-evolution/`'s breakdown (confirmed directly via
     the API), but the already-mounted Achats section on the page kept
     showing its stale pre-payment total, because "Marquer comme payé"
     happens inside the same page as Achats/Globale, unlike a sale or a
     purchase-order receipt (both on separate routes, which naturally
     remount Finances on return). Fixed with a small `financesVersion`
     counter lifted to `FinancesPage.jsx`, bumped by `SalairesSection` after
     a successful "Marquer comme payé," and passed down as a `refreshKey`
     fetch-effect dependency to `AchatsSection`/`GlobaleSection` — the only
     two sections whose totals a payroll action can affect. Re-verified live
     with a fresh employee, clicking between sections via the sidebar (no
     page reload): Achats' total updated correctly in place. All test data
     (temporary employee, hours entries, salary payment, LABOR expense, the
     Cashier test sale/expense, and two throwaway role-check accounts)
     removed after verification.

## Part 20 — Stock restructure: dashboard view, custom categories, supplier directory, protocol-driven daily consumption (2026-08-28)

Task: mirror the batch-view pattern on `/dashboard/stock` (modal config + charts +
suppliers), add custom `StockCategory` entities, a `Supplier` directory, and an
automatic daily stock deduction driven by the protocol. Autonomous mode — decisions
below were made without asking and are also summarised in `README.md`.

190. **Celery Beat: a static `beat_schedule`, not `django-celery-beat`.** The project
     had *no* Beat schedule anywhere (`config/celery.py` had no `beat_schedule`); every
     `SCHEDULED` `AlertRule` type has always been created-but-never-fired for that
     reason (Parts 5/6, items 47/57; `AlertRule` docstring). This task's Part E needs a
     real once-daily job, so `config/celery.py` now defines
     `app.conf.beat_schedule = {'daily-stock-consumption': {..., 'schedule':
     crontab(hour=0, minute=0)}}` — a static schedule, no new dependency, consistent
     with the existing `CELERY_*` settings style. Run with `celery -A config beat`.
     **Only** this one task is wired; the pre-existing unfired `PROTOCOL_TASK` /
     `WEIGHING_REMINDER` rules stay out of scope (not this task's problem). A
     `python manage.py run_stock_consumption [--date YYYY-MM-DD]` command runs the same
     service function synchronously for testing / manual catch-up.

191. **`StockItem.category` became an FK to a new `StockCategory` table; the old
     `ItemCategory` enum was kept as a `kind` discriminator on that table, not
     deleted.** `StockCategory` mirrors `ProtocolCategory` (`farm` FK, `label`, `icon`,
     `sort_order`) plus `kind` (`FEED|VETERINARY|EQUIPMENT|BEDDING|CUSTOM`). Rationale:
     `StockItem.feed_stage` / `cold_chain_required` semantics, and the finance
     `PurchaseOrder` breakdown mapping (`_ITEM_CATEGORY_TO_EXPENSE_CATEGORY`), are tied
     to the four original categories and must survive a user renaming "Aliment" to
     something else. The four defaults are seeded per `Farm` via a `post_save` signal
     (`apps/stock/signals.py`, mirroring `apps/houses/signals.py`) and by a data
     migration (`0002_stockcategory`) for the existing farm; the migration also remaps
     every existing `StockItem.category` string to the matching new row. The form shows
     the feed-stage dropdown only for `kind==FEED` rows and the cold-chain toggle only
     for `kind==VETERINARY`; custom categories show neither. This `kind` field is the
     one deliberate divergence from a pure `ProtocolCategory` copy.

192. **Deleting a `StockCategory` cascades to its `StockItem` rows
     (`on_delete=CASCADE`).** Matches how deleting a `ProtocolCategory` cascades to its
     `ProtocolTemplate` rows; the frontend confirm dialog states it (item count shown)
     before calling `DELETE /api/stock-categories/{id}/`. The four seeded defaults are
     deletable too, for parity with the protocol tabs.

193. **`Supplier` is a new table, kept separate from the free-text
     `PurchaseOrder.supplier` / `StockMovement.supplier` fields, which are unchanged.**
     Per the task's own Part D.4. `StockItem.supplier` (FK, `SET_NULL`, nullable) is an
     item's default/primary supplier, chosen from a dropdown in the parameter form with
     an inline "+ Nouveau fournisseur". `SupplierSerializer.item_names` derives the
     supplied-items list from `StockItem.supplier` (no stored back-reference). A future
     task could migrate `PurchaseOrder.supplier` / `StockMovement.supplier` to reference
     `Supplier` — explicitly deferred here.

194. **`StockMovement.protocol_line` (FK, `SET_NULL`, nullable) was added** so the daily
     task is idempotent at exactly the spec's granularity — "one movement per batch per
     protocol row per calendar date" — via
     `filter(item, batch, protocol_line, movement_date, movement_type=OUT).exists()`,
     and so machine-generated movements are distinguishable from manual entries. It is
     null for every manually-entered movement.

195. **`run_daily_consumption` reuses `apps.houses.services._protocol_line_occurrence`**
     for the "does this row's day range cover today" check — the same helper
     `compute_tasks_now` / `compute_month_schedule` use, so "consumed today" always
     agrees with "shown as due today". `day_of_cycle = (today - batch.start_date).days`,
     matching the existing convention. LOW_STOCK needs **no new wiring**: the task
     creates ordinary `StockMovement` rows, and the existing `on_stock_movement_saved`
     signal runs `check_low_stock` for each — verified by a test
     (`DailyConsumptionTests.test_triggers_low_stock_alert_when_threshold_crossed`).

196. **Insufficient-stock warning is a planning heuristic, non-blocking.**
     `GET /api/stock-items/{itemCode}/coverage/?quantity_per_day=<n>&days=<span>` returns
     `{currentQuantity, dailyRate, daysRemaining, daysNeeded, sufficient}`. `dailyRate`
     = the row being edited plus the sum of `quantity_per_day` of every *other*
     `ProtocolTemplate` row across the farm linked to the same item (a forward-looking
     "at this rate" figure — it does not check whether each of those rows' ranges
     currently overlap). The form shows the warning when `sufficient` is false and never
     blocks the save, per Part E.3.

197. **`/dashboard/stock` no longer renders `StockParametersForm` directly.** It is a
     dashboard (`StockEvolutionChart` + `SuppliersSection`); the form opens in
     `StockParametersModal`, which reuses `ProtocolEditModal`'s `.protocol-modal-*`
     chrome (backdrop blur, focus trap, `Escape`, capture-phase dirty tracking) rather
     than rebuilding it. A "Réinitialiser" button was added to the form's management
     save-bar (restores `initialData`) so the modal offers Save / Cancel / Réinitialiser
     as the brief asks — the reused modal pattern itself has no such button. Charts use
     calendar dates (running `StockMovement` balance), not day-of-cycle: stock is
     farm-scoped, not batch-scoped. Onboarding step 2 keeps using the same form (the
     farm and its four seeded categories already exist by then), so custom categories
     and suppliers work there too. Verified by `vitest` (build + 17 tests) and the full
     `pytest` suite (117 passing); the browser extension was not connected this session,
     so the modal's visual blur/scale was verified by code review against the existing
     `ProtocolEditModal` it copies.

## Part 21 — Login screen: "Créer une ferme" wording + pre-login farm reset flow (2026-08-30)

Task: (A) rename every user-facing "Créer la ferme" / "Créez la ferme" link/button label
to "Créer une ferme"; (B) remove `/login`'s stale "Créez la ferme" link and replace it
with a quiet, credential-gated "Réinitialiser la ferme" entry point; (C) build a
standalone reset flow that works without a session, reusing the existing
`FactoryResetModal` confirm screens. Autonomous mode — decisions below made without
asking, also summarised in `README.md`.

198. **"Créer une ferme" wording — scope of the audit.** Changed in live UI: the
     `/create-farm` page `<h1>`, its submit button, and its `useDocumentTitle`. Also changed
     where the same string is recorded as a *canonical UI label* — `README.md` quick-start,
     the French-pass string list in Part 4 above, and README's civility-field entry that
     names the form. **Not** changed: past-tense changelog/comment prose that narrates old
     behaviour (`frontend/src/api/client.js`'s 401-redirect comment, Part 12's landing-CTA
     sentence here) — editing quoted labels inside a historical record falsifies it without
     fixing any rendered text. The `/login` → `/create-farm` link isn't in either list: it
     was deleted outright (item 199).

199. **`/login`'s "Créez la ferme" link removed, not relabelled.** Farm creation is
     permanently closed once a farm exists (`FarmCreateView` → 409, `/create-farm`'s own
     `farmApi.exists()` guard redirects away), and `/login` is only meaningfully reachable
     *after* a farm exists — so the link was always wrong here. Replaced with a
     `<button class="auth-reset-link">` (muted grey, 12.5px, plain underline, hover →
     `--danger`) wrapped in `.auth-reset-hint` — deliberately not the mint/bold treatment of
     `.auth-switch a`, since this is edge-case recovery, not a primary path. Rendered only
     when `GET /api/farm/exists/` returns true (LoginPage now does that check on mount, the
     same one LandingPage/CreateFarmPage already do). No hard redirect guard was added to
     `/login` for the no-farm case — the task said none was needed if routing already only
     reaches it with a farm, and a fresh install can't authenticate anyone there anyway.

200. **Pre-login reset = `FactoryResetModal mode="pre-login"`, not a new component.** The
     task's step 2 ("same confirmation flow already built — reuse it") is honoured by
     parametrising the existing modal rather than duplicating its backdrop / focus-trap /
     explanation list / type-the-farm-name confirm. `mode="pre-login"` prepends one
     `"credentials"` step and swaps two things: the confirm step drops its password field
     (proven in step 0) and the final call is `farmApi.resetConfirm(token, name)` instead of
     `farmApi.reset(password)`. `mode="dashboard"` (default) is byte-for-byte the old
     behaviour. `user?.farm_name` is now null-safe because there is no session user in
     pre-login mode — the farm name comes from the step-1 response instead.

201. **Two new endpoints, both `AllowAny`; the existing session endpoint untouched.**
     `POST /api/farm/reset/request/` (`PreLoginResetRequestSerializer`) verifies email +
     password belong to a real `UserRole.ADMIN` on the single farm and returns
     `{token, farm_name}`. `POST /api/farm/reset/confirm/` (`PreLoginResetConfirmSerializer`)
     re-opens the token, re-checks the account is still an Administrateur, checks the
     typed-back `Farm.name`, then calls the **same `apps.core.services.factory_reset_farm`**.
     `POST /api/farm/reset/` (session + `IsAdmin` + `FarmResetSerializer`) is unchanged and
     still what `/dashboard/settings` uses.

202. **Step-up token: `django.core.signing`, 5-minute TTL, no DB, no session.**
     `signing.dumps({'uid': user.id}, salt='apps.core.prelogin-farm-reset')` — HMAC-SHA256
     over `SECRET_KEY`. Chosen over (a) issuing a real JWT (that *is* a login session — the
     opposite of the requirement, and would need blacklisting), (b) a DB `PasswordResetToken`
     row (more moving parts; the row would itself be CASCADE-wiped by the reset it authorises)
     and (c) re-sending the password to `/confirm/` (makes the confirm call as sensitive as
     the request call, for no gain). `signing.loads(..., max_age=300)` raises
     `SignatureExpired` (a `BadSignature` subclass) once stale; a token minted with any other
     salt fails the same way. `PRELOGIN_RESET_MAX_AGE` is a module constant so a test can
     `mock.patch` it to force expiry.

203. **No account enumeration for an anonymous caller.** Unknown email, wrong password, and
     valid credentials for a non-Administrateur all raise the identical
     `self.fail('invalid')` → `{"non_field_errors": ["Identifiants invalides."]}` (HTTP 400,
     never 403 — a 403 would confirm the account exists). The unknown-email branch runs a
     throwaway `User().set_password(password)` so response timing doesn't leak existence
     either (mirrors Django's own `ModelBackend.authenticate`). The frontend surfaces it via
     the shared `getServerErrorMessage` helper, which already reads `non_field_errors` and
     also covers the backend-unreachable case.

204. **"role `ADMINISTRATEUR`" → `UserRole.ADMIN`.** The task's wording; this codebase's enum
     value is `ADMIN` (DB string `'ADMIN'`, French label "Administrateur", the single
     per-farm admin created by `FarmCreateView`). `SECONDARY_ADMIN` is a different role and is
     *not* accepted by either new endpoint.

205. **Verification.** 10 new backend tests
     (`apps/core/tests.py::PreLoginFarmResetTests`, isolated test DB): token round-trip →
     full CASCADE wipe + `farm/exists/` → false; the three indistinguishable credential
     failures; tampered / foreign-salt / expired token each rejected with nothing deleted;
     wrong farm name rejected with nothing deleted; request endpoint reachable with no auth.
     Full `apps.core` suite green (32). `vite build` + `oxlint` clean. Consistent with Part
     12, the wipe was **not** triggered against the running dev stack (its DB holds the
     user's real between-session farm data and the action is irreversible) — the `/login`
     link, the credentials step, and the generic-error path were checked headless; the
     request/confirm endpoints were probed with bad input against the dev stack (400s, farm
     intact).

## Part 22 — Time-based trigger for SCHEDULED task reminders (2026-08-30)

Task: build the running process that actually fires `AlertRule` rows of
`trigger_mode = SCHEDULED` at their configured `trigger_time`. Until now these rows
(`PROTOCOL_TASK` from `expand_protocol_to_alert_rules`, `WEIGHING_REMINDER` from
`sync_weighing_reminder`) were created correctly but never evaluated — the project had
only one Beat entry (`daily-stock-consumption`, Part 20). Autonomous mode — decisions
below made without asking, also summarised in `README.md`.

206. **Every-minute Celery Beat entry `check-scheduled-alerts`** → `apps.alerts.tasks.
     check_scheduled_alerts` → `apps.alerts.services.fire_scheduled_alerts`. Added to the
     existing static `app.conf.beat_schedule` in `config/celery.py` (`crontab()` = every
     minute) — no `django-celery-beat` dependency, same style as Part 20. A
     `python manage.py check_scheduled_alerts [--at HH:MM]` command runs the same service
     synchronously for testing / manual catch-up (`--at` simulates a farm-local minute on
     today's date).

207. **New setting `FARM_TIME_ZONE` (env, default `Africa/Douala`).** `TIME_ZONE` stays
     `'UTC'` (all stored/served timestamps unchanged). `AlertRule.trigger_time` is a naive
     wall-clock value the user typed thinking in *local* farm time, so `fire_scheduled_alerts`
     converts `timezone.now()` to `FARM_TIME_ZONE` before comparing. Verified explicitly:
     with `TIME_ZONE='UTC'`, comparing `trigger_time=08:00` against UTC now would fire the
     reminder at 09:00 WAT — an hour late. Default is `Africa/Douala` (WAT, UTC+1) because
     this deployment's default currency is XAF (Central/West Africa); **override
     `FARM_TIME_ZONE` per deployment** if the farm is elsewhere. A test
     (`test_comparison_is_farm_local_not_utc`) pins that the comparison is farm-local, not
     UTC.

208. **3-minute catch-up window + per-rule idempotency.** The task matches rules whose
     `trigger_time` falls in `[now - 3min, now]` (midnight wrap handled) so a brief Beat
     outage (worker restart, redis hiccup) doesn't silently skip a reminder. Duplicates are
     prevented by `_already_fired`: an `Alert` for this `rule + batch` created in the last
     **10 minutes** (wider than the 3-min window, far narrower than any rule's daily
     cadence, no midnight-boundary edge) means the occurrence is already handled. `Alert` has
     no date/time columns and adding them was out of scope, hence the time-delta check rather
     than an exact `rule + batch + date + trigger_time` unique match. `SmsMessage` keeps its
     own `idempotency_key` guard on top (`{rule_type}:{batch}:{recipient}:{date}:{trigger_time}`).

209. **`ONE_TIME` rules are deactivated (`active = False`) once fired**, inside the same
     transaction as the `Alert`. `expand_protocol_to_alert_rules` only ever deletes
     *future-dated* unfired `PROTOCOL_TASK` rows on a protocol re-edit, so a fired
     (past-dated, inactive) row is left in place — it just never re-enters the query
     (`active=True` filter). `DAILY`/`WEEKLY`/`MONTHLY` rules stay active and fire once per
     due day (the 10-minute idempotency check enforces once-per-day).

210. **Due-today check reuses the existing helpers, no parallel schedule logic.**
     `PROTOCOL_TASK`: `apps.houses.services._protocol_line_occurrence(line, day_of_cycle)`
     must be non-`None` (today inside the originating line's day range — so a since-edited
     protocol that moved the line out of range stops firing it) **and**, for `ONE_TIME`,
     `scheduled_date == today`. `WEIGHING_REMINDER`: `apps.batches.services.
     weighing_reminder_task(batch, day_of_cycle)` non-`None` (that helper already encodes the
     `DAILY`/`WEEKLY`/`MONTHLY` cadence). All rule types additionally require
     `batch.status == ACTIVE` and, if `active_days` is set (nothing populates it today, but
     the field exists), today's 3-letter weekday token to be listed.

211. **Message + recipient reuse `apps.alerts.templates`.** `resolve_task_reminder_recipient`
     (the line's `assigned_to` else the batch's Fermier) for `PROTOCOL_TASK`;
     `rule.assigned_to or batch.farmer` for `WEIGHING_REMINDER`. Body from
     `render_task_reminder` — timed to the `ProtocolTimeSlot` whose `start_time` matches
     `trigger_time` when there is one, else the first slot, else "aujourd'hui". One `Alert`
     per fired rule, `severity='info'`, so the notification bell and the Twilio
     `send_sms_task` path behave exactly as for EVENT alerts. **Not** gated by
     `NotificationPreference` (which throttles farm-wide EVENT alerts) — a scheduled task
     reminder is a personal job assignment to the responsible user, per `templates.py`'s
     existing framing. `expand_protocol_to_alert_rules` still writes a single hardcoded
     `trigger_time='08:00'` per line rather than one rule per time slot; wiring per-slot
     trigger times into the expansion is a separate follow-up and out of scope here.

212. **Verification.** 8 new tests (`apps/alerts/tests.py::FireScheduledAlertsTests`):
     matching rule → Alert + SmsMessage to the resolved recipient with the personalised body;
     idempotent re-run within the window; `ONE_TIME` deactivation; closed batch → nothing;
     outside the line's day range → nothing; 2-minute-late catch-up fires, 5-minute-late does
     not; farm-local (not UTC) comparison; `WEIGHING_REMINDER` fires and stays active. Full
     backend suite green. Live smoke test against the running stack: a rule at the current
     farm-local minute fired one Alert + one PENDING SmsMessage, re-run produced nothing, the
     `ONE_TIME` rule went inactive.
