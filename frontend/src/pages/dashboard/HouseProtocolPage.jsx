import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import HouseProtocolForm from "../../components/HouseProtocolForm";
import { housesApi } from "../../api/endpoints";

export default function HouseProtocolPage() {
  const { houseCode } = useParams();
  const [categories, setCategories] = useState(null);
  const [schedules, setSchedules] = useState(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    Promise.all([
      housesApi.listProtocolCategories(houseCode),
      housesApi.getProtocol(houseCode),
    ]).then(([categoriesRes, protocolRes]) => {
      const cats = categoriesRes.data.results || categoriesRes.data;
      const map = Object.fromEntries(cats.map((c) => [c.id, []]));
      for (const line of protocolRes.data) {
        map[line.category]?.push({
          id: line.id,
          fromValue: line.from_value,
          fromUnit: line.from_unit.charAt(0) + line.from_unit.slice(1).toLowerCase(),
          toValue: line.to_value || 1,
          toUnit: line.to_unit.charAt(0) + line.to_unit.slice(1).toLowerCase(),
          untilEnd: line.until_end,
          what: line.what,
          details: line.details,
        });
      }
      setCategories(cats);
      setSchedules(map);
    });
  }, [houseCode]);

  const handleSave = async (payload) => {
    setSaving(true);
    try {
      await housesApi.putProtocol(houseCode, payload.protocolLines);
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
