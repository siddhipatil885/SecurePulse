import type { SecurityEvent } from '../types';
import './DataPanels.css';

export default function RecentEvents({ events, onSelect }: { events: SecurityEvent[]; onSelect: (id: string) => void }) {
  return <section className="data-panel">
    <div className="panel-header"><h2 className="panel-title">Recent Incidents</h2></div>
    <div className="panel-content">{!events.length ? <div className="empty-state">No recent activity</div> :
      <div className="event-list">{events.map(event => <div key={event.id} className="event-item">
        <div className="event-time">{new Date(event.timestamp).toLocaleString()}</div>
        <div className="event-details"><button onClick={() => onSelect(event.id)}>Incident {event.id}: {event.type}</button>
          <p>{event.severity} · {event.status} · Camera {event.cameraId}</p>
          <p>{event.reason ?? 'Reason unavailable'}</p>
        </div>
      </div>)}</div>}
    </div>
  </section>;
}
