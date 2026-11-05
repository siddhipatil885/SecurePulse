import React from 'react';
import type { Camera, PersonTrack } from '../types';
import CameraFeed from './CameraFeed';
import './CameraMonitor.css';

interface CameraMonitorProps {
  propertyId: number;
  primaryCamera: Camera;
  secondaryCameras: Camera[];
  onSelectCamera: (id: string) => void;
  tracksByCamera: Record<string, PersonTrack[]>;
}

const CameraMonitor: React.FC<CameraMonitorProps> = ({ propertyId, primaryCamera, secondaryCameras, onSelectCamera, tracksByCamera }) => {
  return (
    <div className="camera-monitor-container">
      <div className="primary-camera-wrapper">
        <CameraFeed propertyId={propertyId} camera={primaryCamera} isPrimary={true} tracks={tracksByCamera[primaryCamera.id] ?? []} />
      </div>
      
      <div className="secondary-cameras-wrapper">
        {secondaryCameras.map(cam => (
          <div 
            key={cam.id} 
            className="secondary-camera-item"
            onClick={() => onSelectCamera(cam.id)}
          >
            <CameraFeed propertyId={propertyId} camera={cam} isPrimary={false} tracks={tracksByCamera[cam.id] ?? []} />
          </div>
        ))}
      </div>
    </div>
  );
};

export default CameraMonitor;
