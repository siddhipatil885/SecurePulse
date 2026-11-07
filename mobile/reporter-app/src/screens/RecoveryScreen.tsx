import { useState } from 'react';
import { Text, TextInput } from 'react-native';
import { router } from 'expo-router';
import { api } from '../auth/AuthProvider';
import { Screen } from '../components/Screen';
import { PrimaryButton } from '../components/PrimaryButton';
import { Notice, ui } from '../components/Content';

export function RecoveryScreen() {
  const [email, setEmail] = useState(''); const [purpose, setPurpose] = useState<'password' | 'verification'>('password');
  const [code, setCode] = useState(''); const [password, setPassword] = useState(''); const [confirm, setConfirm] = useState('');
  const [sent, setSent] = useState(false); const [busy, setBusy] = useState(false); const [message, setMessage] = useState(''); const [error, setError] = useState('');
  async function submit(requestOnly = false) {
    if (!requestOnly && sent && purpose === 'password' && (password.length < 12 || password !== confirm)) { setError('Use at least 12 characters and matching passwords.'); return; }
    setBusy(true); setError(''); setMessage('');
    try {
      const result = requestOnly || !sent ? await api.requestRecovery(email.trim().toLowerCase(), purpose)
        : purpose === 'verification' ? await api.verifyEmail(email.trim().toLowerCase(), code)
          : await api.resetPassword(email.trim().toLowerCase(), code, password);
      setMessage(result.message);
      if (requestOnly || !sent) setSent(true);
      else { setSent(false); setCode(''); setPassword(''); setConfirm(''); }
    } catch (error) { setError(error instanceof Error ? error.message : 'Unable to recover the account.'); }
    finally { setBusy(false); }
  }
  return <Screen><Text style={ui.title}>Account recovery</Text>
    <Notice>Codes are sent by the account service. Older administrator-managed accounts need administrator assistance.</Notice>
    <PrimaryButton label={purpose === 'password' ? 'Switch to email verification' : 'Switch to password recovery'} variant="secondary" disabled={busy} onPress={() => { setPurpose(purpose === 'password' ? 'verification' : 'password'); setSent(false); setCode(''); setPassword(''); setConfirm(''); setMessage(''); setError(''); }} />
    <Text style={ui.label}>Email</Text><TextInput accessibilityLabel="Recovery email" style={ui.input} autoCapitalize="none" keyboardType="email-address" value={email} editable={!busy && !sent} onChangeText={setEmail} />
    {sent && <><Text style={ui.label}>Email code</Text><TextInput accessibilityLabel="Email code" style={ui.input} keyboardType="number-pad" autoComplete="one-time-code" maxLength={12} value={code} onChangeText={setCode} editable={!busy} />
      {purpose === 'password' && <><Text style={ui.label}>New password</Text><TextInput accessibilityLabel="New password" style={ui.input} secureTextEntry value={password} onChangeText={setPassword} editable={!busy} maxLength={128} />
        <Text style={ui.label}>Confirm new password</Text><TextInput accessibilityLabel="Confirm new password" style={ui.input} secureTextEntry value={confirm} onChangeText={setConfirm} editable={!busy} maxLength={128} /></>}
      <PrimaryButton label="Resend code" variant="secondary" disabled={busy} onPress={() => void submit(true)} />
      <PrimaryButton label="Change email" variant="secondary" disabled={busy} onPress={() => { setSent(false); setCode(''); setPassword(''); setConfirm(''); setMessage(''); setError(''); }} /></>}
    {message && <Notice>{message}</Notice>}{error && <Text accessibilityRole="alert" style={ui.error}>{error}</Text>}
    <PrimaryButton label={busy ? 'Please wait…' : !sent ? 'Send email code' : purpose === 'password' ? 'Reset password' : 'Verify email'} disabled={busy || !email.trim() || (sent && !code)} onPress={() => void submit()} />
    <PrimaryButton label="Back to sign in" variant="secondary" disabled={busy} onPress={() => router.replace('/login')} />
  </Screen>;
}
