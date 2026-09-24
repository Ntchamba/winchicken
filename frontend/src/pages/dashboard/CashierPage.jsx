import { useCallback, useEffect, useRef, useState } from "react";
import { Loader2, Receipt, Wallet2 } from "lucide-react";
import { financeApi } from "../../api/endpoints";
import { fetchAllPages } from "../../api/pagination";
import ReceiptModal from "../../components/ReceiptModal";
import useDocumentTitle from "../../hooks/useDocumentTitle";
import { formatMoney } from "../../utils/money";
import QuickLinksBar from "../../components/QuickLinksBar";
import { getServerErrorMessage } from "../../api/errors";
import { useTodayISO } from "../../hooks/useTodayISO";

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

/**
 * The cashier's screen. Everything recorded here is money, which is why it gets the FIX 6
 * treatment in full (FIX 8, group 1): both forms are real `<form onSubmit>` elements so the
 * phone keyboard's "Go" key works, both say when a save is running, both confirm what was
 * recorded, and both surface the server's own error instead of failing silently. A sale that
 * vanishes with no trace is money nobody can reconcile — "rien ne s'est passé" and "c'est
 * enregistré" must never look the same.
 *
 * `useTodayISO()` rather than a render-time `todayISO()`: this page stays open all day on a
 * phone, and the date it stamps on a sale has to be the farm-local day *now*, not the day the
 * screen happened to render (FIX 2.6).
 */
