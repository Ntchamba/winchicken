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
