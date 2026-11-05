import Dashboard from './components/Dashboard'
import { useEffect, useState } from 'react'
import { AccountFlow, PropertyForm } from './components/AccountFlow'
import { ApiError, request, resetSessionRequests } from './api'
import type { Profile } from './api'
import './account.css'

function savedProperty(user: Profile): number | null {
  try { const id = Number(sessionStorage.getItem(`securepulse.property.${user.id}`)); return user.properties.some(item => item.id === id) ? id : null; }
  catch { return null; }
}
function saveProperty(user: Profile, id: number | null) {
  try {
    if (id === null) sessionStorage.removeItem(`securepulse.property.${user.id}`);
    else sessionStorage.setItem(`securepulse.property.${user.id}`, String(id));
  } catch { /* Storage can be unavailable in private browser sessions. */ }
}

function App() {
  const [profile, setProfile] = useState<Profile | null>(null);
  const [selected, setSelected] = useState<number | null>(null);
  const [adding, setAdding] = useState(false);
  const [loading, setLoading] = useState(true);
  const [config, setConfig] = useState({ auth_enabled: false, registration_enabled: false });
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const [loggingOut, setLoggingOut] = useState(false);
  const [checkingAccess, setCheckingAccess] = useState(false);
  useEffect(() => {
    let active = true;
    const expire = () => { resetSessionRequests(); setProfile(null); setSelected(null); setAdding(false); setNotice('Your session has ended. Please sign in again.'); };
    let checking = false;
    const refreshAccess = async () => {
      if (checking) return;
      checking = true; setCheckingAccess(true);
      try {
        const user = await request<Profile>('/auth/session');
        if (active) { setProfile(user); setNotice('Your property permissions have changed. Access has been refreshed.'); }
      } catch (error) {
        if (active) { expire(); if (!(error instanceof ApiError && error.status === 401)) setError('Unable to verify property access. Please sign in again.'); }
      } finally { checking = false; if (active) setCheckingAccess(false); }
    };
    window.addEventListener('dashboard-session-expired', expire);
    window.addEventListener('dashboard-access-changed', refreshAccess);
    async function bootstrap() {
      try {
        const settings = await request<typeof config>('/config');
        if (!active) return;
        setConfig(settings);
        if (settings.auth_enabled) {
          try { const user = await request<Profile>('/auth/session'); if (active) { setProfile(user); setSelected(savedProperty(user)); setNotice(''); } }
          catch (error) { if (!(error instanceof ApiError && error.status === 401)) throw error; }
        }
      } catch (error) { if (active) setError(error instanceof Error ? error.message : 'Server unavailable.'); }
      finally { if (active) setLoading(false); }
    }
    void bootstrap();
    return () => { active = false; window.removeEventListener('dashboard-session-expired', expire); window.removeEventListener('dashboard-access-changed', refreshAccess); };
  }, []);
  const property = profile?.properties.find(item => item.id === selected) ?? profile?.properties[0];
  async function logout() {
    setLoggingOut(true); setError('');
    try { await request('/auth/logout', { method: 'POST' }); resetSessionRequests(); if (profile) saveProperty(profile, null); setProfile(null); setSelected(null); setAdding(false); setNotice('You have signed out.'); }
    catch (error) {
      if (error instanceof ApiError && error.status === 401) { resetSessionRequests(); setProfile(null); setSelected(null); setAdding(false); setNotice('Your session has ended. Please sign in again.'); }
      else setError(error instanceof Error ? error.message : 'Sign out failed. Try again.');
    }
    finally { setLoggingOut(false); }
  }
  if (loading) return <main className="account-page" role="status">Loading your session…</main>;
  if (checkingAccess) return <main className="account-page" role="status">Verifying property access…</main>;
  if (!profile) return <><AccountFlow onSignedIn={user => { resetSessionRequests(); setProfile(user); setSelected(savedProperty(user)); setNotice(''); setError(''); }} registrationEnabled={config.registration_enabled} authEnabled={config.auth_enabled} notice={notice || error} />
    {error && <button className="retry-server" onClick={() => window.location.reload()}>Retry connection</button>}</>;
  return <>
    <div className="account-toolbar"><div><strong>{profile.name}</strong><span className="account-email">{profile.email}</span></div>
      <label>Property<select aria-label="Select property" value={property?.id ?? ''} onChange={e => { const id = Number(e.target.value); setSelected(id); saveProperty(profile, id); setAdding(false); setError(''); }}>
        {profile.properties.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}
      </select></label>
      <button onClick={() => setAdding(true)}>Add property</button>
      <button disabled={loggingOut} onClick={() => void logout()}>{loggingOut ? 'Signing out…' : 'Sign out'}</button>
    </div>
    {error && <p role="alert" className="global-error">{error}</p>}
    {notice && <p role="status" className="property-context">{notice}</p>}
    {adding || !property || (!property.address && property.role === 'owner')
      ? <main className="account-page"><PropertyForm key={adding ? 'new' : property?.id ?? 'first'} property={adding ? undefined : property} onCancel={adding && property ? () => setAdding(false) : undefined}
        onSaved={user => { if (adding || !property) { const id = user.properties.at(-1)?.id ?? null; setSelected(id); saveProperty(user, id); } setProfile(user); setAdding(false); }} /></main>
      : <><div className="property-context"><h1>{property.name}</h1><p>{property.address || 'Address not provided'} · {property.role}</p></div>
        <Dashboard key={`${profile.id}:${property.id}`} property={property} /></>}
  </>;
}

export default App
