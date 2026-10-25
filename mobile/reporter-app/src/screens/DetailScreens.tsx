import { Text } from 'react-native';
import { router, useLocalSearchParams } from 'expo-router';
import { useCameras, useDetail } from '../api/queries';
import { Screen } from '../components/Screen';
import { PrimaryButton } from '../components/PrimaryButton';
import { Notice, PropertyBanner, QueryState, ui } from '../components/Content';

function useId() { const { id } = useLocalSearchParams<{ id: string }>(); return typeof id === 'string' && /^[1-9]\d*$/.test(id) ? Number(id) : NaN; }
export function AlertDetailScreen() {
  const id = useId(); const query = useDetail('event', id); const cameras = useCameras();
  const event = query.data && 'event_type' in query.data ? query.data : null;
  return <Screen><PropertyBanner />
    {!Number.isSafeInteger(id) ? <Notice>Invalid alert link.</Notice> : <QueryState query={query} />}
    {!query.isError && event && <>
      <Text style={ui.title}>{event.event_type.replaceAll('_', ' ')}</Text>
      <Notice>{cameras.data?.find(camera => camera.id === event.camera_id)?.name ?? 'Camera #' + event.camera_id}</Notice>
      <Notice>{new Date(event.timestamp).toLocaleString()}</Notice>
      <Notice>Severity: {event.severity} · Status: {event.status}</Notice>
      <Notice>{event.reason ?? 'No additional details provided.'}</Notice>
      {event.zone && <Notice>Zone: {event.zone}</Notice>}
      <Notice>Review this detection before deciding whether an incident occurred. No marshal notification or dispatch is sent.</Notice>
      <PrimaryButton label="False alarm — unavailable" onPress={() => {}} disabled />
      <Notice>False alarm review is not supported by the server yet.</Notice>
      <PrimaryButton label="Report incident" onPress={() => router.push({ pathname: '/report', params: { eventId: event.id } })} />
    </>}
  </Screen>;
}
export function CameraDetailScreen() {
  const id = useId(); const query = useDetail('camera', id);
  const camera = query.data && 'enabled' in query.data ? query.data : null;
  return <Screen><PropertyBanner />
    {!Number.isSafeInteger(id) ? <Notice>Invalid camera link.</Notice> : <QueryState query={query} />}
    {!query.isError && camera && <>
      <Text style={ui.title}>{camera.name}</Text><Notice>{camera.location ?? 'No location provided'}</Notice>
      <Notice>Configuration: {camera.enabled ? 'enabled' : 'disabled'}</Notice>
      <Notice>Connection status: unverified. Live camera health is not available from the server.</Notice>
      <Notice>Live streaming is not available in this version.</Notice>
    </>}
  </Screen>;
}
