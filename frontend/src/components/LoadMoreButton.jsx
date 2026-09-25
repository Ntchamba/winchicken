import { Loader2 } from "lucide-react";
import "./task-complete-button.css";
import "./load-more.css";

/**
 * "Afficher plus" under a list read page by page (`usePagedList`). Says how many rows are
 * shown out of how many, so a cut list never passes for a complete one.
 *
 * @param {{hasMore: boolean, loading: boolean, onClick: () => void, shown: number, total: ?number}} props
 */
export default function LoadMoreButton({ hasMore, loading, onClick, shown, total }) {
  if (!hasMore) return null;
  return (
    <div className="load-more">
      {total != null && (
        <span className="load-more-count">{shown} sur {total} affichés</span>
      )}
      <button type="button" className="task-undo-button" onClick={onClick} disabled={loading}>
        {loading ? <Loader2 size={15} className="spin" /> : null}
        Afficher plus
      </button>
    </div>
  );
}
