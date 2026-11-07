import { useEffect, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import { request } from '../api';
import { casePath } from '../cases';
import type { Assignment, CaseDetail, CaseEvidence, CaseSummary, Marshal, Page, TimelineItem } from '../cases';

const message = (error: unknown) => error instanceof Error ? error.message : 'Unable to load incident data.';
const date = (value: string) => new Date(value).toLocaleString();

function Pagination({ data, onPage, label }: { data: { page: number; page_size: number; total: number }; onPage: (page: number) => void; label: string }) {
  return <nav className="pagination" aria-label={`${label} pagination`}><button disabled={data.page <= 1} onClick={() => onPage(data.page - 1)}>Previous</button>
    <span>Page {data.page} of {Math.max(1, Math.ceil(data.total / data.page_size))}</span>
    <button disabled={data.page * data.page_size >= data.total} onClick={() => onPage(data.page + 1)}>Next</button></nav>;
}

function EvidencePreview({ item, path }: { item: CaseEvidence; path: string }) {
  const [url, setUrl] = useState(''); const [error, setError] = useState(''); const [busy, setBusy] = useState(false);
  async function open() {
    setBusy(true); setError(''); setUrl('');
    try { const grant = await request<{ url: string }>(`${path}/evidence/${item.id}/access`, { method: 'POST' }); setUrl(grant.url); }
    catch (error) { setError(message(error)); }
    finally { setBusy(false); }
  }
  const failed = () => { setUrl(''); setError('Evidence is unavailable or access has expired. Request it again.'); };
  const video = item.media_type?.startsWith('video/') || /clip|video/i.test(item.kind);
  return <li><p>{item.original_filename || item.kind} · {date(item.occurred_at)}</p>
    <button onClick={() => void open()} disabled={busy}>{busy ? 'Opening…' : 'View evidence'}</button>
    {error && <p role="alert">{error}</p>}
    {url && (video ? <video className="evidence-media" controls src={url} onError={failed} />
      : <img className="evidence-media" alt={`Incident evidence ${item.id}`} src={url} onError={failed} />)}</li>;
}

/** Show an authorized case's response data and bind pending exports to that case. */
function OperatorDetail({ propertyId, selected, refreshVersion, onChanged }: {
  propertyId: number; selected: Pick<CaseSummary, 'source' | 'source_id'>; refreshVersion: number; onChanged: () => void;
}) {
  const path = casePath(propertyId, selected);
  const [data, setData] = useState<{ detail: CaseDetail; timeline: Page<TimelineItem>; evidence: Page<CaseEvidence>; assignments: Page<Assignment>; marshals: Marshal[] } | null>(null);
  const [error, setError] = useState(''); const [actionError, setActionError] = useState(''); const [success, setSuccess] = useState('');
  const [clock, setClock] = useState(Date.now);
  const [reportBusy, setReportBusy] = useState(false);
  const reportRequest = useRef<AbortController | null>(null);
  const mounted = useRef(false);
  const [busy, setBusy] = useState(false); const [revision, setRevision] = useState(0);
  const [timelinePage, setTimelinePage] = useState(1); const [evidencePage, setEvidencePage] = useState(1); const [assignmentPage, setAssignmentPage] = useState(1);
  const [action, setAction] = useState(''); const [reason, setReason] = useState(''); const [marshalId, setMarshalId] = useState('');
  const [expiry, setExpiry] = useState(300);
  const actionRequest = useRef<{ signature: string; key: string } | null>(null);
  const offerRequest = useRef<{ signature: string; key: string } | null>(null);
  useEffect(() => {
    const abort = new AbortController();
    Promise.all([
      request<CaseDetail>(path, { signal: abort.signal }),
      request<Page<TimelineItem>>(`${path}/timeline?page=${timelinePage}&page_size=20`, { signal: abort.signal }),
      request<Page<CaseEvidence>>(`${path}/evidence?page=${evidencePage}&page_size=20`, { signal: abort.signal }),
      request<Page<Assignment>>(`${path}/assignments?page=${assignmentPage}&page_size=20`, { signal: abort.signal }),
      request<Marshal[]>(`/properties/${propertyId}/cases/eligible-marshals`, { signal: abort.signal }),
    ]).then(([detail, timeline, evidence, assignments, marshals]) => {
      if (abort.signal.aborted) return;
      setData({ detail, timeline, evidence, assignments, marshals }); setError('');
      setAction(current => detail.allowed_actions.includes(current) ? current : detail.allowed_actions[0] ?? '');
      setMarshalId(current => marshals.some(item => String(item.id) === current) ? current : String(marshals[0]?.id ?? ''));
    }).catch(error => { if (!abort.signal.aborted) setError(message(error)); });
    return () => abort.abort();
  }, [path, propertyId, timelinePage, evidencePage, assignmentPage, revision, refreshVersion]);
  useEffect(() => {
    mounted.current = true;
    const timer = window.setInterval(() => setClock(Date.now()), 5000);
    return () => { mounted.current = false; window.clearInterval(timer); reportRequest.current?.abort(); };
  }, []);
  function requestKey(ref: typeof actionRequest, signature: string) {
    if (ref.current?.signature !== signature) ref.current = { signature, key: crypto.randomUUID() };
    return ref.current.key;
  }
  /** Apply a versioned case or dispatch change and reload after success or conflict. */
  async function mutate(kind: 'action' | 'offer' | 'cancel', event?: FormEvent) {
    event?.preventDefault();
    if (busy || !data) return;
    setBusy(true); setActionError(''); setSuccess('');
    try {
      if (kind === 'action') {
        const intent = { command: action, expected_status: data.detail.status, reason: reason.trim() };
        const result = await request<CaseDetail>(`${path}/commands`, { method: 'POST', body: JSON.stringify({ ...intent,
          correlation_id: requestKey(actionRequest, JSON.stringify(intent)) }) });
        setSuccess(`Incident updated to ${result.status}.`); setReason(''); actionRequest.current = null;
      } else if (kind === 'offer') {
        if (!Number.isInteger(expiry) || expiry < 10 || expiry > 300) throw new Error('Choose an offer timeout between 10 and 300 seconds.');
        const intent = { marshal_profile_id: Number(marshalId), expires_in_seconds: expiry };
        await request(`${path}/offers`, { method: 'POST', body: JSON.stringify({ ...intent,
          idempotency_key: requestKey(offerRequest, JSON.stringify(intent)) }) });
        setSuccess('Assignment offered to the selected marshal.'); offerRequest.current = null;
      } else {
        const assignment = data.detail.latest_assignment;
        if (!assignment) return;
        await request(`${path}/assignments/${assignment.id}/cancel`, { method: 'POST', body: JSON.stringify({ expected_version: assignment.version }) });
        setSuccess('Assignment cancelled.');
      }
      onChanged();
    } catch (error) { setActionError(message(error)); }
    finally { setBusy(false); setRevision(value => value + 1); }
  }
  /** Export case JSON with a bounded request that cleanup cancels on navigation. */
  async function downloadReport() {
    if (!data || reportRequest.current) return;
    const controller = new AbortController();
    reportRequest.current = controller;
    setReportBusy(true); setActionError('');
    const timeout = window.setTimeout(() => controller.abort(), 30000);
    try {
      const report = await request<unknown>(`${path}/report`, { signal: controller.signal });
      if (controller.signal.aborted || !mounted.current) return;
      const blob = new Blob([JSON.stringify(report, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url; link.download = `property-${propertyId}-${selected.source}-incident-${selected.source_id}-report.json`;
      document.body.append(link);
      try { link.click(); }
      finally { link.remove(); window.setTimeout(() => URL.revokeObjectURL(url), 1000); }
    } catch (error) {
      if (mounted.current) setActionError(controller.signal.aborted ? 'Report download timed out. Please try again.' : message(error));
    } finally {
      window.clearTimeout(timeout); reportRequest.current = null;
      if (mounted.current) setReportBusy(false);
    }
  }
  const detail = data?.detail;
  const assignment = detail?.latest_assignment;
  const active = assignment && ['OFFERED', 'ACCEPTED', 'EN_ROUTE', 'ON_SCENE'].includes(assignment.status);
  const tracking = assignment && ['ACCEPTED', 'EN_ROUTE', 'ON_SCENE'].includes(assignment.status);
  const position = tracking ? assignment.responder_location : null;
  const validPosition = position && Number.isFinite(position.latitude) && Math.abs(position.latitude) <= 90 && Number.isFinite(position.longitude) && Math.abs(position.longitude) <= 180;
  const locationAge = position ? clock - Date.parse(position.updated_at) : NaN;
  const recentPosition = clock > 0 && Number.isFinite(locationAge) && locationAge >= -5000 && locationAge <= 30000;
  return <section className="incident-panel incident-detail" aria-label="Incident details">
    <h2>{selected.source === 'camera' ? 'Camera incident' : 'Reported incident'} #{selected.source_id}</h2>
    {!data && !error && <p role="status">Loading incident…</p>}
    {error && <><p role="alert">{error}</p><button onClick={() => setRevision(value => value + 1)}>Retry details</button></>}
    {detail && data && !error && <>
      <dl><dt>Reference</dt><dd>{detail.key}</dd><dt>Type</dt><dd>{detail.incident_type.replaceAll('_', ' ')}</dd>
        <dt>Status</dt><dd>{detail.status}</dd><dt>Severity</dt><dd>{detail.severity || 'Not assigned'}</dd>
        <dt>Reported</dt><dd>{date(detail.occurred_at)}</dd><dt>Location</dt><dd>{detail.location.address || 'Address not provided'}</dd>
        {detail.location.latitude !== null && <><dt>Coordinates</dt><dd>{detail.location.latitude}, {detail.location.longitude}</dd></>}
        {detail.camera_id !== null && <><dt>Camera</dt><dd>#{detail.camera_id}</dd></>}
        {detail.confidence !== null && <><dt>Confidence</dt><dd>{Math.round(detail.confidence * 100)}%</dd></>}
        <dt>Details</dt><dd>{detail.description || 'No additional details'}</dd></dl>
      {tracking && <aside aria-label="Responder location">
        <h3>Responder location</h3>
        {position && validPosition ? <>
          <p role="status">{recentPosition ? 'Location updated recently' : 'Location is stale or its update time is unavailable. Showing the last reported position.'}</p>
          <p>{position.latitude.toFixed(5)}, {position.longitude.toFixed(5)}</p>
          <p>Last update: {Number.isFinite(Date.parse(position.updated_at)) ? date(position.updated_at) : 'Unavailable'}</p>
          {position.accuracy_m != null && <p>Reported accuracy: ±{Math.round(position.accuracy_m)} metres</p>}
          {recentPosition && position.eta_seconds != null && <>
            <p>Estimated arrival: {position.eta_seconds < 60 ? 'Under 1 min' : `${Math.ceil(position.eta_seconds / 60)} min`}
              {position.distance_m != null ? ` · ${(position.distance_m / 1000).toFixed(2)} km` : ''}</p>
            <p>Estimate uses the reported position; traffic is not included.</p>
          </>}
          <a href={`https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(`${position.latitude},${position.longitude}`)}`} target="_blank" rel="noopener noreferrer">Open reported position in maps</a>
        </> : <p role="status">Waiting for the responder to share a location.</p>}
      </aside>}
      {detail.allowed_actions.length > 0 && <form onSubmit={event => void mutate('action', event)} aria-label="Incident actions"><fieldset disabled={busy}>
        <h3>Update incident</h3><label>Action<select aria-label="Action" value={action} onChange={e => setAction(e.target.value)}>
          {detail.allowed_actions.map(item => <option key={item} value={item}>{item === 'dismiss' ? 'Dismiss as false alarm' : item.charAt(0).toUpperCase() + item.slice(1)}</option>)}
        </select></label><label>Reason<textarea aria-label="Reason" required maxLength={1000} value={reason} onChange={e => setReason(e.target.value)} /></label>
        <button disabled={busy || !reason.trim()} type="submit">{busy ? 'Saving…' : 'Confirm action'}</button>
      </fieldset></form>}
      <h3>Dispatch</h3>{assignment ? <p>Assignment #{assignment.id} · {assignment.status} · Marshal #{assignment.marshal_profile_id}</p> : <p>No assignment exists for this incident.</p>}
      <button disabled={busy || reportBusy} onClick={() => void downloadReport()}>{reportBusy ? 'Preparing report…' : 'Download incident report'}</button>
      <p>The JSON report includes timeline, notes, notification history and evidence references. Historical GPS is not recorded.</p>
      {active && <button disabled={busy} onClick={() => void mutate('cancel')}>Cancel assignment</button>}
      {detail.dispatch_allowed && (data.marshals.length ? <form onSubmit={event => void mutate('offer', event)} aria-label="Dispatch assignment"><fieldset disabled={busy}>
        <label>Marshal<select aria-label="Marshal" required value={marshalId} onChange={e => setMarshalId(e.target.value)}>
          {data.marshals.map(item => <option key={item.id} value={item.id}>{item.name || `Marshal #${item.id}`} · {item.service_area || 'Property service area'}</option>)}
        </select></label><label>Offer timeout (seconds)<input aria-label="Offer timeout (seconds)" required type="number" min={10} max={300} step={1} value={expiry} onChange={e => setExpiry(Number(e.target.value))} /></label>
        <button disabled={busy || !marshalId} type="submit">Offer assignment</button>
      </fieldset></form> : <p>No eligible marshal is currently available. Availability must be current and capacity free.</p>)}
      <h3>History</h3>{data.timeline.items.length ? <ol className="history-list">{data.timeline.items.map(item => <li key={item.key}>
        <strong>{item.previous_status ? `${item.previous_status} → ` : ''}{item.status}</strong>
        <p>{item.reason}</p><small>{date(item.occurred_at)} · {item.actor_subject}{item.assignment_id ? ` · Assignment #${item.assignment_id}` : ''}</small>
      </li>)}</ol> : <p>No status changes recorded.</p>}
      <Pagination data={data.timeline} onPage={setTimelinePage} label="Timeline" />
      <h3>Evidence</h3>{data.evidence.items.length ? <ul className="history-list">{data.evidence.items.map(item => <EvidencePreview key={item.id} item={item} path={path} />)}</ul> : <p>No evidence has been stored for this incident.</p>}
      <Pagination data={data.evidence} onPage={setEvidencePage} label="Evidence" />
      <h3>Assignment history</h3><ul className="history-list">{data.assignments.items.map(item => <li key={item.id}>#{item.id} · {item.status} · {date(item.offered_at)}</li>)}</ul>
      <Pagination data={data.assignments} onPage={setAssignmentPage} label="Assignments" />
    </>}
    {success && <p role="status">{success}</p>}{actionError && <p role="alert">{actionError}</p>}
  </section>;
}

export default function OperatorWorkspace({ propertyId, initialCameraId, refreshVersion, onChanged }: {
  propertyId: number; initialCameraId: string | null; refreshVersion: number; onChanged: () => void;
}) {
  const [page, setPage] = useState(1); const [source, setSource] = useState(''); const [status, setStatus] = useState(''); const [severity, setSeverity] = useState('');
  const [selected, setSelected] = useState<Pick<CaseSummary, 'source' | 'source_id'> | null>(initialCameraId ? { source: 'camera', source_id: Number(initialCameraId) } : null);
  const [data, setData] = useState<Page<CaseSummary> | null>(null); const [error, setError] = useState('');
  const [loading, setLoading] = useState(true); const [revision, setRevision] = useState(0);
  useEffect(() => {
    const abort = new AbortController();
    const query = new URLSearchParams({ page: String(page), page_size: '20' });
    if (source) query.set('source', source); if (status) query.set('status', status); if (severity) query.set('severity', severity);
    request<Page<CaseSummary>>(`/properties/${propertyId}/cases?${query}`, { signal: abort.signal }).then(result => {
      if (abort.signal.aborted) return;
      setData(result); setError('');
      const last = Math.max(1, Math.ceil(result.total / result.page_size)); if (page > last) setPage(last);
    }).catch(error => { if (!abort.signal.aborted) setError(message(error)); })
      .finally(() => { if (!abort.signal.aborted) setLoading(false); });
    return () => abort.abort();
  }, [propertyId, page, source, status, severity, revision, refreshVersion]);
  const changed = () => { setRevision(value => value + 1); onChanged(); };
  const filterChanged = () => { setPage(1); setLoading(true); };
  return <div className="incident-layout"><section className="incident-panel"><h2>Incident history</h2>
    <div className="incident-filters"><label>Source<select aria-label="Source" value={source} onChange={e => { setSource(e.target.value); filterChanged(); }}>
      <option value="">All sources</option><option value="camera">Camera detections</option><option value="reporter">Manual reports</option></select></label>
      <label>Status<select aria-label="Status" value={status} onChange={e => { setStatus(e.target.value); filterChanged(); }}><option value="">All statuses</option>
        {['OPEN', 'ACKNOWLEDGED', 'UNCLASSIFIED', 'RESOLVED', 'DISMISSED', 'CLOSED'].map(item => <option key={item}>{item}</option>)}</select></label>
      <label>Severity<select aria-label="Severity" value={severity} onChange={e => { setSeverity(e.target.value); filterChanged(); }}><option value="">All severities</option>
        {['INFO', 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL'].map(item => <option key={item}>{item}</option>)}</select></label>
      <button onClick={() => { setLoading(true); setRevision(value => value + 1); }}>Refresh incidents</button></div>
    {loading && <p role="status">Loading incidents…</p>}{error && <p role="alert">{error}</p>}
    {!loading && !error && data && <><p>{data.total} matching incidents</p>{!data.items.length && <p>No incidents match these filters.</p>}
      <ul className="incident-list">{data.items.map(item => <li key={item.key}><button aria-pressed={selected?.source === item.source && selected?.source_id === item.source_id} onClick={() => setSelected(item)}>
        <strong>#{item.source_id} · {item.incident_type.replaceAll('_', ' ')}</strong>
        <span className="incident-status">{item.source === 'camera' ? 'Camera detection' : 'Manual report'} · {item.status} · {item.severity || 'Severity unassigned'}</span>
        <small>{date(item.occurred_at)}</small></button></li>)}</ul>
      <Pagination data={data} label="Incidents" onPage={value => { setPage(value); setLoading(true); }} /></>}
  </section>{selected ? <OperatorDetail key={`${propertyId}:${selected.source}:${selected.source_id}`} propertyId={propertyId} selected={selected} refreshVersion={refreshVersion + revision} onChanged={changed} />
    : <section className="incident-panel"><p>Select an incident to review its details, evidence, and response.</p></section>}</div>;
}
