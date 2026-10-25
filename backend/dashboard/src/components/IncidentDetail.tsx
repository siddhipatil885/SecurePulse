import { useEffect, useState } from 'react';
import { apiFetch, evidenceBlob, get, mapEvent } from '../api';
import type { ApiEvent, Evidence, HistoryEntry } from '../api';
import type { SecurityEvent } from '../types';

export default function IncidentDetail({ id, revision, canWrite, onClose, onChange }: {
  id: string; revision: string; canWrite: boolean; onClose: () => void; onChange: () => void;
}) {
  const [incident, setIncident] = useState<SecurityEvent | null>(null);
  const [history, setHistory] = useState<HistoryEntry[]>([]);
  const [evidence, setEvidence] = useState<Evidence[]>([]);
  const [error, setError] = useState('');
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    const abort = new AbortController();
    void Promise.all([get<ApiEvent>(`/incidents/${id}`, abort.signal),
      get<HistoryEntry[]>(`/incidents/${id}/history`, abort.signal),
      get<Evidence[]>(`/incidents/${id}/evidence`, abort.signal)])
      .then(([event, timeline, files]) => { setIncident(mapEvent(event)); setHistory(timeline); setEvidence(files); setError(''); })
      .catch(e => { if (!abort.signal.aborted) { setIncident(null); setError(String(e)); } });
    return () => abort.abort();
  }, [id, revision]);
  const commands: Record<string, string[]> = { OPEN: ['acknowledge', 'resolve', 'dismiss'], ACKNOWLEDGED: ['resolve', 'dismiss'], UNCLASSIFIED: ['dismiss'], RESOLVED: ['reopen'], DISMISSED: ['reopen'], CLOSED: ['reopen'] };
  async function command(action: string) {
    setBusy(true); setError('');
    try {
      await apiFetch(`/incidents/${id}/commands`, { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ command: action, reason, correlation_id: crypto.randomUUID() }) });
      setReason(''); onChange();
    } catch (e) { setError(String(e)); } finally { setBusy(false); }
  }
  return <section className="data-panel incident-detail" aria-label="Incident details">
    <h2>Incident {id}</h2><button onClick={onClose}>Close details</button>
    {error && <p role="alert">{error}. Evidence may be expired or access revoked.</p>}
    {incident && <>
      <dl>
        <dt>Severity / state</dt><dd>{incident.severity} / {incident.status}</dd>
        <dt>Reason</dt><dd>{incident.reason ?? 'Unavailable'}</dd>
        <dt>Property / camera / zone</dt><dd>{incident.propertyId} / {incident.cameraId} / {incident.zone ?? 'Unavailable'}</dd>
        <dt>Observed</dt><dd>{new Date(incident.timestamp).toLocaleString()}</dd>
        <dt>Created</dt><dd>{incident.createdAt ? new Date(incident.createdAt).toLocaleString() : 'Unavailable'}</dd>
        <dt>Source event</dt><dd>{incident.sourceId ?? 'Unavailable'}</dd>
        <dt>Assignment / notification delivery</dt><dd>Unavailable — dispatch service contract pending</dd>
      </dl>
      <h3>Timeline and correlation</h3>
      {!history.length && <p>No stored transitions.</p>}
      <ol>{history.map(h => <li key={h.id}>{new Date(h.occurred_at).toLocaleString()} · {h.previous_status ?? 'Created'} → {h.new_status} · {h.actor_subject}<p>{h.reason} · Correlation: {h.correlation_id}</p></li>)}</ol>
      <p>Normalized adapter / rule trace / realtime receipt / offers: Unavailable where no persisted trace endpoint exists.</p>
      <h3>Evidence</h3>{!evidence.length && <p>No retained evidence.</p>}
      {evidence.map(file => <EvidenceViewer key={file.id} file={file} />)}
      {canWrite ? <><label>Reason <input aria-label="Command reason" value={reason} maxLength={1000} onChange={e => setReason(e.target.value)} /></label>
        {(commands[incident.status ?? ''] ?? []).map(action => <button key={action} disabled={busy || !reason.trim()} onClick={() => void command(action)}>{action}</button>)}</> : <p>Read-only session. Write permission is required for incident actions.</p>}
    </>}
  </section>;
}

function EvidenceViewer({ file }: { file: Evidence }) {
  const [media, setMedia] = useState<{ url: string; type: string } | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  useEffect(() => () => { if (media) URL.revokeObjectURL(media.url); }, [media]);
  useEffect(() => { // retained blobs are removed after the grant window
    if (!media) return;
    const timer = setTimeout(() => setMedia(null), 60000);
    return () => clearTimeout(timer);
  }, [media]);
  return <div>
    <button disabled={loading} onClick={() => { setLoading(true); setError(''); void evidenceBlob(file.id).then(setMedia).catch(() => setError('Evidence unavailable, expired, or forbidden. Retry to request new access.')).finally(() => setLoading(false)); }}>View {file.type} evidence {file.id}</button>
    {error && <p role="alert">{error}</p>}
    {media && (media.type.startsWith('video/') ? <video src={media.url} controls /> : <img src={media.url} alt={`Incident evidence ${file.id}`} />)}
  </div>;
}
