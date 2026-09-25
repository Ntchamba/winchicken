import { Fragment, useRef, useState } from "react";
import { Pencil, Trash2, UserPlus, Loader2, FileSpreadsheet, Download } from "lucide-react";
import { employeesApi } from "../../api/endpoints";
import { getServerErrorMessage } from "../../api/errors";
import useDocumentTitle from "../../hooks/useDocumentTitle";
import QuickLinksBar from "../../components/QuickLinksBar";
import LoadMoreButton from "../../components/LoadMoreButton";
import usePagedList from "../../hooks/usePagedList";

// Page by page: only page 1 (20 accounts) was ever read, so from the 21st employee on the
// list silently stopped (load test, 2026-09-25).
const fetchEmployeesPage = (page) => employeesApi.list({ page });

const ROLES = [
  { value: "FARMER", label: "Fermier" },
  { value: "WORKER", label: "Ouvrier" },
  { value: "TECHNICIAN", label: "Technicien" },
  { value: "CASHIER", label: "Caissier" },
  { value: "SECONDARY_ADMIN", label: "Administrateur secondaire" },
  { value: "FARM_MANAGER", label: "Gérant de ferme" },
];

const EMPTY_FORM = { name: "", civility: "M", email: "", role: "FARMER", password: "" };

export default function EmployeesPage() {
  useDocumentTitle("Employés");
  const employeeList = usePagedList(fetchEmployeesPage);
  const employees = employeeList.rows;
  const [form, setForm] = useState(EMPTY_FORM);
  const [editingId, setEditingId] = useState(null);
  const [confirmDeleteId, setConfirmDeleteId] = useState(null);
  const [busyId, setBusyId] = useState(null);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState("");
  const [rateEdits, setRateEdits] = useState({});
  const [savingRateId, setSavingRateId] = useState(null);
  // Feedback for the per-row actions (taux horaire, suppression), shown under the row that
  // triggered it — the page-level `error`/`saved` lines live down in the form card, far
  // enough away on a phone to read as nothing having happened. {id, tone, message}.
  const [rowFeedback, setRowFeedback] = useState(null);
  // One row mutates at a time; a ref, not state, so a second tap in the same tick is
  // blocked before React has flushed anything.
  const rowInFlight = useRef(null);

  const importInputRef = useRef(null);
  const [importing, setImporting] = useState(false);
  const [importResult, setImportResult] = useState(null); // { updated, created, skipped, newAccounts }
  const [importError, setImportError] = useState("");

  // Caught on purpose: a create can succeed and this refresh still fail, which used to leave
  // the new account off the list with no message — indistinguishable from a lost submission.
  const load = () => employeeList.reload();
  const listError = employeeList.error
    ? getServerErrorMessage(employeeList.error, "La liste des employés n'a pas pu être rechargée.")
    : "";

  const handleImportFile = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setImporting(true);
    setImportError("");
    setImportResult(null);
    try {
      const { data } = await employeesApi.importXlsx(file);
      setImportResult(data);
      load();
    } catch (err) {
      setImportError(getServerErrorMessage(err, "Échec de l'import du fichier Excel."));
    } finally {
      setImporting(false);
    }
  };


  // `saving` is the in-flight guard: the button carried none, so a second tap during a slow
  // save sent the request twice and the operator had no way to tell a save was running at all
  // (FIX 6). The submit also goes through <form onSubmit>, so the phone keyboard's "Go" key
  // works — it used to do nothing.
  const submit = async (event) => {
    event?.preventDefault();
    if (saving) return;
    setError("");
    setSaved("");
    setSaving(true);
    const wasEditing = editingId;
    try {
      if (editingId) {
        const payload = { ...form };
        if (!payload.password) delete payload.password;
        await employeesApi.update(editingId, payload);
      } else {
        await employeesApi.create(form);
      }
      setSaved(
        wasEditing
          ? `Modifications enregistrées pour ${form.name || form.email}.`
          : `Compte créé : ${form.name || form.email} (${form.email}).`,
      );
      setForm(EMPTY_FORM);
      setEditingId(null);
      await load();
    } catch (err) {
      // Was `err.response?.data?.email?.[0] || "..."` — only ever surfaced an *email* field
      // error and silently swallowed every other one (wrong role, weak password, network
      // outage). getServerErrorMessage checks detail/any-field/unreachable, in that order.
      setError(getServerErrorMessage(err, "Impossible d'enregistrer cet employé."));
    } finally {
      setSaving(false);
    }
  };

  const startEdit = (employee) => {
    setSaved("");
    setEditingId(employee.id);
    setForm({ name: employee.name, civility: employee.civility, email: employee.email, role: employee.role, password: "" });
  };

  // hourly_rate is read-only on EmployeeSerializer — it's set via the dedicated
  // EmployeeHourlyRateView PATCH (2026-08-27, Salaires module Part D), not this page's main
  // create/update form, so it gets its own inline editor per row rather than a form field that
  // would silently be ignored on save.
  const saveRate = async (employeeId) => {
    if (rowInFlight.current !== null) return;
    const raw = rateEdits[employeeId];
    const employee = employees.find((e) => e.id === employeeId);
    rowInFlight.current = employeeId;
    setRowFeedback(null);
    setSavingRateId(employeeId);
    try {
      await employeesApi.setHourlyRate(employeeId, raw === "" ? null : raw);
      await load();
      setRateEdits((prev) => { const next = { ...prev }; delete next[employeeId]; return next; });
      setRowFeedback({
        id: employeeId,
        tone: "ok",
        message: raw === ""
          ? `Taux horaire retiré pour ${employee?.name || "cet employé"}.`
          : `Taux horaire enregistré : ${raw} FCFA/h pour ${employee?.name || "cet employé"}.`,
      });
    } catch (err) {
      // The typed rate stays in `rateEdits`, so the value isn't lost on a failed save.
      setRowFeedback({ id: employeeId, tone: "error", message: getServerErrorMessage(err, "Le taux horaire n'a pas pu être enregistré.") });
    } finally {
      rowInFlight.current = null;
      setSavingRateId(null);
    }
  };

  const remove = async (id) => {
    if (rowInFlight.current !== null) return;
    const employee = employees.find((e) => e.id === id);
    rowInFlight.current = id;
    setRowFeedback(null);
    setBusyId(id);
    try {
      await employeesApi.remove(id);
      setConfirmDeleteId(null);
      await load();
      setRowFeedback({ id: null, tone: "ok", message: `Compte supprimé : ${employee?.name || "employé"}.` });
    } catch (err) {
      // The row stays on screen on failure, which is indistinguishable from a no-op.
      setRowFeedback({ id, tone: "error", message: getServerErrorMessage(err, "Ce compte n'a pas pu être supprimé.") });
    } finally {
      rowInFlight.current = null;
      setBusyId(null);
    }
  };

  return (
    <div className="page-wrap">
      <QuickLinksBar />
      <div className="intro">
        <p>Employés</p>
        <span>Chaque compte créé ici peut se connecter directement avec le mot de passe que vous définissez — sans invitation par email.</span>
      </div>

      <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8, margin: "0 0 16px" }}>
        <a className="add-button" style={{ marginTop: 0, textDecoration: "none" }} href={employeesApi.importTemplateUrl}>
          <Download size={14} strokeWidth={2.2} /> Télécharger un modèle
        </a>
        <button className="add-button" style={{ marginTop: 0 }} onClick={() => importInputRef.current?.click()} disabled={importing}>
          {importing ? <Loader2 size={14} className="spin" /> : <FileSpreadsheet size={14} strokeWidth={2.2} />}
          Importer un fichier Excel
        </button>
        <input ref={importInputRef} type="file" accept=".xlsx" onChange={handleImportFile} style={{ display: "none" }} />
        <span className="schedule-note" style={{ margin: 0, fontSize: 11.5 }}>
          Met à jour ou crée des comptes par email — ne supprime rien, ne change aucun mot de passe existant.
        </span>
      </div>
      {importError && <p className="field-error" style={{ margin: "0 0 12px" }}>{importError}</p>}
      {importResult && (
        <div
          role="status"
          style={{
            margin: "0 0 16px", padding: "12px 14px", borderRadius: 10, fontSize: 13, lineHeight: 1.5,
            background: importResult.skipped.length ? "#fff4f0" : "var(--mint-soft, #d7f5ec)",
            color: importResult.skipped.length ? "#8a3b1f" : "#0b5137",
          }}
        >
          <strong>
            {importResult.updated} ligne{importResult.updated > 1 ? "s" : ""} mise{importResult.updated > 1 ? "s" : ""} à jour,{" "}
            {importResult.created} ligne{importResult.created > 1 ? "s" : ""} créée{importResult.created > 1 ? "s" : ""},{" "}
            {importResult.skipped.length} ligne{importResult.skipped.length > 1 ? "s" : ""} ignorée{importResult.skipped.length > 1 ? "s" : ""}.
          </strong>
          {importResult.skipped.length > 0 && (
            <ul style={{ margin: "6px 0 0", paddingLeft: 18 }}>
              {importResult.skipped.map((s) => <li key={s.line}>Ligne {s.line} : {s.reason}</li>)}
            </ul>
          )}
          {importResult.newAccounts?.length > 0 && (
            <div style={{ marginTop: 10 }}>
              <strong>Mots de passe temporaires (à communiquer, à faire changer à la première connexion) :</strong>
              <ul style={{ margin: "6px 0 0", paddingLeft: 18 }}>
                {importResult.newAccounts.map((a) => (
                  <li key={a.email}>
                    {a.name} — {a.email} — <code>{a.password}</code>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {rowFeedback?.id === null && (
        <p className="save-confirmation" role="status" style={{ margin: "0 0 12px" }}>{rowFeedback.message}</p>
      )}

      {employees.map((employee) => (
        <Fragment key={employee.id}>
        <div className="list-row">
          <div className="list-row-main">
            <div>
              <p className="list-row-name">{employee.name}</p>
              <p className="list-row-sub">{employee.email} · {ROLES.find((r) => r.value === employee.role)?.label || employee.role}</p>
            </div>
          </div>
          <div className="list-row-actions" style={{ gap: 14 }}>
            <label className="field" style={{ margin: 0 }}>
              <span style={{ fontSize: 11 }}>Taux horaire</span>
              <input
                type="number" min="0" step="0.01"
                value={rateEdits[employee.id] !== undefined ? rateEdits[employee.id] : (employee.hourly_rate ?? "")}
                style={{ width: 90, padding: "4px 8px", borderRadius: 8, border: "1px solid var(--line)" }}
                onChange={(e) => setRateEdits((prev) => ({ ...prev, [employee.id]: e.target.value }))}
              />
            </label>
            {rateEdits[employee.id] !== undefined && (
              <button className="icon-button" title="Enregistrer le taux" disabled={savingRateId === employee.id} onClick={() => saveRate(employee.id)}>
                {savingRateId === employee.id ? <Loader2 size={14} className="spin" /> : "OK"}
              </button>
            )}
            {confirmDeleteId === employee.id ? (
              <>
                <button className="icon-button danger" onClick={() => remove(employee.id)} disabled={busyId === employee.id}>
                  {busyId === employee.id ? <Loader2 size={14} className="spin" /> : "Confirmer"}
                </button>
                <button className="icon-button" onClick={() => setConfirmDeleteId(null)}>Annuler</button>
              </>
            ) : (
              <>
                <button className="icon-button" onClick={() => startEdit(employee)} aria-label="Modifier">
                  <Pencil size={15} strokeWidth={1.8} />
                </button>
                <button className="icon-button danger" onClick={() => setConfirmDeleteId(employee.id)} aria-label="Supprimer">
                  <Trash2 size={15} strokeWidth={1.8} />
                </button>
              </>
            )}
          </div>
        </div>
        {rowFeedback?.id === employee.id && (
          <p
            className={rowFeedback.tone === "error" ? "field-error" : "save-confirmation"}
            role={rowFeedback.tone === "error" ? "alert" : "status"}
            style={{ margin: "-4px 0 12px" }}
          >
            {rowFeedback.message}
          </p>
        )}
        </Fragment>
      ))}
      {employees.length === 0 && !employeeList.loading && <p className="empty-state">Aucun compte employé pour le moment.</p>}
      <LoadMoreButton
        hasMore={employeeList.hasMore}
        loading={employeeList.loading}
        onClick={employeeList.loadMore}
        shown={employees.length}
        total={employeeList.count}
      />

      <form className="card schedule-card" style={{ marginTop: 20 }} onSubmit={submit}>
        <p className="schedule-note" style={{ marginBottom: 14 }}>{editingId ? "Modifier l'employé" : "Ajouter un nouvel employé"}</p>
        <div className="detail-grid">
          <label className="field">
            <span>Nom</span>
            <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          </label>
          <label className="field">
            <span>Civilité</span>
            <select value={form.civility} onChange={(e) => setForm({ ...form, civility: e.target.value })}>
              <option value="M">M.</option>
              <option value="MME">Mme</option>
            </select>
          </label>
          <label className="field">
            <span>Email</span>
            <input type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
          </label>
          <label className="field">
            <span>Rôle</span>
            <select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>
              {ROLES.map((r) => (
                <option key={r.value} value={r.value}>{r.label}</option>
              ))}
            </select>
          </label>
        </div>
        <label className="field" style={{ marginTop: 14 }}>
          <span>{editingId ? "Nouveau mot de passe (laisser vide pour ne pas le changer)" : "Mot de passe"}</span>
          <input type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
        </label>
        {(error || listError) && <p className="field-error" style={{ marginTop: 8 }} role="alert">{error || listError}</p>}
        {saved && <p className="save-confirmation" role="status">{saved}</p>}
        <div style={{ display: "flex", gap: 10, marginTop: 16 }}>
          <button className="save-button" type="submit" disabled={saving}>
            {saving
              ? <Loader2 size={14} className="spin" style={{ marginRight: 6 }} />
              : <UserPlus size={14} strokeWidth={2.2} style={{ marginRight: 6 }} />}
            {saving ? "Enregistrement…" : editingId ? "Enregistrer les modifications" : "Ajouter un employé"}
          </button>
          {editingId && (
            <button className="add-button" type="button" disabled={saving} onClick={() => { setEditingId(null); setForm(EMPTY_FORM); setSaved(""); }}>Annuler</button>
          )}
        </div>
      </form>
    </div>
  );
}
