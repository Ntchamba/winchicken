import { useCallback, useEffect, useRef, useState } from "react";
import { employeesApi } from "../api/endpoints";
import { getServerErrorMessage } from "../api/errors";

const STORAGE_KEY = "winchicken_employee_import_job";
export const POLL_MS = 1500;

function remember(jobId) {
  try {
    if (jobId) localStorage.setItem(STORAGE_KEY, jobId);
    else localStorage.removeItem(STORAGE_KEY);
  } catch {
    // Private mode / blocked storage: the import still runs, it just is not resumed on return.
  }
}

function remembered() {
  try {
    return localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

/**
 * The employee Excel import, run as a background job on the server (2026-09-25): each new
 * account hashes a password (~1 s), so a large file outlived the request and was killed with
 * its temporary passwords. The upload returns a job at once; this polls it, shows progress,
 * and keeps the finished summary — temporary passwords included — until the admin closes it.
 * Leaving the page and coming back resumes the same job (its id is kept in localStorage; the
 * server only ever shows it to the admin who started it, for 24 h).
 *
 * @param {{onFinished?: () => void}} [options] - Called once when a job ends in `done`.
 */
export default function useEmployeeImport({ onFinished } = {}) {
  const [job, setJob] = useState(null);
  const [error, setError] = useState("");
  const [uploading, setUploading] = useState(false);
  const timer = useRef(null);
  const finishedRef = useRef(onFinished);
  useEffect(() => { finishedRef.current = onFinished; });

  const follow = useCallback(function poll(jobId) {
    clearTimeout(timer.current);
    employeesApi.importJob(jobId)
      .then(({ data }) => {
        setJob(data);
        if (data.status === "done") {
          finishedRef.current?.();
        } else if (data.status === "error") {
          remember(null);
          setError(data.detail || "Échec de l'import du fichier Excel.");
        } else {
          timer.current = setTimeout(() => poll(jobId), POLL_MS);
        }
      })
      .catch((err) => {
        if (err?.response?.status === 404) {
          remember(null);
          setJob(null);
          return;
        }
        // A dropped connection on a phone is not the end of the import: keep asking.
        timer.current = setTimeout(() => poll(jobId), POLL_MS * 2);
      });
  }, []);

  useEffect(() => {
    const jobId = remembered();
    if (jobId) follow(jobId);
    return () => clearTimeout(timer.current);
  }, [follow]);

  const start = async (file) => {
    setUploading(true);
    setError("");
    setJob(null);
    try {
      const { data } = await employeesApi.importXlsx(file);
      remember(data.jobId);
      setJob(data);
      follow(data.jobId);
    } catch (err) {
      setError(getServerErrorMessage(err, "Échec de l'import du fichier Excel."));
    } finally {
      setUploading(false);
    }
  };

  const dismiss = () => {
    const jobId = job?.jobId;
    clearTimeout(timer.current);
    remember(null);
    setJob(null);
    setError("");
    if (jobId) employeesApi.discardImportJob(jobId).catch(() => {});
  };

  const running = uploading || job?.status === "queued" || job?.status === "running";
  return {
    running,
    progress: running && job ? { processed: job.processed ?? 0, total: job.total } : null,
    result: job?.status === "done" ? job.result : null,
    error,
    start,
    dismiss,
  };
}
