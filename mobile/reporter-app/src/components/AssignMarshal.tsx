import { useEffect, useRef, useState } from 'react';
import { Alert, Linking, Pressable, Text, TextInput, View } from 'react-native';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import MapView, { Marker, Polyline } from 'react-native-maps';
import { api, useAuth } from '../auth/AuthProvider';
import { PrimaryButton } from './PrimaryButton';
import { Notice, ui } from './Content';

export function AssignMarshal({ propertyId, source, incidentId, status, destinationLatitude, destinationLongitude, destinationAddress }: { propertyId: number; source: 'camera' | 'reporter'; incidentId: number; status: string; destinationLatitude?: number | null; destinationLongitude?: number | null; destinationAddress?: string | null }) {
  const { state } = useAuth();
  const client = useQueryClient();
  const permitted = state.profile?.properties.some(p => p.id === propertyId && ['owner', 'dispatcher'].includes(p.role)) ?? false;
  const [choosing, setChoosing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<number[]>([]);
  const [teamMode, setTeamMode] = useState(false);
  const [reviewReason, setReviewReason] = useState('');
  const [chatDraft, setChatDraft] = useState('');
  const retryKey = useRef<{ selection: string; key: string } | null>(null);
  const assignment = useQuery({ queryKey: ['owner-assignment', state.profile?.id, propertyId, source, incidentId], enabled: permitted,
    queryFn: () => api.assignment(propertyId, source, incidentId), refetchInterval: 10000 });
  const tracking = assignment.data && ['ACCEPTED', 'EN_ROUTE', 'ON_SCENE', 'INVESTIGATING', 'PENDING_REVIEW'].includes(assignment.data.status);
  const locationHistory = useQuery({ queryKey: ['owner-assignment-location', state.profile?.id, propertyId, assignment.data?.id], enabled: permitted && Boolean(tracking),
    queryFn: () => api.assignmentLocationHistory(propertyId, assignment.data!.id), refetchInterval: 30000, staleTime: 20000 });
  const candidates = useQuery({ queryKey: ['eligible-marshals', state.profile?.id, propertyId], enabled: permitted && choosing,
    queryFn: () => api.eligibleMarshals(propertyId), staleTime: 0 });
  useEffect(() => {
    if (candidates.data) setSelected(current => current.filter(id => candidates.data.some(candidate => candidate.id === id)));
  }, [candidates.data]);
  const active = assignment.data && ['OFFERED', 'ACCEPTED', 'EN_ROUTE', 'ON_SCENE', 'INVESTIGATING', 'PENDING_REVIEW'].includes(assignment.data.status);
  const conversation = useQuery({ queryKey: ['assignment-chat', state.profile?.id, assignment.data?.id], enabled: permitted && Boolean(assignment.data && ['ACCEPTED', 'EN_ROUTE', 'ON_SCENE', 'INVESTIGATING', 'PENDING_REVIEW'].includes(assignment.data.status)), queryFn: () => api.assignmentMessages(propertyId, assignment.data!.id), refetchInterval: 3000 });
  const dispatchable = ['OPEN', 'ACKNOWLEDGED', 'RECEIVED', 'DISPATCHING', 'ESCALATED'].includes(status);
  useEffect(() => {
    if (source === 'camera' && assignment.isSuccess) {
      void client.invalidateQueries({ queryKey: ['event', state.profile?.id, propertyId, incidentId] });
      void client.invalidateQueries({ queryKey: ['events', state.profile?.id, propertyId] });
    }
  }, [assignment.data?.status, assignment.isSuccess, client, source, state.profile?.id, propertyId, incidentId]);
  async function assign() {
    setBusy(true); setError(null);
    const ids = [...selected].sort((a, b) => a - b);
    const selection = ids.join(',');
    if (retryKey.current?.selection !== selection) retryKey.current = { selection, key: `mobile-offer-${Date.now()}-${Math.random().toString(36).slice(2)}` };
    try {
      if (teamMode) await api.assignTeamMarshals(propertyId, source, incidentId, ids, retryKey.current.key);
      else await api.assignMarshals(propertyId, source, incidentId, ids, retryKey.current.key);
      retryKey.current = null; setChoosing(false); setSelected([]);
      await assignment.refetch();
      await client.invalidateQueries({ queryKey: ['event', state.profile?.id, propertyId, incidentId] });
      await client.invalidateQueries({ queryKey: ['events', state.profile?.id, propertyId] });
      await client.invalidateQueries({ queryKey: ['reporter-incident'] });
      await client.invalidateQueries({ queryKey: ['reporter-incidents'] });
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unable to assign this incident. Refresh and retry.');
      await assignment.refetch(); await candidates.refetch();
    } finally { setBusy(false); }
  }
  async function dispatchNearest() {
    setBusy(true); setError(null);
    try {
      const result = await api.dispatchNearest(propertyId, incidentId, `nearest-${incidentId}-${Date.now()}`);
      if (result.status === 'ESCALATED') setError(result.reason ?? 'No eligible marshal is currently available.');
      await assignment.refetch();
      await client.invalidateQueries({ queryKey: ['reporter-incident'] });
      await client.invalidateQueries({ queryKey: ['reporter-incidents'] });
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unable to dispatch to the nearest marshal.');
    } finally { setBusy(false); }
  }
  async function review(approved: boolean) {
    const item = assignment.data;
    if (!item || reviewReason.trim().length < 5) return;
    setBusy(true); setError(null);
    try {
      await api.reviewAssignment(propertyId, item.id, item.version, approved, reviewReason.trim());
      setReviewReason(''); await assignment.refetch();
      await client.invalidateQueries({ queryKey: ['event', state.profile?.id, propertyId, incidentId] });
      await client.invalidateQueries({ queryKey: ['events', state.profile?.id, propertyId] });
      await client.invalidateQueries({ queryKey: ['reporter-incident'] });
    } catch (e) { setError(e instanceof Error ? e.message : 'Unable to review this response.'); await assignment.refetch(); }
    finally { setBusy(false); }
  }
  async function sendMessage() {
    const item = assignment.data;
    if (!item || !chatDraft.trim()) return;
    const text = chatDraft.trim(); setChatDraft('');
    try { await api.sendAssignmentMessage(propertyId, item.id, text, `owner-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`); await conversation.refetch(); }
    catch (e) { setChatDraft(text); setError(e instanceof Error ? e.message : 'Unable to send message.'); }
  }
  if (!permitted) return null;
  return <View style={ui.card}><Text style={ui.heading}>Marshal response</Text>
    {assignment.isPending && <Notice>Checking assignment…</Notice>}
    {assignment.isError && <><Notice>Unable to check the current assignment.</Notice><PrimaryButton label="Retry assignment status" onPress={() => { void assignment.refetch(); }} /></>}
    {assignment.data && <Notice>{assignment.data.status === 'OFFERED' ? 'Assignment sent. Waiting for the marshal to accept.' : `Response: ${assignment.data.status.replaceAll('_', ' ')}`} · Assignment #{assignment.data.id}</Notice>}
    {assignment.data && ['ACCEPTED', 'EN_ROUTE', 'ON_SCENE', 'INVESTIGATING', 'PENDING_REVIEW'].includes(assignment.data.status) && <>
      {assignment.data.responder_location ? <View style={ui.card}>
        <Text style={ui.heading}>Live responder location</Text>
        <Notice>Updated {new Date(assignment.data.responder_location.updated_at).toLocaleTimeString()}</Notice>
        {assignment.data.responder_location.distance_m != null && <Notice>{(assignment.data.responder_location.distance_m / 1000).toFixed(1)} km from the incident{assignment.data.responder_location.eta_seconds != null ? ` · about ${Math.max(1, Math.ceil(assignment.data.responder_location.eta_seconds / 60))} min` : ''}</Notice>}
        <MapView style={{ height: 220, borderRadius: 12 }} region={{
          latitude: (assignment.data.responder_location.latitude + (destinationLatitude ?? assignment.data.responder_location.latitude)) / 2,
          longitude: (assignment.data.responder_location.longitude + (destinationLongitude ?? assignment.data.responder_location.longitude)) / 2,
          latitudeDelta: Math.max(.01, Math.abs((destinationLatitude ?? assignment.data.responder_location.latitude) - assignment.data.responder_location.latitude) * 2.5),
          longitudeDelta: Math.max(.01, Math.abs((destinationLongitude ?? assignment.data.responder_location.longitude) - assignment.data.responder_location.longitude) * 2.5),
        }}>
          <Marker coordinate={{ latitude: assignment.data.responder_location.latitude, longitude: assignment.data.responder_location.longitude }} title="Marshal location" description="Latest location update" pinColor="#0f766e" />
          {destinationLatitude != null && destinationLongitude != null && <Marker coordinate={{ latitude: destinationLatitude, longitude: destinationLongitude }} title="Incident location" pinColor="#dc2626" />}
          {!!locationHistory.data?.items.length && <Polyline coordinates={locationHistory.data.items.map(point => ({ latitude: point.latitude, longitude: point.longitude }))} strokeColor="#0f766e" strokeWidth={4} />}
        </MapView>
        {locationHistory.data?.items.length ? <>
          <Notice>Recent route · up to {locationHistory.data.retention_hours} hours of GPS points</Notice>
          {locationHistory.data.items.slice(-5).reverse().map((point, index) => <Notice key={`${point.recorded_at}-${index}`}>{new Date(point.recorded_at).toLocaleTimeString()} · {point.latitude.toFixed(5)}, {point.longitude.toFixed(5)}</Notice>)}
        </> : <Notice>Waiting for GPS history to arrive.</Notice>}
        <Pressable accessibilityRole="link" onPress={() => void Linking.openURL(`https://www.google.com/maps/dir/?api=1&origin=${assignment.data!.responder_location!.latitude},${assignment.data!.responder_location!.longitude}&destination=${encodeURIComponent(destinationLatitude != null && destinationLongitude != null ? `${destinationLatitude},${destinationLongitude}` : destinationAddress || '')}&travelmode=driving`)}>
          <Text style={ui.link}>View live location and route in Maps ↗</Text>
        </Pressable>
      </View> : <Notice>Waiting for the responder’s first location update. They must allow background location while on an active job.</Notice>}
    </>}
    {assignment.data && ['ACCEPTED', 'EN_ROUTE', 'ON_SCENE', 'INVESTIGATING', 'PENDING_REVIEW'].includes(assignment.data.status) && <View style={ui.card}>
      <Text style={ui.heading}>Incident chat</Text>
      {conversation.data?.items.map(message => <View key={message.id} style={ui.card}><Text style={ui.text}>{message.sender}</Text><Text style={ui.text}>{message.body}</Text><Notice>{new Date(message.created_at).toLocaleTimeString()}</Notice></View>)}
      <TextInput accessibilityLabel="Message response team" value={chatDraft} onChangeText={setChatDraft} maxLength={2000} placeholder="Message the response team" style={ui.input} />
      <PrimaryButton label="Send message" disabled={busy || !chatDraft.trim()} onPress={() => void sendMessage()} />
    </View>}
    {assignment.data?.status === 'PENDING_REVIEW' && <View style={ui.card}>
      <Text style={ui.heading}>Supervisor review</Text><Notice>Read the marshal’s notes and evidence before approving final closure. Rejecting returns the response to investigation.</Notice>
      <TextInput accessibilityLabel="Supervisor review reason" value={reviewReason} onChangeText={setReviewReason} maxLength={2000} placeholder="Review notes (required)" multiline style={ui.input} />
      <PrimaryButton label="Approve and close incident" disabled={busy || reviewReason.trim().length < 5} onPress={() => Alert.alert('Approve final closure?', 'This closes the incident for all responders.', [{ text: 'Cancel', style: 'cancel' }, { text: 'Approve', onPress: () => void review(true) }])} />
      <PrimaryButton variant="secondary" label="Return to investigation" disabled={busy || reviewReason.trim().length < 5} onPress={() => void review(false)} />
    </View>}
    {!assignment.isPending && !assignment.isError && !active && dispatchable && <>
      {source === 'reporter' && <PrimaryButton label="Assign nearest available marshal" disabled={busy} onPress={() => Alert.alert('Dispatch nearest responder?', 'SecurePulse uses fresh marshal locations and incident coordinates when available. If location is unavailable, it balances current workload.', [{ text: 'Cancel', style: 'cancel' }, { text: 'Dispatch', onPress: () => void dispatchNearest() }])} />}
      <PrimaryButton label="Assign marshal" disabled={busy} onPress={() => { setChoosing(true); void candidates.refetch(); }} />
      {choosing && <>
        <View style={{ flexDirection: 'row', gap: 8 }}><View style={{ flex: 1 }}><PrimaryButton variant={!teamMode ? 'primary' : 'secondary'} label={!teamMode ? '✓ One responder' : 'One responder'} onPress={() => setTeamMode(false)} /></View><View style={{ flex: 1 }}><PrimaryButton variant={teamMode ? 'primary' : 'secondary'} label={teamMode ? '✓ Response team' : 'Response team'} onPress={() => setTeamMode(true)} /></View></View>
        <Notice>{teamMode ? 'Invite responders into one team. More than one can accept; the team can coordinate and split tasks.' : 'Select one or more on-duty responders. Offers expire in 5 minutes. The first marshal to accept gets the job; the other offers close.'}</Notice>
        {candidates.isFetching && <Notice>Finding available marshals…</Notice>}
        {candidates.isError && <Notice>Unable to load responders. Tap Assign marshal to retry.</Notice>}
        {candidates.data?.length === 0 && <Notice>No marshals are currently available. Ask the marshal to open their app and go on duty, then retry.</Notice>}
        {candidates.data?.map(marshal => <Pressable key={marshal.id} accessibilityRole="checkbox" accessibilityLabel={`Select ${marshal.name ?? `marshal #${marshal.id}`}`} accessibilityState={{ checked: selected.includes(marshal.id), disabled: busy }} disabled={busy} style={ui.card} onPress={() => setSelected(current => current.includes(marshal.id) ? current.filter(id => id !== marshal.id) : [...current, marshal.id])}><Text style={ui.text}>{selected.includes(marshal.id) ? '☑' : '☐'} {marshal.name ?? `Marshal #${marshal.id}`}</Text></Pressable>)}
        <PrimaryButton label={busy ? 'Sending offers…' : `${teamMode ? 'Invite team' : 'Send to'} ${selected.length} marshal${selected.length === 1 ? '' : 's'}`} disabled={busy || candidates.isFetching || !selected.length} onPress={() => Alert.alert(teamMode ? 'Invite response team?' : 'Send assignment offers?', teamMode ? `Invite ${selected.length} responder(s) to this team? More than one can accept.` : `Send a 5-minute offer to ${selected.length} responder(s)? The first acceptance wins.`, [{ text: 'Cancel', style: 'cancel' }, { text: 'Assign', onPress: () => void assign() }])} />
      </>}
    </>}
    {!dispatchable && !active && <Notice>This incident is not open for dispatch.</Notice>}
    {error && <Text accessibilityRole="alert" style={ui.error}>{error}</Text>}
  </View>;
}