export default function CashierPage() {
  useDocumentTitle("Caissier");
  const [sales, setSales] = useState([]);
  const [form, setForm] = useState(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState("");
  const [receiptSale, setReceiptSale] = useState(null);
  const [expenseForm, setExpenseForm] = useState(EMPTY_EXPENSE_FORM);
  const [savingExpense, setSavingExpense] = useState(false);
  // Belt to `saving`'s braces. `saving` is React state, so it only blocks a second submit once
  // the update has flushed — three programmatic clicks inside one JavaScript tick got past it
  // and wrote three Sale rows (found by the FIX 8 verification pass). No human or touch device
  // can do that, but this is money, and a ref flips synchronously, so the window closes.
  const inFlight = useRef(false);
  const expenseInFlight = useRef(false);
  const [expenseError, setExpenseError] = useState("");
  const [expenseSaved, setExpenseSaved] = useState("");

  const today = useTodayISO();

  // Caught like EmployeesPage's: the sale can be recorded and this refresh still fail, which
  // would leave the row out of "Ventes du jour" and read exactly like a lost sale.
  // The day's sales, every page: summing today's rows out of page 1 of every sale (20 rows)
  // left "Total du jour" short from the 21st sale. Reloaded when the farm's day turns.
  const load = useCallback(
    () =>
      fetchAllPages(financeApi.sales, { sale_date: today })
        .then(setSales)
        .catch((err) => setError(getServerErrorMessage(err, "La liste des ventes n'a pas pu être rechargée."))),
    [today],
  );

  useEffect(() => { load(); }, [load]);

  const total = (Number(form.quantity) || 0) * (Number(form.unitPrice) || 0);

  const todaySales = sales.filter((s) => s.sale_date === today);
  // Every Sale row already recorded today by any cashier (financeApi.sales() is farm-scoped,
  // not filtered by the logged-in cashier) — "Ventes du jour" is deliberately farm-wide, not
  // per-user, per the task's own wording ("every Sale recorded today by any cashier").
  const todayTotal = todaySales.reduce((sum, s) => sum + Number(s.total_amount), 0);

  const submit = async (event) => {
    event?.preventDefault();
    if (saving || inFlight.current) return;
    setError("");
    setSaved("");
    // Was a bare `return`: tapping "Enregistrer la vente" with a field empty did nothing at
    // all, which on a phone is indistinguishable from a dead button.
    if (!form.quantity || !form.unitPrice) {
      setError("Renseignez la quantité et le prix unitaire avant d'enregistrer.");
      return;
    }
    inFlight.current = true;
    setSaving(true);
    const recorded = { total, label: PRODUCT_TYPES.find((p) => p.value === form.productType)?.label };
    try {
      await financeApi.addSale({
        product_type: form.productType,
        quantity: Number(form.quantity),
        unit_price: Number(form.unitPrice),
        sale_date: today,
        customer: form.customer,
      });
      setSaved(`Vente enregistrée : ${recorded.label} — ${formatMoney(recorded.total)}.`);
      setForm(EMPTY_FORM);
      await load();
    } catch (err) {
      // The form keeps what was typed: the cashier re-taps rather than re-enters the sale.
      setError(getServerErrorMessage(err, "La vente n'a pas été enregistrée. Réessayez."));
    } finally {
      inFlight.current = false;
      setSaving(false);
    }
  };

  const submitExpense = async (event) => {
    event?.preventDefault();
    if (savingExpense || expenseInFlight.current) return;
    setExpenseError("");
    setExpenseSaved("");
    if (!expenseForm.amount) {
      setExpenseError("Renseignez le montant avant d'enregistrer.");
      return;
    }
    expenseInFlight.current = true;
    setSavingExpense(true);
    const recorded = {
      amount: Number(expenseForm.amount),
      label: EXPENSE_CATEGORIES.find((c) => c.value === expenseForm.category)?.label,
    };
    try {
      await financeApi.addExpense({
        category: expenseForm.category,
        amount: recorded.amount,
        expense_date: today,
        supplier: expenseForm.supplier,
      });
      // Nothing on this page lists expenses, so this line is the *only* evidence the entry
      // exists — it has to say what was recorded, not just that something was.
      setExpenseSaved(`Dépense enregistrée : ${recorded.label} — ${formatMoney(recorded.amount)}.`);
      setExpenseForm(EMPTY_EXPENSE_FORM);
    } catch (err) {
      setExpenseError(getServerErrorMessage(err, "La dépense n'a pas été enregistrée. Réessayez."));
    } finally {
      expenseInFlight.current = false;
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

      <form className="card house-card" style={{ marginTop: 18 }} onSubmit={submit}>
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
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 14, marginTop: 16, flexWrap: "wrap" }}>
          <p style={{ margin: 0, fontFamily: "'Space Grotesk',sans-serif", fontSize: 20 }}>Total : {formatMoney(total)}</p>
          <button type="submit" className="save-button" disabled={saving}>
            {saving ? <><Loader2 size={16} className="spin" /> Enregistrement…</> : "Enregistrer la vente"}
          </button>
        </div>
        {error && <p className="field-error" style={{ marginBottom: 0 }} role="alert">{error}</p>}
        {saved && <p className="save-message success" style={{ marginBottom: 0 }}>{saved}</p>}
      </form>

      <div className="section-row" style={{ marginTop: 26 }}><h2>Enregistrer une dépense</h2></div>
      <form className="card house-card" onSubmit={submitExpense}>
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
        <div style={{ display: "flex", alignItems: "center", justifyContent: "flex-end", gap: 14, marginTop: 16, flexWrap: "wrap" }}>
          {expenseSaved && <p className="save-message success" style={{ margin: 0 }}>{expenseSaved}</p>}
          <button type="submit" className="save-button" disabled={savingExpense}>
            {savingExpense ? <><Loader2 size={16} className="spin" /> Enregistrement…</> : "Enregistrer la dépense"}
          </button>
        </div>
        {expenseError && <p className="field-error" style={{ marginBottom: 0 }} role="alert">{expenseError}</p>}
      </form>

      <div className="section-row" style={{ marginTop: 26 }}><h2>Ventes du jour</h2></div>
      {todaySales.length === 0 ? (
        <p className="empty-state">Aucune vente enregistrée aujourd'hui.</p>
      ) : (
        <table className="data-table stacked">
          <thead>
            <tr><th>Produit</th><th>Qté</th><th>Prix unitaire</th><th>Total</th><th>Client</th><th></th></tr>
          </thead>
          <tbody>
            {todaySales.map((s) => (
              <tr key={s.id}>
                <td data-label="Produit">{PRODUCT_TYPES.find((p) => p.value === s.product_type)?.label || s.product_type}</td>
                <td data-label="Qté">{s.quantity}</td>
                <td data-label="Prix unitaire">{s.unit_price}</td>
                <td className="amount in" data-label="Total">{s.total_amount}</td>
                <td data-label="Client">{s.customer || "—"}</td>
                <td>
                  <button className="icon-button" title="Reçu" onClick={() => setReceiptSale(s)}>
                    <Receipt size={15} strokeWidth={1.8} />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            {/* The rule above this row was three inline borderTops, which an inline style makes
                impossible to drop when the row becomes a card on a phone. It is a class now. */}
            <tr className="table-total-row">
              <td colSpan={3}>Total du jour</td>
              <td className="amount in" data-label="Total du jour">{formatMoney(todayTotal)}</td>
              <td colSpan={2}></td>
            </tr>
          </tfoot>
        </table>
      )}

      <ReceiptModal sale={receiptSale} onClose={() => setReceiptSale(null)} />
    </div>
  );
}
