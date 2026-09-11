import { useEffect, useState } from "react";
import { Loader2, Receipt, Wallet2 } from "lucide-react";
import { financeApi } from "../../api/endpoints";
import ReceiptModal from "../../components/ReceiptModal";
import useDocumentTitle from "../../hooks/useDocumentTitle";
import { formatMoney } from "../../utils/money";
import QuickLinksBar from "../../components/QuickLinksBar";

const PRODUCT_TYPES = [
  { value: "BIRD", label: "Volaille" },
  { value: "EGG", label: "Œufs" },
  { value: "CULL", label: "Réforme" },
  { value: "MANURE", label: "Fumier" },
];

const EMPTY_FORM = { productType: "BIRD", quantity: "", unitPrice: "", customer: "" };

// LABOR deliberately excluded — that category is system-generated only, created when a
// SalaryPayment is marked paid (see SalaryPaymentPayView), never entered by hand here
// (2026-08-27, Finances restructure Part C).
const EXPENSE_CATEGORIES = [
  { value: "FEED", label: "Aliment" },
  { value: "VETERINARY", label: "Vétérinaire" },
  { value: "DEPRECIATION", label: "Amortissement" },
  { value: "MISC", label: "Divers" },
];

const EMPTY_EXPENSE_FORM = { category: "FEED", amount: "", supplier: "" };

