import { useEffect, useState } from "react";
import { getServerErrorMessage } from "../../api/errors";
import { useNavigate } from "react-router-dom";
import { Coins, HeartPulse, Package } from "lucide-react";
import { farmApi } from "../../api/endpoints";
import QuickLinksBar from "../../components/QuickLinksBar";
import useDocumentTitle from "../../hooks/useDocumentTitle";
import { formatMoney } from "../../utils/money";
import "./global-overview.css";
import { TIER_WORD } from "../../utils/statusTier";

// Each branch: where it goes, and how it is labelled. The *status* never comes from here —
// it is computed server-side (apps/core/overview.py) so the rules live in one place.
const BRANCHES = [
  { key: "finance", title: "Finances", Icon: Coins, to: "/dashboard/finances" },
  { key: "stock", title: "Stock", Icon: Package, to: "/dashboard/stock" },
  { key: "health", title: "Santé du cheptel", Icon: HeartPulse, to: "/dashboard/houses" },
];


function formatValue(branch) {
  if (branch.key === "finance") return formatMoney(branch.value);
  return String(branch.value ?? "");
}

/**
 * "Bilan global" — a tree: one core node for the farm's overall state, three branches for
 * finances, stock and cheptel health, each a link into the view that already owns that data.
 *
 * Purely additive: it reads the same records the Finances / Stock / Bâtiments pages read and
 * changes none of them. The tree is CSS + one small SVG-free layout (connectors are borders),
 * so there is no animation library and nothing to measure on resize.
 */
export default function GlobalOverviewPage() {
  useDocumentTitle("Bilan global");
  const navigate = useNavigate();
  const [overview, setOverview] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    farmApi.overview()
      .then(({ data }) => setOverview(data))
      .catch((err) => setError(getServerErrorMessage(err, "Le bilan global n'a pas pu être chargé. Réessayez.")));
  }, []);

  // The heading and the shortcuts render before the data does, on purpose: leaving the user
  // on a bare "Chargement…" with no way to navigate is worse than an empty tree for a moment.
  const header = (
    <>
      <div className="section-heading">
        <div>
          <p className="section-kicker">VUE D'ENSEMBLE</p>
          <h1>Bilan global</h1>
        </div>
      </div>
      <QuickLinksBar />
    </>
  );

  if (error) return <div className="overview-page">{header}<p className="empty-state">{error}</p></div>;
  if (!overview) {
    return <div className="overview-page">{header}<p className="empty-state">Chargement du bilan…</p></div>;
  }

  const { core, branches } = overview;

  return (
    <div className="overview-page">
      {header}

      <div className="tree">
        <div className={`tree-core tree-core--${core.tier}`} role="status">
          <span className="tree-core-label">{core.label}</span>
          <span className="tree-core-tier">{TIER_WORD[core.tier]}</span>
        </div>

        <div className="tree-trunk" aria-hidden="true" />

        <div className="tree-branches">
          {BRANCHES.map(({ key, title, Icon, to }) => {
            const branch = branches[key] || {};
            return (
              <div className="tree-branch" key={key}>
                <div className="tree-limb" aria-hidden="true" />
                <button
                  type="button"
                  className={`tree-node tree-node--${branch.tier || "good"}`}
                  onClick={() => navigate(to)}
                >
                  <span className="tree-node-icon"><Icon size={22} strokeWidth={1.9} /></span>
                  <span className="tree-node-title">{title}</span>
                  <span className="tree-node-value">{formatValue({ ...branch, key })}</span>
                  <span className="tree-node-unit">{branch.valueLabel}</span>
                  <span className="tree-node-message">{branch.message}</span>
                  <span className={`tree-node-tier tree-node-tier--${branch.tier || "good"}`}>{TIER_WORD[branch.tier || "good"]}</span>
                </button>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
