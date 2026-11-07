import { useEffect, useRef, useState } from 'react';
import { Alert, Pressable, Text, View } from 'react-native';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { api, useAuth } from '../auth/AuthProvider';
import { PrimaryButton } from './PrimaryButton';
import { Notice, ui } from './Content';

export function AssignMarshal({ propertyId, source, incidentId, status }: { propertyId: number; source: 'camera' | 'reporter'; incidentId: number; status: string }) {
  const { state } = useAuth();
  const client = useQueryClient();
  const permitted = state.profile?.properties.some(p => p.id === propertyId && p.role === 'owner') ?? false;
  const [choosing, setChoosing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<number[]>([]);
  const retryKey = useRef<{ selection: string; key: string } | null>(null);
  const assignment = useQuery({ queryKey: ['owner-assignment', state.profile?.id, propertyId, source, incidentId], enabled: permitted,
    queryFn: () => api.assignment(propertyId, source, incidentId), refetchInterval: 10000 });
  const candidates = useQuery({ queryKey: ['eligible-marshals', state.profile?.id, propertyId], enabled: permitted && choosing,
    queryFn: () => api.eligibleMarshals(propertyId), staleTime: 0 });
  useEffect(() => {
    if (candidates.data) setSelected(current => current.filter(id => candidates.data.some(candidate => candidate.id === id)));
  }, [candidates.data]);
  const active = assignment.data && ['OFFERED', 'ACCEPTED', 'EN_ROUTE', 'ON_SCENE'].includes(assignment.data.status);
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
      await api.assignMarshals(propertyId, source, incidentId, ids, retryKey.current.key);
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
  if (!permitted) return null;
  return <View style={ui.card}><Text style={ui.heading}>Marshal response</Text>
    {assignment.isPending && <Notice>Checking assignment…</Notice>}
    {assignment.isError && <><Notice>Unable to check the current assignment.</Notice><PrimaryButton label="Retry assignment status" onPress={() => { void assignment.refetch(); }} /></>}
    {assignment.data && <Notice>{assignment.data.status === 'OFFERED' ? 'Assignment sent. Waiting for the marshal to accept.' : `Response: ${assignment.data.status.replaceAll('_', ' ')}`} · Assignment #{assignment.data.id}</Notice>}
    {!assignment.isPending && !assignment.isError && !active && dispatchable && <>
      <PrimaryButton label="Assign marshal" disabled={busy} onPress={() => { setChoosing(true); void candidates.refetch(); }} />
      {choosing && <>
        <Notice>Select one or more on-duty responders. Offers expire in 5 minutes. The first marshal to accept gets the job; the other offers close.</Notice>
        {candidates.isFetching && <Notice>Finding available marshals…</Notice>}
        {candidates.isError && <Notice>Unable to load responders. Tap Assign marshal to retry.</Notice>}
        {candidates.data?.length === 0 && <Notice>No marshals are currently available. Ask the marshal to open their app and go on duty, then retry.</Notice>}
        {candidates.data?.map(marshal => <Pressable key={marshal.id} accessibilityRole="checkbox" accessibilityLabel={`Select ${marshal.name ?? `marshal #${marshal.id}`}`} accessibilityState={{ checked: selected.includes(marshal.id), disabled: busy }} disabled={busy} style={ui.card} onPress={() => setSelected(current => current.includes(marshal.id) ? current.filter(id => id !== marshal.id) : [...current, marshal.id])}><Text style={ui.text}>{selected.includes(marshal.id) ? '☑' : '☐'} {marshal.name ?? `Marshal #${marshal.id}`}</Text></Pressable>)}
        <PrimaryButton label={busy ? 'Sending offers…' : `Send to ${selected.length} marshal${selected.length === 1 ? '' : 's'}`} disabled={busy || candidates.isFetching || !selected.length} onPress={() => Alert.alert('Send assignment offers?', `Send a 5-minute offer to ${selected.length} responder(s)? The first acceptance wins.`, [{ text: 'Cancel', style: 'cancel' }, { text: 'Assign', onPress: () => void assign() }])} />
      </>}
    </>}
    {!dispatchable && !active && <Notice>This incident is not open for dispatch.</Notice>}
    {error && <Text accessibilityRole="alert" style={ui.error}>{error}</Text>}
  </View>;
}
