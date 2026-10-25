import { useState } from 'react';
import { Platform, Text, TextInput } from 'react-native';
import { session, useAuth } from '../auth/AuthProvider';
import { normalizeError } from '../api/client';
import { serverUrl } from '../config';
import { Screen } from '../components/Screen';
import { PrimaryButton } from '../components/PrimaryButton';
import { Notice, ui } from '../components/Content';

export function LoginScreen() {
  const { state, online } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function submit() {
    setBusy(true); setError(null);
    try { await session.login(email, password); }
    catch (caught) { setError(normalizeError(caught).message); }
    finally { setBusy(false); setPassword(''); }
  }
  return <Screen>
    <Text style={ui.title}>Welcome back</Text>
    <Notice>Sign in to review your property's security alerts.</Notice>
    {!serverUrl && <Text style={ui.error}>Server address is not configured. Set EXPO_PUBLIC_SERVER_URL in the app environment.</Text>}
    {Platform.OS === 'web' && <Notice>Secure sign-in is available in the Android and iOS app.</Notice>}
    {state.message && <Notice>{state.message}</Notice>}
    {!online && <Notice>You are offline. Connect to sign in.</Notice>}
    {error && <Text accessibilityRole="alert" style={ui.error}>{error}</Text>}
    <Text style={ui.label}>Email</Text>
    <TextInput accessibilityLabel="Email" style={ui.input} value={email} onChangeText={setEmail} autoCapitalize="none" autoCorrect={false} keyboardType="email-address" autoComplete="email" editable={!busy} maxLength={254} />
    <Text style={ui.label}>Password</Text>
    <TextInput accessibilityLabel="Password" style={ui.input} value={password} onChangeText={setPassword} secureTextEntry autoCapitalize="none" autoCorrect={false} autoComplete="current-password" editable={!busy} maxLength={128} />
    <PrimaryButton label={busy ? 'Signing in…' : 'Sign in'} onPress={() => void submit()} disabled={busy || !email.trim() || !password || !serverUrl || !online || Platform.OS === 'web'} />
    <PrimaryButton variant="secondary" label="Restore saved session" onPress={() => void session.restore()} disabled={busy || !online || !serverUrl} />
    <Notice>Contact your property administrator if you need an account or password assistance.</Notice>
  </Screen>;
}
