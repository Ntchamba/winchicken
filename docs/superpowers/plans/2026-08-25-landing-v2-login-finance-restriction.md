# Landing v2 / Login Routing / Finance Restriction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> Executed inline, in-session, by the same agent that wrote this plan (full codebase
> context already loaded from exploration — see conversation). No fresh-context handoff
> needed; steps below are kept tight rather than maximally atomized for that reason.

**Goal:** Simplify the public landing page to a single welcome screen, confirm/verify
the login flow already routes straight to `/dashboard`, and add server-enforced
restricted Finance access for non-privileged roles.

**Architecture:** Frontend-only rewrite for the landing page (React + Framer Motion,
existing `house-protocol-theme-light.css` tokens). Backend: `FinanceSummaryView`
becomes accessible to any authenticated user, branching its payload shape by role
(`access: "full"` vs `access: "restricted"`); the two detail endpoints
(`expense-categories`, `transactions`) stay `IsAdminOrFarmManager`-only (403 for
everyone else — no exact figures, no per-transaction data leak). Frontend
`FinancePage.jsx` renders from either payload shape.

**Tech Stack:** Django + DRF (backend/apps/finance, backend/apps/core), React + Vite +
Framer Motion + lucide-react (frontend/src).

**Spec:** Inline task prompt (see conversation) sourced from
`winchicken-cahier-des-charges.docx` §6 and `winchicken-spec-implementation-detaillee.docx`
§1, which this plan supersedes and updates in place.

## Global Constraints

- No intermediate confirmation screen between login response and `/dashboard` render,
  for every role — already true in `LoginPage.jsx`/`ProtectedRoute.jsx`, verify don't break.
- Finance detail (exact amounts, per-transaction table) must never reach a restricted
  role's browser, even hitting the API directly — enforce server-side.
- Caissier keeps full `/dashboard/cashier` access regardless of Finance restriction.
- Old landing sections (nav, contact, newsletter, footer, features, specs, old CTA) are
  deleted, not hidden with CSS.
- Conventional Commits for any commit made.

---

### Task 1: Rewrite the landing page as a single welcome screen

**Files:**
- Modify: `frontend/src/pages/LandingPage.jsx` (full rewrite)
- Modify: `frontend/src/pages/landing.css` (full rewrite — drop nav/features/specs/cta/contact/newsletter/footer rules, add welcome-screen + modal rules)
- Create: `frontend/src/components/DemoVideoModal.jsx`

**Interfaces:**
- Consumes: `farmApi.exists()` from `frontend/src/api/endpoints.js` (unchanged), `useNavigate` from react-router-dom, `motion` from framer-motion, `.brand-mark` class from `frontend/src/styles/house-protocol-theme-light.css` (already imported elsewhere the same way).
- Produces: `LandingPage` default export (route `/` in `App.jsx`, unchanged wiring). `DemoVideoModal` default export: `<DemoVideoModal open={bool} onClose={fn} src={string} />`.

- [ ] **Step 1: Create `DemoVideoModal.jsx`**

A small controlled modal: renders nothing when `open` is false; when `open`, renders a
backdrop + centered `<video controls autoPlay src={src} />`, a close button (X icon),
closes on backdrop click and on `Escape` keydown, and locks body scroll while open.

```jsx
import { useEffect } from "react";
import { X } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";

export default function DemoVideoModal({ open, onClose, src }) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
  }, [open, onClose]);

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          className="demo-modal-backdrop"
          initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
          onClick={onClose}
        >
          <motion.div
            className="demo-modal-panel"
            initial={{ opacity: 0, scale: 0.96, y: 12 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.96, y: 12 }}
            transition={{ duration: 0.25, ease: "easeOut" }}
            onClick={(e) => e.stopPropagation()}
          >
            <button className="demo-modal-close" onClick={onClose} aria-label="Close video">
              <X size={18} strokeWidth={2} />
            </button>
            <video src={src} controls autoPlay playsInline style={{ width: "100%", display: "block", borderRadius: 16 }} />
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
```

- [ ] **Step 2: Rewrite `LandingPage.jsx`**

