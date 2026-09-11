# Batch Creation: Manual vs Excel Choice Screen — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement
> this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Insert a "Comment voulez-vous configurer cette bande ?" choice step (manuel vs
Excel) into the batch-creation flow, reachable from both entry points that hit
`/onboarding/protocol` today (`+ Nouvelle bande` on an existing farm, and the very first
batch during initial farm onboarding), without changing the manual path's behavior.

**Architecture:** `OnboardingProtocolPage` becomes a tiny 3-step state machine
(`header` → `choice` → `manual` | `excel`) instead of rendering `HouseProtocolForm`
directly. Two new presentational components carry the new screens. The Excel screen's
Protocol card reuses `protocolImportApi` + a newly-extracted resolution helper (pulled out
of `HouseProtocolForm.jsx` verbatim, not rewritten) so parsing/validation logic is untouched.
The Stock card reuses `stockApi.importXlsx` (the safe, update-or-create importer already
used by `StockParametersModal`, never the destructive onboarding full-replace one). Finance
has no backend endpoint (`apps/finance/urls.py` confirmed) → disabled "Bientôt disponible"
card.

**Tech Stack:** React (Vite), existing `frontend/src/api/endpoints.js` clients, existing
onboarding CSS classes (`card`, `add-button`, `schedule-card`, mint/navy dashboard theme).

**Spec:** PROMPT 1 (pasted by user, "Onboarding: manual vs Excel choice screen"). Two
decisions were confirmed with the user before writing this plan (not in the original spec):
1. Add a Broiler/Layer selector to the new small step — the backend already supports
   `PoultryBatch.production_type` (`BROILER`/`LAYER`) but no UI ever exposed it.
2. The new choice screen applies to **both** flows that reach `/onboarding/protocol`
   (`+ Nouvelle bande` and first-time onboarding), not just one.

## Autonomous decisions (documented per README "Autonomous decisions" convention)

- **No literal "modal" exists today.** The spec describes validating "the existing small
  modal" before showing the choice screen, but `/onboarding/protocol` has never been a
  modal — it's a routed page, consistent with `/onboarding/stock` and `/onboarding/employees`.
  Building the small header step as a true dialog overlay here would be the only modal in an
  otherwise all-page onboarding flow. Decision: implement it as a compact step-card on the
  same page (visually distinct, single-column, matches `schedule-card` styling), not an
  overlay. Documented here and in `docs/deviations.md`.
- **First-time onboarding keeps its separate `/onboarding/stock` step unchanged.** If a user
  imports Stock from the new Excel screen during their very first batch, `/onboarding/stock`
  still runs afterward exactly as it does today (full-replace PUT). This is a deliberate,
  narrow scope choice — Prompt 1 says not to touch existing import systems' behavior, and
  reconciling "safe update-or-create now" with "full-replace later" is out of scope here.
  Since the full-replace step already lets the user review/edit before saving, the two
  imports don't conflict, just potentially overlap. For `+ Nouvelle bande` (existing farm),
  there's no such step today, so the Stock card is a net-new capability there and this
  overlap doesn't apply.

## Global Constraints

- All UI text in French.
- Small, separate commits: header/protocol-type step → choice screen → Excel import screen →
  back navigation. One commit per task below.
- No changes to `protocolImportApi`/`stockApi` parsing/validation logic — only extraction of
  existing client-side resolution code into a shared helper, call sites updated, behavior
  identical.
- Mobile: cards must stack in a single column and stay tappable below 400px width.
- No new "tree" dashboard, no keyword remapping, no AI calls — out of scope (Prompt 2/3).

---

## File Structure

- Modify: `frontend/src/pages/onboarding/OnboardingProtocolPage.jsx` — becomes the step
  orchestrator (`step` state: `"header" | "choice" | "manual" | "excel"`).
- Create: `frontend/src/components/onboarding/BatchHeaderStep.jsx` — the 4-field step
  (batch name, chicken count, room/building name, protocol type). Replaces the header fields
  that used to live inline at the top of `HouseProtocolForm`'s onboarding usage — but
  `HouseProtocolForm` itself is untouched (its header fields still exist for the
  `ProtocolEditModal`/management path and for direct re-entry); this step is a lighter
  standalone form whose output seeds `HouseProtocolForm`'s `initialHeader` prop.
- Create: `frontend/src/components/onboarding/BatchMethodChoice.jsx` — the two-card
  manuel/Excel screen.
- Create: `frontend/src/components/onboarding/BatchExcelImportScreen.jsx` — the
  three-button Excel screen (Protocol / Stock / Finances).
- Create: `frontend/src/components/onboarding/ExcelImportCard.jsx` — shared card UI
  (title, "Télécharger un modèle" link, "Importer un fichier Excel" button + hidden file
  input, result/error summary). Parameterized by `onImport(file)`, `templateUrl`,
  `resultRenderer`. Used by both the Protocol and Stock cards; Finance renders its own
  disabled variant inline (no import wiring needed).
