import { ActivityIndicator, StyleSheet, Text, View } from 'react-native';
import { router } from 'expo-router';
import { useAuth } from '../auth/AuthProvider';
import { normalizeError } from '../api/client';
import type { SecurityEvent } from '../api/types';
import { PrimaryButton } from './PrimaryButton';

export const ui = StyleSheet.create({
  title: { color: '#0f172a', fontSize: 28, fontWeight: '800' },
  heading: { color: '#0f172a', fontSize: 19, fontWeight: '700' },
  text: { color: '#475569', fontSize: 16, lineHeight: 23 },
  card: { backgroundColor: '#fff', borderColor: '#e2e8f0', borderWidth: 1, borderRadius: 12, padding: 16, gap: 8 },
  label: { color: '#334155', fontSize: 15, fontWeight: '600' },
  input: { backgroundColor: '#fff', borderWidth: 1, borderColor: '#94a3b8', borderRadius: 10, color: '#0f172a', padding: 14, minHeight: 50, fontSize: 16 },
  error: { color: '#991b1b', backgroundColor: '#fee2e2', padding: 12, borderRadius: 8 },
});
export function Notice({ children }: { children: React.ReactNode }) { return <Text style={ui.text}>{children}</Text>; }
export function PropertyBanner() {
  const { state, propertyId, online } = useAuth();
  const property = state.profile?.properties.find(item => item.id === propertyId);
  return <View style={ui.card}>
    <Text style={ui.heading}>{property?.name ?? 'No property assigned'}</Text>
    <Notice>{property ? 'Access: ' + property.role : 'Ask your administrator to assign a property.'}</Notice>
    {!online && <Text accessibilityRole="alert" style={ui.error}>You are offline. Displayed data may be out of date.</Text>}
  </View>;
}
export function QueryState({ query, empty }: { query: { isPending: boolean; isError: boolean; error: unknown; fetchStatus: string; refetch: () => unknown }; empty?: boolean }) {
  const { propertyId } = useAuth();
  if (!propertyId) return null;
  if (query.isError) return <View style={ui.card}><Text accessibilityRole="alert" style={ui.error}>{normalizeError(query.error).message}</Text><PrimaryButton label="Retry" onPress={() => { query.refetch(); }} /></View>;
  if (query.fetchStatus === 'paused') return <Notice>Waiting for a network connection.</Notice>;
  if (query.isPending) return <ActivityIndicator accessibilityLabel="Loading" color="#0f766e" />;
  if (empty) return <Notice>No records are available for this property yet.</Notice>;
  return null;
}
export function EventCard({ event, cameraName }: { event: SecurityEvent; cameraName?: string }) {
  return <View style={ui.card}>
    <Text style={ui.heading}>{event.event_type.replaceAll('_', ' ')}</Text>
    <Notice>{cameraName ?? 'Camera #' + event.camera_id} · {event.severity}</Notice>
    <Notice>{new Date(event.timestamp).toLocaleString()} · {event.status}</Notice>
    <PrimaryButton variant="secondary" label="Review alert" onPress={() => router.push({ pathname: '/alerts/[id]', params: { id: event.id } })} />
  </View>;
}
