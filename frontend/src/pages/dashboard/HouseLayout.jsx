import { useCallback, useEffect, useState } from "react";
import { Link, Outlet, useLocation, useNavigate, useOutletContext, useParams } from "react-router-dom";
import QuickLinksBar from "../../components/QuickLinksBar";
import { batchesApi } from "../../api/endpoints";
import { HOUSE_SECTIONS, houseBasePath, houseCrossLinks } from "./houseSections";
import "../../styles/house-protocol-theme-light.css";
import "../../styles/dashboard-theme.css";
import "./house-hub.css";

/**
 * Parent route of `/dashboard/houses/:houseCode` and its destinations (Cas signalés, …).
 * Loads the house's current batch once for the hub and every destination, and owns the
 * breadcrumb and cross-links so each destination is reachable from every other one.
 *
 * Re-exposes DashboardShell's outlet context (`houses`, `refreshHouses`) with `house`,
 * `batch` and `loadBatch` added — a nested <Outlet context> replaces the parent's, so passing
 * it through is what keeps `useOutletContext()` working unchanged in the children.
 */
export default function HouseLayout() {
  const { houseCode } = useParams();
  const shell = useOutletContext();
  const { houses } = shell;
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const house = houses.find((h) => h.houseCode === houseCode);
  const base = houseBasePath(houseCode);
  const section = HOUSE_SECTIONS.find(({ path }) => pathname === `${base}/${path}`);

  // `undefined` while loading, `null` once known to have no batch — the pages tell the two
  // apart so "Ce bâtiment n'a pas encore de bande" never flashes before the data arrives.
  // Stored with the house it belongs to, so switching house reads as "loading" at once
  // instead of showing the previous house's batch until the new request lands.
  const [loaded, setLoaded] = useState({ houseCode: null, batch: undefined });
  const batch = loaded.houseCode === houseCode ? loaded.batch : undefined;

  const loadBatch = useCallback(() => (
    batchesApi.list(houseCode).then(({ data }) => {
      const results = data.results || data;
      setLoaded({ houseCode, batch: results.find((b) => b.status === "ACTIVE") || results[0] || null });
    })
  ), [houseCode]);

  useEffect(() => {
    loadBatch();
  }, [loadBatch]);

  return (
    <div className="page-wrap">
      <QuickLinksBar sections={houseCrossLinks(houseCode)} sectionsLabel="Sections du bâtiment" />
      <div className="breadcrumb">
        Tableau de bord /{" "}
        {section ? (
          <>
            <Link to={base}>{house?.name || houseCode}</Link> / <strong>{section.label}</strong>
          </>
        ) : (
          <strong>{house?.name || houseCode}</strong>
        )}
        {houses.length > 1 && (
          <select
            aria-label="Changer de bâtiment"
            value={houseCode}
            onChange={(e) => navigate(section ? `${houseBasePath(e.target.value)}/${section.path}` : houseBasePath(e.target.value))}
          >
            {houses.map((h) => (
              <option key={h.houseCode} value={h.houseCode}>{h.name}</option>
            ))}
          </select>
        )}
      </div>
      <Outlet context={{ ...shell, house, batch, loadBatch }} />
    </div>
  );
}
