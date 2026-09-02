# Import de protocole depuis un fichier Excel

An **"Importer un fichier Excel"** button + **"Télécharger un modèle"** link on the protocol
configuration screen — in **both** places that render `HouseProtocolForm`: the onboarding
protocol step and the "Modifier" edit modal for an existing batch. Same shared component, so
the two behave identically.

## User flow

1. Click **"Télécharger un modèle"** → `modele-protocole.xlsx` (headers + 3 example rows).
2. Fill it in, click **"Importer un fichier Excel"** → an explicit warning:
   *"Cet import va remplacer toutes les lignes de protocole actuelles de ce bâtiment par le
   contenu du fichier. Cette action est irréversible."* — **Annuler** / **Choisir le fichier
   et remplacer**. Nothing is parsed until the user confirms.
3. On confirm, the file is parsed **server-side** and the form's protocol becomes **exactly the
   file's rows — full replacement, not a merge** (re-importing an edited file never duplicates
   or leaves stray rows). Still nothing is *saved* yet: the user reviews the result and saves
   normally. `PUT /houses/{code}/protocol/` then does the DB replace transactionally (all rows
   for the house deleted + recreated in one transaction) and regenerates the active batch's
   future `PROTOCOL_TASK` `AlertRule` rows — **past `Alert` / `SmsMessage` history is left
   untouched** (`expand_protocol_to_alert_rules`, already used by every protocol edit).
4. A summary appears: *"Protocole remplacé — X ligne(s) importée(s) avec succès[, Y ligne(s)
   ignorée(s)]"* with one bullet per skipped row (`Ligne N : <raison>`).
5. **Guard:** a file with **zero usable rows** does *not* wipe the protocol — the skip report
   is shown and the existing rows are kept (protection against an accidental total erase).

## Excel format

Header row required. Columns are matched **by header name** (case-insensitive, trimmed) — order
does not matter.

| Header | Type | Notes |
|---|---|---|
| **Catégorie** | text | Matched to an existing `ProtocolCategory` by name; created automatically if unknown. |
| **De** | number | Start of the period. Required. |
| **À** | number | End of the period. **Blank ⇒ "jusqu'à la fin du cycle".** |
| **Action** | text | → `ProtocolTemplate.what`. Required. |
| **Détails** | text | → `ProtocolTemplate.details`. |
| **Consommation** | text, optional | Stock resource this row consumes; matched to a `StockItem` by name, created if unknown. |
| **Quantité/jour** | number, optional | Fixed daily quantity of that resource. |

## Backend

- `apps/protocols/xlsx_import.py` — `parse_protocol_rows(file)` and `build_template_workbook()`.
- `POST /api/protocols/import-xlsx/` (`ProtocolImportView`, multipart field `file`) — **parse
  only**, returns `{rows, imported, skipped:[{line, reason}]}`. Auth: any authenticated user
  (same as who may edit the protocol). Farm-agnostic on purpose — onboarding uploads it before
  the house exists.
- `GET /api/protocols/import-template.xlsx` (`ProtocolImportTemplateView`) — the template.
  `AllowAny` (static content, no farm data) so the frontend can use a plain `<a href>`.
- Library: **`openpyxl`** (added to `requirements.txt`; lighter than pandas, which is not a
  dependency). Rebuild the `web` image after pulling: `docker compose build web`.

## Per-row validation (one bad row never fails the whole import)

| Condition | Result |
|---|---|
| `Catégorie`, `De` or `Action` missing | row skipped, reason: `catégorie manquante` / `valeur « De » manquante` / `action manquante` |
| `De` / `À` not a number | skipped, reason names the offending value |
| `À` < `De` | skipped, reason: `« À » (x) est inférieur à « De » (y)` |
| every cell blank | ignored silently (not counted as skipped) |
| `Quantité/jour` filled but `Consommation` blank | quantity dropped, **row still imported** |
| a required **header column** absent | whole file rejected with a clear 400 |
| file is not `.xlsx` / unreadable | 400 with a clear message |

## Decisions made (autonomous mode)

1. **`openpyxl`**, not pandas.
2. **No unit column.** Every imported row is period unit **"Jour"** (`DAY`). A short note next
   to the import button states this; the user changes individual rows to Semaine/Mois in the
   normal UI afterwards.
3. **Parse-only endpoint.** The backend never writes `ProtocolTemplate` rows on import — the
   frontend sets the form's rows to the parsed rows for review before the normal save. The
   transactional DB replace + `AlertRule` regeneration + history preservation asked for by the
   "make import replace, not append" change are **already done by the existing save path**
   (`HouseProtocolView.put`), so no separate import-write path was added.
3b. **Import is a full replacement**, behind a confirm dialog, since re-importing an edited
   file must make the protocol match the file — not append. A file with 0 usable rows is the
   one exception: it does not wipe the protocol (accidental-erase guard).
