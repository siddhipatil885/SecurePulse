import React from 'react';
import type { Camera } from '../types';
import './DataPanels.css';

interface CameraStatusProps {
  cameras: Camera[];
}

const CameraStatus: React.FC<CameraStatusProps> = ({ cameras }) => {
  return (
    <div className="data-panel">
      <div className="panel-header">
        <h2 className="panel-title">Camera Status</h2>
      </div>
      <div className="panel-content">
        <div className="camera-list">
          {cameras.map(cam => (
            <div key={cam.id} className="camera-status-item">
              <div className="camera-status-name">{cam.name}<small>Property {cam.propertyId} · {cam.location ?? 'Location unavailable'}<br/>Last observation: {cam.lastSeen ? new Date(cam.lastSeen).toLocaleString() : 'Unknown'}</small></div>
              <div className={`camera-status-indicator ${cam.health}`}>
                <span className="status-dot"></span>
                {cam.status === 'disabled' ? 'Disabled' : cam.health}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

export default CameraStatus;
