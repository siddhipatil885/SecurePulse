import React, { useState, useEffect, useMemo } from 'react';
import Header from './Header';
import CameraMonitor from './CameraMonitor';
import SecuritySummary from './SecuritySummary';
import ActiveAlerts from './ActiveAlerts';
import RecentEvents from './RecentEvents';
import CameraStatus from './CameraStatus';
import { fetchDashboardData, mapAlert, mapEvent } from '../api';
import type { Camera, SecurityAlert, SecurityEvent, SystemStatus } from '../types';
import './Dashboard.css';

const Dashboard: React.FC = () => {
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [alerts, setAlerts] = useState<SecurityAlert[]>([]);
  const [events, setEvents] = useState<SecurityEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [streamConnected, setStreamConnected] = useState(false);
  
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

  useEffect(() => {
    let active = true;
    const socketUrl = import.meta.env.VITE_WS_URL
      ?? `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}/api/v1/events/stream`;
    const socket = new WebSocket(socketUrl);

    socket.onopen = () => {
      if (active) setStreamConnected(true);
    };

    socket.onmessage = (message) => {
      try {
        const payload = JSON.parse(message.data) as {
          type?: string;
          data?: Parameters<typeof mapEvent>[0];
        };
        if (payload.type !== 'security_event' || !payload.data) return;
        const incoming = mapEvent(payload.data);
        setEvents((current) => [
          incoming,
          ...current.filter((event) => event.id !== incoming.id),
        ].slice(0, 100));
        setAlerts((current) => {
          const isAlert = ['high', 'critical'].includes(incoming.severity?.toLowerCase() ?? '');
          if (!isAlert) return current.filter((alert) => alert.id !== incoming.id);
          return [mapAlert(incoming), ...current.filter((alert) => alert.id !== incoming.id)].slice(0, 100);
        });
      } catch {
        setError('Received an invalid live event from the backend');
      }
    };

    socket.onerror = () => {
      if (active) setStreamConnected(false);
    };
    socket.onclose = () => {
      if (active) setStreamConnected(false);
    };
    return () => {
      active = false;
      socket.close();
    };
  }, []);

  const primaryCamera = useMemo(() => cameras.find(c => c.id === primaryCameraId) ?? cameras[0], [cameras, primaryCameraId]);

  // The secondary cameras should be the next two in priority, or just the first two available
  // Exclude the primary camera.
  const secondaryCameras = useMemo(() => {
    return cameras.filter(c => c.id !== primaryCamera?.id).slice(0, 2);
  }, [cameras, primaryCamera]);

  const systemStatus: SystemStatus = useMemo(() => ({
    online: !error && streamConnected,
    activeAlerts: alerts.filter(a => a.status === 'active').length,
    criticalAlerts: alerts.filter(a => a.status === 'active' && a.severity === 'critical').length,
    camerasOnline: cameras.filter(c => c.status === 'enabled').length,
    totalCameras: cameras.length,
    peopleDetected: events.filter(e => e.objectType === 'person').length
  }), [alerts, cameras, error, events, streamConnected]);

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
