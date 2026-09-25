import { useCallback, useEffect, useState } from "react";
import { useNavigate, useOutletContext, useParams } from "react-router-dom";
import HubPage from "../../components/HubPage";
import ProtocolEditModal from "../../components/ProtocolEditModal";
import ConfirmDialog from "../../components/ConfirmDialog";
import CycleTimeline from "../../components/CycleTimeline";
import { batchesApi, housesApi } from "../../api/endpoints";
import { getServerErrorMessage } from "../../api/errors";
import { countOpenIncidents } from "../../api/incidents";
import useDocumentTitle from "../../hooks/useDocumentTitle";
import { HOUSE_SECTIONS, houseBasePath } from "./houseSections";
import "../../styles/house-protocol-theme-light.css";
import "../../styles/dashboard-theme.css";
import { formatDateFR } from "../../utils/localDate";

// Farm-locale decimals ("1,16"). The shared chart kit's formatNumber takes over once it lands.
const formatNumber = (value, digits) => Number(value).toLocaleString("fr-FR", { maximumFractionDigits: digits });

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
  const [growthSeries, setGrowthSeries] = useState([]);
  // Hub figures read "Chargement…" until their data is in, not "Aucune pesée" / "0 faites".
  const [loadedFor, setLoadedFor] = useState({ growth: null, tasks: null });
  const [tasksNow, setTasksNow] = useState({ dayOfCycle: null, tasks: [] });
  const [closing, setClosing] = useState(false);
  const [confirmClose, setConfirmClose] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [editingProtocol, setEditingProtocol] = useState(false);
  // Kept per-dialog rather than as one page-level banner: both dialogs stay open on
  // failure, so the message belongs inside the one the user is looking at.
  const [closeError, setCloseError] = useState("");
  const [deleteError, setDeleteError] = useState("");

  // Stored with the house it was loaded for, so another house never shows stale figures.
  useEffect(() => {
    countOpenIncidents(houseCode).then((count) => setOpenCases({ houseCode, count })).catch(() => {});
  }, [houseCode]);
  const openCasesCount = openCases?.houseCode === houseCode ? openCases.count : null;

  const loadGrowthCurve = useCallback(() => {
    batchesApi.growthCurves({ house_code: houseCode }).then(({ data }) => { setGrowthSeries(data); setLoadedFor((l) => ({ ...l, growth: houseCode })); });
  }, [houseCode]);

  const loadTasksNow = useCallback(() => {
    housesApi.tasksNow(houseCode).then(({ data }) => { setTasksNow(data); setLoadedFor((l) => ({ ...l, tasks: houseCode })); });
  }, [houseCode]);

  useEffect(() => {
    loadGrowthCurve();
    loadTasksNow();
  }, [loadGrowthCurve, loadTasksNow]);

  // Latest logged value of a growth-curve field — the same series Évolution and Pesée draw.
  const latest = (field) => {
    const points = growthSeries[0]?.points || [];
    for (let i = points.length - 1; i >= 0; i -= 1) if (points[i][field] != null) return points[i];
    return null;
  };
  const survival = latest("survivalPct");
  const weighing = latest("weightKg");
  const tasksToDo = tasksNow.tasks.filter((task) => !task.done).length;
  const tasksDone = tasksNow.tasks.length - tasksToDo;
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
    evolution: survival
      ? { value: `${formatNumber(survival.survivalPct, 1)} %`, unit: "survie", message: `Au jour ${survival.dayOfCycle} · croissance, indice de consommation, mortalité` }
      : { message: "Croissance, indice de consommation, mortalité" },
    tasks: loadedFor.tasks !== houseCode ? { message: "Chargement…" } : {
      value: tasksToDo,
      unit: "à faire aujourd'hui",
      message: `${tasksDone} faite${tasksDone === 1 ? "" : "s"} · saisie du jour, alimentation, soins`,
    },
    weighing: loadedFor.growth !== houseCode ? { message: "Chargement…" } : weighing
      ? { value: `${formatNumber(weighing.weightKg, 2)} kg`, unit: "poids moyen", message: `Dernière pesée au jour ${weighing.dayOfCycle}` }
      : { message: "Aucune pesée enregistrée" },
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
            <span className="house-chip">{batch === undefined ? "CHARGEMENT…" : batch ? BATCH_STATUS_LABELS[batch.status] || batch.status : "AUCUNE BANDE ACTIVE"}</span>
            <h1 style={{ margin: "7px 0 0", fontFamily: "'Space Grotesk',sans-serif", fontSize: 22 }}>{house?.name || houseCode}</h1>
            {batch && (
              <p className="schedule-note">
                {batch.name ? (
                  <>Bande {batch.name} <span style={{ color: "var(--muted)" }}>({batch.batch_code})</span></>
                ) : (
                  <>Bande {batch.batch_code}</>
                )}
                {" "}· {batch.current_count} volailles · démarrée le {formatDateFR(batch.start_date)}
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

      {batch && <CycleTimeline houseCode={houseCode} />}

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
