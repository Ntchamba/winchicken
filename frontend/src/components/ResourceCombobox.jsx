import { useEffect, useRef, useState } from "react";
import { Check, Loader2, Plus, X } from "lucide-react";

/**
 * "Ressource" selector for a protocol row's Consommation section — type to filter existing
 * `StockItem` names, or, when what's typed matches nothing, one click on
 * "+ Créer '{typed}' comme nouvel article de stock" creates it and links the row.
 *
 * @param {{item_code: string, name: string, unit?: string}[]} items
 * @param {string|null} value - linked item_code
 * @param {(code: string|null) => void} onSelect
 * @param {(name: string) => Promise<{item_code: string}>} [onCreate] - omit to disable inline
 *   creation (read-only / demo); the field then behaves as a plain filterable picker.
 * @param {boolean} [disabled]
 */
export default function ResourceCombobox({ items = [], value = null, onSelect, onCreate, disabled }) {
  const selected = items.find((i) => i.item_code === value) || null;
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const blurTimer = useRef(null);

  useEffect(() => () => clearTimeout(blurTimer.current), []);

  const shown = selected && !open ? selected.name : query;
  const q = query.trim().toLowerCase();
  const matches = q ? items.filter((i) => i.name.toLowerCase().includes(q)) : items;
  const exact = items.some((i) => i.name.trim().toLowerCase() === q);
  const canCreate = !!onCreate && q.length > 0 && !exact;

  const pick = (item) => {
    onSelect(item.item_code);
    setQuery("");
    setOpen(false);
    setError("");
  };

  const create = async () => {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      const created = await onCreate(query.trim());
      onSelect(created.item_code);
      setQuery("");
      setOpen(false);
    } catch {
      setError("Impossible de créer l'article.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <span style={{ position: "relative", display: "inline-flex", alignItems: "center", gap: 4, minWidth: 220 }}>
      <input
        type="text"
        aria-label="Article de stock consommé"
        placeholder="Aucun article de stock consommé"
        value={shown}
        disabled={disabled}
        onFocus={() => setOpen(true)}
        onChange={(e) => { setQuery(e.target.value); setOpen(true); if (selected) onSelect(null); }}
        onKeyDown={(e) => {
          if (e.key === "Enter" && canCreate) { e.preventDefault(); create(); }
          if (e.key === "Escape") setOpen(false);
        }}
        onBlur={() => { blurTimer.current = setTimeout(() => setOpen(false), 150); }}
        style={{ width: 220 }}
      />
      {value && (
        <button type="button" className="icon-button" aria-label="Retirer l'article" onClick={() => { onSelect(null); setQuery(""); }}>
          <X size={13} strokeWidth={2.2} />
        </button>
      )}
      {open && !disabled && (matches.length > 0 || canCreate) && (
        <ul
          style={{
            position: "absolute", top: "calc(100% + 2px)", left: 0, zIndex: 30, margin: 0, padding: 4,
            listStyle: "none", minWidth: 260, maxHeight: 220, overflowY: "auto",
            background: "#fff", border: "1px solid var(--line)", borderRadius: 10,
            boxShadow: "0 10px 30px rgba(15,40,33,.14)",
          }}
        >
          {matches.map((i) => (
            <li key={i.item_code}>
              <button
                type="button"
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => pick(i)}
                style={{ display: "flex", width: "100%", gap: 8, alignItems: "center", padding: "7px 9px", border: 0, background: "none", cursor: "pointer", fontSize: 13, textAlign: "left" }}
              >
                {i.item_code === value && <Check size={13} strokeWidth={2.4} />}
                <span>{i.name}{i.unit ? ` (${i.unit})` : ""}</span>
              </button>
            </li>
          ))}
          {canCreate && (
            <li>
              <button
                type="button"
                onMouseDown={(e) => e.preventDefault()}
                onClick={create}
                disabled={busy}
                style={{ display: "flex", width: "100%", gap: 8, alignItems: "center", padding: "7px 9px", border: 0, borderTop: matches.length ? "1px solid var(--line)" : 0, background: "none", cursor: "pointer", fontSize: 13, color: "var(--mint)", fontWeight: 700, textAlign: "left" }}
              >
                {busy ? <Loader2 size={13} className="spin" /> : <Plus size={13} strokeWidth={2.6} />}
                Créer «&nbsp;{query.trim()}&nbsp;» comme nouvel article de stock
              </button>
            </li>
          )}
        </ul>
      )}
      {error && <span className="field-error" style={{ margin: 0, fontSize: 11 }}>{error}</span>}
    </span>
  );
}
