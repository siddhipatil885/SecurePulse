import React from 'react';
import type { SecurityEvent } from '../types';
import './DataPanels.css';

interface RecentEventsProps {
  events: SecurityEvent[];
}

const RecentEvents: React.FC<RecentEventsProps> = ({ events }) => {
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
                    <div className="event-meta">
                      <span className="event-camera">{event.cameraId}</span>
                      {event.confidence && (
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
