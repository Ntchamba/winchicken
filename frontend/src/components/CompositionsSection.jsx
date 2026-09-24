import { useEffect, useState } from "react";
import { Check, Loader2, Play, Plus, Trash2, X } from "lucide-react";
import { stockApi } from "../api/endpoints";
import { getServerErrorMessage } from "../api/errors";
import { useAuth } from "../context/AuthContext";
import ResourceCombobox from "./ResourceCombobox";
import "./table-wrap.css";

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
  const [baseYield, setBaseYield] = useState("");
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
    setCreating(false); setName(""); setIngredients([blankIngredient()]);
    setOutputItem(null); setBaseYield(""); setError("");
  };

  const save = async () => {
    const rows = ingredients
      .filter((r) => r.item && Number(r.quantity) > 0)
      .map((r) => ({ item: r.item, quantity: Number(r.quantity) }));
    if (!name.trim()) { setError("Le nom de la composition est requis."); return; }
    if (rows.length === 0) { setError("Ajoutez au moins un ingrédient avec une quantité."); return; }
    if (!outputItem) { setError("Sélectionnez ou créez l'article produit."); return; }
    if (baseYield !== "" && Number(baseYield) <= 0) { setError("Le rendement de base doit être positif."); return; }
    setBusy(true); setError("");
    try {
      await stockApi.addComposition(farmId, {
        name: name.trim(), output_item: outputItem, ingredients: rows,
        ...(baseYield !== "" ? { base_output_quantity: Number(baseYield) } : {}),
      });
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

  // --- Rendement de base (inline edit on an existing recipe) --------------------
  const [yieldEditFor, setYieldEditFor] = useState(null);
  const [yieldDraft, setYieldDraft] = useState("");
  const [yieldBusy, setYieldBusy] = useState(false);
  const [yieldError, setYieldError] = useState("");

  const startYieldEdit = (c) => { setYieldEditFor(c.id); setYieldDraft(c.base_output_quantity ?? ""); setYieldError(""); };
  const saveYield = async (c) => {
    // A bare `return` here was a dead button on a phone — nothing moved and nothing said why.
    if (yieldDraft !== "" && Number(yieldDraft) <= 0) {
      setYieldError("Le rendement doit être supérieur à 0.");
      return;
    }
    if (yieldBusy) return;
    setYieldError("");
    setYieldBusy(true);
    try {
      await stockApi.updateComposition(c.id, {
        base_output_quantity: yieldDraft === "" ? null : Number(yieldDraft),
      });
      setYieldEditFor(null);
      await load();
      onChanged?.();
    } catch (err) {
      // The draft stays on screen and the editor stays open — the typed value isn't lost.
      setYieldError(getServerErrorMessage(err, "Le rendement n'a pas pu être enregistré."));
    } finally {
      setYieldBusy(false);
    }
  };

  // --- Exécuter ---------------------------------------------------------------
  const [runFor, setRunFor] = useState(null);          // composition being executed
  const [runIngredients, setRunIngredients] = useState({});  // {itemCode: qty}
  const [runOutput, setRunOutput] = useState("");
  const [runShortfalls, setRunShortfalls] = useState([]);
  const [runBusy, setRunBusy] = useState(false);
  const [runError, setRunError] = useState("");

  const openRun = (c) => {
    setRunFor(c);
    setRunIngredients(Object.fromEntries(c.ingredients.map((i) => [i.item, String(i.quantity)])));
    setRunOutput("");
    setRunShortfalls([]);
    setRunError("");
  };
  const closeRun = () => { setRunFor(null); setRunShortfalls([]); setRunError(""); };

  const execute = async (force) => {
    if (!Number(runOutput) || Number(runOutput) <= 0) { setRunError("La quantité produite doit être positive."); return; }
    setRunBusy(true); setRunError("");
    try {
      const { data } = await stockApi.executeComposition(runFor.id, {
        ingredients: runFor.ingredients.map((i) => ({ item: i.item, quantity: Number(runIngredients[i.item]) })),
        outputQuantity: Number(runOutput),
        force,
      });
      if (data.status === "insufficient_stock") {
        setRunShortfalls(data.shortfalls);   // non-blocking — user may confirm anyway
        return;
      }
      closeRun();
      load();
      onChanged?.();
    } catch {
      setRunError("Impossible d'exécuter la composition.");
    } finally {
      setRunBusy(false);
    }
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

          <label className="field" style={{ maxWidth: 340, marginTop: 12 }}>
            <span>Rendement de base (facultatif)</span>
            <input
              type="number" min="0" step="any"
              placeholder="ex. 1800 (produit par lot)"
              value={baseYield}
              onChange={(e) => setBaseYield(e.target.value)}
            />
            <span className="schedule-note" style={{ marginTop: 4 }}>
              Quantité produite par ce lot d'ingrédients. Renseignez-la pour que l'ajout de stock
              de ce produit ailleurs décompte les ingrédients au prorata.
            </span>
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
              {compositions.flatMap((c) => [
                <tr key={c.id}>
                  <td>{c.name}</td>
                  <td>{ingredientSummary(c)}</td>
                  <td>
                    {c.output_item_name}{c.output_item_unit ? ` (${c.output_item_unit})` : ""}
                    <div className="schedule-note" style={{ marginTop: 2 }}>
                      {yieldEditFor === c.id ? (
                        <span style={{ display: "inline-flex", gap: 4, alignItems: "center" }}>
                          rendement
                          <input
                            type="number" min="0" step="any" autoFocus
                            value={yieldDraft}
                            onChange={(e) => setYieldDraft(e.target.value)}
                            onKeyDown={(e) => { if (e.key === "Enter") saveYield(c); if (e.key === "Escape") { setYieldEditFor(null); setYieldError(""); } }}
                            placeholder="par lot"
                            style={{ width: 90 }}
                          />
                          {c.output_item_unit ? ` ${c.output_item_unit}/lot` : "/lot"}
                          <button type="button" className="icon-button" onClick={() => saveYield(c)} aria-label="Enregistrer" disabled={yieldBusy}>
                            {yieldBusy ? <Loader2 size={12} className="spin" /> : <Check size={12} strokeWidth={2.2} />}
                          </button>
                          <button type="button" className="icon-button" onClick={() => { setYieldEditFor(null); setYieldError(""); }} aria-label="Annuler">
                            <X size={12} strokeWidth={2.2} />
                          </button>
                          {yieldError && <span className="field-error" role="alert">{yieldError}</span>}
                        </span>
                      ) : canManage ? (
                        <button
                          type="button"
                          onClick={() => startYieldEdit(c)}
                          style={{ background: "none", border: "none", padding: 0, cursor: "pointer", color: "inherit", textDecoration: "underline" }}
                        >
                          {c.base_output_quantity > 0
                            ? `rendement ${c.base_output_quantity}${c.output_item_unit ? ` ${c.output_item_unit}` : ""}/lot`
                            : "définir le rendement de base"}
                        </button>
                      ) : c.base_output_quantity > 0 ? (
                        `rendement ${c.base_output_quantity}${c.output_item_unit ? ` ${c.output_item_unit}` : ""}/lot`
                      ) : null}
                    </div>
                  </td>
                  {canManage && (
                    <td style={{ whiteSpace: "nowrap", textAlign: "right" }}>
                      <button className="add-button" style={{ marginTop: 0, padding: "5px 9px", fontSize: 12 }}
                        onClick={() => (runFor?.id === c.id ? closeRun() : openRun(c))} type="button">
                        <Play size={12} strokeWidth={2.4} /> Exécuter
                      </button>
                      <button className="icon-button" aria-label={`Supprimer ${c.name}`} onClick={() => remove(c.id)}>
                        <Trash2 size={13} strokeWidth={2} />
                      </button>
                    </td>
                  )}
                </tr>,
                runFor?.id === c.id && (
                  <tr key={`${c.id}-run`}>
                    <td colSpan={canManage ? 4 : 3}>
                      <div style={{ padding: "6px 0" }}>
                        <p className="schedule-note" style={{ marginBottom: 6 }}>Exécuter «&nbsp;{c.name}&nbsp;»</p>
                        {c.ingredients.map((i) => (
                          <div key={i.item} style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4, flexWrap: "wrap" }}>
                            <span style={{ minWidth: 160 }}>{i.item_name}</span>
                            <input
                              type="number" min="0" step="any"
                              aria-label={`Quantité ${i.item_name}`}
                              value={runIngredients[i.item] ?? ""}
                              onChange={(e) => setRunIngredients((p) => ({ ...p, [i.item]: e.target.value }))}
                              style={{ width: 130 }}
                            />
                            <span className="schedule-note">{i.unit} · en stock : {i.current_quantity}</span>
                          </div>
                        ))}
                        <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 6, flexWrap: "wrap" }}>
                          <span style={{ minWidth: 160, fontWeight: 700 }}>{c.output_item_name} (produit)</span>
                          <input
                            type="number" min="0" step="any" autoFocus
                            placeholder="Quantité produite"
                            aria-label="Quantité produite"
                            value={runOutput}
                            onChange={(e) => setRunOutput(e.target.value)}
                            style={{ width: 130 }}
                          />
                          <span className="schedule-note">{c.output_item_unit} — saisie manuelle, pas la somme des entrées</span>
                        </div>

                        {runShortfalls.length > 0 && (
                          <div className="field-error" style={{ margin: "8px 0 0", fontSize: 12 }}>
                            Stock insuffisant :{" "}
                            {runShortfalls.map((s) => `${s.itemName} (besoin ${s.needed} ${s.unit}, dispo ${s.onHand})`).join(" ; ")}
                            {" "}— vous pouvez confirmer quand même.
                          </div>
                        )}
                        {runError && <p className="field-error" style={{ margin: "6px 0 0" }}>{runError}</p>}

                        <div style={{ display: "flex", gap: 10, marginTop: 10 }}>
                          <button className="save-button" style={{ width: "auto" }} disabled={runBusy}
                            onClick={() => execute(runShortfalls.length > 0)}>
                            {runBusy ? <Loader2 size={16} className="spin" />
                              : runShortfalls.length > 0 ? "Confirmer quand même" : "Confirmer l'exécution"}
                          </button>
                          <button className="add-button" style={{ marginTop: 0 }} type="button" onClick={closeRun}>Annuler</button>
                        </div>
                      </div>
                    </td>
                  </tr>
                ),
              ].filter(Boolean))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
