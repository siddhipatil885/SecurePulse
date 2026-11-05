import { useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import { allowedActions, request } from '../api';
import type { Evidence, IncidentAction, IncidentHistory, IncidentRecord, PropertyAccess } from '../api';

type Page = { items: IncidentRecord[]; total: number; page: number; page_size: number };
const describe = (error: unknown) => error instanceof Error ? error.message : 'Unable to load incident data.';
const formatDate = (value: string) => new Date(value).toLocaleString();

function EvidenceItem({ item, base }: { item: Evidence; base: string }) {
  const [url, setUrl] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  async function open() {
    setBusy(true); setError(''); setUrl('');
    try { const access = await request<{ url: string }>(`${base}/evidence/${item.id}/access`, { method: 'POST' }); setUrl(access.url); }
    catch (error) { setError(describe(error)); }
    finally { setBusy(false); }
  }
  const isVideo = /clip|video/i.test(item.type);
  return <li><p>{item.type} · {formatDate(item.timestamp)}</p>
    <button onClick={() => void open()} disabled={busy}>{busy ? 'Opening…' : 'View evidence'}</button>
    {error && <p role="alert">{error}</p>}
    {url && (isVideo
      ? <video className="evidence-media" src={url} controls onError={() => { setUrl(''); setError('Evidence could not be loaded. Request access again or contact your administrator.'); }} />
      : <img className="evidence-media" src={url} alt={`Incident evidence ${item.id}`} onError={() => { setUrl(''); setError('Evidence could not be loaded. Request access again or contact your administrator.'); }} />)}
  </li>;
}

function IncidentDetail({ id, property, onChanged, refreshVersion }: { id: string; property: PropertyAccess; onChanged: () => void; refreshVersion: number }) {
  const [detail, setDetail] = useState<{ incident: IncidentRecord; history: IncidentHistory[]; evidence: Evidence[] } | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [actionError, setActionError] = useState('');
  const [success, setSuccess] = useState('');
  const [action, setAction] = useState<IncidentAction>('acknowledge');
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const [revision, setRevision] = useState(0);
  const base = `/properties/${property.id}`;
  useEffect(() => {
    const controller = new AbortController();
    Promise.all([
      request<IncidentRecord>(`${base}/incidents/${id}`, { signal: controller.signal }),
      request<IncidentHistory[]>(`${base}/incidents/${id}/history`, { signal: controller.signal }),
      request<Evidence[]>(`${base}/incidents/${id}/evidence`, { signal: controller.signal }),
    ]).then(([incident, history, evidence]) => {
      if (controller.signal.aborted) return;
      setDetail({ incident, history, evidence });
      setAction(current => allowedActions(incident.status).includes(current) ? current : allowedActions(incident.status)[0] ?? 'acknowledge');
    }).catch(error => { if (!controller.signal.aborted) setError(describe(error)); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [base, id, revision, refreshVersion]);
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (busy || !reason.trim()) return;
    setBusy(true); setActionError(''); setSuccess('');
    try {
      const result = await request<IncidentRecord>(`${base}/incidents/${id}/commands`, { method: 'POST',
        body: JSON.stringify({ command: action, reason: reason.trim(), correlation_id: crypto.randomUUID() }),
      });
      setSuccess(`Incident updated to ${result.status}.`); setReason(''); onChanged();
    } catch (error) { setActionError(describe(error)); }
    finally { setBusy(false); setLoading(true); setError(''); setRevision(value => value + 1); }
  }
  const actions = detail ? allowedActions(detail.incident.status) : [];
  return <section className="incident-panel incident-detail" aria-label="Incident details">
    <h2>Incident #{id}</h2>
    {loading && <p role="status">Loading incident…</p>}
    {error && <><p role="alert">{error}</p><button onClick={() => { setLoading(true); setError(''); setRevision(value => value + 1); }}>Retry details</button></>}
    {!loading && !error && detail && <>
      <dl><dt>Type</dt><dd>{detail.incident.event_type.replaceAll('_', ' ')}</dd>
        <dt>Status</dt><dd>{detail.incident.status}</dd><dt>Severity</dt><dd>{detail.incident.severity}</dd>
        <dt>Camera</dt><dd>#{detail.incident.camera_id}</dd><dt>Detected</dt><dd>{formatDate(detail.incident.timestamp)}</dd>
        <dt>Confidence</dt><dd>{Math.round(detail.incident.confidence * 100)}%</dd>
        <dt>Zone</dt><dd>{detail.incident.zone || 'Not specified'}</dd>
        <dt>Details</dt><dd>{detail.incident.reason || 'No additional details'}</dd></dl>
      {property.role !== 'reporter' && actions.length > 0 ? <form onSubmit={submit} aria-label="Incident actions"><fieldset disabled={busy}>
        <h3>Update incident</h3><label>Action<select aria-label="Action" value={action} onChange={e => setAction(e.target.value as IncidentAction)}>
          {actions.map(item => <option key={item} value={item}>{item === 'dismiss' ? 'Dismiss as false alarm' : item.charAt(0).toUpperCase() + item.slice(1)}</option>)}
        </select></label>
        <label>Reason<textarea value={reason} onChange={e => setReason(e.target.value)} required maxLength={1000} /></label>
        <p className="field-hint">This change is recorded in the incident history.</p>
        <button type="submit" disabled={busy || !reason.trim()}>{busy ? 'Saving action…' : 'Confirm action'}</button>
      </fieldset></form> : property.role === 'reporter' && <p>You have read-only access to this property.</p>}
      <h3>History</h3>{detail.history.length === 0 ? <p>No status changes recorded.</p> : <ol className="history-list">
        {detail.history.map(item => <li key={item.id}><strong>{item.previous_status ?? 'Created'} → {item.new_status}</strong>
          <p>{item.reason}</p><small>{formatDate(item.occurred_at)} · {item.actor_subject}</small></li>)}
      </ol>}
      <h3>Evidence</h3>{detail.evidence.length === 0 ? <p>No evidence has been stored for this incident.</p> : <ul className="history-list">
        {detail.evidence.map(item => <EvidenceItem key={item.id} item={item} base={base} />)}
      </ul>}
    </>}
    {success && <p role="status">{success}</p>}{actionError && <p role="alert">{actionError}</p>}
  </section>;
}

export default function IncidentWorkspace({ property, initialId, onChanged, refreshVersion }: {
  property: PropertyAccess; initialId: string | null; onChanged: () => void; refreshVersion: number;
}) {
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState('');
  const [severity, setSeverity] = useState('');
  const [selected, setSelected] = useState(initialId);
  const [data, setData] = useState<Page | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    const query = new URLSearchParams({ page: String(page), page_size: '20' });
    if (status) query.set('status', status);
    if (severity) query.set('severity', severity);
    request<Page>(`/properties/${property.id}/incidents?${query}`, { signal: controller.signal })
      .then(result => {
        if (controller.signal.aborted) return;
        setData(result);
        const lastPage = Math.max(1, Math.ceil(result.total / result.page_size));
        if (page > lastPage) setPage(lastPage);
      })
      .catch(error => { if (!controller.signal.aborted) setError(describe(error)); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [property.id, page, status, severity, revision, refreshVersion]);
  return <div className="incident-layout"><section className="incident-panel"><h2>Incident history</h2>
    <div className="incident-filters"><label>Status<select aria-label="Status" value={status} onChange={e => { setStatus(e.target.value); setPage(1); setLoading(true); setError(''); }}>
      <option value="">All statuses</option>{['OPEN', 'ACKNOWLEDGED', 'UNCLASSIFIED', 'RESOLVED', 'DISMISSED', 'CLOSED'].map(item => <option key={item}>{item}</option>)}
    </select></label><label>Severity<select aria-label="Severity" value={severity} onChange={e => { setSeverity(e.target.value); setPage(1); setLoading(true); setError(''); }}>
      <option value="">All severities</option>{['INFO', 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL'].map(item => <option key={item}>{item}</option>)}
    </select></label><button onClick={() => { setLoading(true); setError(''); setRevision(value => value + 1); }}>Refresh incidents</button></div>
    {loading && <p role="status">Loading incidents…</p>}{error && <p role="alert">{error}</p>}
    {!loading && !error && data && <><p>{data.total} matching incidents</p>{data.items.length === 0 ? <p>No incidents match these filters.</p> : <ul className="incident-list">
      {data.items.map(item => <li key={item.id}><button aria-pressed={selected === String(item.id)} onClick={() => setSelected(String(item.id))}>
        <strong>#{item.id} · {item.event_type.replaceAll('_', ' ')}</strong><span className="incident-status">{item.status} · {item.severity} · Camera #{item.camera_id}</span>
        <small>{formatDate(item.timestamp)}</small></button></li>)}
    </ul>}<div className="pagination"><button disabled={page === 1} onClick={() => { setPage(value => value - 1); setLoading(true); setError(''); }}>Previous</button>
      <span>Page {page} of {Math.max(1, Math.ceil(data.total / data.page_size))}</span>
      <button disabled={page * data.page_size >= data.total} onClick={() => { setPage(value => value + 1); setLoading(true); setError(''); }}>Next</button></div></>}
  </section>{selected ? <IncidentDetail key={`${property.id}:${selected}`} id={selected} property={property} refreshVersion={refreshVersion}
    onChanged={() => { setLoading(true); setError(''); setRevision(value => value + 1); onChanged(); }} /> : <section className="incident-panel"><p>Select an incident to view its history, evidence, and available actions.</p></section>}
  </div>;
}