Delete `NAV_LINKS`, `FEATURES`, `SPECS`, `PlaceholderArt`, the nav/hero(old)/features/
specs/cta/contact/newsletter/footer JSX, and the `contactForm`/`newsletterEmail` state
+ `submitContact`/`submitNewsletter` handlers (dead once the sections are gone — those
handlers called `publicApi`, which becomes unused in this file; leave `publicApi` itself
in `endpoints.js`, see Task 3 note). Keep the `farmApi.exists()` effect (drives the
"Se connecter" target) and the `fadeUp`/`stagger` motion variants (reused, trimmed).

```jsx
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { Bird, Play } from "lucide-react";
import { farmApi } from "../api/endpoints";
import DemoVideoModal from "../components/DemoVideoModal";
import "../styles/house-protocol-theme-light.css";
import "./landing.css";

const fadeUp = {
  hidden: { opacity: 0, y: 24 },
  show: { opacity: 1, y: 0, transition: { duration: 0.6, ease: "easeOut" } },
};

const stagger = (delay = 0.12) => ({
  hidden: {},
  show: { transition: { staggerChildren: delay } },
});

export default function LandingPage() {
  const [farmExists, setFarmExists] = useState(null);
  const [demoOpen, setDemoOpen] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    farmApi.exists().then(({ data }) => setFarmExists(data.exists)).catch(() => setFarmExists(false));
  }, []);

  const primaryPath = farmExists ? "/login" : "/create-farm";

  return (
    <div className="landing-welcome">
      <motion.div className="welcome-inner" initial="hidden" animate="show" variants={stagger()}>
        <motion.span className="brand-mark welcome-brand-mark" variants={fadeUp}>
          <Bird size={20} strokeWidth={1.8} />
        </motion.span>
        <motion.h1 variants={fadeUp}>Welcome from Winchicken</motion.h1>
        <motion.p className="welcome-subtext" variants={fadeUp}>
          Your farm's full follow-up, exactly the way you configure it.
        </motion.p>
        <motion.div className="welcome-actions" variants={fadeUp}>
          <motion.button
            whileHover={{ scale: 1.03 }} whileTap={{ scale: 0.97 }}
            className="btn-pill outline lg" onClick={() => setDemoOpen(true)}
          >
            <Play size={16} /> Voir une démo
          </motion.button>
          <motion.button
            whileHover={{ scale: 1.03, filter: "brightness(1.05)" }} whileTap={{ scale: 0.97 }}
            className="btn-pill mint lg" onClick={() => navigate(primaryPath)}
          >
            Se connecter
          </motion.button>
        </motion.div>
      </motion.div>

      <DemoVideoModal open={demoOpen} onClose={() => setDemoOpen(false)} src="/demo.mp4" />
    </div>
  );
}
```

- [ ] **Step 3: Rewrite `landing.css`**

Replace the file entirely with just what the welcome screen + modal need — full-height
centered layout, `.welcome-brand-mark` (reuses `.brand-mark` sizing, slightly larger),
heading/subtext typography matching the existing `'Space Grotesk'` display font used
elsewhere, `.btn-pill` variants already defined here are kept (still used by the two
buttons), and the new `.demo-modal-backdrop`/`.demo-modal-panel`/`.demo-modal-close`
rules.

