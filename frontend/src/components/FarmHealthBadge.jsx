import { useEffect, useState } from "react";
import { AlertOctagon, AlertTriangle, CheckCircle2 } from "lucide-react";
import { batchesApi } from "../api/endpoints";

const TIER_CONFIG = {
  good: { Icon: CheckCircle2, className: "farm-health-good" },
  watch: { Icon: AlertTriangle, className: "farm-health-watch" },
  critical: { Icon: AlertOctagon, className: "farm-health-critical" },
};

/**
 * Farm health score badge (2026-08-26, docs/deviations.md Part 16, Part A) — global view only.
 * Self-fetches `GET /api/batches/health-score/`; see `apps.batches.calculations.
 * farm_health_score` for the full, documented tier rule set (also in the root README's "Farm
 * health score" section). Renders nothing while loading or on a fetch failure, rather than a
 * placeholder skeleton — this is a small, secondary-priority badge, not core page content
 * worth reserving layout space for before it resolves.
 */
export default function FarmHealthBadge() {
  const [score, setScore] = useState(null);

  useEffect(() => {
    batchesApi.healthScore().then(({ data }) => setScore(data)).catch(() => {});
  }, []);

  if (!score) return null;
  const { Icon, className } = TIER_CONFIG[score.tier] || TIER_CONFIG.good;

  return (
    <div className={`farm-health-badge ${className}`}>
      <Icon size={22} strokeWidth={1.8} />
      <div>
        <p className="farm-health-label">{score.label}</p>
        <p className="farm-health-reason">{score.reason}</p>
      </div>
    </div>
  );
}
