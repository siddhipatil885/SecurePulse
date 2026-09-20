import React from 'react';
import type { SecurityAlert } from '../types';
import './DataPanels.css';

interface ActiveAlertsProps {
  alerts: SecurityAlert[];
}

const ActiveAlerts: React.FC<ActiveAlertsProps> = ({ alerts }) => {
  return (
    <div className="data-panel">
      <div className="panel-header">
        <h2 className="panel-title">Active Alerts</h2>
      </div>
      <div className="panel-content">
        {alerts.length === 0 ? (
          <div className="empty-state">No active security alerts</div>
        ) : (
          <div className="alert-list">
            {alerts.map(alert => {
              const time = new Date(alert.timestamp).toLocaleTimeString('en-GB');
              return (
                <div key={alert.id} className="alert-item">
                  <div className={`alert-severity ${alert.severity}`}>
                    {alert.severity.toUpperCase()}
                  </div>
                  <div className="alert-details">
                    <div className="alert-type">{alert.type}</div>
                    <div className="alert-meta">
                      <span className="alert-camera">{alert.cameraId}</span>
                      <span className="alert-time">{time}</span>
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

export default ActiveAlerts;
