import React from 'react';
import type { SecurityEvent } from '../types';
import './DataPanels.css';

function snapshotUrl(event: SecurityEvent): string | null {
  const value = event.metadata?.snapshot_url;
  return typeof value === 'string' ? value : null;
}

function eventBox(event: SecurityEvent): { x: number; y: number; width: number; height: number } | null {
  const value = event.metadata?.bounding_box_normalized;
  if (!value || typeof value !== 'object') return null;
  const box = value as Record<string, unknown>;
  if (![box.x, box.y, box.width, box.height].every((item) => typeof item === 'number')) return null;
  return { x: box.x as number, y: box.y as number, width: box.width as number, height: box.height as number };
}

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
              const evidence = snapshotUrl(event);
              const box = eventBox(event);
              return (
                <div key={event.id} className="event-item">
                  {evidence && (
                    <a className="event-evidence" href={evidence} target="_blank" rel="noreferrer">
                      <img src={evidence} alt={`Evidence for ${event.type}`} />
                      {box && <span className="event-evidence-box" style={{ left: `${box.x * 100}%`, top: `${box.y * 100}%`, width: `${box.width * 100}%`, height: `${box.height * 100}%` }} />}
                    </a>
                  )}
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
