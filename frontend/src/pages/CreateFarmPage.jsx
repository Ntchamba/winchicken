import { useEffect, useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { ChevronLeft } from "lucide-react";
import { farmApi } from "../api/endpoints";
import { getFieldErrors, getServerErrorMessage } from "../api/errors";
import { useAuth } from "../context/AuthContext";
import AnimatedBackground from "../components/AnimatedBackground";
import FireflyField from "../components/FireflyField";
import TransitionScreen from "../components/TransitionScreen";
import useDocumentTitle from "../hooks/useDocumentTitle";
import "../styles/house-protocol-theme-light.css";
import "./auth-pages.css";

export default function CreateFarmPage() {
  useDocumentTitle("Créer une ferme");
  const [adminName, setAdminName] = useState("");
  const [civility, setCivility] = useState("M");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [farmName, setFarmName] = useState("");
  const [errors, setErrors] = useState({});
  const [serverError, setServerError] = useState("");
  const [showTransition, setShowTransition] = useState(false);
  // Blocks the form from ever rendering for a farm that already exists — covers direct
  // URL navigation to /create-farm, not just the landing page hiding its own button.
  const [checkingFarm, setCheckingFarm] = useState(true);
  const { createAccountInBackground, accountCreationError, setAccountCreationError } = useAuth();
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

  // Landed back here because a background creation (see handleSubmit) ultimately failed —
  // ProtectedRoute redirects here instead of /login once accountCreationError is set and no
  // user ever showed up. Same error formatting the old synchronous handleSubmit used inline.
  useEffect(() => {
    if (!accountCreationError) return;
    const err = accountCreationError;
    if (err.response?.status === 409) {
      setServerError(err.response?.data?.detail || "Une ferme existe déjà — veuillez vous connecter.");
    } else {
      const fieldErrors = getFieldErrors(err);
      if (Object.keys(fieldErrors).length > 0) setErrors(fieldErrors);
      else setServerError(getServerErrorMessage(err));
    }
    setAccountCreationError(null);
  }, [accountCreationError, setAccountCreationError]);

  const validate = () => {
    const next = {};
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) next.email = "Saisissez une adresse email valide.";
    if (password.length < 8) next.password = "8 caractères minimum.";
    setErrors(next);
    return Object.keys(next).length === 0;
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    setServerError("");
    setErrors({});
    if (!validate()) return;
    // Fired, not awaited: Django's password hash (PBKDF2) is deliberately slow — several
    // seconds on a farm PC's modest, often-virtualized hardware — and nothing in the
    // protocol/stock/employees steps needs the account to exist yet. createAccountInBackground
    // finishes the real login once this resolves; OnboardingProtocolPage's save is the one
    // place that actually waits for it (waitForAccount), right before it needs the account for
    // real. If it ultimately fails, ProtectedRoute sends the user back here to see why
    // (accountCreationError, handled by the effect above).
    createAccountInBackground(
      farmApi.create({ admin_name: adminName, civility, email, password, farm_name: farmName }),
    );
    setShowTransition(true);
  };

  if (checkingFarm) {
    return <div className="auth-shell" />;
  }

  if (showTransition) {
    return (
      <TransitionScreen
        message="Veuillez patienter, nous préparons votre tableau de bord."
        durationMs={300}
        onComplete={() => navigate("/onboarding/protocol", { replace: true })}
      />
    );
  }

  return (
    <div className="auth-shell">
      <AnimatedBackground src="/image22.png" blur />
      <FireflyField className="auth-fireflies" />
      <Link to="/" className="auth-back-link">
        <ChevronLeft size={15} strokeWidth={2} /> Retour à l'accueil
      </Link>
      <form className="card auth-card" onSubmit={handleSubmit}>
        <p className="eyebrow" style={{ textAlign: "center" }}>WINCHICKEN</p>
        <h1 className="auth-title">Créer une ferme</h1>
        <p className="auth-subtitle">Cela crée le compte unique de la ferme pour cette installation.</p>

        <label className="field">
          <span>Nom de l'administrateur</span>
          <input value={adminName} onChange={(e) => setAdminName(e.target.value)} required />
          {errors.admin_name && <p className="field-error">{errors.admin_name}</p>}
        </label>
        <label className="field">
          <span>Civilité</span>
          <select value={civility} onChange={(e) => setCivility(e.target.value)}>
            <option value="M">M.</option>
            <option value="MME">Mme</option>
          </select>
          {errors.civility && <p className="field-error">{errors.civility}</p>}
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
          {errors.farm_name && <p className="field-error">{errors.farm_name}</p>}
        </label>

        {serverError && <p className="field-error" style={{ marginTop: 4 }}>{serverError}</p>}

        <button className="save-button auth-submit" type="submit">
          Créer une ferme
        </button>

        <p className="auth-switch">
          Déjà un compte ? <Link to="/login">Se connecter</Link>
        </p>
      </form>
    </div>
  );
}
