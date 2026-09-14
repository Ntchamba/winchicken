import { useEffect, useMemo, useRef, useState } from "react";
import { Search } from "lucide-react";
import { searchApi } from "../api/endpoints";

const GROUPS = [
  { key: "houses", label: "Bâtiments" },
  { key: "batches", label: "Bandes" },
  { key: "stockItems", label: "Stock" },
];

function resultLabel(group, item) {
  return item.name;
}

function resultPath(group, item) {
  if (group === "houses") return `/dashboard/houses/${item.houseCode}`;
  if (group === "batches") return `/dashboard/houses/${item.houseCode}`;
  return "/dashboard/stock";
}

/**
 * Sidebar quick-search bar (2026-08-26) — debounced (275ms), grouped dropdown (Bâtiments /
 * Bandes / Stock), arrow-key + Enter navigation, "Aucun résultat" empty state. Reuses the
 * `onNavigate` prop DashboardLayout already threads through every other sidebar link, so
 * routing stays owned by DashboardShellContent, not this component.
 *
 * @param {(path: string) => void} onNavigate
 */
export default function SidebarSearch({ onNavigate }) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState(null);
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);
  const ref = useRef(null);

  useEffect(() => {
    const trimmed = query.trim();
    if (!trimmed) {
      setResults(null);
      return;
    }
    const id = setTimeout(() => {
      searchApi.query(trimmed).then(({ data }) => setResults(data));
    }, 275);
    return () => clearTimeout(id);
  }, [query]);

  useEffect(() => {
    function onClickOutside(e) {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    }
    document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, []);

  const flatResults = useMemo(() => {
    if (!results) return [];
    return GROUPS.flatMap(({ key }) => (results[key] || []).map((item) => ({ group: key, item })));
  }, [results]);

  const select = (entry) => {
    if (!entry) return;
    onNavigate(resultPath(entry.group, entry.item));
    setOpen(false);
    setQuery("");
    setResults(null);
  };

  const onKeyDown = (e) => {
    if (!open || flatResults.length === 0) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActiveIndex((i) => (i + 1) % flatResults.length);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActiveIndex((i) => (i <= 0 ? flatResults.length - 1 : i - 1));
    } else if (e.key === "Enter") {
      e.preventDefault();
      select(flatResults[activeIndex] ?? flatResults[0]);
    } else if (e.key === "Escape") {
      setOpen(false);
    }
  };

  const showDropdown = open && query.trim().length > 0;

  return (
    <div className="sidebar-search" ref={ref}>
      <Search size={14} className="sidebar-search-icon" />
      <input
        type="text"
        value={query}
        placeholder="Rechercher…"
        onChange={(e) => {
          setQuery(e.target.value);
          setOpen(true);
          setActiveIndex(-1);
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={onKeyDown}
      />

      {showDropdown && (
        <div className="sidebar-search-dropdown">
          {!results && <p className="sidebar-search-empty">Recherche…</p>}
          {results && flatResults.length === 0 && <p className="sidebar-search-empty">Aucun résultat</p>}
          {GROUPS.map(({ key, label }) => {
            const items = results?.[key] || [];
            if (items.length === 0) return null;
            return (
              <div key={key}>
                <p className="sidebar-search-group-label">{label}</p>
                {items.map((item) => {
                  const flatIndex = flatResults.findIndex((r) => r.group === key && r.item === item);
                  return (
                    <button
                      key={item.houseCode || item.batchCode || item.itemCode}
                      className={`sidebar-search-result ${flatIndex === activeIndex ? "active" : ""}`}
                      onMouseEnter={() => setActiveIndex(flatIndex)}
                      onClick={() => select({ group: key, item })}
                    >
                      {resultLabel(key, item)}
                      {key === "batches" && <span>{item.houseName}</span>}
                    </button>
                  );
                })}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