export default function CashierPage() {
  useDocumentTitle("Caissier");
  const [sales, setSales] = useState([]);
  const [form, setForm] = useState(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [receiptSale, setReceiptSale] = useState(null);
  const [expenseForm, setExpenseForm] = useState(EMPTY_EXPENSE_FORM);
  const [savingExpense, setSavingExpense] = useState(false);
  const [expenseSaved, setExpenseSaved] = useState(false);

  const load = () => financeApi.sales().then(({ data }) => setSales(data.results || data));

  useEffect(() => { load(); }, []);

  const total = (Number(form.quantity) || 0) * (Number(form.unitPrice) || 0);

  const today = new Date().toISOString().slice(0, 10);
  const todaySales = sales.filter((s) => s.sale_date === today);
  // Every Sale row already recorded today by any cashier (financeApi.sales() is farm-scoped,
  // not filtered by the logged-in cashier) — "Ventes du jour" is deliberately farm-wide, not
  // per-user, per the task's own wording ("every Sale recorded today by any cashier").
  const todayTotal = todaySales.reduce((sum, s) => sum + Number(s.total_amount), 0);

  const submit = async () => {
    if (!form.quantity || !form.unitPrice) return;
    setSaving(true);
    try {
      await financeApi.addSale({
        product_type: form.productType,
        quantity: Number(form.quantity),
        unit_price: Number(form.unitPrice),
        sale_date: today,
        customer: form.customer,
      });
      setForm(EMPTY_FORM);
      load();
    } finally {
      setSaving(false);
    }
  };

  const submitExpense = async () => {
    if (!expenseForm.amount) return;
    setSavingExpense(true);
    setExpenseSaved(false);
    try {
      await financeApi.addExpense({
        category: expenseForm.category,
        amount: Number(expenseForm.amount),
        expense_date: today,
        supplier: expenseForm.supplier,
      });
      setExpenseForm(EMPTY_EXPENSE_FORM);
      setExpenseSaved(true);
    } finally {
      setSavingExpense(false);
    }
  };

  return (
    <div className="page-wrap">
      <QuickLinksBar />
      <div className="brand-row">
        <span className="brand-mark"><Wallet2 size={20} strokeWidth={1.8} /></span>
        <div>
          <p className="eyebrow">WINCHICKEN</p>
          <p className="brand-subtitle">Caissier</p>
        </div>
      </div>

      <div className="card house-card" style={{ marginTop: 18 }}>
        <div className="detail-grid">
          <label className="field">
            <span>Produit</span>
            <select value={form.productType} onChange={(e) => setForm({ ...form, productType: e.target.value })}>
              {PRODUCT_TYPES.map((p) => <option key={p.value} value={p.value}>{p.label}</option>)}
            </select>
          </label>
          <label className="field">
            <span>Quantité</span>
            <input type="number" value={form.quantity} onChange={(e) => setForm({ ...form, quantity: e.target.value })} />
          </label>
          <label className="field">
            <span>Prix unitaire</span>
            <input type="number" value={form.unitPrice} onChange={(e) => setForm({ ...form, unitPrice: e.target.value })} />
          </label>
        </div>
        <label className="field" style={{ marginTop: 14 }}>
          <span>Client</span>
          <input value={form.customer} onChange={(e) => setForm({ ...form, customer: e.target.value })} placeholder="Facultatif" />
        </label>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginTop: 16 }}>
          <p style={{ margin: 0, fontFamily: "'Space Grotesk',sans-serif", fontSize: 20 }}>Total : {formatMoney(total)}</p>
          <button className="save-button" onClick={submit} disabled={saving}>
            {saving ? <Loader2 size={16} className="spin" /> : "Enregistrer la vente"}
          </button>
        </div>
      </div>

      <div className="section-row" style={{ marginTop: 26 }}><h2>Enregistrer une dépense</h2></div>
      <div className="card house-card">
        <div className="detail-grid">
          <label className="field">
            <span>Catégorie</span>
            <select value={expenseForm.category} onChange={(e) => setExpenseForm({ ...expenseForm, category: e.target.value })}>
              {EXPENSE_CATEGORIES.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
            </select>
          </label>
          <label className="field">
            <span>Montant</span>
            <input type="number" value={expenseForm.amount} onChange={(e) => setExpenseForm({ ...expenseForm, amount: e.target.value })} />
          </label>
          <label className="field">
            <span>Fournisseur</span>
            <input value={expenseForm.supplier} onChange={(e) => setExpenseForm({ ...expenseForm, supplier: e.target.value })} placeholder="Facultatif" />
          </label>
        </div>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "flex-end", gap: 14, marginTop: 16 }}>
          {expenseSaved && <p style={{ margin: 0, color: "var(--mint)", fontSize: 13 }}>Dépense enregistrée.</p>}
          <button className="save-button" onClick={submitExpense} disabled={savingExpense}>
            {savingExpense ? <Loader2 size={16} className="spin" /> : "Enregistrer la dépense"}
          </button>
        </div>
      </div>

      <div className="section-row" style={{ marginTop: 26 }}><h2>Ventes du jour</h2></div>
      {todaySales.length === 0 ? (
        <p className="empty-state">Aucune vente enregistrée aujourd'hui.</p>
      ) : (
        <table className="data-table">
          <thead>
            <tr><th>Produit</th><th>Qté</th><th>Prix unitaire</th><th>Total</th><th>Client</th><th></th></tr>
          </thead>
          <tbody>
            {todaySales.map((s) => (
              <tr key={s.id}>
                <td>{PRODUCT_TYPES.find((p) => p.value === s.product_type)?.label || s.product_type}</td>
                <td>{s.quantity}</td>
                <td>{s.unit_price}</td>
                <td className="amount in">{s.total_amount}</td>
                <td>{s.customer || "—"}</td>
                <td>
                  <button className="icon-button" title="Reçu" onClick={() => setReceiptSale(s)}>
                    <Receipt size={15} strokeWidth={1.8} />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr>
              <td colSpan={3} style={{ fontWeight: 700, borderTop: "2px solid #10242c" }}>Total du jour</td>
              <td className="amount in" style={{ fontWeight: 700, borderTop: "2px solid #10242c" }}>{formatMoney(todayTotal)}</td>
              <td style={{ borderTop: "2px solid #10242c" }} colSpan={2}></td>
            </tr>
          </tfoot>
        </table>
      )}

      <ReceiptModal sale={receiptSale} onClose={() => setReceiptSale(null)} />
    </div>
  );
}