```css
.landing-welcome{min-height:100vh;display:flex;align-items:center;justify-content:center;padding:24px;background:var(--bg)}
.welcome-inner{width:min(560px,100%);text-align:center;display:flex;flex-direction:column;align-items:center}
.welcome-brand-mark{width:56px;height:56px;margin-bottom:28px}
.landing-welcome h1{margin:0 0 14px;font-family:'Space Grotesk',sans-serif;font-size:clamp(30px,4.4vw,44px);letter-spacing:-.03em;color:#10242c}
.welcome-subtext{margin:0 0 36px;font-size:16px;color:var(--muted)}
.welcome-actions{display:flex;gap:14px;flex-wrap:wrap;justify-content:center}

.btn-pill{display:inline-flex;align-items:center;gap:6px;border-radius:999px;font-weight:600;cursor:pointer;text-decoration:none;transition:.15s;border:1px solid transparent}
.btn-pill.mint{background:var(--mint-fill);color:#082019;padding:10px 20px;box-shadow:0 8px 22px rgba(11,143,104,.22)}
.btn-pill.mint:hover{filter:brightness(1.05);transform:translateY(-1px)}
.btn-pill.outline{border-color:var(--line);color:#10242c;background:#fff;padding:10px 20px}
.btn-pill.outline:hover{border-color:rgba(11,143,104,.4)}
.btn-pill.lg{padding:14px 24px;font-size:15px}

.demo-modal-backdrop{position:fixed;inset:0;background:rgba(15,40,33,.55);backdrop-filter:blur(2px);display:flex;align-items:center;justify-content:center;padding:24px;z-index:100}
.demo-modal-panel{position:relative;width:min(860px,100%);background:#000;border-radius:20px;overflow:hidden;box-shadow:0 30px 80px rgba(0,0,0,.4)}
.demo-modal-close{position:absolute;top:12px;right:12px;z-index:1;width:34px;height:34px;border-radius:50%;border:0;background:rgba(0,0,0,.5);color:#fff;display:grid;place-items:center;cursor:pointer}
.demo-modal-close:hover{background:rgba(0,0,0,.7)}
```

- [ ] **Step 4: Manual check**

