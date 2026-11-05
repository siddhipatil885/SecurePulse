import React, { useState, useEffect, useMemo } from 'react';
import Header from './Header';
import CameraMonitor from './CameraMonitor';
import SecuritySummary from './SecuritySummary';
import ActiveAlerts from './ActiveAlerts';
import RecentEvents from './RecentEvents';
import CameraStatus from './CameraStatus';
import IncidentWorkspace from './IncidentWorkspace';
import OperatorWorkspace from './OperatorWorkspace';
import { dashboardBase, fetchDashboardData, mapTrack } from '../api';
import type { DashboardData, PropertyAccess } from '../api';
import type { Camera, PersonTrack, SecurityAlert, SecurityEvent, SystemStatus } from '../types';
import './Dashboard.css';

const Dashboard: React.FC<{ property: PropertyAccess }> = ({ property }) => {
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [alerts, setAlerts] = useState<SecurityAlert[]>([]);
  const [events, setEvents] = useState<SecurityEvent[]>([]);
  const [tracksByCamera, setTracksByCamera] = useState<Record<string, PersonTrack[]>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [streamConnected, setStreamConnected] = useState(false);
  const [overview, setOverview] = useState<DashboardData['overview']>({ total_incidents: 0, active_incidents: 0, critical_incidents: 0 });
  const [revision, setRevision] = useState(0);
  const [view, setView] = useState<'monitoring' | 'incidents'>('monitoring');
  const [selectedIncident, setSelectedIncident] = useState<string | null>(null);
  
  const [primaryCameraId, setPrimaryCameraId] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    fetchDashboardData(property.id, controller.signal, property.role !== 'reporter')
      .then((data) => {
        if (!active) return;
        setCameras(data.cameras);
        setAlerts(data.alerts);
        setEvents(data.events);
        setTracksByCamera(data.tracksByCamera);
        setOverview(data.overview);
        setError(null);
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
      controller.abort();
    };
  }, [property.id, property.role, revision]);

  useEffect(() => {
    let active = true;
    let socket: WebSocket | null = null;
    let reconnect: ReturnType<typeof setTimeout> | undefined;
    let refresh: ReturnType<typeof setTimeout> | undefined;
    const scheduleRefresh = () => {
      if (!active || refresh) return;
      refresh = setTimeout(() => { refresh = undefined; if (active) setRevision(value => value + 1); }, 150);
    };
    const connect = () => {
      if (!active) return;
      const url = new URL(`${dashboardBase}/properties/${property.id}/stream`, window.location.origin);
      url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
      socket = new WebSocket(url);
      socket.onopen = () => { if (active) { setStreamConnected(true); scheduleRefresh(); } };
      socket.onmessage = message => {
        if (!active) return;
        try {
          const payload = JSON.parse(message.data) as { type?: string; property_id?: number; data?: { camera_id: string; tracks: Parameters<typeof mapTrack>[0][] } };
          if (payload.property_id !== property.id) return;
          if (payload.type === 'person_tracks' && payload.data && Array.isArray(payload.data.tracks)) {
            const data = payload.data;
            setTracksByCamera(current => ({ ...current, [String(data.camera_id)]: data.tracks.map(mapTrack) }));
          } else if (payload.type === 'security_event' || payload.type === 'case_updated') scheduleRefresh();
        } catch { scheduleRefresh(); }
      };
      socket.onerror = () => { if (active) setStreamConnected(false); };
      socket.onclose = event => {
        if (!active) return;
        setStreamConnected(false); setTracksByCamera({});
        if (event.code === 1008) { scheduleRefresh(); return; }
        reconnect = setTimeout(connect, 3000);
      };
    };
    connect();
    const poll = setInterval(scheduleRefresh, 10000);
    return () => {
      active = false;
      clearInterval(poll); clearTimeout(reconnect); clearTimeout(refresh);
      socket?.close();
    };
  }, [property.id]);

  const primaryCamera = useMemo(() => cameras.find(c => c.id === primaryCameraId) ?? cameras[0], [cameras, primaryCameraId]);

  // The secondary cameras should be the next two in priority, or just the first two available
  // Exclude the primary camera.
  const secondaryCameras = useMemo(() => {
    return cameras.filter(c => c.id !== primaryCamera?.id).slice(0, 2);
  }, [cameras, primaryCamera]);

  const systemStatus: SystemStatus = useMemo(() => ({
    online: !error && streamConnected,
    activeAlerts: overview.active_incidents,
    criticalAlerts: overview.critical_incidents,
    camerasOnline: cameras.filter(c => c.healthStatus === 'online').length,
    totalCameras: cameras.length,
    // This is a count of active anonymous person tracks, not historical events
    // or unique identities. Ended/grace-period tracks are excluded by design.
    peopleDetected: Object.values(tracksByCamera)
      .flat()
      .filter((track) => track.objectType === 'person' && track.state === 'ACTIVE')
      .length
  }), [overview, cameras, error, streamConnected, tracksByCamera]);

  const handleSelectCamera = (cameraId: string) => {
    setPrimaryCameraId(cameraId);
  };

  return (
    <div className="dashboard-container">
      <Header status={systemStatus} />
      
      <main className="dashboard-main">
        <nav className="workspace-tabs" aria-label="Dashboard views"><button aria-pressed={view === 'monitoring'} onClick={() => setView('monitoring')}>Live monitoring</button>
          <button aria-pressed={view === 'incidents'} onClick={() => setView('incidents')}>Incidents ({overview.total_incidents})</button></nav>
        {!streamConnected && <p role="status">Live connection interrupted. Reconnecting; data refreshes automatically.</p>}
        {view === 'incidents' && (property.role === 'reporter'
          ? <IncidentWorkspace key={`${property.id}:${selectedIncident ?? 'list'}`} property={property} initialId={selectedIncident} refreshVersion={revision} onChanged={() => setRevision(value => value + 1)} />
          : <OperatorWorkspace key={`${property.id}:${selectedIncident ?? 'list'}`} propertyId={property.id} initialCameraId={selectedIncident} refreshVersion={revision} onChanged={() => setRevision(value => value + 1)} />)}
        {view === 'monitoring' && <>
        {loading && <div className="empty-state">Loading dashboard data...</div>}
        {error && <div className="empty-state">Unable to load dashboard data: {error}</div>}
        {!loading && !error && !primaryCamera && <div className="empty-state">No cameras are configured.</div>}
        {!loading && !error && primaryCamera && (
          <div className="monitor-layout">
        <div className="dashboard-center-section">
          <CameraMonitor 
            propertyId={property.id}
            primaryCamera={primaryCamera} 
            secondaryCameras={secondaryCameras} 
            onSelectCamera={handleSelectCamera}
            tracksByCamera={tracksByCamera}
          />
        </div>
        
        <div className="dashboard-right-sidebar">
          <SecuritySummary status={systemStatus} />
          <ActiveAlerts alerts={alerts} onSelect={id => { setSelectedIncident(id); setView('incidents'); }} />
          <RecentEvents events={events} onSelect={id => { setSelectedIncident(id); setView('incidents'); }} />
          <CameraStatus cameras={cameras} />
        </div>
          </div>
        )}
        </>}
      </main>
    </div>
  );
};

export default Dashboard;
