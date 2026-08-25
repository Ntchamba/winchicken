import { useEffect, useState } from "react";
import { Loader2, Wallet2 } from "lucide-react";
import { financeApi } from "../../api/endpoints";

const PRODUCT_TYPES = [
  { value: "BIRD", label: "Volaille" },
  { value: "EGG", label: "Œufs" },
  { value: "CULL", label: "Réforme" },
  { value: "MANURE", label: "Fumier" },
];

const EMPTY_FORM = { productType: "BIRD", quantity: "", unitPrice: "", customer: "" };

export default function CashierPage() {
  const [sales, setSales] = useState([]);
  const [form, setForm] = useState(EMPTY_FORM);
  const [saving, setSaving] = useState(false);

  const load = () => financeApi.sales().then(({ data }) => setSales(data.results || data));

  useEffect(() => { load(); }, []);

  const total = (Number(form.quantity) || 0) * (Number(form.unitPrice) || 0);

  const today = new Date().toISOString().slice(0, 10);
  const todaySales = sales.filter((s) => s.sale_date === today);

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

  return (
    <div className="page-wrap">
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
          <p style={{ margin: 0, fontFamily: "'Space Grotesk',sans-serif", fontSize: 20 }}>Total : {total.toLocaleString()}</p>
          <button className="save-button" onClick={submit} disabled={saving}>
            {saving ? <Loader2 size={16} className="spin" /> : "Enregistrer la vente"}
          </button>
        </div>
      </div>

      <div className="section-row" style={{ marginTop: 26 }}><h2>Ventes du jour</h2></div>
      {todaySales.length === 0 ? (
        <p className="empty-state">Aucune vente enregistrée aujourd'hui.</p>
      ) : (
        <table className="data-table">
          <thead>
            <tr><th>Produit</th><th>Qté</th><th>Prix unitaire</th><th>Total</th><th>Client</th></tr>
          </thead>
          <tbody>
            {todaySales.map((s) => (
              <tr key={s.id}>
                <td>{PRODUCT_TYPES.find((p) => p.value === s.product_type)?.label || s.product_type}</td>
                <td>{s.quantity}</td>
                <td>{s.unit_price}</td>
                <td className="amount in">{s.total_amount}</td>
                <td>{s.customer || "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
