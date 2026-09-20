import React from 'react';
import type { Camera } from '../types';
import CameraFeed from './CameraFeed';
import './CameraMonitor.css';

interface CameraMonitorProps {
  primaryCamera: Camera;
  secondaryCameras: Camera[];
  onSelectCamera: (id: string) => void;
}

const CameraMonitor: React.FC<CameraMonitorProps> = ({ primaryCamera, secondaryCameras, onSelectCamera }) => {
  return (
    <div className="camera-monitor-container">
      <div className="primary-camera-wrapper">
        <CameraFeed camera={primaryCamera} isPrimary={true} />
      </div>
      
      <div className="secondary-cameras-wrapper">
        {secondaryCameras.map(cam => (
          <div 
            key={cam.id} 
            className="secondary-camera-item"
            onClick={() => onSelectCamera(cam.id)}
          >
            <CameraFeed camera={cam} isPrimary={false} />
          </div>
        ))}
      </div>
    </div>
  );
};

export default CameraMonitor;
