import { useState } from "react";
import { Link } from "react-router-dom";
import { Info } from "lucide-react";
import HomeDashboard from "../components/HomeDashboard";
import HouseProtocolForm from "../components/HouseProtocolForm";
import StockParametersForm from "../components/StockParametersForm";
import { DEMO_ALERTS, DEMO_HOUSES, DEMO_HOUSE_HEADER, DEMO_SCHEDULES, DEMO_STOCK } from "./demoData";
import "../styles/house-protocol-theme-light.css";
import "../styles/dashboard-theme.css";

const VIEWS = [
  { id: "dashboard", label: "Vue d'ensemble" },
  { id: "protocol", label: "Protocole du bâtiment" },
  { id: "stock", label: "Paramètres de stock" },
];

// Entirely client-side: no network calls, no writes to the database (cahier des charges 5.4).
export default function DemoPage() {
  const [view, setView] = useState("dashboard");

  return (
    <div className="app-shell">
      <div className="page-wrap">
        <div className="banner demo">
          <Info size={16} strokeWidth={2} />
          Mode démo — données d'exemple uniquement, rien n'est enregistré ni envoyé à un serveur.
          <span style={{ marginLeft: "auto" }}><Link to="/" style={{ color: "inherit" }}>Retour à l'accueil</Link></span>
        </div>

        <div className="tabs" style={{ marginBottom: 24 }}>
          {VIEWS.map((v) => (
            <button key={v.id} className={`tab ${view === v.id ? "active" : ""}`} onClick={() => setView(v.id)}>
              {v.label}
            </button>
          ))}
        </div>
      </div>

      {view === "dashboard" && (
        <HomeDashboard farmName="Ferme de démonstration" houses={DEMO_HOUSES} alerts={DEMO_ALERTS} onNavigate={() => {}} />
      )}
      {view === "protocol" && (
        <HouseProtocolForm initialHeader={DEMO_HOUSE_HEADER} initialSchedules={DEMO_SCHEDULES} mode="management" onSave={() => {}} />
      )}
      {view === "stock" && (
        <StockParametersForm initialData={DEMO_STOCK} mode="management" onSave={() => {}} />
      )}
    </div>
  );
}
