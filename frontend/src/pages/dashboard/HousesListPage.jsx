import { useNavigate, useOutletContext } from "react-router-dom";
import { Bird } from "lucide-react";
import "../../styles/dashboard-theme.css";

export default function HousesListPage() {
  const { houses } = useOutletContext();
  const navigate = useNavigate();

  return (
    <div className="page-wrap">
      <div className="breadcrumb">Tableau de bord / <strong>Bâtiments</strong></div>
      {houses.length === 0 ? (
        <p className="empty-state">Aucun bâtiment configuré pour le moment.</p>
      ) : (
        <div className="house-list">
          {houses.map((house) => (
            <button key={house.houseCode} className="house-item" onClick={() => navigate(`/dashboard/houses/${house.houseCode}`)}>
              <div className="house-item-main">
                <span className="house-avatar"><Bird size={18} strokeWidth={1.8} /></span>
                <div>
                  <p className="house-name">{house.name}</p>
                  <p className="house-sub">{house.houseCode}</p>
                </div>
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
