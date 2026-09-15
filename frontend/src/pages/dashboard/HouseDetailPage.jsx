import { useCallback, useEffect, useState } from "react";
import { useNavigate, useOutletContext, useParams } from "react-router-dom";
import GrowthCurves from "../../components/GrowthCurves";
import WeighingSection from "../../components/WeighingSection";
import QuickEntryPanel from "../../components/QuickEntryPanel";
import ProtocolEditModal from "../../components/ProtocolEditModal";
import ConfirmDialog from "../../components/ConfirmDialog";
import TasksNowPanel from "../../components/TasksNowPanel";
import AssignmentsPanel from "../../components/AssignmentsPanel";
import WeeklyKpiCharts from "../../components/WeeklyKpiCharts";
import UnusualCaseReportForm from "../../components/UnusualCaseReportForm";
import CycleTimeline from "../../components/CycleTimeline";
import IncidentsPanel from "../../components/IncidentsPanel";
import { batchesApi, housesApi } from "../../api/endpoints";
import useDocumentTitle from "../../hooks/useDocumentTitle";
import "../../styles/house-protocol-theme-light.css";
import "../../styles/dashboard-theme.css";
import QuickLinksBar from "../../components/QuickLinksBar";

// batch.status is the raw BatchStatus backend enum (ACTIVE/CLOSED) — displayed only
// through this French label map, never shown raw.
const BATCH_STATUS_LABELS = { ACTIVE: "En cours", CLOSED: "Clôturée" };

