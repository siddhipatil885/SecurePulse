import { useState } from 'react';
import type { FormEvent } from 'react';
import { request } from '../api';
import type { Profile, PropertyAccess } from '../api';

export function PropertyForm({ property, onSaved, onCancel }: {
  property?: PropertyAccess; onSaved: (profile: Profile) => void; onCancel?: () => void;
}) {
  const [name, setName] = useState(property?.name ?? '');
  const [address, setAddress] = useState(property?.address ?? '');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function submit(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError('');
    try {
      onSaved(await request<Profile>(property ? `/properties/${property.id}` : '/properties', {
        method: property ? 'PATCH' : 'POST', body: JSON.stringify({ name, address }),
      }));
    } catch (error) { setError(error instanceof Error ? error.message : 'Unable to save property.'); }
    finally { setBusy(false); }
  }
  return <section className="account-card"><h1>{property ? 'Complete property details' : 'Add your property'}</h1>
    <p>Each property has its own cameras, incidents, and access permissions.</p>
    <form onSubmit={submit}><fieldset disabled={busy}>
      <label>Property name<input required minLength={2} maxLength={255} value={name} onChange={e => setName(e.target.value)} autoComplete="organization" /></label>
      <label>Property address<textarea required minLength={5} maxLength={1000} value={address} onChange={e => setAddress(e.target.value)} autoComplete="street-address" /></label>
      {error && <p role="alert">{error}</p>}
      <button type="submit">{busy ? 'Saving…' : 'Save property'}</button>
      {onCancel && <button type="button" onClick={onCancel}>Cancel</button>}
    </fieldset></form>
  </section>;
}

export function AccountFlow({ onSignedIn, registrationEnabled, authEnabled, notice }: {
  onSignedIn: (profile: Profile) => void; registrationEnabled: boolean; authEnabled: boolean; notice: string;
}) {
  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [step, setStep] = useState(1);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmation, setConfirmation] = useState('');
  const [fullName, setFullName] = useState('');
  const [name, setName] = useState('');
  const [address, setAddress] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  function changeMode(next: 'login' | 'register') {
    setMode(next); setStep(1); setPassword(''); setConfirmation(''); setError('');
  }
  async function submit(event: FormEvent) {
    event.preventDefault(); setError('');
    if (mode === 'register') {
      if (password !== confirmation) { setError('Passwords do not match.'); return; }
      if (!/[a-zA-Z]/.test(password) || !/\d/.test(password)) { setError('Include a letter and a number in your password.'); return; }
      if (step === 1) { setStep(2); return; }
    }
    setBusy(true);
    try {
      const profile = await request<Profile>(`/auth/${mode}`, { method: 'POST',
        body: JSON.stringify(mode === 'login' ? { email, password } : { email, password, full_name: fullName, name, address }),
      });
      setPassword(''); setConfirmation(''); onSignedIn(profile);
    } catch (error) { setError(error instanceof Error ? error.message : 'Unable to sign in.'); }
    finally { setBusy(false); }
  }
  return <main className="account-page"><section className="account-card">
    <div className="brand">SECUREPULSE</div><h1>{mode === 'login' ? 'Welcome back' : step === 1 ? 'Create your account' : 'Tell us about your property'}</h1>
    <p>{mode === 'login' ? 'Sign in to monitor your properties and manage incidents.' : `Step ${step} of 2 · ${step === 1 ? 'Account details' : 'Property details'}`}</p>
    {notice && <p role="status">{notice}</p>}
    {!authEnabled && <p role="alert">Dashboard authentication is not enabled on this server. Ask your administrator to enable it.</p>}
    <form onSubmit={submit}><fieldset disabled={busy || !authEnabled}>
      {(mode === 'login' || step === 1) && <>
        {mode === 'register' && <label>Full name<input autoComplete="name" required minLength={2} maxLength={255} value={fullName} onChange={e => setFullName(e.target.value)} /></label>}
        <label>Email<input type="email" autoComplete="username" required maxLength={254} value={email} onChange={e => setEmail(e.target.value)} /></label>
        <label>Password<input type="password" autoComplete={mode === 'login' ? 'current-password' : 'new-password'} required minLength={mode === 'register' ? 12 : 1} maxLength={128} value={password} onChange={e => setPassword(e.target.value)} /></label>
        {mode === 'register' && <><p className="field-hint">At least 12 characters, including a letter and a number.</p>
          <label>Confirm password<input type="password" autoComplete="new-password" required value={confirmation} onChange={e => setConfirmation(e.target.value)} /></label></>}
      </>}
      {mode === 'register' && step === 2 && <>
        <label>Property name<input required minLength={2} maxLength={255} value={name} onChange={e => setName(e.target.value)} /></label>
        <label>Property address<textarea required minLength={5} maxLength={1000} autoComplete="street-address" value={address} onChange={e => setAddress(e.target.value)} /></label>
        <p className="field-hint">This creates a new property that you own. Access to an existing property must be granted by its administrator.</p>
      </>}
      {error && <p role="alert">{error}</p>}
      <button type="submit">{busy ? 'Please wait…' : mode === 'login' ? 'Sign in' : step === 1 ? 'Continue to property details' : 'Create account'}</button>
      {mode === 'register' && step === 2 && <button type="button" onClick={() => setStep(1)}>Back to account details</button>}
    </fieldset></form>
    {(mode === 'register' || registrationEnabled) ? <button className="text-button" type="button" disabled={busy} onClick={() => changeMode(mode === 'login' ? 'register' : 'login')}>
      {mode === 'register' ? 'Already have an account? Sign in' : 'Create an account'}
    </button> : <p>Registration is managed by your administrator</p>}
  </section></main>;
}