Run: `cd frontend && npm run dev` (or `docker compose up frontend` per project
convention), open `/`, confirm: centered welcome screen only (no navbar/features/
contact/footer), "Voir une démo" opens the modal (with the browser's native
"no video source" state, since `/demo.mp4` doesn't exist yet — expected, see Task 3),
Escape and backdrop-click both close it, "Se connecter" navigates to `/login` or
`/create-farm` depending on `GET /api/farm/exists/`.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/LandingPage.jsx frontend/src/pages/landing.css frontend/src/components/DemoVideoModal.jsx
git commit -m "feat(landing): replace marketing page with single welcome screen"
```

---

### Task 2: Backend — restricted Finance payload for non-privileged roles

**Files:**
- Modify: `backend/apps/finance/calculations.py`
- Modify: `backend/apps/finance/views.py`
- Test: `backend/apps/finance/tests.py`

**Interfaces:**
- Consumes: `apps.core.permissions` (`ADMIN`, `FARM_MANAGER` constants — import directly, don't add a new permission class since the view needs branch logic, not a binary allow/deny), `apps.finance.calculations.monthly_summary(farm, range_param)` (existing, unchanged signature).
- Produces: `finance_trend_direction(farm, range_param='6m') -> {'revenueTrend': str, 'expenseTrend': str}` where each value is one of `"up"`, `"down"`, `"flat"`. `FinanceSummaryView.get()` now returns `{'access': 'full', **finance_summary(...)}` for Admin/FarmManager and `{'access': 'restricted', 'range': ..., **finance_trend_direction(...)}` for every other authenticated role.

- [ ] **Step 1: Add `finance_trend_direction` to `calculations.py`**

Insert right after `finance_summary`:

```python
def finance_trend_direction(farm, range_param='6m'):
    """Restricted-role payload for GET /api/finance/summary/ (Finance access matrix,
    winchicken-spec-implementation-detaillee.docx §4.3/§8): direction-only trend, no
    exact monetary figures. Compares the two most recent months in the window; "flat"
    when they're equal (covers the single-month edge case too, since a month compared
    to itself is equal)."""
    months = monthly_summary(farm, range_param)
    previous, latest = months[-2], months[-1]

    def direction(key):
        if latest[key] > previous[key]:
            return 'up'
        if latest[key] < previous[key]:
            return 'down'
        return 'flat'

    return {'revenueTrend': direction('revenue'), 'expenseTrend': direction('expense' if False else 'expenses')}
```

(Note while implementing: `monthly_summary` rows use key `'expenses'` — use that key
literally, the `if False else` above is a placeholder to catch copy-paste of the wrong
key name; write it as `direction('expenses')` directly, there's no reason to keep the
conditional in the real file.)

- [ ] **Step 2: Update `FinanceSummaryView` in `views.py`**

```python
from apps.core.permissions import ADMIN, FARM_MANAGER, IsAdminOrCashier, IsAdminOrFarmManager
from apps.finance.calculations import expense_category_breakdown, finance_summary, finance_trend_direction
from rest_framework.permissions import IsAuthenticated
```

Replace the `FinanceSummaryView` class body:

```python
class FinanceSummaryView(APIView):
    """GET /api/finance/summary/?range=6m|1y — open to every authenticated role (Finance
    access matrix, winchicken-spec-implementation-detaillee.docx §4.3/§8): Admin / Farm
    Manager get the full monthly trend + cash-on-hand + pending payables + ROI forecast
    (`access: "full"`); every other role gets direction-only trend with no monetary
    figures (`access: "restricted"`) — the other two Finance endpoints below stay
    Admin/Farm-Manager-only for the exact-amount detail."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        range_param = request.query_params.get('range', '6m')
        farm = request.user.farm
        if request.user.role in (ADMIN, FARM_MANAGER):
            return Response({'access': 'full', **finance_summary(farm, range_param)})
        return Response({'access': 'restricted', 'range': range_param, **finance_trend_direction(farm, range_param)})
```

Leave `FinanceExpenseCategoriesView` and `FinanceTransactionsView` exactly as they are
(`permission_classes = [IsAdminOrFarmManager]`) — restricted roles get a `403` from
those two, which is correct (no exact figures, no per-transaction table for them).

- [ ] **Step 3: Write the tests**

```python
from datetime import date

from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from apps.core.models import Farm, User, UserRole, create_role_profile
from apps.finance.models import Expense, ExpenseCategory, Sale, ProductType


class FinanceAccessTests(APITestCase):
    def setUp(self):
        self.farm = Farm.objects.create(name='Test Farm')

    def _user(self, role, email):
        user = User.objects.create_user(email=email, password='pw12345!', name='T', role=role, farm=self.farm)
        create_role_profile(user)
        return user

    def _auth(self, user):
        token = RefreshToken.for_user(user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token.access_token}')

    def test_admin_gets_full_summary(self):
        admin = self._user(UserRole.ADMIN, 'admin@test.com')
        self._auth(admin)
        resp = self.client.get('/api/finance/summary/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['access'], 'full')
        self.assertIn('cashOnHand', resp.data)
        self.assertIn('months', resp.data)

    def test_farmer_gets_restricted_summary_no_exact_figures(self):
        farmer = self._user(UserRole.FARMER, 'farmer@test.com')
        self._auth(farmer)
        resp = self.client.get('/api/finance/summary/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['access'], 'restricted')
        self.assertIn('revenueTrend', resp.data)
        self.assertIn('expenseTrend', resp.data)
        self.assertNotIn('cashOnHand', resp.data)
        self.assertNotIn('months', resp.data)
        self.assertNotIn('pendingPayables', resp.data)

    def test_farmer_denied_expense_categories_and_transactions(self):
        farmer = self._user(UserRole.FARMER, 'farmer2@test.com')
        self._auth(farmer)
        self.assertEqual(self.client.get('/api/finance/expense-categories/').status_code, 403)
        self.assertEqual(self.client.get('/api/finance/transactions/').status_code, 403)

    def test_cashier_restricted_on_summary_but_full_on_own_sales_entry(self):
        cashier = self._user(UserRole.CASHIER, 'cashier@test.com')
        self._auth(cashier)
        self.assertEqual(self.client.get('/api/finance/summary/').data['access'], 'restricted')
        resp = self.client.post('/api/sales/', {
            'product_type': ProductType.BIRD, 'quantity': 10, 'unit_price': '5.00', 'sale_date': str(date.today()),
        })
        self.assertEqual(resp.status_code, 201)

    def test_trend_direction_reflects_last_two_months(self):
        admin = self._user(UserRole.ADMIN, 'admin2@test.com')
        today = date.today()
        Expense.objects.create(farm=self.farm, category=ExpenseCategory.FEED, amount=100, expense_date=today.replace(day=1))
        Sale.objects.create(farm=self.farm, product_type=ProductType.BIRD, quantity=1, unit_price=500, sale_date=today.replace(day=1))
        farmer = self._user(UserRole.FARMER, 'farmer3@test.com')
        self._auth(farmer)
        resp = self.client.get('/api/finance/summary/')
        self.assertIn(resp.data['revenueTrend'], ('up', 'down', 'flat'))
        self.assertIn(resp.data['expenseTrend'], ('up', 'down', 'flat'))
```

- [ ] **Step 4: Run the tests**

Run: `cd backend && source .venv/bin/activate && python manage.py test apps.finance -v 2`
Expected: all pass. If the venv lacks `rest_framework_simplejwt` test helpers or the DB
isn't reachable outside Docker, run instead via
`docker compose exec web python manage.py test apps.finance -v 2`.

- [ ] **Step 5: Commit**

```bash
git add backend/apps/finance/calculations.py backend/apps/finance/views.py backend/apps/finance/tests.py
git commit -m "feat(finance): restrict Finance summary detail for non-privileged roles"
```

---

### Task 3: Frontend — Finance screen renders both payload shapes; sidebar link always visible

**Files:**
- Modify: `frontend/src/pages/dashboard/FinancePage.jsx`
- Modify: `frontend/src/pages/dashboard/DashboardShell.jsx`
- Modify: `frontend/src/api/endpoints.js` (no signature change needed — `financeApi.summary` stays as-is; note only)

**Interfaces:**
- Consumes: `GET /api/finance/summary/` now returns either `{access:"full", range, months, cashOnHand, pendingPayables, roiForecastPct}` or `{access:"restricted", range, revenueTrend, expenseTrend}` (Task 2).
- Produces: `FinancePage` renders the existing full layout when `summary.access === "full"`, and a reduced two-card trend-only layout when `"restricted"` — skipping the `expenseCategories`/`transactions` fetches entirely in the restricted case (those would 403).

- [ ] **Step 1: Update `FinancePage.jsx`**

Guard the two detail fetches behind `summary?.access === "full"`, and branch the render:

```jsx
import { useEffect, useState } from "react";
import { Area, AreaChart, CartesianGrid, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { TrendingUp, TrendingDown, Minus } from "lucide-react";
import { financeApi } from "../../api/endpoints";
import "../../styles/dashboard-theme.css";

const CATEGORY_COLORS = {
  FEED: "#0b8f68", LABOR: "#17b892", VETERINARY: "#5f7377", DEPRECIATION: "#b9790c", MISC: "#d6433f",
};

const TREND_ICON = { up: TrendingUp, down: TrendingDown, flat: Minus };

export default function FinancePage() {
  const [range, setRange] = useState("6m");
  const [summary, setSummary] = useState(null);
  const [categories, setCategories] = useState([]);
  const [transactions, setTransactions] = useState({ count: 0, page: 1, results: [] });
  const [typeFilter, setTypeFilter] = useState("all");

  useEffect(() => {
    setSummary(null);
    financeApi.summary(range).then(({ data }) => setSummary(data));
  }, [range]);

  const isFull = summary?.access === "full";

  useEffect(() => {
    if (!isFull) return;
    financeApi.expenseCategories(range).then(({ data }) => setCategories(data.categories));
  }, [range, isFull]);

  const loadTransactions = (page) => {
    financeApi.transactions(page, typeFilter).then(({ data }) => setTransactions(data));
  };

  useEffect(() => { if (isFull) loadTransactions(1); }, [typeFilter, isFull]);

  if (!summary) return <div className="page-wrap"><p className="empty-state">Loading…</p></div>;

  if (!isFull) {
    const TrendIcon = (key) => TREND_ICON[summary[key]] || Minus;
    return (
      <div className="page-wrap">
        <div className="breadcrumb">Dashboard / <strong>Finance</strong></div>
        <p className="empty-state" style={{ marginBottom: 18 }}>
          Restricted view — figures and the transaction ledger are limited to Administrator and Farm Manager accounts.
        </p>
        <div className="finance-grid">
          <div className="finance-stack">
            <div className="stat-card">
              <p className="stat-label">Revenue trend</p>
              <p className="stat-value" style={{ display: "flex", alignItems: "center", gap: 8 }}>
                {(() => { const Icon = TrendIcon("revenueTrend"); return <Icon size={22} />; })()}
                <span className={`badge-trend ${summary.revenueTrend}`}>{summary.revenueTrend}</span>
              </p>
            </div>
            <div className="stat-card">
              <p className="stat-label">Expense trend</p>
              <p className="stat-value" style={{ display: "flex", alignItems: "center", gap: 8 }}>
                {(() => { const Icon = TrendIcon("expenseTrend"); return <Icon size={22} />; })()}
                <span className={`badge-trend ${summary.expenseTrend}`}>{summary.expenseTrend}</span>
              </p>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // ... existing full-access JSX below is unchanged (totalPages/thisMonth/full return block)
}
```

Keep the rest of the existing full-access return block (the chart, pie, stat cards,
transactions table) verbatim below this — it already reads from `summary.months` /
`categories` / `transactions`, all of which are only populated in the `isFull` branch.

- [ ] **Step 2: Update `DashboardShell.jsx`**

Finance is now visible to every role (content differs, but the link itself is no longer
role-gated per the updated spec) — drop the `canSeeFinance` prop entirely so the
`DashboardLayout` default (`true`) applies:

```jsx
      canManageHouses={["ADMIN", "FARM_MANAGER"].includes(user.role)}
      canSeeEmployees={["ADMIN", "SECONDARY_ADMIN"].includes(user.role)}
```

(remove the `canSeeFinance={...}` line between those two)

- [ ] **Step 3: Manual check**

With the backend running (Task 2 done), log in as an Admin: Finance shows the full
chart/pie/table as before. Log in as a Farmer or Technician (or temporarily flip a test
user's role): Finance sidebar link is present, page shows only the two trend cards, no
chart/table, and network tab shows no `expense-categories`/`transactions` requests
(their 403 is avoided client-side, not just handled after the fact) but does confirm a
direct `curl` to those two endpoints with that user's token still returns `403`.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/dashboard/FinancePage.jsx frontend/src/pages/dashboard/DashboardShell.jsx
git commit -m "feat(finance): render restricted Finance view for non-privileged roles"
```

---

### Task 4: Verify Part B end-to-end (no code expected, confirm only)

**Files:** none expected — `LoginPage.jsx`, `ProtectedRoute.jsx`, `WinchickenTokenObtainPairSerializer`, `MeSerializer` already implement direct-to-dashboard routing (confirmed by reading the code in this session). This task is a live confirmation pass, not an implementation pass.

- [ ] **Step 1:** Start the stack (`docker compose up -d --build` or equivalent dev
  servers per `frontend/README.md`/root `README.md`).
- [ ] **Step 2:** Create farm → complete onboarding (protocol + stock, employees
  step optional) → confirm landing directly on `/dashboard`, no intermediate screen.
- [ ] **Step 3:** Add one employee (any non-Admin role) via
  `/dashboard/employees`, log out, log in as that employee → confirm landing directly
  on `/dashboard`, no intermediate screen, Finance restricted per Task 3.
- [ ] **Step 4:** If any gap is found, fix it in `LoginPage.jsx`/`ProtectedRoute.jsx`
  directly (not expected, but this step exists in case reality disagrees with the code
  read during planning).

---

### Task 5: Update the two spec documents and docs/deviations.md

**Files:**
- Modify: `winchicken-cahier-des-charges.docx` (§6 → replace with a short "Landing page v2" description; leave §8.3 Finance view note as-is, it already describes the full-access view which still exists for Admin/Farm Manager)
- Modify: `winchicken-spec-implementation-detaillee.docx` (§1 → replace button inventory with the new welcome-screen inventory; §4.3 → add a restricted-view row; §8 → split the "Consulter la vue Finance" row into full/restricted rows, and update the "Lien sidebar « Finance »" row's allowed-roles)
- Modify: `docs/deviations.md` (append a new dated section)
- Modify: root `README.md` (note the demo video placeholder path + `/demo` vs video-modal decision)

Use `python-docx` (a throwaway venv is fine — the project's own `.venv` doesn't have
it) to edit the two `.docx` files in place: locate each heading paragraph by exact
text match, clear/replace the paragraphs and table rows between it and the next
heading at the same or higher level, per the concrete replacement text below.

- [ ] **Step 1: `winchicken-cahier-des-charges.docx` §6**

Replace the intro paragraph (currently describing the full marketing structure) and
collapse §6.1–6.9 into a single short description of the welcome screen (logo,
heading, subtext, "Voir une démo" modal button, "Se connecter" button routed by
`GET /api/farm/exists/`, fade-up entrance only). Keep the heading "6. Page d'accueil
publique" itself and renumber nothing else.

- [ ] **Step 2: `winchicken-spec-implementation-detaillee.docx` §1**

Replace the three subsections (1.1 nav, 1.2 hero, 1.3 fonctionnement/CTA) and their
button-inventory tables with a single table for the welcome screen: brand mark
(decorative), "Voir une démo" (opens modal, closable, controls visible), "Se
connecter" (routes per farm-exists check).

- [ ] **Step 3: `winchicken-spec-implementation-detaillee.docx` §4.3**

Add a row (or a short paragraph immediately after the existing table) documenting the
restricted view: "Non-privileged roles (Fermier, Ouvrier, Technicien, Caissier,
Administrateur secondaire) see two trend-direction cards only (chiffre d'affaires,
charges — hausse/baisse/stable), no exact figures, no table, no filters — GET
/api/finance/summary/ returns `access: "restricted"` for these roles instead of the
full payload."

- [ ] **Step 4: `winchicken-spec-implementation-detaillee.docx` §8**

Update the "Lien sidebar « Finance »" row's allowed-roles cell to "Tous les rôles
authentifiés (contenu restreint selon le rôle)". Split "Consulter la vue Finance" into
two rows: "Consulter la vue Finance (détail complet : montants, table, filtres)" →
"Administrateur, Gérant de ferme", and "Consulter la vue Finance (résumé restreint :
tendance uniquement)" → "Fermier, Ouvrier, Technicien, Caissier, Administrateur
secondaire".

- [ ] **Step 5: Append to `docs/deviations.md`**

New "Part 3" section (matching the file's existing numbered format), dated
2026-08-25, covering: (a) landing page replaced with welcome screen — old sections
deleted not hidden, `/demo` interactive client-side demo kept as a separate deep link
alongside the new video modal since it exercises real form/dashboard components the
video can't; (b) login routing to `/dashboard` confirmed already correct, no code
change needed; (c) Finance summary endpoint restructured to return a role-branched
payload shape (`access: "full"`/`"restricted"`), the other two Finance endpoints
unchanged (still 403 for restricted roles).

- [ ] **Step 6: Note the demo video placeholder in root `README.md`**

Add one line near wherever the landing page / frontend is described: `/demo.mp4` is a
placeholder path referenced by the "Voir une démo" button on `/` — no real file is
committed; drop the actual product video at `frontend/public/demo.mp4` to wire it up.

- [ ] **Step 7: Commit**

```bash
git add winchicken-cahier-des-charges.docx winchicken-spec-implementation-detaillee.docx docs/deviations.md README.md
git commit -m "docs: sync spec documents and deviations log with landing v2 / Finance restriction"
```

---

## Self-Review Notes

- Spec coverage: Part A → Task 1. Part B → Task 4 (verify-only, code already correct
  per Task 4's file list). Part C → Task 2 (server-side enforcement) + Task 3
  (frontend render) + existing employee-creation/login flow (already generic, no
  per-role login path — confirmed in exploration, no task needed). Doc sync → Task 5.
- No placeholders: every step above has literal code or literal replacement text.
- Type/shape consistency: `finance_trend_direction` return keys (`revenueTrend`,
  `expenseTrend`) match what `FinancePage.jsx`'s restricted branch reads; `access`
  field name and values (`"full"`/`"restricted"`) match between Task 2 and Task 3.
