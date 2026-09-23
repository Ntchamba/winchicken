import { useState } from "react";
import { CheckCircle2, Download, Smartphone } from "lucide-react";
import { promptInstall, useInstallState } from "../pwa/installPrompt";

/**
 * "Application" card in Paramètres: install Winchicken as an app (home-screen / desktop icon,
 * full screen without the browser bars). A button the user chooses to press — never a popup.
 * Browsers that do not offer the install event get the manual steps instead.
 */
export default function InstallAppCard() {
  const { installed, canInstall, ios } = useInstallState();
  const [message, setMessage] = useState("");

  const install = async () => {
    setMessage("");
    const outcome = await promptInstall();
    if (outcome === "dismissed") setMessage("Installation annulée. Vous pourrez la relancer plus tard depuis cette page.");
  };

  return (
    <div className="card house-card" style={{ marginTop: 18 }}>
      <h2 style={{ display: "flex", alignItems: "center", gap: 8, margin: "0 0 6px" }}>
        <Smartphone size={18} strokeWidth={1.8} aria-hidden="true" /> Application
      </h2>
      <p className="schedule-note">
        Installez Winchicken sur ce téléphone ou cet ordinateur : une icône sur l'écran d'accueil,
        et l'application s'ouvre en plein écran, sans la barre du navigateur. Une connexion au
        serveur de la ferme reste nécessaire pour enregistrer quoi que ce soit.
      </p>

      {installed ? (
        <p className="schedule-note" style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 12, color: "var(--success, #16a34a)" }}>
          <CheckCircle2 size={18} strokeWidth={2} aria-hidden="true" /> Winchicken est installée sur cet appareil.
        </p>
      ) : canInstall ? (
        <button className="save-button" style={{ width: "auto", marginTop: 12 }} onClick={install}>
          <Download size={16} strokeWidth={2} aria-hidden="true" /> Installer l'application
        </button>
      ) : ios ? (
        <p className="schedule-note" style={{ marginTop: 12 }}>
          Sur iPhone ou iPad : dans Safari, touchez le bouton Partager, puis « Sur l'écran d'accueil ».
        </p>
      ) : (
        <p className="schedule-note" style={{ marginTop: 12 }}>
          Votre navigateur ne propose pas l'installation pour le moment. Dans Chrome ou Edge, ouvrez
          le menu ⋮ puis « Installer Winchicken » (ou « Ajouter à l'écran d'accueil » sur Android).
        </p>
      )}
      {message && <p className="schedule-note" role="status" style={{ marginTop: 10 }}>{message}</p>}
    </div>
  );
}
