import { useState } from "react";
import { Plus, Loader2, Check, X } from "lucide-react";
import { stockApi } from "../api/endpoints";
import { useAuth } from "../context/AuthContext";

const CAN_MANAGE = new Set(["ADMIN", "FARM_MANAGER", "FARMER"]);
const today = () => new Date().toISOString().slice(0, 10);
const emptyDraft = () => ({ quantity: "", date: today(), note: "", totalPrice: "", priceTouched: false });

/**
 * "Niveaux de stock" section of the Stock dashboard — current on-hand quantity per item, with a
 * manual "Ajouter du stock" action. Creates an `IN` StockMovement (no batch, no PurchaseOrder)
 * and, when "Prix total payé" is filled, a matching `Expense` in the same transaction — that
 * Expense is what makes the purchase show up in Finances → Achats / Globale.
 *
 * @param {{item_code, name, unit, current_quantity, alert_threshold, unit_price?}[]} items
 * @param {() => void} onChanged - refetch trigger after a movement is created.
 */
export default function StockLevelsSection({ items = [], onChanged }) {
  const { user } = useAuth();
  const canManage = CAN_MANAGE.has(user?.role);
  const [openFor, setOpenFor] = useState(null);
  const [draft, setDraft] = useState(emptyDraft());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const open = (code) => { setOpenFor(code); setDraft(emptyDraft()); setError(""); };
  const cancel = () => { setOpenFor(null); setError(""); };

  // Suggested "Prix total payé" = quantity × the item's reference unit price, until the user
  // edits the price field themselves (it stays their number after that).
  const suggestedPrice = (item, qty) => {
    const q = Number(qty);
    const p = Number(item?.unit_price);
    return q > 0 && p > 0 ? String(Math.round(q * p * 100) / 100) : "";
  };

  const onQuantityChange = (item, value) => {
    setDraft((d) => ({
      ...d,
      quantity: value,
      totalPrice: d.priceTouched ? d.totalPrice : suggestedPrice(item, value),
    }));
  };

  const submit = async (code) => {
    const quantity = Number(draft.quantity);
    if (!quantity || quantity <= 0) { setError("La quantité doit être un nombre positif."); return; }
    if (!draft.date) { setError("La date est requise."); return; }
    if (draft.totalPrice !== "" && Number(draft.totalPrice) < 0) { setError("Le prix total doit être positif."); return; }
    setBusy(true);
    setError("");
    try {
      await stockApi.addMovement({
        item: code,
        movement_type: "IN",
        quantity,
        movement_date: draft.date,
        note: draft.note.trim(),
        ...(draft.totalPrice !== "" ? { total_price: Number(draft.totalPrice) } : {}),
      });
      cancel();
      onChanged?.();
    } catch {
      setError("Impossible d'ajouter le stock. Réessayez.");
    } finally {
      setBusy(false);
    }
  };

  if (items.length === 0) {
    return (
      <div className="card schedule-card" style={{ marginBottom: 18 }}>
        <div className="section-row"><h2>Niveaux de stock</h2></div>
        <p className="empty-state">Aucun article de stock. Ajoutez-en via « Mettre à jour le stock ».</p>
      </div>
    );
  }

  return (
    <div className="card schedule-card" style={{ marginBottom: 18 }}>
      <div className="section-row"><h2>Niveaux de stock</h2></div>
      <div className="table-wrap">
        <table className="help-example-table" style={{ width: "100%" }}>
          <thead>
            <tr>
              <th>Article</th><th>Stock actuel</th>{canManage && <th />}
            </tr>
          </thead>
          <tbody>
            {items.flatMap((it) => {
              const low = it.current_quantity <= it.alert_threshold;
              return [
                <tr key={it.item_code}>
                  <td>{it.name}</td>
                  <td style={low ? { color: "var(--danger)", fontWeight: 700 } : undefined}>
                    {it.current_quantity} {it.unit}
                    {low && " · sous le seuil"}
                  </td>
                  {canManage && (
                    <td style={{ whiteSpace: "nowrap", textAlign: "right" }}>
                      <button
                        className="add-button"
                        style={{ marginTop: 0, padding: "6px 10px", fontSize: 12 }}
                        onClick={() => (openFor === it.item_code ? cancel() : open(it.item_code))}
                        type="button"
                      >
                        <Plus size={13} strokeWidth={2.5} /> Ajouter du stock
                      </button>
                    </td>
                  )}
                </tr>,
                openFor === it.item_code && (
                  <tr key={`${it.item_code}-form`}>
                    <td colSpan={canManage ? 3 : 2}>
                      <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8, padding: "4px 0" }}>
                        <input
                          type="number" min="0" step="any" autoFocus
                          placeholder={it.unit ? `Quantité (${it.unit})` : "Quantité"}
                          aria-label={it.unit ? `Quantité à ajouter (${it.unit})` : "Quantité à ajouter"}
                          value={draft.quantity}
                          onChange={(e) => onQuantityChange(it, e.target.value)}
                          style={{ width: 150 }}
                        />
                        <input
                          type="date"
                          aria-label="Date"
                          value={draft.date}
                          onChange={(e) => setDraft({ ...draft, date: e.target.value })}
                          style={{ width: 160 }}
                        />
                        <input
                          type="number" min="0" step="any"
                          placeholder="Prix total payé"
                          aria-label="Prix total payé"
                          title={Number(it.unit_price) > 0 ? `Prix de référence : ${it.unit_price} / ${it.unit || "unité"}` : undefined}
                          value={draft.totalPrice}
                          onChange={(e) => setDraft({ ...draft, totalPrice: e.target.value, priceTouched: true })}
                          style={{ width: 150 }}
                        />
                        <input
                          type="text"
                          placeholder="Note (facultatif)"
                          aria-label="Note"
                          value={draft.note}
                          onChange={(e) => setDraft({ ...draft, note: e.target.value })}
                          style={{ flex: "1 1 160px", minWidth: 140 }}
                        />
                        <button type="button" className="icon-button" onClick={() => submit(it.item_code)} aria-label="Ajouter" disabled={busy}>
                          {busy ? <Loader2 size={14} className="spin" /> : <Check size={14} strokeWidth={2.2} />}
                        </button>
                        <button type="button" className="icon-button" onClick={cancel} aria-label="Annuler">
                          <X size={14} strokeWidth={2.2} />
                        </button>
                      </div>
                      {error && <p className="field-error" style={{ margin: "4px 0 0" }}>{error}</p>}
                    </td>
                  </tr>
                ),
              ].filter(Boolean);
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