- Create: `frontend/src/utils/protocolImportResolve.js` — extracted from
  `HouseProtocolForm.jsx` lines ~336-389 (`resolveProtocolImportRows`): given parsed
  `data.rows`, current `categories`, current `stockItemList`, `farmId`, and the same
  `createCategory`/`createStockItem` calls, returns `{ schedules, categories }` (or, for
  callers that don't yet have live categories/stock — the onboarding Excel screen — creates
  them via the same API calls `HouseProtocolForm` already makes). Byte-identical logic, only
  moved.
- Modify: `frontend/src/components/HouseProtocolForm.jsx` — replace its inline import
  resolution block with a call to `resolveProtocolImportRows` (no behavior change, just
  dedup so the Excel screen and the manual form never drift).
- Create: `frontend/src/pages/onboarding/batch-flow.css` — stacking rules for the two/three
  card grids (`grid-template-columns: repeat(2, 1fr)` → `1fr` under 480px), imported by the
  new components.
- Modify: `docs/deviations.md` — add the two autonomous-decision entries above.

## Interfaces

- `BatchHeaderStep`
  - Props: `{ initial: {buildingName, chicksPlaced, batchName, productionType, growthCycle, growthCycleUnit, weighingFrequency}, onNext: (header) => void }`
  - Produces on `onNext`: the same shape plus `productionType: "BROILER"|"LAYER"`.
- `BatchMethodChoice`
  - Props: `{ onSelectManual: () => void, onSelectExcel: () => void, onBack: () => void }`
- `BatchExcelImportScreen`
  - Props: `{ header, categories, farmId, isAddingHouse, onProtocolImported: (categories, schedules) => void, onContinue: () => void, onBack: () => void }`
  - Internally calls `protocolImportApi.parse`, `resolveProtocolImportRows`,
    `stockApi.importXlsx(farmId, file)`.
- `resolveProtocolImportRows(rows, { categories, stockItemList, farmId, createCategory, createStockItem })`
  → `Promise<{ schedules: Record<catId, Row[]>, importResult: {imported, skipped, warnings} }>`
  (exact signature matches the current inline block's captured variables in
  `HouseProtocolForm.jsx`, just parameterized).

---

## Tasks

### Task 1: Extract `resolveProtocolImportRows` (no behavior change)

**Files:**
- Create: `frontend/src/utils/protocolImportResolve.js`
- Modify: `frontend/src/components/HouseProtocolForm.jsx:322-401` (the `handleImportFile` body)
- Test: `frontend/src/components/__tests__/HouseProtocolForm.test.jsx` (existing import tests
  must still pass unmodified — this task must not change their expectations)

- [ ] Step 1: Read `HouseProtocolForm.jsx:237-401` in full to copy the exact current logic
      (category resolution, stock-item resolution, schedule building, the empty-rows guard).
- [ ] Step 2: Write `protocolImportResolve.js` exporting
      `export async function resolveProtocolImportRows(rows, { categories, stockItemList, createCategory, createStockItem })`
      containing that logic verbatim, returning `{ schedules, skipped, warnings, imported }`
      instead of calling `setSchedules`/`setImportResult` directly (the caller does that).
- [ ] Step 3: Update `HouseProtocolForm.jsx`'s `handleImportFile` to call the new helper and
      keep setting the same state (`setSchedules`, `setImportResult`) from its return value.
- [ ] Step 4: Run `docker compose exec frontend npx vitest run HouseProtocolForm` — all
      existing import tests must pass unchanged (proves no behavior drift).
- [ ] Step 5: Commit — `refactor(onboarding): extract protocol-import row resolution into a shared helper`

### Task 2: `BatchHeaderStep` — batch name / chicken count / room / protocol type

**Files:**
- Create: `frontend/src/components/onboarding/BatchHeaderStep.jsx`
- Create: `frontend/src/pages/onboarding/batch-flow.css`
- Test: `frontend/src/components/onboarding/__tests__/BatchHeaderStep.test.jsx`

- [ ] Step 1: Write failing test asserting: renders 4 fields, "Suivant" disabled until batch
      name + chicken count + room are non-blank, calls `onNext` with
      `{buildingName, chicksPlaced, batchName, productionType, ...}` on submit.
