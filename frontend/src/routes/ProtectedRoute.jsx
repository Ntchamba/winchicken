import { Navigate, Outlet } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import AppLoadingScreen from "../components/AppLoadingScreen";

// Redirects unauthenticated visitors to /login. While /dashboard/* is unconfigured,
// redirects to /onboarding/protocol (cahier des charges 5.5) — except the onboarding
// routes themselves, which are exempt via `allowUnconfigured`.
export default function ProtectedRoute({ allowUnconfigured = false }) {
  const { user, loading, unreachable, refreshMe, logout, creatingAccount, accountCreationError } = useAuth();

  if (loading || (!user && unreachable)) {
    return <AppLoadingScreen unreachable={unreachable} onRetry={refreshMe} onLogout={logout} />;
  }
  // CreateFarmPage navigates here optimistically while the account (and its deliberately-slow
  // PBKDF2 hash) is still being created in the background — tolerate the momentary absence of
  // `user` on the onboarding routes themselves rather than bouncing to /login. The first step
  // that genuinely needs the account (OnboardingProtocolPage's save) awaits the same creation
  // itself, so the only user-visible wait left is whatever's left of that hash by the time
  // onboarding is filled in.
  if (!user && allowUnconfigured && creatingAccount) {
    return <Outlet />;
  }
  if (!user) {
    // The background creation finished but failed — send back to the form instead of /login so
    // it can show accountCreationError, same as its old synchronous catch block did inline.
    return <Navigate to={accountCreationError ? "/create-farm" : "/login"} replace />;
  }
  if (!allowUnconfigured && !user.is_configured) return <Navigate to="/onboarding/protocol" replace />;

  return <Outlet />;
}
