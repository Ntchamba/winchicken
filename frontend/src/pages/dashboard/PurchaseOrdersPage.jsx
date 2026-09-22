import { useCallback, useEffect, useRef, useState } from "react";
import { Check, Loader2, Plus, Truck, X } from "lucide-react";
import { financeApi, stockApi } from "../../api/endpoints";
import { getServerErrorMessage } from "../../api/errors";
import { useAuth } from "../../context/AuthContext";
import useDocumentTitle from "../../hooks/useDocumentTitle";
import ConfirmDialog from "../../components/ConfirmDialog";
import "../../styles/dashboard-theme.css";
import { formatMoney } from "../../utils/money";
import QuickLinksBar from "../../components/QuickLinksBar";
import { todayISO } from "../../utils/localDate";

const STATUS_LABELS = { PENDING: "En attente", RECEIVED: "Reçue", CANCELLED: "Annulée" };
const STATUS_PILL_CLASS = { PENDING: "pending", RECEIVED: "received", CANCELLED: "cancelled" };
const CATEGORY_LABELS = { FEED: "Aliment", VETERINARY: "Vétérinaire", EQUIPMENT: "Équipement", BEDDING: "Litière" };
const CAN_MANAGE_ROLES = ["ADMIN", "FARM_MANAGER", "CASHIER"];
const EMPTY_FORM = { itemCode: "", supplier: "", quantity: "", amount: "" };


/**
 * Searchable item picker (2026-08-27) — no existing "select an existing StockItem" pattern to
 * reuse elsewhere in this app (checked, not assumed: grepped the whole frontend). Built as a
 * small self-contained combobox over the farm's already-loaded item catalog (bounded, farm-own
 * stock — no server-side search needed), reusing the dropdown-*panel* look from
 * `SidebarSearch.jsx` rather than that component itself, whose input styling is tuned for the
 * dark sidebar and would read wrong on this page's light cards.
 */
