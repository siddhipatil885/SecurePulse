import { useEffect, useState } from 'react';
import { Switch, Text, View } from 'react-native';
import { api, useAuth } from '../auth/AuthProvider';
import { serverUrl } from '../config';
import { Screen } from '../components/Screen';
import { Notice, ui } from '../components/Content';
import { isExpoGo, registerPush } from '../notifications';
import { PrimaryButton } from '../components/PrimaryButton';
import { useQuery } from '@tanstack/react-query';
export function SettingsScreen() {
  const { propertyId, state } = useAuth();
  const [testId, setTestId] = useState<number | null>(null);
  const test = useQuery({ queryKey: ['push-test', state.profile?.id, testId], enabled: testId !== null,
    queryFn: () => api.notificationTestStatus(testId!), refetchInterval: query => query.state.data && ['SENT', 'SKIPPED', 'EXHAUSTED'].includes(query.state.data.status) ? false : 5000 });
  const [notifications, setNotifications] = useState<Record<string, boolean>>({
    SECURITY_ALERTS: false, INCIDENT_UPDATES: false, DISPATCH_UPDATES: false,
  });
  const [busy, setBusy] = useState(true);
  const [loaded, setLoaded] = useState(false);
  const [revision, setRevision] = useState(0);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let active = true;
    setBusy(true); setLoaded(false); setError(null);
    api.notificationPreferences().then(values => {
      if (!active) return;
      setNotifications(current => values.reduce((result, value) => ({ ...result, [value.category]: value.enabled }), current));
      setLoaded(true);
    })
      .catch(() => { if (active) setError('Unable to read saved preferences.'); })
      .finally(() => { if (active) setBusy(false); });
    return () => { active = false; };
  }, [revision]);
  async function save(category: string, value: boolean) {
    setBusy(true); setError(null);
    try {
      if (value) await registerPush(api);
      await api.updateNotificationPreference(category, value);
      setNotifications(current => ({ ...current, [category]: value }));
    } catch (error) { setError(error instanceof Error ? error.message : 'Unable to save this preference.'); }
    finally { setBusy(false); }
  }
  async function testPush() {
    if (!propertyId) return;
    setBusy(true); setError(null);
    try { setTestId((await api.testNotification(propertyId)).id); }
    catch (error) { setError(error instanceof Error ? error.message : 'Unable to queue a test notification.'); }
    finally { setBusy(false); }
  }
  return <Screen><Text style={ui.title}>Settings</Text>
    <Text style={ui.heading}>Notification preferences</Text>
    {([
      ['SECURITY_ALERTS', 'Security alerts'],
      ['INCIDENT_UPDATES', 'My incident updates'],
      ['DISPATCH_UPDATES', 'Responder updates'],
    ] as const).map(([category, label]) => <View key={category} style={ui.card}><Text style={ui.label}>{label}</Text><Switch accessibilityLabel={`${label} notification preference`} value={notifications[category]} disabled={busy || !loaded || isExpoGo} onValueChange={value => void save(category, value)} /></View>)}
    {!loaded && !busy && <PrimaryButton label="Retry notification preferences" onPress={() => setRevision(value => value + 1)} />}
    <Notice>{isExpoGo ? 'Remote push notifications are unavailable in Expo Go. Install a development build to enable and test push delivery.' : 'Preferences are synchronized with the server. Delivery requires configured Expo/FCM/APNs infrastructure.'}</Notice>
    <PrimaryButton label="Send test notification" variant="secondary" disabled={busy || !loaded || !propertyId || isExpoGo} onPress={() => void testPush()} />
    {test.data && <Notice>Test status: {test.data.status}. {test.data.message}</Notice>}
    {test.isError && <><Text accessibilityRole="alert" style={ui.error}>Unable to read test delivery status. Retry when connected.</Text>
      <PrimaryButton label="Retry notification status" disabled={test.isFetching} onPress={() => { void test.refetch(); }} /></>}
    {error && <Text accessibilityRole="alert" style={ui.error}>{error}</Text>}
    <Text style={ui.heading}>Connected server</Text><Notice>{serverUrl ?? 'Not configured'}</Notice>
    <Notice>Session tokens are stored securely. When your session expires, sign in again.</Notice>
  </Screen>;
}
