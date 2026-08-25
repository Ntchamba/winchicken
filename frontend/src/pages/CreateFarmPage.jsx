import { useEffect, useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { ChevronLeft, Loader2 } from "lucide-react";
import { farmApi } from "../api/endpoints";
import { useAuth } from "../context/AuthContext";
import AnimatedBackground from "../components/AnimatedBackground";
import TransitionScreen from "../components/TransitionScreen";
import "../styles/house-protocol-theme-light.css";
import "./auth-pages.css";

export default function CreateFarmPage() {
  const [adminName, setAdminName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [farmName, setFarmName] = useState("");
  const [errors, setErrors] = useState({});
  const [submitting, setSubmitting] = useState(false);
  const [serverError, setServerError] = useState("");
  const [showTransition, setShowTransition] = useState(false);
  // Blocks the form from ever rendering for a farm that already exists — covers direct
  // URL navigation to /create-farm, not just the landing page hiding its own button.
  const [checkingFarm, setCheckingFarm] = useState(true);
  const { loginWithTokens } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    farmApi.exists().then(({ data }) => {
      if (data.exists) {
        navigate("/login", {
          replace: true,
          state: { noticeMessage: "Une ferme existe déjà — vous êtes redirigé vers la connexion." },
        });
      } else {
        setCheckingFarm(false);
      }
    }).catch(() => setCheckingFarm(false));
  }, [navigate]);

  const validate = () => {
    const next = {};
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) next.email = "Saisissez une adresse email valide.";
    if (password.length < 8) next.password = "8 caractères minimum.";
    setErrors(next);
    return Object.keys(next).length === 0;
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setServerError("");
    if (!validate()) return;
    setSubmitting(true);
    try {
      const { data } = await farmApi.create({ admin_name: adminName, email, password, farm_name: farmName });
      await loginWithTokens(data);
      // Farm/admin already created and saved server-side at this point — the transition
      // screen only delays this page's own navigation, it never blocks the save itself.
      setShowTransition(true);
    } catch (err) {
      if (err.response?.status === 409) setServerError("Une ferme existe déjà — veuillez vous connecter.");
      else setServerError(err.response?.data?.email?.[0] || "Impossible de créer la ferme. Vérifiez les champs.");
    } finally {
      setSubmitting(false);
    }
  };

  if (checkingFarm) {
    return <div className="auth-shell" />;
  }

  if (showTransition) {
    return (
      <TransitionScreen
        message="Veuillez patienter, nous préparons votre tableau de bord."
        durationMs={8000}
        onComplete={() => navigate("/onboarding/protocol", { replace: true })}
      />
    );
  }

  return (
    <div className="auth-shell">
      <AnimatedBackground src="/welcome-bg.jpg" />
      <Link to="/" className="auth-back-link">
        <ChevronLeft size={15} strokeWidth={2} /> Retour à l'accueil
      </Link>
      <form className="card auth-card" onSubmit={handleSubmit}>
        <p className="eyebrow" style={{ textAlign: "center" }}>WINCHICKEN</p>
        <h1 className="auth-title">Créer la ferme</h1>
        <p className="auth-subtitle">Cela crée le compte unique de la ferme pour cette installation.</p>

        <label className="field">
          <span>Nom de l'administrateur</span>
          <input value={adminName} onChange={(e) => setAdminName(e.target.value)} required />
        </label>
        <label className="field">
          <span>Email</span>
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
          {errors.email && <p className="field-error">{errors.email}</p>}
        </label>
        <label className="field">
          <span>Mot de passe</span>
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required />
          {errors.password && <p className="field-error">{errors.password}</p>}
        </label>
        <label className="field">
          <span>Nom de la ferme</span>
          <input value={farmName} onChange={(e) => setFarmName(e.target.value)} required />
        </label>

        {serverError && <p className="field-error" style={{ marginTop: 4 }}>{serverError}</p>}

        <button className="save-button auth-submit" type="submit" disabled={submitting}>
          {submitting ? <Loader2 size={16} className="spin" /> : "Créer la ferme"}
        </button>

        <p className="auth-switch">
          Déjà un compte ? <Link to="/login">Se connecter</Link>
        </p>
      </form>
    </div>
  );
}
