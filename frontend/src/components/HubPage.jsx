import { Link } from "react-router-dom";
import "../pages/dashboard/global-overview.css";
import "./hub-page.css";
import { TIER_WORD } from "../utils/statusTier";

/**
 * Hub-and-spoke landing view: one core node summarising the whole, one branch card per
 * destination. Same tree as "Bilan global" (GlobalOverviewPage) — it renders the very same
 * `.tree*` classes from global-overview.css, so the two cannot drift apart visually — but
 * parameterised by a section list, so the house view and Finances build their hubs from data
 * rather than each carrying a bespoke copy.
 *
 * Branches are real links, not buttons calling navigate(): each destination is its own route,
 * so the browser's back button, long-press "open in new tab" and screen-reader link lists all
 * work without any extra code.
 *
 * @param {{label: string, detail?: string, tier?: "good"|"watch"|"critical"}} core - The
 *   centre node. `tier` only picks the colour; it is never computed here.
 * @param {{key: string, title: string, Icon: import("react").ComponentType, to: string,
 *   value?: import("react").ReactNode, unit?: string, message?: string,
 *   tier?: "good"|"watch"|"critical"}[]} sections - One branch each, in display order.
 * @param {string} ariaLabel - Names the branch list for assistive tech (French).
 */
export default function HubPage({ core, sections, ariaLabel }) {
  return (
    <div className="tree hub-tree">
      <div className={`tree-core tree-core--${core.tier || "good"}`} role="status">
        <span className="tree-core-label">{core.label}</span>
        {core.detail && <span className="tree-core-tier">{core.detail}</span>}
      </div>

      <div className="tree-trunk" aria-hidden="true" />

      <nav className="tree-branches" aria-label={ariaLabel}>
        {sections.map(({ key, title, Icon, to, value, unit, message, tier }) => (
          <div className="tree-branch" key={key}>
            <div className="tree-limb" aria-hidden="true" />
            <Link className={`tree-node hub-node tree-node--${tier || "good"}`} to={to}>
              <span className="tree-node-icon"><Icon size={22} strokeWidth={1.9} aria-hidden="true" /></span>
              <span className="tree-node-title">{title}</span>
              {value != null && value !== "" && <span className="tree-node-value">{value}</span>}
              {unit && <span className="tree-node-unit">{unit}</span>}
              {message && <span className="tree-node-message">{message}</span>}
              {tier && <span className={`tree-node-tier tree-node-tier--${tier}`}>{TIER_WORD[tier]}</span>}
            </Link>
          </div>
        ))}
      </nav>
    </div>
  );
}
