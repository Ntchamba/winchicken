import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import HouseProtocolForm from "../../components/HouseProtocolForm";
import { housesApi } from "../../api/endpoints";
import { buildProtocolSchedules } from "../../utils/protocolRows";
import useDocumentTitle from "../../hooks/useDocumentTitle";

// Kept as a plain full-page route (2026-08-25) even after the "Modifier" buttons on the
// global/per-house dashboard views moved to `ProtocolEditModal` — this stays useful as a
// direct/shareable link straight to a house's protocol, and duplicating the fetch/save logic
// here is cheap compared to teaching DashboardShell to open a modal from a URL (which would
// need to reconcile two "source of truth" mechanisms — route vs. modal open state — for no
// real benefit). See ProtocolEditModal's docstring and root README.md "Autonomous decisions".
export default function HouseProtocolPage() {
  useDocumentTitle("Protocole du bâtiment");
  const { houseCode } = useParams();
  const navigate = useNavigate();
  const [categories, setCategories] = useState(null);
  const [schedules, setSchedules] = useState(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    Promise.all([
      housesApi.listProtocolCategories(houseCode),
      housesApi.getProtocol(houseCode),
    ]).then(([categoriesRes, protocolRes]) => {
      const cats = categoriesRes.data.results || categoriesRes.data;
      setCategories(cats);
      setSchedules(buildProtocolSchedules(cats, protocolRes.data));
    });
  }, [houseCode]);

  const handleSave = async (payload) => {
    setSaving(true);
    try {
      await housesApi.putProtocol(houseCode, payload.protocolLines);
      // Navigate back to the house view rather than staying in place — it re-fetches on mount,
      // so the "tâches à effectuer maintenant" panel there reflects this save immediately.
      navigate(`/dashboard/houses/${houseCode}`);
    } finally {
      setSaving(false);
    }
  };

  if (!categories || !schedules) return <div className="page-wrap"><p className="empty-state">Chargement…</p></div>;

  return (
    <HouseProtocolForm
      initialCategories={categories}
      initialSchedules={schedules}
      mode="management"
      houseCode={houseCode}
      saving={saving}
      onSave={handleSave}
    />
  );
}
