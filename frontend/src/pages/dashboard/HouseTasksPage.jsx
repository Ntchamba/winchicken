import { useCallback, useEffect, useState } from "react";
import { useOutletContext, useParams } from "react-router-dom";
import TasksNowPanel from "../../components/TasksNowPanel";
import AssignmentsPanel from "../../components/AssignmentsPanel";
import { housesApi } from "../../api/endpoints";
import useDocumentTitle from "../../hooks/useDocumentTitle";

/**
 * "Tâches" destination of the house hub: every protocol task due today — feeding, cleaning,
 * medication, whatever the protocol lines say — split into to-do and done, then the house's
 * standing assignments. Layout only: the rows are TasksNowPanel's, completion is its
 * TaskCompleteButton and the data is the same GET /houses/{code}/tasks-now/ as before.
 */
export default function HouseTasksPage() {
  const { houseCode } = useParams();
  const { house, batch } = useOutletContext();
  useDocumentTitle(`Tâches — ${house?.name || houseCode}`);

  const [tasksNow, setTasksNow] = useState({ dayOfCycle: null, tasks: [] });
  const [assignmentsKey, setAssignmentsKey] = useState(0);

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
    loadTasksNow();
  }, [loadTasksNow]);

  const pending = tasksNow.tasks.filter((task) => !task.done);
  const done = tasksNow.tasks.filter((task) => task.done);

  return (
    <>
      <div className="section-row"><h1 className="house-section-title">Tâches</h1></div>
      {batch === null && <p className="empty-state">Ce bâtiment n'a pas encore de bande.</p>}
      {batch && (
        <>
          <div className="section-row"><h2>À faire ({pending.length})</h2></div>
          {pending.length === 0 && done.length > 0 ? (
            <p className="empty-state" style={{ marginBottom: 18 }}>Toutes les tâches du jour sont faites.</p>
          ) : (
            <TasksNowPanel tasksNow={{ ...tasksNow, tasks: pending }} houseCode={houseCode} onAssigned={handleAssigned} />
          )}

          {done.length > 0 && (
            <>
              <div className="section-row"><h2>Faites ({done.length})</h2></div>
              <TasksNowPanel tasksNow={{ dayOfCycle: null, tasks: done }} houseCode={houseCode} onAssigned={handleAssigned} />
            </>
          )}
        </>
      )}

      {/* Outside the `batch &&` block on purpose: a house between two batches still carries its
          assignments, and they were exactly as invisible as the ones FIX 4 is about. */}
      <AssignmentsPanel houseCode={houseCode} reloadKey={assignmentsKey} onChanged={loadTasksNow} />
    </>
  );
}
