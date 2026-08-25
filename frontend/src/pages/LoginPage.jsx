import { useState } from "react";
import { useLocation, useNavigate, Link } from "react-router-dom";
import { ChevronLeft, Loader2 } from "lucide-react";
import { authApi } from "../api/endpoints";
import { useAuth } from "../context/AuthContext";
import AnimatedBackground from "../components/AnimatedBackground";
import TransitionScreen from "../components/TransitionScreen";
import "../styles/house-protocol-theme-light.css";
import "./auth-pages.css";

// Same message family as the farm-creation/onboarding-finish transitions
// ("[greeting], nous [verb]ons [objet]") — kept together so the four read as one
// coherent set rather than each screen inventing its own phrasing.
const TRANSITION_MESSAGES = {
  dashboard: "Bon retour, nous chargeons votre tableau de bord.",
  onboarding: "Bienvenue, nous préparons la suite de votre configuration.",
};

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [serverError, setServerError] = useState("");
  const [transitionTarget, setTransitionTarget] = useState(null);
  const { loginWithTokens } = useAuth();
  const navigate = useNavigate();
  // Brief explanatory notice when redirected here from /create-farm because a farm
  // already exists (router state, not persisted — gone on the next navigation).
  const location = useLocation();
  const noticeMessage = location.state?.noticeMessage;

  const handleSubmit = async (e) => {
    e.preventDefault();
    setServerError("");
    setSubmitting(true);
    try {
      const { data } = await authApi.login(email, password);
      await loginWithTokens(data);
      // Login already succeeded and is saved (tokens issued, user session live) at this
      // point — the transition screen only delays this page's own navigation.
      setTransitionTarget(data.is_configured ? "/dashboard" : "/onboarding/protocol");
    } catch {
      setServerError("Email ou mot de passe incorrect.");
    } finally {
      setSubmitting(false);
    }
  };

  if (transitionTarget) {
    return (
      <TransitionScreen
        message={transitionTarget === "/dashboard" ? TRANSITION_MESSAGES.dashboard : TRANSITION_MESSAGES.onboarding}
        durationMs={8000}
        onComplete={() => navigate(transitionTarget, { replace: true })}
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
        {noticeMessage && <p className="auth-notice">{noticeMessage}</p>}
        <p className="eyebrow" style={{ textAlign: "center" }}>WINCHICKEN</p>
        <h1 className="auth-title">Connexion</h1>
        <p className="auth-subtitle">Accédez au tableau de bord de votre ferme.</p>

        <label className="field">
          <span>Email</span>
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
        </label>
        <label className="field">
          <span>Mot de passe</span>
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required />
        </label>

        {serverError && <p className="field-error" style={{ marginTop: 4 }}>{serverError}</p>}

        <button className="save-button auth-submit" type="submit" disabled={submitting}>
          {submitting ? <Loader2 size={16} className="spin" /> : "Se connecter"}
        </button>

        <p className="auth-switch">
          Pas encore de compte ? <Link to="/create-farm">Créer la ferme</Link>
        </p>
      </form>
    </div>
  );
}