export default function HouseDetailPage() {
  const { houseCode } = useParams();
  const { houses, refreshHouses } = useOutletContext();
  const navigate = useNavigate();
  const house = houses.find((h) => h.houseCode === houseCode);
  useDocumentTitle(house?.name || "Bâtiment");

  const [batch, setBatch] = useState(null);
  const [weeklyKpi, setWeeklyKpi] = useState(null);
  const [growthSeries, setGrowthSeries] = useState([]);
  const [tasksNow, setTasksNow] = useState({ dayOfCycle: null, tasks: [] });
  const [assignmentsKey, setAssignmentsKey] = useState(0);
  const [closing, setClosing] = useState(false);
  const [confirmClose, setConfirmClose] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [editingProtocol, setEditingProtocol] = useState(false);

  const loadBatch = useCallback(() => {
    batchesApi.list(houseCode).then(({ data }) => {
      const results = data.results || data;
      const active = results.find((b) => b.status === "ACTIVE") || results[0];
      setBatch(active || null);
      if (active) {
        batchesApi.weeklyKpi(active.batch_code).then((res) => setWeeklyKpi(res.data));
      }
    });
  }, [houseCode]);

  const loadGrowthCurve = useCallback(() => {
    batchesApi.growthCurves({ house_code: houseCode }).then(({ data }) => setGrowthSeries(data));
  }, [houseCode]);

  const loadTasksNow = useCallback(() => {
    housesApi.tasksNow(houseCode).then(({ data }) => setTasksNow(data));
  }, [houseCode]);

  // An assignment changed in the tasks panel must also refresh the assignments card: two views
  // of the same rows must never be able to disagree.
  const handleAssigned = useCallback(() => {
    loadTasksNow();
    setAssignmentsKey((k) => k + 1);
  }, [loadTasksNow]);

  useEffect(() => {
    loadBatch();
    loadGrowthCurve();
    loadTasksNow();
  }, [loadBatch, loadGrowthCurve, loadTasksNow]);

  const handleClose = async () => {
    if (!batch) return;
    setClosing(true);
    try {
      await batchesApi.close(batch.batch_code);
      setConfirmClose(false);
      navigate(0);
    } finally {
      setClosing(false);
    }
  };

  const handleDelete = async () => {
    if (!batch) return;
    setDeleting(true);
    try {
      await batchesApi.remove(batch.batch_code);
      setConfirmDelete(false);
      refreshHouses();
      navigate(0);
    } finally {
      setDeleting(false);
    }
  };

  return (
    <div className="page-wrap">
      <QuickLinksBar />
      <div className="breadcrumb">
        Tableau de bord / <strong>{house?.name || houseCode}</strong>
        {houses.length > 1 && (
          <select value={houseCode} onChange={(e) => navigate(`/dashboard/houses/${e.target.value}`)}>
            {houses.map((h) => (
              <option key={h.houseCode} value={h.houseCode}>{h.name}</option>
            ))}
          </select>
        )}
      </div>

      <div className="card house-card" style={{ marginBottom: 18 }}>
        <div className="section-heading">
          <div>
            <span className="house-chip">{batch ? BATCH_STATUS_LABELS[batch.status] || batch.status : "AUCUNE BANDE ACTIVE"}</span>
            <h1 style={{ margin: "7px 0 0", fontFamily: "'Space Grotesk',sans-serif", fontSize: 22 }}>{house?.name || houseCode}</h1>
            {batch && (
              <p className="schedule-note">
                {batch.name ? (
                  <>Bande {batch.name} <span style={{ opacity: .6 }}>({batch.batch_code})</span></>
                ) : (
                  <>Bande {batch.batch_code}</>
                )}
                {" "}· {batch.current_count} volailles · démarrée le {batch.start_date}
              </p>
            )}
          </div>
          {/* Three-way severity scale — see .batch-action* in house-protocol-theme-light.css.
              Neutral (mint outline) / caution (amber) / destructive (solid red). */}
          <div style={{ display: "flex", gap: 10 }}>
            <button className="batch-action batch-action--edit" onClick={() => setEditingProtocol(true)}>
              Modifier le protocole
            </button>
            {batch?.status === "ACTIVE" && (
              <button className="batch-action batch-action--close" onClick={() => setConfirmClose(true)}>
                Clôturer la bande
              </button>
            )}
            {batch && (
              <button className="batch-action batch-action--delete" onClick={() => setConfirmDelete(true)}>
                Supprimer la bande
              </button>
            )}
          </div>
        </div>
      </div>

      {confirmClose && (
        <ConfirmDialog
          message="Clôturer cette bande est définitif et génère le rapport financier de clôture. Continuer ?"
          confirmLabel="Confirmer la clôture"
          onConfirm={handleClose}
          onCancel={() => setConfirmClose(false)}
          busy={closing}
        />
      )}

      {confirmDelete && (
        <ConfirmDialog
          message="Supprimer cette bande est définitif et supprime aussi tout son historique lié : journaux quotidiens, alertes, cas signalés, vaccinations, mouvements de stock, dépenses et ventes. Continuer ?"
          confirmLabel="Supprimer définitivement"
          onConfirm={handleDelete}
          onCancel={() => setConfirmDelete(false)}
          busy={deleting}
        />
      )}

      {!batch && <p className="empty-state">Ce bâtiment n'a pas encore de bande.</p>}

      <IncidentsPanel houseCode={houseCode} />

      {/* Outside the `batch &&` block on purpose: a house between two batches still carries its
          assignments, and they were exactly as invisible as the ones FIX 4 is about. */}
      <AssignmentsPanel houseCode={houseCode} reloadKey={assignmentsKey} onChanged={loadTasksNow} />

      {batch && (
        <>
          <CycleTimeline houseCode={houseCode} />

          <GrowthCurves series={growthSeries} scope="single" />

          <div className="section-row"><h2>Pesée</h2></div>
          <WeighingSection batches={[{ batchCode: batch.batch_code, name: batch.name }]} onLogged={loadGrowthCurve} />

          <div className="section-row"><h2>Tâches à effectuer maintenant</h2></div>
          <TasksNowPanel tasksNow={tasksNow} houseCode={houseCode} onAssigned={handleAssigned} />

          <div className="section-row"><h2>Saisie rapide du jour</h2></div>
          <QuickEntryPanel batches={[{ batch_code: batch.batch_code, name: batch.name }]} onLogged={loadGrowthCurve} />
          <div style={{ marginBottom: 18 }}>
            <UnusualCaseReportForm batchCode={batch.batch_code} />
          </div>

          {weeklyKpi && <WeeklyKpiCharts weeklyKpi={weeklyKpi} />}
        </>
      )}

      <ProtocolEditModal
        houseCode={editingProtocol ? houseCode : null}
        onClose={() => setEditingProtocol(false)}
        onSaved={() => {
          loadBatch();
          loadTasksNow();
          loadGrowthCurve();
          refreshHouses();
        }}
      />
    </div>
  );
}
