import { useEffect, useState } from 'react';
import { Switch, Text, View } from 'react-native';
import * as SecureStore from 'expo-secure-store';
import * as Notifications from 'expo-notifications';
import { Platform } from 'react-native';
import { api, useAuth } from '../auth/AuthProvider';
import { expoProjectId, serverUrl } from '../config';
import { Screen } from '../components/Screen';
import { Notice, ui } from '../components/Content';
export function SettingsScreen() {
  const { state } = useAuth();
  const [notifications, setNotifications] = useState<Record<string, boolean>>({
    SECURITY_ALERTS: false, INCIDENT_UPDATES: false, DISPATCH_UPDATES: false,
  });
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let active = true;
    api.notificationPreferences().then(values => {
      if (!active) return;
      setNotifications(current => values.reduce((result, value) => ({ ...result, [value.category]: value.enabled }), current));
    })
      .catch(() => { if (active) setError('Unable to read saved preferences.'); })
      .finally(() => { if (active) setBusy(false); });
    return () => { active = false; };
  }, []);
  async function save(category: string, value: boolean) {
    setBusy(true); setError(null);
    try {
      if (value) await registerNotifications();
      await api.updateNotificationPreference(category, value);
      setNotifications(current => ({ ...current, [category]: value }));
    } catch (error) { setError(error instanceof Error ? error.message : 'Unable to save this preference.'); }
    finally { setBusy(false); }
  }
  async function registerNotifications() {
    if (Platform.OS === 'web') throw new Error('Push notifications require a native build.');
    if (!expoProjectId) throw new Error('Push notifications are not configured for this build.');
    const permission = await Notifications.requestPermissionsAsync();
    if (!permission.granted) throw new Error('Notification permission was denied.');
    const token = await Notifications.getExpoPushTokenAsync({ projectId: expoProjectId });
    const deviceKey = 'securepulse.device.id';
    let deviceId = await SecureStore.getItemAsync(deviceKey);
    if (!deviceId) {
      deviceId = `${Platform.OS}-${Date.now()}-${Math.random().toString(36).slice(2)}`;
      await SecureStore.setItemAsync(deviceKey, deviceId);
    }
    await api.registerDevice({ device_id: deviceId, push_token: token.data, provider: 'expo' });
  }
  return <Screen><Text style={ui.title}>Settings</Text>
    <Text style={ui.heading}>Notification preferences</Text>
    {([
      ['SECURITY_ALERTS', 'Security alerts'],
      ['INCIDENT_UPDATES', 'My incident updates'],
      ['DISPATCH_UPDATES', 'Responder updates'],
    ] as const).map(([category, label]) => <View key={category} style={ui.card}><Text style={ui.label}>{label}</Text><Switch accessibilityLabel={`${label} notification preference`} value={notifications[category]} disabled={busy} onValueChange={value => void save(category, value)} /></View>)}
    <Notice>Preferences are synchronized with the server. Delivery requires configured Expo/FCM/APNs infrastructure.</Notice>
    {error && <Text accessibilityRole="alert" style={ui.error}>{error}</Text>}
    <Text style={ui.heading}>Connected server</Text><Notice>{serverUrl ?? 'Not configured'}</Notice>
    <Notice>Session tokens are stored securely. When your session expires, sign in again.</Notice>
  </Screen>;
}
