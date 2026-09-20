import React, { useState, useEffect, useMemo } from 'react';
import Header from './Header';
import CameraMonitor from './CameraMonitor';
import SecuritySummary from './SecuritySummary';
import ActiveAlerts from './ActiveAlerts';
import RecentEvents from './RecentEvents';
import CameraStatus from './CameraStatus';
import { mockCameras, mockAlerts, mockEvents, getPriorityCamera } from '../mock';
import type { Camera, SecurityAlert, SecurityEvent, SystemStatus } from '../types';
import './Dashboard.css';

const Dashboard: React.FC = () => {
  const [cameras] = useState<Camera[]>(mockCameras);
  const [alerts] = useState<SecurityAlert[]>(mockAlerts);
  const [events] = useState<SecurityEvent[]>(mockEvents);
  
  const [primaryCameraId, setPrimaryCameraId] = useState<string | null>(null);

  // Automatically determine the priority camera if the user hasn't explicitly selected one
  // In a real app, this might reset after a timeout or when the activity ends.
  useEffect(() => {
    if (!primaryCameraId) {
      const priorityCam = getPriorityCamera(cameras, alerts, events);
      if (priorityCam) {
        setPrimaryCameraId(priorityCam.id);
      }
    }
  }, [cameras, alerts, events, primaryCameraId]);

  const primaryCamera = useMemo(() => 
    cameras.find(c => c.id === primaryCameraId) || cameras[0]
  , [cameras, primaryCameraId]);

  // The secondary cameras should be the next two in priority, or just the first two available
  // Exclude the primary camera.
  const secondaryCameras = useMemo(() => {
    return cameras.filter(c => c.id !== primaryCamera?.id).slice(0, 2);
  }, [cameras, primaryCamera]);

  const systemStatus: SystemStatus = useMemo(() => ({
    online: true,
    activeAlerts: alerts.filter(a => a.status === 'active').length,
    criticalAlerts: alerts.filter(a => a.status === 'active' && a.severity === 'critical').length,
    camerasOnline: cameras.filter(c => c.status === 'online').length,
    totalCameras: cameras.length,
    peopleDetected: events.filter(e => e.type === 'Person Detected').length // mock stat
  }), [alerts, cameras, events]);

  const handleSelectCamera = (cameraId: string) => {
    setPrimaryCameraId(cameraId);
  };

  return (
    <div className="dashboard-container">
      <Header status={systemStatus} />
      
      <main className="dashboard-main">
        <div className="dashboard-center-section">
          <CameraMonitor 
            primaryCamera={primaryCamera} 
            secondaryCameras={secondaryCameras} 
            onSelectCamera={handleSelectCamera}
          />
        </div>
        
        <div className="dashboard-right-sidebar">
          <SecuritySummary status={systemStatus} />
          <ActiveAlerts alerts={alerts} />
          <RecentEvents events={events} />
          <CameraStatus cameras={cameras} />
        </div>
      </main>
    </div>
  );
};

export default Dashboard;
