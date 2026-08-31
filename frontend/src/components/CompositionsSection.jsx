import { useEffect, useState } from "react";
import { Loader2, Plus, Trash2, X } from "lucide-react";
import { stockApi } from "../api/endpoints";
import { useAuth } from "../context/AuthContext";
import ResourceCombobox from "./ResourceCombobox";

const CAN_MANAGE = new Set(["ADMIN", "FARM_MANAGER", "FARMER"]);
const blankIngredient = () => ({ item: null, quantity: "" });

/**
 * "Compositions" section of the Stock dashboard — recipes that combine quantities of existing
 * StockItems into an output product (e.g. 1000kg maïs + 1000kg macabo → "Provende maison").
 * Defining a recipe writes NO stock movement; executing it does (one OUT per ingredient + one
 * IN for the output, in one transaction — see the "Exécuter" flow).
 *
 * @param {number} farmId
 * @param {{item_code, name, unit}[]} items - the farm's stock items, for the resource comboboxes
 * @param {() => void} onChanged - refetch trigger for the rest of the Stock dashboard
 */
export default function CompositionsSection({ farmId, items = [], onChanged }) {
  const { user } = useAuth();
  const canManage = CAN_MANAGE.has(user?.role);

  const [compositions, setCompositions] = useState([]);
  const [itemList, setItemList] = useState(items);
  useEffect(() => { setItemList(items); }, [items]);

  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [ingredients, setIngredients] = useState([blankIngredient()]);
  const [outputItem, setOutputItem] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const load = () => stockApi.compositions(farmId).then(({ data }) => setCompositions(data.results || data));
  useEffect(() => { load(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [farmId]);

  const createInlineItem = async (itemName) => {
    const { data } = await stockApi.addItem(farmId, { name: itemName, unit: "kg" });
    setItemList((prev) => [...prev, data]);
    return data;
  };

  const resetForm = () => {
    setCreating(false); setName(""); setIngredients([blankIngredient()]); setOutputItem(null); setError("");
  };

  const save = async () => {
    const rows = ingredients
      .filter((r) => r.item && Number(r.quantity) > 0)
      .map((r) => ({ item: r.item, quantity: Number(r.quantity) }));
    if (!name.trim()) { setError("Le nom de la composition est requis."); return; }
    if (rows.length === 0) { setError("Ajoutez au moins un ingrédient avec une quantité."); return; }
    if (!outputItem) { setError("Sélectionnez ou créez l'article produit."); return; }
    setBusy(true); setError("");
    try {
      await stockApi.addComposition(farmId, { name: name.trim(), output_item: outputItem, ingredients: rows });
      resetForm();
      load();
      onChanged?.();
    } catch {
      setError("Impossible d'enregistrer la composition.");
    } finally {
      setBusy(false);
    }
  };

  const remove = async (id) => {
    await stockApi.removeComposition(id);
    load();
    onChanged?.();
  };

  const ingredientSummary = (c) =>
    c.ingredients.map((i) => `${i.item_name} ${i.quantity}${i.unit || ""}`).join(" + ");

  return (
    <div className="card schedule-card" style={{ marginBottom: 18 }}>
      <div className="section-row" style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <h2>Compositions</h2>
        {canManage && !creating && (
          <button className="add-button" style={{ marginTop: 0 }} type="button" onClick={() => setCreating(true)}>
            <Plus size={14} strokeWidth={2.5} /> Nouvelle composition
          </button>
        )}
      </div>

      {creating && (
        <div className="card schedule-card" style={{ marginBottom: 14, background: "var(--surface-2)" }}>
          <label className="field" style={{ maxWidth: 340 }}>
            <span>Nom de la composition</span>
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder="ex. Provende maison" autoFocus />
          </label>

          <p className="schedule-note" style={{ margin: "12px 0 6px" }}>Ingrédients</p>
          {ingredients.map((row, idx) => (
            <div key={idx} style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6, flexWrap: "wrap" }}>
              <ResourceCombobox
                items={itemList}
                value={row.item}
                onSelect={(code) => setIngredients((p) => p.map((r, i) => (i === idx ? { ...r, item: code } : r)))}
                onCreate={createInlineItem}
              />
              <input
                type="number" min="0" step="any"
                placeholder="Quantité de base"
                aria-label="Quantité de base"
                value={row.quantity}
                onChange={(e) => setIngredients((p) => p.map((r, i) => (i === idx ? { ...r, quantity: e.target.value } : r)))}
                style={{ width: 150 }}
              />
              <span className="schedule-note">
                {itemList.find((s) => s.item_code === row.item)?.unit || ""}
              </span>
              {ingredients.length > 1 && (
                <button type="button" className="icon-button" aria-label="Retirer l'ingrédient"
                  onClick={() => setIngredients((p) => p.filter((_, i) => i !== idx))}>
                  <X size={13} strokeWidth={2.2} />
                </button>
              )}
            </div>
          ))}
          <button type="button" className="add-button" style={{ marginTop: 4 }}
            onClick={() => setIngredients((p) => [...p, blankIngredient()])}>
            <Plus size={13} strokeWidth={2.5} /> Ajouter un ingrédient
          </button>

          <label className="field" style={{ maxWidth: 340, marginTop: 12 }}>
            <span>Article produit</span>
            <ResourceCombobox
              items={itemList}
              value={outputItem}
              onSelect={setOutputItem}
              onCreate={createInlineItem}
            />
          </label>

          {error && <p className="field-error" style={{ margin: "8px 0 0" }}>{error}</p>}
          <div style={{ display: "flex", gap: 10, marginTop: 12 }}>
            <button className="save-button" style={{ width: "auto" }} onClick={save} disabled={busy}>
              {busy ? <Loader2 size={16} className="spin" /> : "Enregistrer la composition"}
            </button>
            <button className="add-button" style={{ marginTop: 0 }} onClick={resetForm} type="button">Annuler</button>
          </div>
        </div>
      )}

      {compositions.length === 0 && !creating ? (
        <p className="empty-state">Aucune composition. Créez-en une pour combiner des articles en un produit.</p>
      ) : (
        <div className="table-wrap">
          <table className="help-example-table" style={{ width: "100%" }}>
            <thead>
              <tr><th>Nom</th><th>Ingrédients</th><th>Produit</th>{canManage && <th />}</tr>
            </thead>
            <tbody>
              {compositions.map((c) => (
                <tr key={c.id}>
                  <td>{c.name}</td>
                  <td>{ingredientSummary(c)}</td>
                  <td>{c.output_item_name}{c.output_item_unit ? ` (${c.output_item_unit})` : ""}</td>
                  {canManage && (
                    <td style={{ whiteSpace: "nowrap", textAlign: "right" }}>
                      <button className="icon-button" aria-label={`Supprimer ${c.name}`} onClick={() => remove(c.id)}>
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
