/**
 * The view catalogue the audit walks. One entry per screen a real user can reach, not a sample.
 *
 * `houseCode` is discovered from the API at run time rather than hardcoded, so the audit works
 * against any seeded test farm.
 */
export function adminViews(houseCode) {
  return [
    { key: "dashboard_home", label: "Vue d'ensemble (accueil)", path: "/dashboard" },
    { key: "dashboard_overview", label: "Bilan global (l'arbre)", path: "/dashboard/overview" },
    { key: "houses_list", label: "Bâtiments (liste)", path: "/dashboard/houses" },
    { key: "house_detail", label: "Bâtiment (détail)", path: `/dashboard/houses/${houseCode}` },
    { key: "house_protocol", label: "Protocole du bâtiment", path: `/dashboard/houses/${houseCode}/protocol` },
    { key: "finances_ventes", label: "Finances — Ventes", path: "/dashboard/finances#ventes" },
    { key: "finances_achats", label: "Finances — Achats", path: "/dashboard/finances#achats" },
    { key: "finances_salaires", label: "Finances — Salaires", path: "/dashboard/finances#salaires" },
    { key: "finances_globale", label: "Finances — Globale", path: "/dashboard/finances#globale" },
    { key: "stock", label: "Stock", path: "/dashboard/stock" },
    { key: "purchase_orders", label: "Commandes fournisseurs", path: "/dashboard/purchase-orders" },
    { key: "employees", label: "Employés", path: "/dashboard/employees" },
    { key: "cashier", label: "Caisse", path: "/dashboard/cashier" },
    { key: "alerts", label: "Alertes", path: "/dashboard/alerts" },
    { key: "calendar", label: "Calendrier", path: "/dashboard/calendar" },
    { key: "my_tasks", label: "Mes tâches", path: "/dashboard/my-tasks" },
    { key: "audit_log", label: "Journal d'audit", path: "/dashboard/audit" },
    { key: "settings", label: "Paramètres", path: "/dashboard/settings" },
  ];
}

/** The worker side. Same routes, different role — the sidebar and the page bodies both differ. */
export function workerViews() {
  return [
    { key: "worker_home", label: "Ouvrier — accueil", path: "/dashboard" },
    { key: "worker_my_tasks", label: "Ouvrier — Mes tâches", path: "/dashboard/my-tasks" },
    { key: "worker_calendar", label: "Ouvrier — Calendrier", path: "/dashboard/calendar" },
    { key: "worker_alerts", label: "Ouvrier — Alertes", path: "/dashboard/alerts" },
    { key: "worker_settings", label: "Ouvrier — Paramètres", path: "/dashboard/settings" },
  ];
}

/** Unauthenticated screens — measured with no token seeded. */
export const publicViews = [
  { key: "landing", label: "Accueil (landing)", path: "/" },
  { key: "login", label: "Connexion", path: "/login" },
  { key: "create_farm", label: "Créer la ferme", path: "/create-farm" },
  { key: "demo", label: "Démo", path: "/demo" },
];

/** The onboarding wizard, which only an authenticated admin reaches. */
export const onboardingViews = [
  { key: "onboarding_protocol", label: "Onboarding — protocole", path: "/onboarding/protocol" },
  { key: "onboarding_stock", label: "Onboarding — stock d'ouverture", path: "/onboarding/stock" },
  { key: "onboarding_employees", label: "Onboarding — employés", path: "/onboarding/employees" },
];
