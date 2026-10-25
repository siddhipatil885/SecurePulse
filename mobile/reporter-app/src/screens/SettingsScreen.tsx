import { useEffect, useState } from 'react';
import { Switch, Text } from 'react-native';
import * as SecureStore from 'expo-secure-store';
import { serverUrl } from '../config';
import { useAuth } from '../auth/AuthProvider';
import { Screen } from '../components/Screen';
import { Notice, ui } from '../components/Content';
export function SettingsScreen() {
  const { state } = useAuth();
  const key = 'securepulse.preferences.' + state.profile?.id;
  const [notifications, setNotifications] = useState(false);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let active = true;
    SecureStore.getItemAsync(key).then(value => { if (active) setNotifications(value === 'true'); })
      .catch(() => { if (active) setError('Unable to read saved preferences.'); })
      .finally(() => { if (active) setBusy(false); });
    return () => { active = false; };
  }, [key]);
  async function save(value: boolean) {
    setBusy(true); setError(null);
    try { await SecureStore.setItemAsync(key, String(value)); setNotifications(value); }
    catch { setError('Unable to save this preference.'); }
    finally { setBusy(false); }
  }
  return <Screen><Text style={ui.title}>Settings</Text>
    <Text style={ui.heading}>Security alert notifications</Text>
    <Switch accessibilityLabel="Security alert notification preference" value={notifications} disabled={busy} onValueChange={value => void save(value)} />
    <Notice>This preference is saved only on this device. Push notifications are not enabled yet.</Notice>
    {error && <Text accessibilityRole="alert" style={ui.error}>{error}</Text>}
    <Text style={ui.heading}>Connected server</Text><Notice>{serverUrl ?? 'Not configured'}</Notice>
    <Notice>Session tokens are stored securely. When your session expires, sign in again.</Notice>
  </Screen>;
}
