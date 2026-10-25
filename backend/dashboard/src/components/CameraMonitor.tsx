import React from 'react';
import type { Camera, PersonTrack } from '../types';
import CameraFeed from './CameraFeed';
import './CameraMonitor.css';

interface CameraMonitorProps {
  primaryCamera: Camera;
  secondaryCameras: Camera[];
  onSelectCamera: (id: string) => void;
  tracksByCamera: Record<string, PersonTrack[]>;
}

const CameraMonitor: React.FC<CameraMonitorProps> = ({ primaryCamera, secondaryCameras, onSelectCamera, tracksByCamera }) => {
  return (
    <div className="camera-monitor-container">
      <div className="primary-camera-wrapper">
        <CameraFeed camera={primaryCamera} isPrimary={true} tracks={tracksByCamera[primaryCamera.id] ?? []} />
      </div>
      
      <div className="secondary-cameras-wrapper">
        {secondaryCameras.map(cam => (
          <div 
            key={cam.id} 
            className="secondary-camera-item"
            onClick={() => onSelectCamera(cam.id)}
          >
            <CameraFeed camera={cam} isPrimary={false} tracks={tracksByCamera[cam.id] ?? []} />
          </div>
        ))}
      </div>
    </div>
  );
};

export default CameraMonitor;
