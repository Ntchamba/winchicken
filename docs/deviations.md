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
