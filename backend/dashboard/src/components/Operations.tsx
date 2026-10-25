import { useEffect, useState } from 'react';
import { readiness } from '../api';

export default function Operations({ generation }: { generation: number }) {
  const [health, setHealth] = useState<Awaited<ReturnType<typeof readiness>> | null>(null);
  const [observed, setObserved] = useState('');
  useEffect(() => {
    const abort = new AbortController();
    const update = async () => {
      try {
        const value = await readiness(AbortSignal.any([abort.signal, AbortSignal.timeout(10000)]));
        if (!abort.signal.aborted) { setHealth(value); setObserved(new Date().toISOString()); }
      } catch { if (!abort.signal.aborted) { setHealth(null); setObserved(new Date().toISOString()); } }
    };
    void update(); const timer = setInterval(() => void update(), 15000);
    return () => { abort.abort(); clearInterval(timer); };
  }, [generation]);
  return <section className="data-panel operations" aria-label="Operations health">
    <h2>Operations</h2>
    <p>API readiness: {health ? health.status === 'ok' ? 'healthy' : 'degraded' : 'unknown — unavailable'}</p>
    <p>Database: {health?.checks.database === 'ok' ? 'healthy' : health ? 'offline' : 'unknown'}</p>
    <p>MQTT consumer: {health?.checks.mqtt === 'ok' ? 'healthy' : health ? 'offline' : 'unknown'}</p>
    <p>Checked: {observed ? new Date(observed).toLocaleString() : 'Unknown'}</p>
    <p>Ingestion lag, queue backlog, parsing errors, DB retries, notification worker: Unavailable — metrics endpoint pending.</p>
  </section>;
}