4. **Category / stock-item auto-creation happens client-side**, reusing the form's existing
   flows: `createCategory` (the "+" button's logic — local-only in onboarding, persisted
   immediately in "Modifier") and `createStockItem` (the resource combobox's inline "+ Créer"
   — `category_hint` taken from the row's own `Catégorie`, unit defaulted to `kg`, adjustable
   later from the Stock screen). This is why it works unchanged before the house exists.
5. **Blank `Catégorie` ⇒ row skipped** (`catégorie manquante`). A protocol row must belong to a
   category and the spec doesn't define a default.
6. **`Quantité/jour` without `Consommation` ⇒ quantity dropped**, row still imported (no error).
7. **`.xlsx` only** (not `.xls` / `.csv`), first worksheet only.
8. **Fully-empty rows are ignored**, not reported as skipped.
9. **Template endpoint is `AllowAny`** (static example content) so the download is a plain link.
10. Import controls live **in the header card**, next to "Charger le modèle de départ" — the
    only change to the form outside the header card is appending the parsed rows to `schedules`.
11. French decimals (`12,5`) are accepted in number cells.

---

# Import Stock (paramètres) — mise à jour ou création par nom d'article

**"Importer un fichier Excel"** + **"Télécharger un modèle"** on the "Mettre à jour le stock"
modal. Unlike the Protocol import, this is **update-or-create, never a replacement and never a
delete.**

## Columns (`modele-stock.xlsx`)

| Header | Notes |
|---|---|
| **Article** | name — the **matching key** (case-insensitive, within the farm). |
| **Catégorie** | matched to a `StockCategory` by name; auto-created as `CUSTOM` (icon `Package`, `sort_order = max+1`) if unknown. |
| **Détail** | polymorphic by category kind: `FEED` → feed stage; `VETERINARY` → cold-chain flag (`oui`/`yes`/`true`/`1`/`x` → true); otherwise → free-text `item_type`. |
| **Unité** | `StockItem.unit`. |
| **Seuil d'alerte** | `alert_threshold` (blank → 0). |
| **Prix unitaire** | `unit_price` (blank → 0). |
| **Fournisseur** | matched to a `Supplier` by name; auto-created if unknown; blank → none. |

## Behaviour

- `POST /api/farms/{farmId}/stock-items/import-xlsx/` — Admin / Farm Manager / Farmer. Returns
  `{updated, created, skipped:[{line, reason}]}`.
- **Match by Article name** → update only the parameter fields via `StockItemSerializer`
  (`partial=True`). No quantity field on that serializer ⇒ stock level / `StockMovement`
  history is untouched. **This import creates no `StockMovement`.**
- **No match** → new `StockItem` (`item_code` from `next_free_item_code`).
- **Never deletes** an item not named in the file. One bad row is skipped + reported.

---

# Import Employés — mise à jour ou création par email

**"Importer un fichier Excel"** + **"Télécharger un modèle"** on `/dashboard/employees`.
Update-or-create, **never deletes, never resets an existing account's password.**

## Columns (`modele-employes.xlsx`)

| Header | Notes |
|---|---|
| **Nom** | `User.name`. Required. |
| **Email** | the **matching key** (case-insensitive exact, within the farm). Required. |
| **Rôle** | enum value (`FARMER`) or French label (`Fermier`, `Ouvrier`, `Technicien`, `Caissier`, `Gérant de ferme`, `Administrateur secondaire`). **`ADMIN` rejected.** An unrecognised value skips the row with a specific reason — never guessed. |
| **Civilité** | `M.`/`M`/`Monsieur` → M ; `Mme`/`Madame` → MME ; blank → M. |
| **Taux horaire** | optional `User.hourly_rate` (applied like `EmployeeHourlyRateView`). |

## Behaviour

- `POST /api/employees/import-xlsx/` — Admin / Secondary Admin. Returns
  `{updated, created, skipped:[{line, reason}], newAccounts:[{line, name, email, password}]}`.
- **Match by Email** → update Nom / Rôle / Civilité / Taux horaire via `EmployeeSerializer`
  (`partial=True`). **No password column read for a match** — an existing account is never
  locked out. On a role change the class-table-inheritance subtype row is swapped via the
  existing `ROLE_PROFILE_MODELS` / `create_role_profile`.
- **No match** → new account via `EmployeeSerializer` with a **generated temporary password**
  (`secrets.token_urlsafe(9)`), returned **once** in `newAccounts` and shown in the summary for
  the admin to hand off. Never stored in plaintext or logged.
- **Never deletes** a user absent from the file.

## Shared decisions (Stock + Employees, autonomous mode)

1. **Update-or-create, per-row atomic** — a failing row is skipped + reported, the rest apply.
2. **Reuses `StockItemSerializer` / `EmployeeSerializer`** and the existing category / supplier
   / role-profile helpers — no parallel validation.
3. Shared spreadsheet plumbing in `apps/core/xlsx.py`; per-feature rules in
   `apps/stock/xlsx_import.py` and `apps/core/employee_xlsx_import.py`.
4. Both endpoints write to the DB immediately and are non-destructive (no delete, no
   quantity/password change) — so, unlike the Protocol import, **no confirm dialog**.
5. Both templates are `AllowAny` (static content) → plain download links.
