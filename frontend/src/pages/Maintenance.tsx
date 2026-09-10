import './Maintenance.css';

export default function Maintenance() {
  return (
    <div className="maintenance-page">
      <div className="maintenance-card">
        <div className="maintenance-icon" aria-hidden="true">🛠️</div>
        <h1>Application en maintenance</h1>
        <p>
          Nous effectuons actuellement des opérations de maintenance afin
          d'améliorer votre expérience.
        </p>
        <p className="maintenance-sub">
          Le service sera de nouveau disponible très prochainement. Merci de
          votre patience.
        </p>
        <button
          className="maintenance-retry"
          onClick={() => window.location.reload()}
        >
          Réessayer
        </button>
      </div>
    </div>
  );
}
