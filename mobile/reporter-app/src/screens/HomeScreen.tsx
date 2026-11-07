import { Text } from 'react-native';
import { router } from 'expo-router';
import { useCameras, useEvents, useSummary } from '../api/queries';
import { useAuth } from '../auth/AuthProvider';
import { Screen } from '../components/Screen';
import { InfoCard } from '../components/InfoCard';
import { PrimaryButton } from '../components/PrimaryButton';
import { EventCard, Notice, PropertyBanner, QueryState, ui } from '../components/Content';

export function HomeScreen() {
  const { propertyId } = useAuth();
  const cameras = useCameras(); const events = useEvents(); const summary = useSummary();
  const recent = events.data?.pages[0]?.items.slice(0, 3) ?? [];
  const refreshing = summary.isRefetching || events.isRefetching || cameras.isRefetching;
  const refresh = () => { void Promise.all([summary.refetch(), events.refetch(), cameras.refetch()]); };
  return <Screen refreshing={refreshing} onRefresh={refresh}>
    <Text style={ui.title}>Your security overview</Text>
    <PropertyBanner />
    <Notice>{summary.data?.security_status === 'attention_required' ? 'Active alerts or incident records need review.'
      : summary.data?.security_status === 'camera_issue' ? 'A camera is offline or disabled.'
      : summary.data?.security_status === 'no_active_incidents' ? 'No active incident records. Camera health is currently verified.'
      : 'Camera monitoring cannot currently be verified.'} An automated detection does not confirm an incident.</Notice>
    <PrimaryButton label="Report incident" onPress={() => router.push('/report')} disabled={!propertyId} />
    <PrimaryButton variant="secondary" label="Alerts" onPress={() => router.push('/alerts')} />
    <PrimaryButton variant="secondary" label="My incident reports" onPress={() => router.push('/incidents')} />
    {propertyId !== null && <PrimaryButton variant="secondary" label="Cameras" onPress={() => router.push('/cameras')} />}
    <PrimaryButton variant="secondary" label="Profile and properties" onPress={() => router.push('/profile')} />
    <PrimaryButton variant="secondary" label="Settings" onPress={() => router.push('/settings')} />
    <QueryState query={summary} />
    {!summary.isError && summary.data && <>
      <InfoCard label="Registered cameras" value={String(summary.data.camera_count)} detail="Registration does not verify a live connection." />
      <InfoCard label="Connected cameras" value={summary.data.connected_camera_count === null ? 'Unavailable' : String(summary.data.connected_camera_count)} />
      <InfoCard label="Active alerts" value={String(summary.data.active_alert_count)} detail="Operator alerts recorded by the backend." />
      <InfoCard label="Open incident records" value={summary.data.active_incident_count === null ? 'Unverified' : String(summary.data.active_incident_count)} detail="Actionable camera records and your own open reports." />
    </>}
    <Text style={ui.heading}>Recent security alerts</Text>
    <QueryState query={events} empty={!recent.length} />
    {!events.isError && recent.map(event => <EventCard key={event.id} event={event} cameraName={cameras.data?.find(c => c.id === event.camera_id)?.name} />)}
    <PrimaryButton variant="secondary" label="Refresh overview" disabled={!propertyId || refreshing} onPress={refresh} />
  </Screen>;
}
