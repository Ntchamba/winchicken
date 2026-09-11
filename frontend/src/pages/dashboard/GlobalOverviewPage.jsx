import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Coins, HeartPulse, Package } from "lucide-react";
import { farmApi } from "../../api/endpoints";
import QuickLinksBar from "../../components/QuickLinksBar";
import useDocumentTitle from "../../hooks/useDocumentTitle";
import "./global-overview.css";

// Each branch: where it goes, and how it is labelled. The *status* never comes from here —
// it is computed server-side (apps/core/overview.py) so the rules live in one place.
const BRANCHES = [
  { key: "finance", title: "Finances", Icon: Coins, to: "/dashboard/finances" },
  { key: "stock", title: "Stock", Icon: Package, to: "/dashboard/stock" },
  { key: "health", title: "Santé du cheptel", Icon: HeartPulse, to: "/dashboard/houses" },
];

const TIER_WORD = { good: "Bon", watch: "À surveiller", critical: "Critique" };

function formatValue(branch) {
  if (branch.key === "finance") return Number(branch.value || 0).toLocaleString();
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
      .catch(() => setError("Impossible de charger le bilan global."));
  }, []);

  if (error) return <p className="empty-state">{error}</p>;
  if (!overview) return <p className="empty-state">Chargement du bilan…</p>;

  const { core, branches } = overview;

  return (
    <div className="overview-page">
      <div className="section-heading">
        <div>
          <p className="section-kicker">VUE D'ENSEMBLE</p>
          <h1>Bilan global</h1>
        </div>
      </div>

      <QuickLinksBar />

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
                </button>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