function ItemPicker({ items, value, onChange }) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  const selected = items.find((i) => i.item_code === value);

  useEffect(() => {
    function onClickOutside(e) {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    }
    document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, []);

  const filtered = query
    ? items.filter((i) => i.name.toLowerCase().includes(query.toLowerCase()))
    : items;

  return (
    <div className="item-picker" ref={ref}>
      <input
        value={open ? query : (selected?.name || "")}
        onChange={(e) => { setQuery(e.target.value); setOpen(true); onChange(""); }}
        onFocus={() => { setQuery(""); setOpen(true); }}
        placeholder="Rechercher un article…"
        autoComplete="off"
      />
      {open && (
        <div className="item-picker-dropdown">
          {filtered.length === 0 && <p className="item-picker-empty">Aucun article ne correspond.</p>}
          {filtered.map((i) => (
            <button
              key={i.item_code}
              type="button"
              className="item-picker-result"
              onClick={() => { onChange(i.item_code); setOpen(false); setQuery(""); }}
            >
              {i.name}
              <span>{CATEGORY_LABELS[i.category] || i.category} · {i.item_code}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export default function PurchaseOrdersPage() {
  useDocumentTitle("Commandes fournisseurs");
  const { user } = useAuth();
  const canManage = CAN_MANAGE_ROLES.includes(user.role);

  const [items, setItems] = useState([]);
  const [orders, setOrders] = useState({ count: 0, results: [] });
  const [page, setPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("");
  const [loading, setLoading] = useState(true);

  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState(EMPTY_FORM);
  const [formError, setFormError] = useState("");
  const [saving, setSaving] = useState(false);

  const [receivingOrder, setReceivingOrder] = useState(null);
  const [supplierBatchNumber, setSupplierBatchNumber] = useState("");
  const [cancellingOrder, setCancellingOrder] = useState(null);
  const [actionBusy, setActionBusy] = useState(false);
  const [actionError, setActionError] = useState("");

  useEffect(() => {
    stockApi.items(user.farm).then(({ data }) => setItems(data.items || []));
  }, [user.farm]);

  const loadOrders = useCallback(() => {
    setLoading(true);
    financeApi.purchaseOrders({
      page, status: statusFilter || undefined, category: categoryFilter || undefined,
    }).then(({ data }) => {
      setOrders(data.results ? data : { count: data.length, results: data });
    }).finally(() => setLoading(false));
  }, [page, statusFilter, categoryFilter]);

  useEffect(() => { loadOrders(); }, [loadOrders]);

  const pageSize = 20;
  const totalPages = Math.max(1, Math.ceil(orders.count / pageSize));

  const submitOrder = async (e) => {
    e.preventDefault();
    if (!form.itemCode || !form.supplier || !form.quantity || !form.amount) {
      setFormError("Article, fournisseur, quantité et montant sont obligatoires.");
      return;
    }
    setFormError("");
    setSaving(true);
    try {
      await financeApi.addPurchaseOrder({
        item: form.itemCode, supplier: form.supplier, quantity: Number(form.quantity), amount: form.amount,
      });
      setForm(EMPTY_FORM);
      setShowForm(false);
      setPage(1);
      loadOrders();
    } catch (err) {
      setFormError(getServerErrorMessage(err, "Impossible d'enregistrer la commande."));
    } finally {
      setSaving(false);
    }
  };

  const confirmReceive = async () => {
    setActionBusy(true);
    setActionError("");
    try {
      await financeApi.receivePurchaseOrder(receivingOrder.order_code, supplierBatchNumber.trim());
      setReceivingOrder(null);
      setSupplierBatchNumber("");
      loadOrders();
    } catch (err) {
      setActionError(getServerErrorMessage(err, "Impossible de marquer cette commande comme reçue."));
    } finally {
      setActionBusy(false);
    }
  };

  const confirmCancel = async () => {
    if (actionBusy) return;
    const orderCode = cancellingOrder.order_code;
    setActionError("");
    setActionBusy(true);
    try {
      await financeApi.cancelPurchaseOrder(orderCode);
      setCancellingOrder(null);
      await loadOrders();
    } catch (err) {
      // Same treatment as the "marquer comme reçue" handler right above: the order stays in
      // the list either way, so silence here is indistinguishable from a cancel that worked.
      setActionError(getServerErrorMessage(err, `La commande ${orderCode} n'a pas pu être annulée.`));
    } finally {
      setActionBusy(false);
    }
  };

  return (
    <div className="page-wrap">
      <QuickLinksBar />
      <div className="brand-row">
        <span className="brand-mark"><Truck size={20} strokeWidth={1.8} /></span>
        <div>
          <p className="eyebrow">WINCHICKEN</p>
          <p className="brand-subtitle">Commandes fournisseurs</p>
        </div>
      </div>

      {canManage && (
        <div className="card house-card" style={{ marginTop: 18, marginBottom: 18 }}>
          {showForm ? (
            <form onSubmit={submitOrder}>
              <div className="detail-grid">
                <label className="field">
                  <span>Article</span>
                  <ItemPicker items={items} value={form.itemCode} onChange={(itemCode) => setForm({ ...form, itemCode })} />
                </label>
                <label className="field">
                  <span>Fournisseur</span>
                  <input value={form.supplier} onChange={(e) => setForm({ ...form, supplier: e.target.value })} />
                </label>
                <label className="field">
                  <span>Quantité</span>
                  <input type="number" min="0" step="any" value={form.quantity} onChange={(e) => setForm({ ...form, quantity: e.target.value })} />
                </label>
              </div>
              <div className="detail-grid" style={{ marginTop: 14 }}>
                <label className="field">
                  <span>Montant</span>
                  <input type="number" min="0" step="0.01" value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })} />
                </label>
                <label className="field">
                  <span>Date de commande</span>
                  {/* Always today's date server-side (PurchaseOrder.order_date is auto_now_add
                      at the model level — pre-existing, unchanged per this task's own "no schema
                      change" rule) — shown for clarity, genuinely not editable; see
                      docs/deviations.md for why this can't honor the task's "editable" wording. */}
                  <input value={todayISO()} disabled />
                </label>
              </div>
              {formError && <p className="field-error" style={{ marginTop: 8 }}>{formError}</p>}
              <div style={{ display: "flex", gap: 10, marginTop: 16 }}>
                <button type="submit" className="save-button" style={{ width: "auto", padding: "0 16px" }} disabled={saving}>
                  {saving ? <Loader2 size={16} className="spin" /> : "Enregistrer la commande"}
                </button>
                <button type="button" className="add-button" style={{ marginTop: 0 }} onClick={() => { setShowForm(false); setForm(EMPTY_FORM); setFormError(""); }}>
                  Annuler
                </button>
              </div>
            </form>
          ) : (
            <button className="add-button" style={{ marginTop: 0 }} onClick={() => setShowForm(true)}>
              <Plus size={14} strokeWidth={2.5} />
              Nouvelle commande
            </button>
          )}
        </div>
      )}

      <div className="detail-grid" style={{ marginBottom: 16 }}>
        <label className="field">
          <span>Statut</span>
          <select value={statusFilter} onChange={(e) => { setStatusFilter(e.target.value); setPage(1); }}>
            <option value="">Tout</option>
            <option value="PENDING">En attente</option>
            <option value="RECEIVED">Reçues</option>
            <option value="CANCELLED">Annulées</option>
          </select>
        </label>
        <label className="field">
          <span>Catégorie</span>
          <select value={categoryFilter} onChange={(e) => { setCategoryFilter(e.target.value); setPage(1); }}>
            <option value="">Toutes</option>
            {Object.entries(CATEGORY_LABELS).map(([value, label]) => (
              <option key={value} value={value}>{label}</option>
            ))}
          </select>
        </label>
      </div>

      {cancellingOrder && (
        <ConfirmDialog
          message={`Annuler la commande ${cancellingOrder.order_code} (${cancellingOrder.itemName}) ? Cette action est définitive — la commande ne pourra plus être reçue ensuite.`}
          confirmLabel="Annuler la commande"
          onConfirm={confirmCancel}
          onCancel={() => setCancellingOrder(null)}
          busy={actionBusy}
        />
      )}

      {loading ? (
        <p className="empty-state">Chargement…</p>
      ) : orders.results.length === 0 ? (
        <p className="empty-state">Aucune commande pour ces filtres.</p>
      ) : (
        <>
          <table className="data-table stacked">
            <thead>
              <tr><th>Code</th><th>Article</th><th>Fournisseur</th><th>Quantité</th><th>Montant</th><th>Date</th><th>Statut</th><th></th></tr>
            </thead>
            <tbody>
              {orders.results.map((order) => (
                <tr key={order.order_code}>
                  <td data-label="Code">{order.order_code}</td>
                  <td data-label="Article">{order.itemName}</td>
                  <td data-label="Fournisseur">{order.supplier || "—"}</td>
                  <td data-label="Quantité">{order.quantity}</td>
                  <td data-label="Montant">{formatMoney(order.amount)}</td>
                  <td data-label="Date">{order.order_date}</td>
                  <td data-label="Statut"><span className={`status-pill ${STATUS_PILL_CLASS[order.status]}`}>{STATUS_LABELS[order.status] || order.status}</span></td>
                  <td>
                    {canManage && order.status === "PENDING" && (
                      <div style={{ display: "flex", gap: 6 }}>
                        <button className="add-button" style={{ marginTop: 0, padding: "6px 10px", fontSize: 12 }} onClick={() => setReceivingOrder(order)}>
                          Marquer comme reçue
                        </button>
                        <button className="delete-button" style={{ width: "auto", padding: "0 10px" }} onClick={() => setCancellingOrder(order)} aria-label="Annuler la commande">
                          <X size={14} strokeWidth={2} />
                        </button>
                      </div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {totalPages > 1 && (
            <div className="pagination">
              <button disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>Précédent</button>
              <span>Page {page} / {totalPages}</span>
              <button disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)}>Suivant</button>
            </div>
          )}
        </>
      )}

      {receivingOrder && (
        <div style={{ position: "fixed", inset: 0, zIndex: 70, display: "flex", alignItems: "center", justifyContent: "center", background: "rgba(0,0,0,.4)" }}>
          <div className="card schedule-card" style={{ width: 420, maxWidth: "90vw" }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 14 }}>
              <h2 style={{ margin: 0, fontSize: 15, fontWeight: 700, color: "#10242c" }}>Confirmer la réception</h2>
              <button onClick={() => { setReceivingOrder(null); setActionError(""); }} aria-label="Fermer" style={{ border: 0, background: "none", color: "var(--muted)", cursor: "pointer", padding: 0 }}>
                <X size={18} />
              </button>
            </div>
            <p style={{ fontSize: 13.5, color: "#374548", marginBottom: 4 }}>
              Confirmez-vous que la quantité complète de cette commande est arrivée ?
            </p>
            <p style={{ fontSize: 13.5, margin: "10px 0 16px", padding: "10px 12px", background: "var(--surface-2)", borderRadius: 10 }}>
              <strong>{receivingOrder.itemName}</strong> — {receivingOrder.quantity} unité(s) · {receivingOrder.supplier || "fournisseur non précisé"}
            </p>
            <label className="field" style={{ marginBottom: 16 }}>
              <span>Numéro de lot fournisseur (optionnel)</span>
              <input value={supplierBatchNumber} onChange={(e) => setSupplierBatchNumber(e.target.value)} placeholder="ex. LOT-2026-042" />
            </label>
            {actionError && <p className="field-error" style={{ marginBottom: 10 }}>{actionError}</p>}
            <div style={{ display: "flex", gap: 10 }}>
              <button className="save-button" style={{ width: "auto", padding: "0 16px" }} onClick={confirmReceive} disabled={actionBusy}>
                {actionBusy ? <Loader2 size={16} className="spin" /> : <><Check size={15} strokeWidth={2.2} style={{ marginRight: 6 }} />Confirmer la réception</>}
              </button>
              <button className="add-button" onClick={() => { setReceivingOrder(null); setActionError(""); }} disabled={actionBusy}>Annuler</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
