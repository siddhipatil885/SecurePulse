import { useState } from 'react';
import { Text } from 'react-native';
import { router, useLocalSearchParams } from 'expo-router';
import { useCameras, useDetail, useReviewEvent } from '../api/queries';
import { Screen } from '../components/Screen';
import { PrimaryButton } from '../components/PrimaryButton';
import { Notice, PropertyBanner, QueryState, ui } from '../components/Content';

function useId() { const { id } = useLocalSearchParams<{ id: string }>(); return typeof id === 'string' && /^[1-9]\d*$/.test(id) ? Number(id) : NaN; }
export function AlertDetailScreen() {
  const id = useId(); const query = useDetail('event', id); const cameras = useCameras();
  const reviewEvent = useReviewEvent();
  const [reviewError, setReviewError] = useState<string | null>(null);
  const [reviewing, setReviewing] = useState(false);
  const event = query.data && 'event_type' in query.data ? query.data : null;
  async function review(decision: 'CONFIRMED' | 'FALSE_ALARM') {
    setReviewing(true); setReviewError(null);
    try { await reviewEvent(id, decision); await query.refetch(); }
    catch (error) { setReviewError(error instanceof Error ? error.message : 'Unable to review this alert.'); }
    finally { setReviewing(false); }
  }
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
      {event.alert_id && event.alert_status === 'ACTIVE' ? <>
        <PrimaryButton label={reviewing ? 'Reviewing…' : 'Confirm threat'} onPress={() => void review('CONFIRMED')} disabled={reviewing} />
        <PrimaryButton variant="secondary" label={reviewing ? 'Reviewing…' : 'Dismiss as false alarm'} onPress={() => void review('FALSE_ALARM')} disabled={reviewing} />
      </> : <Notice>Alert review status: {event.alert_status ?? 'not an operator alert'}.</Notice>}
      {reviewError && <Text accessibilityRole="alert" style={ui.error}>{reviewError}</Text>}
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
