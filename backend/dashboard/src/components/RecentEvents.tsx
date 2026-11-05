import React from 'react';
import type { SecurityEvent } from '../types';
import './DataPanels.css';

interface RecentEventsProps {
  events: SecurityEvent[];
  onSelect: (id: string) => void;
}

const RecentEvents: React.FC<RecentEventsProps> = ({ events, onSelect }) => {
  return (
    <div className="data-panel">
      <div className="panel-header">
        <h2 className="panel-title">Recent Events</h2>
      </div>
      <div className="panel-content">
        {events.length === 0 ? (
          <div className="empty-state">No recent security events</div>
        ) : (
          <div className="event-list">
            {events.map(event => {
              const time = new Date(event.timestamp).toLocaleTimeString('en-GB');
              return (
                <div key={event.id} className="event-item">
                  <div className="event-time">{time}</div>
                  <div className="event-details">
                    <div className="event-type">{event.type}</div>
                    <button className="incident-link" onClick={() => onSelect(event.id)}>View incident #{event.id}</button>
                    <div className="event-meta">
                      <span className="event-camera">{event.cameraId}</span>
                      {event.confidence !== undefined && (
                        <span className="event-confidence">{Math.round(event.confidence * 100)}%</span>
                      )}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
};

export default RecentEvents;
