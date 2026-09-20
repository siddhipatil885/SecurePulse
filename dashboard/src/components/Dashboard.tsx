import React, { useState, useEffect, useMemo } from 'react';
import Header from './Header';
import CameraMonitor from './CameraMonitor';
import SecuritySummary from './SecuritySummary';
import ActiveAlerts from './ActiveAlerts';
import RecentEvents from './RecentEvents';
import CameraStatus from './CameraStatus';
import { fetchDashboardData } from '../api';
import type { Camera, SecurityAlert, SecurityEvent, SystemStatus } from '../types';
import './Dashboard.css';

const Dashboard: React.FC = () => {
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [alerts, setAlerts] = useState<SecurityAlert[]>([]);
  const [events, setEvents] = useState<SecurityEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  
  const [primaryCameraId, setPrimaryCameraId] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    fetchDashboardData()
      .then((data) => {
        if (!active) return;
        setCameras(data.cameras);
        setAlerts(data.alerts);
        setEvents(data.events);
        setPrimaryCameraId((current) => current ?? data.cameras[0]?.id ?? null);
      })
      .catch((requestError: unknown) => {
        if (active) {
          setError(requestError instanceof Error ? requestError.message : 'Unable to load dashboard data');
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  const primaryCamera = useMemo(() => cameras.find(c => c.id === primaryCameraId) ?? cameras[0], [cameras, primaryCameraId]);

  // The secondary cameras should be the next two in priority, or just the first two available
  // Exclude the primary camera.
  const secondaryCameras = useMemo(() => {
    return cameras.filter(c => c.id !== primaryCamera?.id).slice(0, 2);
  }, [cameras, primaryCamera]);

  const systemStatus: SystemStatus = useMemo(() => ({
    online: !error,
    activeAlerts: alerts.filter(a => a.status === 'active').length,
    criticalAlerts: alerts.filter(a => a.status === 'active' && a.severity === 'critical').length,
    camerasOnline: cameras.filter(c => c.status === 'enabled').length,
    totalCameras: cameras.length,
    peopleDetected: events.filter(e => e.objectType === 'person').length
  }), [alerts, cameras, error, events]);

  const handleSelectCamera = (cameraId: string) => {
    setPrimaryCameraId(cameraId);
  };

  return (
    <div className="dashboard-container">
      <Header status={systemStatus} />
      
      <main className="dashboard-main">
        {loading && <div className="empty-state">Loading dashboard data...</div>}
        {error && <div className="empty-state">Unable to load dashboard data: {error}</div>}
        {!loading && !error && !primaryCamera && <div className="empty-state">No cameras are configured.</div>}
        {!loading && !error && primaryCamera && (
          <>
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
          </>
        )}
      </main>
    </div>
  );
};

export default Dashboard;
