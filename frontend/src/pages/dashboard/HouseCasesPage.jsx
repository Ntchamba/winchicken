import { useState } from "react";
import { useOutletContext, useParams } from "react-router-dom";
import IncidentsPanel from "../../components/IncidentsPanel";
import UnusualCaseReportForm from "../../components/UnusualCaseReportForm";
import useDocumentTitle from "../../hooks/useDocumentTitle";

/** "Cas signalés" destination of the house hub: open cases, history, and reporting one. */
export default function HouseCasesPage() {
  const { houseCode } = useParams();
  const { house, batch } = useOutletContext();
  useDocumentTitle(`Cas signalés — ${house?.name || houseCode}`);
  const [incidentsKey, setIncidentsKey] = useState(0);

  return (
    <>
      {/* No page title of its own: IncidentsPanel's header already reads "Cas signalés", and a
          second copy of it directly above was the first thing the page said twice. */}
      {batch && (
        <div style={{ marginBottom: 18 }}>
          {/* Refreshes the list below: the form used to collapse silently while the list
              stayed as it was, which reads as a report that never went through. */}
          <UnusualCaseReportForm
            batchCode={batch.batch_code}
            onReported={() => setIncidentsKey((key) => key + 1)}
          />
        </div>
      )}
      <IncidentsPanel houseCode={houseCode} reloadKey={incidentsKey} />
    </>
  );
}
