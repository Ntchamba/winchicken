import { useCallback, useEffect, useState } from "react";
import { useNavigate, useOutletContext, useParams } from "react-router-dom";
import HubPage from "../../components/HubPage";
import GrowthCurves from "../../components/GrowthCurves";
import WeighingSection from "../../components/WeighingSection";
import QuickEntryPanel from "../../components/QuickEntryPanel";
import ProtocolEditModal from "../../components/ProtocolEditModal";
import ConfirmDialog from "../../components/ConfirmDialog";
import TasksNowPanel from "../../components/TasksNowPanel";
import AssignmentsPanel from "../../components/AssignmentsPanel";
import WeeklyKpiCharts from "../../components/WeeklyKpiCharts";
import CycleTimeline from "../../components/CycleTimeline";
import { batchesApi, housesApi } from "../../api/endpoints";
import { getServerErrorMessage } from "../../api/errors";
import { countOpenIncidents } from "../../api/incidents";
import useDocumentTitle from "../../hooks/useDocumentTitle";
import { HOUSE_SECTIONS, houseBasePath } from "./houseSections";
import "../../styles/house-protocol-theme-light.css";
import "../../styles/dashboard-theme.css";

// batch.status is the raw BatchStatus backend enum (ACTIVE/CLOSED) — displayed only
// through this French label map, never shown raw.
const BATCH_STATUS_LABELS = { ACTIVE: "En cours", CLOSED: "Clôturée" };

/**
 * House hub (`/dashboard/houses/:houseCode`, index route of HouseLayout): the house and batch
 * header with its actions, then one branch per destination (HOUSE_SECTIONS). Each branch's
 * figure comes from the same query its destination lists, so the two cannot disagree.
 */
export default function HouseDetailPage() {
  const { houseCode } = useParams();
  const { house, batch, loadBatch, refreshHouses } = useOutletContext();
  const navigate = useNavigate();
  useDocumentTitle(house?.name || "Bâtiment");

  const [openCases, setOpenCases] = useState(null);
  const [weeklyKpi, setWeeklyKpi] = useState(null);
  const [growthSeries, setGrowthSeries] = useState([]);
  const [tasksNow, setTasksNow] = useState({ dayOfCycle: null, tasks: [] });
  const [assignmentsKey, setAssignmentsKey] = useState(0);
  const [closing, setClosing] = useState(false);
  const [confirmClose, setConfirmClose] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [editingProtocol, setEditingProtocol] = useState(false);
  // Kept per-dialog rather than as one page-level banner: both dialogs stay open on
  // failure, so the message belongs inside the one the user is looking at.
  const [closeError, setCloseError] = useState("");
  const [deleteError, setDeleteError] = useState("");

  // Each stored with what it was loaded for, so another house/batch never shows stale figures.
  const batchCode = batch?.batch_code;
  useEffect(() => {
    if (batchCode) batchesApi.weeklyKpi(batchCode).then((res) => setWeeklyKpi({ batchCode, data: res.data }));
  }, [batchCode]);
  const currentWeeklyKpi = weeklyKpi && weeklyKpi.batchCode === batchCode ? weeklyKpi.data : null;

  useEffect(() => {
    countOpenIncidents(houseCode).then((count) => setOpenCases({ houseCode, count })).catch(() => {});
  }, [houseCode]);
  const openCasesCount = openCases?.houseCode === houseCode ? openCases.count : null;

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
    loadGrowthCurve();
    loadTasksNow();
  }, [loadGrowthCurve, loadTasksNow]);

  // Per-destination figures for the hub branches, keyed like HOUSE_SECTIONS.
  const branchFigures = {
    cases: openCasesCount == null
      ? {}
      : {
        value: openCasesCount,
        unit: openCasesCount === 1 ? "cas ouvert" : "cas ouverts",
        message: openCasesCount === 0 ? "Aucun cas en attente" : "Voir et résoudre",
        tier: openCasesCount > 0 ? "watch" : "good",
      },
  };
  const hubSections = HOUSE_SECTIONS.map(({ key, path, label, Icon }) => ({
    key, title: label, Icon, to: `${houseBasePath(houseCode)}/${path}`, ...branchFigures[key],
  }));

  const handleClose = async () => {
    if (!batch || closing) return;
    setCloseError("");
    setClosing(true);
    try {
      await batchesApi.close(batch.batch_code);
      setConfirmClose(false);
      navigate(0);
    } catch (err) {
      // navigate(0) never runs on failure, so without this the dialog just sits there.
      setCloseError(getServerErrorMessage(err, "Cette bande n'a pas pu être clôturée."));
    } finally {
      setClosing(false);
    }
  };

  const handleDelete = async () => {
    if (!batch || deleting) return;
    setDeleteError("");
    setDeleting(true);
    try {
      await batchesApi.remove(batch.batch_code);
      setConfirmDelete(false);
      refreshHouses();
      navigate(0);
    } catch (err) {
      setDeleteError(getServerErrorMessage(err, "Cette bande n'a pas pu être supprimée."));
    } finally {
      setDeleting(false);
    }
  };

  return (
    <>
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
          onCancel={() => { setConfirmClose(false); setCloseError(""); }}
          busy={closing}
          error={closeError}
        />
      )}

      {confirmDelete && (
        <ConfirmDialog
          message="Supprimer cette bande est définitif et supprime aussi tout son historique lié : journaux quotidiens, alertes, cas signalés, vaccinations, mouvements de stock, dépenses et ventes. Continuer ?"
          confirmLabel="Supprimer définitivement"
          onConfirm={handleDelete}
          onCancel={() => { setConfirmDelete(false); setDeleteError(""); }}
          busy={deleting}
          error={deleteError}
        />
      )}

      {batch === null && <p className="empty-state">Ce bâtiment n'a pas encore de bande.</p>}

      <HubPage
        ariaLabel="Sections du bâtiment"
        core={{
          label: batch ? (batch.name || batch.batch_code) : batch === null ? "Aucune bande" : "…",
          detail: tasksNow.dayOfCycle != null ? `Jour ${tasksNow.dayOfCycle} du cycle` : undefined,
        }}
        sections={hubSections}
      />

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

          {currentWeeklyKpi && <WeeklyKpiCharts weeklyKpi={currentWeeklyKpi} />}
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
    </>
  );
}
