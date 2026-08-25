import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Trash2, Loader2, UserPlus } from "lucide-react";
import { employeesApi } from "../../api/endpoints";
import { useAuth } from "../../context/AuthContext";
import { useOnboarding } from "../../context/OnboardingContext";
import TransitionScreen from "../../components/TransitionScreen";

const ROLES = [
  { value: "FARMER", label: "Fermier" },
  { value: "WORKER", label: "Ouvrier" },
  { value: "TECHNICIAN", label: "Technicien" },
  { value: "CASHIER", label: "Caissier" },
  { value: "SECONDARY_ADMIN", label: "Administrateur secondaire" },
  { value: "FARM_MANAGER", label: "Gérant de ferme" },
];

const EMPTY_FORM = { name: "", email: "", role: "FARMER", password: "" };

export default function OnboardingEmployeesPage() {
  const { employees, setEmployees } = useOnboarding();
  const [form, setForm] = useState(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [showTransition, setShowTransition] = useState(false);
  const { refreshMe } = useAuth();
  const navigate = useNavigate();

  const addEmployee = () => {
    if (!form.name || !form.email || !form.password) {
      setError("Le nom, l'email et le mot de passe sont obligatoires.");
      return;
    }
    setError("");
    setEmployees([...employees, { ...form, tempId: Date.now() }]);
    setForm(EMPTY_FORM);
  };

  const removeEmployee = (tempId) => {
    setEmployees(employees.filter((e) => e.tempId !== tempId));
  };

  const finish = async () => {
    setSaving(true);
    setError("");
    try {
      for (const employee of employees) {
        await employeesApi.create({
          name: employee.name, email: employee.email, role: employee.role, password: employee.password,
        });
      }
      await refreshMe();
      // Employees + refreshed is_configured already saved/confirmed server-side here —
      // the transition screen only delays this page's own navigation.
      setShowTransition(true);
    } catch (err) {
      setError(err.response?.data?.email?.[0] || "Impossible de créer l'un des employés.");
    } finally {
      setSaving(false);
    }
  };

  const skip = async () => {
    setSaving(true);
    await refreshMe();
    setShowTransition(true);
  };

  if (showTransition) {
    return (
      <TransitionScreen
        message="Merci beaucoup, nous configurons votre tableau de bord."
        durationMs={8000}
        onComplete={() => navigate("/dashboard", { replace: true })}
      />
    );
  }

  return (
    <div className="page-wrap">
      <div className="intro">
        <p>Ajouter des comptes employés</p>
        <span>Facultatif — les mots de passe sont définis directement par vous, sans invitation par email. Vous pourrez toujours en ajouter d'autres plus tard depuis Employés.</span>
      </div>

      {employees.length > 0 && (
        <div className="card house-card" style={{ marginBottom: 18 }}>
          {employees.map((employee) => (
            <div key={employee.tempId} className="list-row">
              <div className="list-row-main">
                <div>
                  <p className="list-row-name">{employee.name}</p>
                  <p className="list-row-sub">{employee.email} · {ROLES.find((r) => r.value === employee.role)?.label}</p>
                </div>
              </div>
              <button className="icon-button danger" onClick={() => removeEmployee(employee.tempId)} aria-label="Supprimer">
                <Trash2 size={15} strokeWidth={1.8} />
              </button>
            </div>
          ))}
        </div>
      )}

      <div className="card schedule-card">
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
          <span>Mot de passe</span>
          <input type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
        </label>
        {error && <p className="field-error" style={{ marginTop: 8 }}>{error}</p>}
        <button className="add-button" onClick={addEmployee} style={{ marginTop: 16 }}>
          <UserPlus size={14} strokeWidth={2.2} />
          Ajouter un autre employé
        </button>
      </div>

      <div className="save-bar">
        <button className="add-button" onClick={skip} disabled={saving}>Sauter</button>
        <span style={{ flex: 1 }} />
        <button className="save-button" onClick={finish} disabled={saving}>
          {saving ? <Loader2 size={16} className="spin" /> : "Suivant"}
        </button>
      </div>
    </div>
  );
}
