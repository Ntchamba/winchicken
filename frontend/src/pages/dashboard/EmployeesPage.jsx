import { useEffect, useState } from "react";
import { Pencil, Trash2, UserPlus, Loader2 } from "lucide-react";
import { employeesApi } from "../../api/endpoints";

const ROLES = [
  { value: "FARMER", label: "Fermier" },
  { value: "WORKER", label: "Ouvrier" },
  { value: "TECHNICIAN", label: "Technicien" },
  { value: "CASHIER", label: "Caissier" },
  { value: "SECONDARY_ADMIN", label: "Administrateur secondaire" },
  { value: "FARM_MANAGER", label: "Gérant de ferme" },
];

const EMPTY_FORM = { name: "", email: "", role: "FARMER", password: "" };

export default function EmployeesPage() {
  const [employees, setEmployees] = useState([]);
  const [form, setForm] = useState(EMPTY_FORM);
  const [editingId, setEditingId] = useState(null);
  const [confirmDeleteId, setConfirmDeleteId] = useState(null);
  const [busyId, setBusyId] = useState(null);
  const [error, setError] = useState("");

  const load = () => employeesApi.list().then(({ data }) => setEmployees(data.results || data));

  useEffect(() => { load(); }, []);

  const submit = async () => {
    setError("");
    try {
      if (editingId) {
        const payload = { ...form };
        if (!payload.password) delete payload.password;
        await employeesApi.update(editingId, payload);
      } else {
        await employeesApi.create(form);
      }
      setForm(EMPTY_FORM);
      setEditingId(null);
      load();
    } catch (err) {
      setError(err.response?.data?.email?.[0] || "Impossible d'enregistrer cet employé.");
    }
  };

  const startEdit = (employee) => {
    setEditingId(employee.id);
    setForm({ name: employee.name, email: employee.email, role: employee.role, password: "" });
  };

  const remove = async (id) => {
    setBusyId(id);
    try {
      await employeesApi.remove(id);
      setConfirmDeleteId(null);
      load();
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className="page-wrap">
      <div className="intro">
        <p>Employés</p>
        <span>Chaque compte créé ici peut se connecter directement avec le mot de passe que vous définissez — sans invitation par email.</span>
      </div>

      {employees.map((employee) => (
        <div key={employee.id} className="list-row">
          <div className="list-row-main">
            <div>
              <p className="list-row-name">{employee.name}</p>
              <p className="list-row-sub">{employee.email} · {ROLES.find((r) => r.value === employee.role)?.label || employee.role}</p>
            </div>
          </div>
          <div className="list-row-actions">
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
      ))}
      {employees.length === 0 && <p className="empty-state">Aucun compte employé pour le moment.</p>}

      <div className="card schedule-card" style={{ marginTop: 20 }}>
        <p className="schedule-note" style={{ marginBottom: 14 }}>{editingId ? "Modifier l'employé" : "Ajouter un nouvel employé"}</p>
        <div className="detail-grid">
          <label className="field">
            <span>Nom</span>
            <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
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
        {error && <p className="field-error" style={{ marginTop: 8 }}>{error}</p>}
        <div style={{ display: "flex", gap: 10, marginTop: 16 }}>
          <button className="save-button" onClick={submit}>
            <UserPlus size={14} strokeWidth={2.2} style={{ marginRight: 6 }} />
            {editingId ? "Enregistrer les modifications" : "Ajouter un employé"}
          </button>
          {editingId && (
            <button className="add-button" onClick={() => { setEditingId(null); setForm(EMPTY_FORM); }}>Annuler</button>
          )}
        </div>
      </div>
    </div>
  );
}
