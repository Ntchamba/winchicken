import { useState } from "react";
import { Plus, Pencil, Trash2, Loader2, Check, X } from "lucide-react";
import { stockApi } from "../api/endpoints";
import { getServerErrorMessage } from "../api/errors";
import { useAuth } from "../context/AuthContext";
import "./table-wrap.css";

const CAN_MANAGE = new Set(["ADMIN", "FARM_MANAGER", "FARMER"]);
const emptyDraft = { name: "", contact: "", email: "" };

/**
 * "Fournisseurs" section of the Stock dashboard — every Supplier for the farm with the items it
 * supplies (derived server-side from StockItem.supplier). Basic add/edit/delete for
 * Administrateur / Gérant de ferme / Fermier, consistent with who manages stock parameters.
 *
 * @param {{id, name, contact, email, item_names: string[]}[]} suppliers
 * @param {number} farmId
 * @param {() => void} onChanged - refetch trigger after any write.
 */
export default function SuppliersSection({ suppliers = [], farmId, onChanged }) {
  const { user } = useAuth();
  const canManage = CAN_MANAGE.has(user?.role);
  const [adding, setAdding] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [draft, setDraft] = useState(emptyDraft);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const startAdd = () => { setDraft(emptyDraft); setEditingId(null); setAdding(true); setError(""); };
  const startEdit = (s) => {
    setDraft({ name: s.name, contact: s.contact || "", email: s.email || "" });
    setEditingId(s.id); setAdding(false); setError("");
  };
  const cancel = () => { setAdding(false); setEditingId(null); setDraft(emptyDraft); setError(""); };

  const save = async () => {
    if (!draft.name.trim()) { setError("Le nom du fournisseur est requis."); return; }
    setBusy(true);
    setError("");
    try {
      if (editingId) await stockApi.updateSupplier(editingId, draft);
      else await stockApi.addSupplier(farmId, draft);
      cancel();
      onChanged?.();
    } catch (err) {
      // The server's reason ("Saisissez une adresse e-mail valide.") — not a generic failure.
      setError(getServerErrorMessage(err, "Impossible d'enregistrer le fournisseur."));
    } finally {
      setBusy(false);
    }
  };

  const remove = async (id) => {
    if (busy) return;
    setError("");
    setBusy(true);
    try {
      await stockApi.removeSupplier(id);
      onChanged?.();
    } catch (err) {
      // A supplier still referenced by a stock item comes back as a PROTECT/409 from the API;
      // the row stays either way, so the reason has to be said out loud.
      setError(getServerErrorMessage(err, "Ce fournisseur n'a pas pu être supprimé."));
    } finally {
      setBusy(false);
    }
  };

  const rows = suppliers.results || suppliers;

  return (
    <div className="card schedule-card" style={{ marginBottom: 18 }}>
      <div className="section-row" style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <h2>Fournisseurs</h2>
        {canManage && !adding && editingId === null && (
          <button className="add-button" style={{ marginTop: 0 }} onClick={startAdd} type="button">
            <Plus size={14} strokeWidth={2.5} /> Nouveau fournisseur
          </button>
        )}
      </div>

      {(adding || editingId !== null) && (
        <div className="schedule-row" style={{ gridTemplateColumns: "1fr 1fr 1fr auto", gap: 10, marginBottom: 12 }}>
          <input placeholder="Nom" value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} autoFocus />
          <input placeholder="Téléphone" value={draft.contact} onChange={(e) => setDraft({ ...draft, contact: e.target.value })} />
          <input placeholder="Email" value={draft.email} onChange={(e) => setDraft({ ...draft, email: e.target.value })} />
          <span style={{ display: "inline-flex", gap: 4 }}>
            <button type="button" className="icon-button" onClick={save} aria-label="Enregistrer" disabled={busy}>
              {busy ? <Loader2 size={14} className="spin" /> : <Check size={14} strokeWidth={2.2} />}
            </button>
            <button type="button" className="icon-button" onClick={cancel} aria-label="Annuler"><X size={14} strokeWidth={2.2} /></button>
          </span>
        </div>
      )}
      {error && <p className="field-error" style={{ margin: "0 0 10px" }}>{error}</p>}

      {rows.length === 0 && !adding ? (
        <p className="empty-state">Aucun fournisseur pour le moment.</p>
      ) : (
        <div className="table-wrap">
          <table className="help-example-table" style={{ width: "100%" }}>
            <thead>
              <tr>
                <th>Nom</th><th>Téléphone</th><th>Email</th><th>Articles fournis</th>
                {canManage && <th />}
              </tr>
            </thead>
            <tbody>
              {rows.map((s) => (
                <tr key={s.id}>
                  <td>{s.name}</td>
                  <td>{s.contact || "—"}</td>
                  <td>{s.email || "—"}</td>
                  <td>{s.item_names && s.item_names.length ? s.item_names.join(", ") : "—"}</td>
                  {canManage && (
                    <td style={{ whiteSpace: "nowrap" }}>
                      <button className="icon-button" onClick={() => startEdit(s)} aria-label={`Modifier ${s.name}`}>
                        <Pencil size={13} strokeWidth={2} />
                      </button>
                      <button className="icon-button" onClick={() => remove(s.id)} aria-label={`Supprimer ${s.name}`} disabled={busy}>
                        <Trash2 size={13} strokeWidth={2} />
                      </button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
