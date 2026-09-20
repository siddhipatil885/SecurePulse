import React from 'react';
import type { SystemStatus } from '../types';
import './SecuritySummary.css';

interface SecuritySummaryProps {
  status: SystemStatus;
}

const SecuritySummary: React.FC<SecuritySummaryProps> = ({ status }) => {
  return (
    <div className="security-summary-container">
      <div className="summary-item">
        <div className="summary-label">People Detected</div>
        <div className="summary-value">{status.peopleDetected}</div>
      </div>
      
      <div className="summary-item">
        <div className="summary-label">Active Alerts</div>
        <div className="summary-value warning">{status.activeAlerts}</div>
      </div>
      
      <div className="summary-item">
        <div className="summary-label">Critical Alerts</div>
        <div className="summary-value critical">{status.criticalAlerts}</div>
      </div>
      
      <div className="summary-item">
        <div className="summary-label">Cameras Enabled</div>
        <div className="summary-value">
          <span className={status.camerasOnline === status.totalCameras ? 'success' : 'warning'}>
            {status.camerasOnline}
          </span>
          <span className="summary-muted"> / {status.totalCameras}</span>
        </div>
      </div>
    </div>
  );
};

export default SecuritySummary;