- [ ] Step 2: Run it, confirm it fails (component doesn't exist).
- [ ] Step 3: Implement `BatchHeaderStep.jsx` — a `schedule-card`-styled block with:
      Nom de la bande (text), Nombre de poussins (number), Bâtiment / Salle (text — reuses
      `buildingName`), Type de protocole (`<select>` Broiler="Poulet de chair" /
      Layer="Pondeuse"). Defaults: `productionType: initial.productionType || "BROILER"`.
- [ ] Step 4: Run tests, confirm pass.
- [ ] Step 5: Commit — `feat(onboarding): batch header step with protocol-type selector`

### Task 3: Wire `OnboardingProtocolPage` step machine — header → manual (parity check)

**Files:**
- Modify: `frontend/src/pages/onboarding/OnboardingProtocolPage.jsx`
- Modify: `frontend/src/pages/onboarding/OnboardingProtocolPage.test.jsx` (or the existing
  test file at `frontend/src/pages/onboarding/__tests__/OnboardingProtocolPage.test.jsx`)

- [ ] Step 1: Add `const [step, setStep] = useState("header")` and `const [pendingHeader, setPendingHeader] = useState(houseHeader)`.
- [ ] Step 2: When `step === "header"`, render `<BatchHeaderStep initial={pendingHeader} onNext={(h) => { setPendingHeader(h); setStep("choice"); }} />`.
- [ ] Step 3: When `step === "choice"`, render `<BatchMethodChoice onSelectManual={() => setStep("manual")} onSelectExcel={() => setStep("excel")} onBack={() => setStep("header")} />` (Task 4 builds this component; stub it minimally here if sequencing before Task 4, or do Task 4 first — recommend doing Task 4 before this step).
- [ ] Step 4: When `step === "manual"`, render exactly what `OnboardingProtocolPage` renders
      today (`<HouseProtocolForm initialHeader={pendingHeader} .../>` with all existing props
      and `handleSave`/`handleAddAnother` untouched) plus a "Retour" link calling
      `setStep("choice")`.
- [ ] Step 5: `buildOnboardingRequest` must read `payload.house.buildingName`/`chicksPlaced`
      from `pendingHeader` merged with the form payload — confirm `productionType` flows into
      `batch.productionType` instead of the hardcoded `"BROILER"` string (this is the one
      required behavior change to the existing submit payload).
- [ ] Step 6: Update/extend the existing onboarding-protocol test to click through
      header → choice → "Configurer manuellement" and assert `HouseProtocolForm` renders with
      the header pre-filled, and that the save payload's `batch.productionType` matches what
      was picked in step 1.
- [ ] Step 7: Run `docker compose exec frontend npx vitest run OnboardingProtocolPage`.
- [ ] Step 8: Commit — `feat(onboarding): route batch creation through header + method-choice steps (manual path)`

### Task 4: `BatchMethodChoice` — the two cards

**Files:**
- Create: `frontend/src/components/onboarding/BatchMethodChoice.jsx`
- Test: `frontend/src/components/onboarding/__tests__/BatchMethodChoice.test.jsx`

- [ ] Step 1: Failing test: renders two buttons/cards ("Configurer manuellement",
      "Importer via Excel"), clicking each calls the matching prop, "Retour" calls `onBack`.
- [ ] Step 2: Run, confirm fails.
- [ ] Step 3: Implement using existing pen/file icons from `lucide-react` (already a
      dependency — see `ProtocolEditModal.jsx`'s `X` import, `OnboardingEmployeesPage.jsx`'s
      `UserPlus`): `Pencil` for manual, `FileSpreadsheet` for Excel. Two-column CSS grid via
      `batch-flow.css`, `grid-template-columns: 1fr` under 480px (media query). Background:
      same as the page (no new background component — inherits `OnboardingLayout`'s).
- [ ] Step 4: Run tests, confirm pass.
- [ ] Step 5: Commit — `feat(onboarding): manual-vs-Excel method choice screen`

### Task 5: `ExcelImportCard` — shared import UI

**Files:**
- Create: `frontend/src/components/onboarding/ExcelImportCard.jsx`
- Test: `frontend/src/components/onboarding/__tests__/ExcelImportCard.test.jsx`

- [ ] Step 1: Failing test: renders title, template link (`href={templateUrl}`), "Importer un
      fichier Excel" button that triggers a hidden `<input type="file">`, calls `onImport(file)`
      on selection, shows `busy` spinner while `importing`, renders `resultSlot` when provided,
      shows `disabled` + "Bientôt disponible" badge and no working input when `disabled` is true.
- [ ] Step 2: Run, confirm fails.
- [ ] Step 3: Implement — props
      `{ title, templateUrl, onImport, importing, disabled, badge, resultSlot, errorMessage }`.
      Mirrors the exact markup pattern already in `StockParametersModal.jsx:220-260` and
      `HouseProtocolForm.jsx:590-624` (button + hidden input + accept=".xlsx" + note text)
      so it looks identical to the existing import UI elsewhere in the app.
- [ ] Step 4: Run tests, confirm pass.
- [ ] Step 5: Commit — `feat(onboarding): shared Excel-import card component`

### Task 6: `BatchExcelImportScreen` — Protocol / Stock / Finances

**Files:**
- Create: `frontend/src/components/onboarding/BatchExcelImportScreen.jsx`
- Test: `frontend/src/components/onboarding/__tests__/BatchExcelImportScreen.test.jsx`

- [ ] Step 1: Failing tests (3 cases):
      (a) Protocol import success → calls `onProtocolImported(categories, schedules)` and
          shows a summary using the same `{imported, skipped, warnings}` shape
          `HouseProtocolForm` already displays.
      (b) Stock import success → calls `stockApi.importXlsx(farmId, file)` and renders
          `{updated, created, skipped}` (same shape as `StockParametersModal`).
      (c) Finance card renders disabled with "Bientôt disponible" badge, no file input wired.
      (d) "Continuer" button is disabled until the Protocol import has succeeded at least
          once; clicking it calls `onContinue`.
- [ ] Step 2: Run, confirm fail.
- [ ] Step 3: Implement — three `ExcelImportCard`s in a 3-column grid (stacks to 1 column
      under 480px, matches Task 4's card grid breakpoint). Protocol card's `onImport` calls
      `protocolImportApi.parse(file)` then `resolveProtocolImportRows` (from Task 1) using
      `categories` prop + an internal `stockItemList` fetched once via
      `stockApi.items(farmId)` on mount (same data `HouseProtocolForm` already loads) +
      `createCategory`/`createStockItem` closures posting through `housesApi`/`stockApi`
      exactly like `HouseProtocolForm.jsx` does today. Stock card's `onImport` calls
      `stockApi.importXlsx(farmId, file)` directly — no extra client logic, server does
      update-or-create. Track `protocolImported` boolean state to gate "Continuer".
      "Retour" calls `onBack` → `setStep("choice")`.
- [ ] Step 4: Run tests, confirm pass.
- [ ] Step 5: Commit — `feat(onboarding): Excel import screen with Protocol/Stock/Finances cards`

### Task 7: Wire the Excel path into `OnboardingProtocolPage` + back navigation

**Files:**
- Modify: `frontend/src/pages/onboarding/OnboardingProtocolPage.jsx`
- Modify: `frontend/src/pages/onboarding/__tests__/OnboardingProtocolPage.test.jsx`

- [ ] Step 1: When `step === "excel"`, render `<BatchExcelImportScreen header={pendingHeader} categories={categories} farmId={user.farm} isAddingHouse={isAddingHouse} onProtocolImported={(cats, sched) => { setCategories(cats); setSchedules(sched); }} onContinue={() => { /* same continuation buildOnboardingRequest + submit + navigate logic as handleSave, using pendingHeader + the categories/schedules just set */ }} onBack={() => setStep("choice")} />`.
- [ ] Step 2: Factor the shared "submit + navigate" tail of `handleSave` (lines ~63-72 today)
      into a small `finishOnboarding(payload)` function so both the manual path's `handleSave`
      and the Excel path's `onContinue` call the same submit/navigate code — "identical
      behavior to the end of the current manual flow" per spec.
- [ ] Step 3: Back-navigation check: going `manual`/`excel` → `choice` → `header` must not
      lose `pendingHeader` (it's lifted state in `OnboardingProtocolPage`, not re-fetched) —
      add a test asserting header field values survive a full round trip through all 4 steps.
- [ ] Step 4: Run `docker compose exec frontend npx vitest run OnboardingProtocolPage`.
- [ ] Step 5: Commit — `feat(onboarding): wire Excel import path into batch-creation flow + back navigation`

---

## Live Verification (blocks marking Prompt 1 complete)

Chrome extension was not connected when this plan was written — reconnect it before this
step. Then, via `mcp__claude-in-chrome__*` on `http://localhost:5173`:

1. Log in, click "+ Nouvelle bande" → confirm the header step (4 fields incl. protocol type)
   appears, fill it, "Suivant" → confirm the two-card choice screen appears.
2. Manual path: click "Configurer manuellement" → confirm it is pixel-identical to today's
   form (no regressions), complete it, confirm the batch is created with the chosen
   `production_type` persisted (check via `batchesApi`/admin or the house detail page).
3. Excel path: "Importer via Excel" → confirm 3 cards, import a real Protocol template file
   and a real Stock template file (download the templates from the page first), confirm both
   succeed and "Continuer" navigates identically to the manual path's end state.
4. Resize viewport to <400px width: confirm both the method-choice cards and the 3
   Excel-import cards stack to one column and remain tappable (no overlap, no horizontal
   scroll).
5. First-time onboarding: factory-reset or use a fresh test farm, confirm the same header →
   choice → manual/excel sequence appears before `/onboarding/stock`, and that
   `/onboarding/stock` still runs afterward unchanged.

Hand off to the `qa-verifier` subagent for this pass per CLAUDE.md's verification gate before
reporting Prompt 1 complete.
