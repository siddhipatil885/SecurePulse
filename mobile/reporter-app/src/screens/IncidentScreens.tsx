import { Image, Pressable, Text, View } from 'react-native';
import { router, useLocalSearchParams } from 'expo-router';
import { useState } from 'react';
import { useIncident, useIncidents } from '../api/queries';
import { api, useAuth } from '../auth/AuthProvider';
import { serverUrl } from '../config';
import { Screen } from '../components/Screen';
import { PrimaryButton } from '../components/PrimaryButton';
import { Notice, QueryState, ui } from '../components/Content';
import { EvidenceVideo } from '../components/EvidenceVideo';

function idFromRoute(value: string | string[] | undefined) {
  const raw = Array.isArray(value) ? value[0] : value;
  return raw && /^[1-9]\d*$/.test(raw) ? Number(raw) : NaN;
}

export function IncidentDetailScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const query = useIncident(idFromRoute(id));
  const { state } = useAuth();
  const [mediaUrls, setMediaUrls] = useState<Record<number, string>>({});
  const [mediaError, setMediaError] = useState<string | null>(null);
  const incident = query.data;
  function mediaFailed(evidenceId: number) {
    setMediaUrls(current => { const next = { ...current }; delete next[evidenceId]; return next; });
    setMediaError('Evidence access expired or the file is unavailable. Request the preview again.');
  }
  async function showEvidence(evidenceId: number) {
    setMediaError(null);
    try {
      const grant = await api.reporterEvidenceAccess(idFromRoute(id), evidenceId);
      if (!serverUrl) throw new Error('Configure the server before viewing evidence.');
      setMediaUrls(current => ({ ...current, [evidenceId]: `${serverUrl}${grant.url}` }));
    } catch (error) {
      setMediaError(error instanceof Error ? error.message : 'Unable to load evidence.');
    }
  }
  return <Screen refreshing={query.isRefetching} onRefresh={() => { void query.refetch(); }}><Text style={ui.title}>Incident report</Text>
    {!Number.isSafeInteger(idFromRoute(id)) ? <Notice>Invalid incident link.</Notice> : <QueryState query={query} />}
    {!query.isError && incident && <>
      <Text style={ui.heading}>Report #{incident.id} · {incident.status.replaceAll('_', ' ')}</Text>
      <Notice>{incident.incident_type.replaceAll('_', ' ')}</Notice>
      <Notice>{incident.address ?? `${incident.latitude}, ${incident.longitude}`}</Notice>
      {incident.description && <Notice>{incident.description}</Notice>}
      <Notice>Submitted {new Date(incident.created_at).toLocaleString()}</Notice>
      {incident.dispatch && <Notice>Response status: {incident.dispatch.status.replaceAll('_', ' ')}</Notice>}
      <Text style={ui.heading}>Timeline</Text>
      {incident.timeline.map(item => <Notice key={item.id}>{new Date(item.occurred_at).toLocaleString()} · {item.message}</Notice>)}
      <Text style={ui.heading}>Evidence</Text>
      {incident.evidence.length ? incident.evidence.map(item => <View key={item.id} style={ui.card}>
        <Notice>{item.original_filename} · {Math.ceil(item.byte_size / 1024)} KB</Notice>
        <Pressable accessibilityRole="button" onPress={() => void showEvidence(item.id)}>
          <Text style={ui.text}>{mediaUrls[item.id] ? 'Refresh preview' : item.media_type.startsWith('video/') ? 'View video' : 'View image'}</Text>
        </Pressable>
        {mediaUrls[item.id] && (item.media_type.startsWith('video/')
          ? <EvidenceVideo uri={mediaUrls[item.id]!} token={state.token?.access_token ?? ''} onError={() => mediaFailed(item.id)} />
          : <Image accessibilityLabel={item.original_filename} source={{ uri: mediaUrls[item.id], headers: { Authorization: `Bearer ${state.token?.access_token ?? ''}` } }} style={{ width: '100%', height: 220, borderRadius: 8 }} resizeMode="contain" onError={() => mediaFailed(item.id)} />)}
      </View>) : <Notice>No evidence attached.</Notice>}
      {mediaError && <Text accessibilityRole="alert" style={ui.error}>{mediaError}</Text>}
      {!incident.dispatch && <Notice>No responder assignment has been confirmed.</Notice>}
    </>}
  </Screen>;
}

export function IncidentHistoryScreen() {
  const [status, setStatus] = useState<string | undefined>();
  const incidents = useIncidents(status === 'ASSIGNED' ? { has_active_assignment: 'true' } : { status });
  const items = incidents.data?.pages.flatMap(page => page.items) ?? [];
  return <Screen refreshing={incidents.isRefetching} onRefresh={() => { void incidents.refetch(); }}><Text style={ui.title}>My incident reports</Text>
    <Text style={ui.heading}>Filter by status</Text>
    <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
      {[undefined, 'RECEIVED', 'ACKNOWLEDGED', 'ASSIGNED', 'RESOLVED', 'DISMISSED'].map(value => <Pressable key={value ?? 'all'} accessibilityRole="button" accessibilityState={{ selected: status === value }} onPress={() => setStatus(value)} style={ui.card}>
        <Text style={ui.text}>{value === 'ASSIGNED' ? 'With active assignment' : value ? value.replaceAll('_', ' ') : 'All'}</Text>
      </Pressable>)}
    </View>
    <QueryState query={incidents} empty={!items.length} />
    {items.map(item => <Pressable key={item.id} accessibilityRole="button" accessibilityLabel={`Open incident ${item.id}`} onPress={() => router.push({ pathname: '/incidents/[id]', params: { id: item.id } })} style={ui.card}>
      <Text style={ui.heading}>Report #{item.id}</Text><Text style={ui.text}>{item.incident_type.replaceAll('_', ' ')} · {item.status.replaceAll('_', ' ')}</Text>
    </Pressable>)}
    {incidents.hasNextPage && <PrimaryButton label="Load more" onPress={() => void incidents.fetchNextPage()} disabled={incidents.isFetchingNextPage} />}
  </Screen>;
}
