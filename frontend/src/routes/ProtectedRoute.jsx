import { Navigate, Outlet } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

// Redirects unauthenticated visitors to /login. While /dashboard/* is unconfigured,
// redirects to /onboarding/protocol (cahier des charges 5.5) — except the onboarding
// routes themselves, which are exempt via `allowUnconfigured`.
export default function ProtectedRoute({ allowUnconfigured = false }) {
  const { user, loading } = useAuth();

  if (loading) return <div style={{ padding: 40, textAlign: "center", color: "var(--muted)" }}>Chargement…</div>;
  if (!user) return <Navigate to="/login" replace />;
  if (!allowUnconfigured && !user.is_configured) return <Navigate to="/onboarding/protocol" replace />;

  return <Outlet />;
}
