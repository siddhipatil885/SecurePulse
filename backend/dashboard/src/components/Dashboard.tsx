import React, { useEffect, useMemo, useState } from 'react';
import Header from './Header';
import CameraMonitor from './CameraMonitor';
import SecuritySummary from './SecuritySummary';
import ActiveAlerts from './ActiveAlerts';
import RecentEvents from './RecentEvents';
import CameraStatus from './CameraStatus';
import IncidentDetail from './IncidentDetail';
import Operations from './Operations';
import { ApiError, fetchDashboardData, setAccessToken, socketProtocols, socketUrl } from '../api';
import type { DashboardData } from '../api';
import type { SystemStatus } from '../types';
import './Dashboard.css';

const Dashboard: React.FC = () => {
  const [generation, setGeneration] = useState(0);
  const [token, setToken] = useState('');
  const [data, setData] = useState<DashboardData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [connection, setConnection] = useState('Connecting');
  const [propertyId, setPropertyId] = useState('');
  const [selectedCamera, setSelectedCamera] = useState<string | null>(null);
  const [incidentId, setIncidentId] = useState<string | null>(null);
  const [updatedAt, setUpdatedAt] = useState('');
  const [notice, setNotice] = useState('');

  useEffect(() => {
    let disposed = false, loading = false, dirty = false, attempts = 0, stopped = false;
    let socket: WebSocket | null = null;
    let retry: ReturnType<typeof setTimeout> | undefined;
    let throttle: ReturnType<typeof setTimeout> | undefined;
    let lastMessage = Date.now();
    const abort = new AbortController();
    const seen = new Set<string>();
    const announced = new Set<string>();
    let baseline = false;
    const refresh = async () => {
      if (disposed || stopped) return;
      if (loading) { dirty = true; return; }
      loading = true;
      try {
        const next = await fetchDashboardData(AbortSignal.any([abort.signal, AbortSignal.timeout(20000)]));
        if (disposed) return;
        for (const alert of next.alerts) {
          if (baseline && !announced.has(alert.id) && alert.status === 'active') setNotice(`Incident ${alert.id}: ${alert.type} — awaiting acknowledgment`);
          announced.add(alert.id);
        }
        baseline = true;
        setData(next); setError(null); setUpdatedAt(new Date().toISOString());
      } catch (e) {
        if (disposed) return;
        setData(null);
        setNotice('');
        if (e instanceof ApiError && [401, 403].includes(e.status)) {
          stopped = true; socket?.close(); setConnection('Sign in required');
        }
        setError(e instanceof Error ? e.message : 'Backend unavailable');
      } finally {
        loading = false;
        if (dirty && !disposed) { dirty = false; scheduleRefresh(); }
      }
    };
    const scheduleRefresh = () => {
      if (throttle || disposed) return;
      throttle = setTimeout(() => { throttle = undefined; void refresh(); }, 1000);
    };
    const connect = () => {
      if (disposed || stopped) return;
      setConnection(attempts ? 'Connection lost; retrying' : 'Connecting');
      try { socket = new WebSocket(socketUrl(), socketProtocols()); }
      catch { setConnection('Invalid realtime configuration; REST polling active'); return; }
      socket.onopen = () => { lastMessage = Date.now(); if (!disposed) { setConnection('Connected'); void refresh(); } };
      socket.onmessage = message => {
        if (disposed) return;
        lastMessage = Date.now();
        try {
          const event = JSON.parse(String(message.data)) as { version?: number; type?: string; event_id?: string };
          if (event.version !== 1) { scheduleRefresh(); return; }
          if (event.type === 'heartbeat') { attempts = 0; return; }
          if (event.event_id && seen.has(event.event_id)) return;
          if (event.event_id) { seen.add(event.event_id); if (seen.size > 1000) seen.delete(seen.values().next().value!); }
          scheduleRefresh(); // REST remains the authoritative state and permission check
        } catch { setConnection('Invalid live message; refreshing'); scheduleRefresh(); }
      };
      socket.onclose = event => {
        if (disposed || stopped) return;
        if ([4401, 1008].includes(event.code)) { stopped = true; setData(null); setError('Session expired or access denied. Sign in again.'); setConnection('Sign in required'); return; }
        setConnection('Connection lost; retrying');
        if (++attempts <= 6) retry = setTimeout(connect, Math.min(30000, 1000 * 2 ** (attempts - 1)) + Math.random() * 250);
        else setConnection('Realtime offline; polling every 15 seconds. Use Retry to reconnect.');
      };
      const currentSocket = socket;
      socket.onerror = () => currentSocket.close();
    };
    void refresh(); connect();
    const poll = setInterval(() => {
      if (socket?.readyState === WebSocket.OPEN && Date.now() - lastMessage > 35000) socket.close();
      void refresh();
    }, 15000);
    return () => { disposed = true; abort.abort(); clearInterval(poll); clearTimeout(retry); clearTimeout(throttle); socket?.close(); };
  }, [generation]);

  const cameras = useMemo(() => data?.cameras.filter(c => !propertyId || String(c.propertyId) === propertyId) ?? [], [data, propertyId]);
  const events = useMemo(() => data?.events.filter(e => !propertyId || String(e.propertyId) === propertyId) ?? [], [data, propertyId]);
  const alerts = data?.alerts.filter(a => cameras.some(c => c.id === a.cameraId)) ?? [];
  const activity = [...events].sort((a, b) => {
    const active = (s?: string) => ['OPEN', 'ACKNOWLEDGED'].includes(s ?? '') ? 1 : 0;
    return active(b.status) - active(a.status) || Date.parse(b.timestamp) - Date.parse(a.timestamp);
  });
  const primary = cameras.find(c => c.id === selectedCamera) ?? cameras.find(c => c.id === activity[0]?.cameraId) ?? cameras.find(c => c.health === 'healthy') ?? cameras[0];
  const status: SystemStatus = {
    online: !!data && connection === 'Connected', activeAlerts: alerts.length,
    criticalAlerts: alerts.filter(a => a.severity === 'critical').length,
    camerasOnline: cameras.filter(c => c.health === 'healthy').length, totalCameras: cameras.length,
    peopleDetected: cameras.reduce((sum, c) => sum + (data?.tracksByCamera[c.id]?.length ?? 0), 0),
  };
  return <div className="dashboard-container" id="dashboard">
    <Header status={status} />
    <div className="dashboard-toolbar">
      <form onSubmit={e => { e.preventDefault(); setAccessToken(token.trim()); setToken(''); setData(null); setIncidentId(null); setNotice(''); setPropertyId(''); setGeneration(g => g + 1); }}>
        <label>Access token <input aria-label="Access token" type="password" autoComplete="off" value={token} onChange={e => setToken(e.target.value)} /></label>
        <button type="submit">Use session</button>
      </form>
      <button onClick={() => { setAccessToken(''); setData(null); setIncidentId(null); setNotice(''); setGeneration(g => g + 1); }}>Clear session</button>
      <label>Property <select aria-label="Property" value={propertyId} onChange={e => { setPropertyId(e.target.value); setSelectedCamera(null); setIncidentId(null); }}>
        <option value="">All authorized properties</option>
        {data?.properties.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
      </select></label>
      <button onClick={() => setGeneration(g => g + 1)}>Retry</button>
      <span role="status">{connection} · Last REST update: {updatedAt ? new Date(updatedAt).toLocaleString() : 'Unknown'}</span>
    </div>
    {notice && <div className="dashboard-notice" role="alert">{notice} <button onClick={() => setNotice('')}>Dismiss notification</button></div>}
    <main className="dashboard-main">
      {error && <div className="empty-state" role="alert">{error}. Data unavailable.</div>}
      {!data && !error && <div className="empty-state">Loading dashboard data…</div>}
      {data && <>
        <div className="dashboard-center-section" id="cameras">
          {primary ? <CameraMonitor primaryCamera={primary} secondaryCameras={cameras.filter(c => c.id !== primary.id).slice(0, 2)} onSelectCamera={setSelectedCamera} tracksByCamera={data.tracksByCamera} /> : <div className="empty-state">No authorized cameras.</div>}
          <label>Active camera <select aria-label="Active camera" value={primary?.id ?? ''} onChange={e => setSelectedCamera(e.target.value)}>{cameras.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}</select></label>
          <Operations generation={generation} />
        </div>
        <div className="dashboard-right-sidebar">
          <p>Counts: all retained authorized incidents in the selected property. Tracks: latest asynchronous observations.</p>
          <SecuritySummary status={status} />
          <div id="alerts"><ActiveAlerts alerts={alerts} /></div>
          <div id="events"><RecentEvents events={events.slice(0, 100)} onSelect={setIncidentId} /></div>
          {events.length > 100 && <p>Showing latest 100 of {events.length} retained incidents.</p>}
          {incidentId && events.some(e => e.id === incidentId) && <IncidentDetail key={incidentId} id={incidentId} revision={updatedAt} canWrite={data.session.scopes.includes('write')} onClose={() => setIncidentId(null)} onChange={() => setGeneration(g => g + 1)} />}
          <CameraStatus cameras={cameras} />
        </div>
      </>}
    </main>
  </div>;
};
export default Dashboard;
