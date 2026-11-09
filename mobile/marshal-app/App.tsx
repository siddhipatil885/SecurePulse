import React, { useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Alert, AppState, Linking, Pressable, RefreshControl, ScrollView, StyleSheet, Switch, Text, TextInput, View } from 'react-native';
import { SafeAreaProvider, SafeAreaView } from 'react-native-safe-area-context';
import { StatusBar } from 'expo-status-bar';
import * as SecureStore from 'expo-secure-store';
import * as Location from 'expo-location';
import * as ImagePicker from 'expo-image-picker';
import Constants from 'expo-constants';
import * as Notifications from 'expo-notifications';
import { IncomingAlarm } from './IncomingAlarm';
import { EvidencePhoto, type Evidence } from './EvidencePhoto';
import { Onboarding } from './Onboarding';
import { registerMarshalPush, unregisterMarshalPush } from './push';
import { startActiveLocationTracking, stopActiveLocationTracking } from './activeLocation';

type Workspace = { property_id: number; property_name: string; service_area: string | null; on_duty: boolean; available: boolean; verification_status: string };
type TeamMember = { assignment_id: number; marshal_profile_id: number; name: string | null; status: string; role: string | null };
type NearbyMarshal = { marshal_profile_id: number; name: string | null; distance_m: number | null };
type Job = { id: number; property_name: string; status: string; version: number; incident_type: string; severity: string | null; description: string | null; address: string | null; latitude: number | null; longitude: number | null; expires_at: string; team_key?: string | null; team_role?: string | null; team?: TeamMember[]; evidence?: Evidence[]; timeline?: { id: number; status: string; note: string | null; at: string }[] };
type ChatMessage = { id: number; sender: string; body: string; created_at: string; mine: boolean };
type Session = { access_token: string; expires_at: string };
const origin = process.env.EXPO_PUBLIC_SERVER_URL?.trim().replace(/\/+$/, '');
const storageKey = 'securepulse.marshal.session.v1';
const names: Record<string, string> = { OFFERED: 'New assignment', ACCEPTED: 'Accepted', EN_ROUTE: 'On the way', ON_SCENE: 'Arrived', INVESTIGATING: 'Investigation', PENDING_REVIEW: 'Supervisor review', COMPLETED: 'Closed', DECLINED: 'Declined', EXPIRED: 'Offer expired', CANCELLED: 'Cancelled' };
const steps = ['ACCEPTED', 'EN_ROUTE', 'ON_SCENE', 'INVESTIGATING', 'PENDING_REVIEW', 'COMPLETED'];
const readable = (value: string) => value.toLowerCase().replace(/_/g, ' ');

function Button({ label, onPress, secondary = false, disabled = false }: { label: string; onPress: () => void; secondary?: boolean; disabled?: boolean }) {
  return <Pressable accessibilityRole="button" accessibilityState={{ disabled }} disabled={disabled} onPress={onPress} style={({ pressed }) => [s.button, secondary && s.secondary, (disabled || pressed) && { opacity: .5 }]}><Text style={[s.buttonText, secondary && { color: '#18332B' }]}>{label}</Text></Pressable>;
}

export default function App() {
  return <SafeAreaProvider><SafeAreaView style={s.safe}><StatusBar style="dark" /><Marshal /></SafeAreaView></SafeAreaProvider>;
}

function Marshal() {
  const [session, setSession] = useState<Session | null>(null);
  const [restoring, setRestoring] = useState(true);
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [jobsLoaded, setJobsLoaded] = useState(false);
  const [history, setHistory] = useState<Job[]>([]);
  const [historyPage, setHistoryPage] = useState(1);
  const [moreHistory, setMoreHistory] = useState(false);
  const [selected, setSelected] = useState<Job | null>(null);
  const [tab, setTab] = useState<'jobs' | 'history' | 'account'>('jobs');
  const [showOnboarding, setShowOnboarding] = useState(false);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [note, setNote] = useState('');
  const [nearby, setNearby] = useState<NearbyMarshal[]>([]);
  const [selectedBackups, setSelectedBackups] = useState<number[]>([]);
  const [teamRole, setTeamRole] = useState('');
  const [chat, setChat] = useState<ChatMessage[]>([]);
  const [chatDraft, setChatDraft] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [synced, setSynced] = useState<string | null>(null);
  const [pushMessage, setPushMessage] = useState<string | null>(null);
  const [now, setNow] = useState(Date.now());
  const tokenRef = useRef<string | null>(null);
  const dutyRef = useRef(false);
  const generation = useRef(0);
  const selectedRef = useRef<number | null>(null);
  const historyPageRef = useRef(1);
  const refreshRevision = useRef(0);
  tokenRef.current = session?.access_token ?? null;
  selectedRef.current = selected?.id ?? null;
  historyPageRef.current = historyPage;

  async function clearSession() {
    generation.current++; dutyRef.current = false;
    await stopActiveLocationTracking().catch(() => undefined);
    setSession(null); setWorkspace(null); setJobs([]); setJobsLoaded(false); setHistory([]); setSelected(null); setNote(''); setSynced(null);
    await SecureStore.deleteItemAsync(storageKey);
  }

  async function request(path: string, body?: unknown, token = tokenRef.current, method?: string) {
    if (!origin || !/^https?:\/\//.test(origin)) throw new Error('Configure the marshal app server address before signing in.');
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 15000);
    try {
      const response = await fetch(`${origin}/api/v1/${path}`, { method: method ?? (body === undefined ? 'GET' : 'POST'), headers: { Accept: 'application/json', ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}), ...(token ? { Authorization: `Bearer ${token}` } : {}) }, body: body === undefined ? undefined : JSON.stringify(body), signal: controller.signal });
      if (response.status === 401) { if (token && token === tokenRef.current) await clearSession(); throw new Error('Please sign in again.'); }
      if (!response.ok) { const result = await response.json().catch(() => null); throw new Error(result?.error?.message ?? 'Unable to complete this action. Refresh and try again.'); }
      return response.status === 204 ? null : response.json();
    } catch (e) {
      if (e instanceof Error && (e.name === 'AbortError' || e.message === 'Network request failed')) throw new Error('Connection lost. Reconnect and refresh before retrying.');
      throw e;
    } finally { clearTimeout(timeout); }
  }

  async function refresh() {
    const current = generation.current;
    const revision = ++refreshRevision.current;
    const [nextWorkspace, active, past] = await Promise.all([request('marshal/workspace'), request('marshal/assignments'), request('marshal/assignments?history=true')]);
    const detail = selectedRef.current ? await request(`marshal/assignments/${selectedRef.current}`) : null;
    if (current !== generation.current || revision !== refreshRevision.current) return;
    dutyRef.current = nextWorkspace.verification_status === 'APPROVED' && nextWorkspace.on_duty && nextWorkspace.available;
    setWorkspace(nextWorkspace); setJobs(active.items); setJobsLoaded(true);
    setHistory(previous => historyPageRef.current > 1
      ? [...past.items, ...previous.filter(job => !past.items.some((latest: Job) => latest.id === job.id))]
      : past.items);
    if (historyPageRef.current === 1) setMoreHistory(past.items.length === 20);
    if (detail && selectedRef.current === detail.id) setSelected(detail);
    setSynced(new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }));
    return nextWorkspace as Workspace;
  }

  async function run(action: () => Promise<unknown>) {
    setBusy(true); setError(null);
    try { await action(); } catch (e) { setError(e instanceof Error ? e.message : 'Please try again.'); }
    finally { setBusy(false); }
  }

  useEffect(() => { void (async () => {
    try {
      const saved = await SecureStore.getItemAsync(storageKey);
      if (saved) {
        const parsed = JSON.parse(saved);
        if (parsed.origin === origin && Date.parse(parsed.session.expires_at) > Date.now()) {
          const fresh: Workspace = await request('marshal/workspace', undefined, parsed.session.access_token);
          dutyRef.current = fresh.verification_status === 'APPROVED' && fresh.on_duty && fresh.available;
          setWorkspace(fresh);
          setSession(parsed.session);
        } else await SecureStore.deleteItemAsync(storageKey);
      }
    } catch { setError('Connect to the server and sign in to restore your session.'); }
    finally { setRestoring(false); }
  })(); }, []);

  useEffect(() => {
    if (!session) return;
    let active = true;
    const poll = async () => {
      if (!active || AppState.currentState !== 'active') return;
      if (Date.parse(session.expires_at) <= Date.now()) { await clearSession(); return; }
      try {
        const fresh = await refresh();
        if (active && dutyRef.current && fresh?.on_duty && fresh.available) await request('dispatch/marshal/availability', { property_id: fresh.property_id, on_duty: fresh.on_duty, available: fresh.available }, undefined, 'PUT');
        if (active) setError(null);
      } catch (e) { if (active) setError(e instanceof Error ? e.message : 'Unable to refresh.'); }
    };
    void poll();
    const timer = setInterval(() => { void poll(); }, 10000);
    const listener = AppState.addEventListener('change', state => { if (state === 'active') void poll(); });
    return () => { active = false; clearInterval(timer); listener.remove(); };
  }, [session, workspace?.property_id]);

  useEffect(() => {
    if (!session || !origin) return;
    if (Constants.appOwnership === 'expo') {
      setPushMessage('Remote assignment alerts need the SecurePulse development build; Expo Go cannot receive them.');
      return;
    }
    void registerMarshalPush(origin, session.access_token)
      .then(() => setPushMessage('Urgent assignment alerts are enabled on this phone.'))
      .catch(error => setPushMessage(error instanceof Error ? error.message : 'Assignment alerts could not be enabled.'));
    const handleResponse = (response: Notifications.NotificationResponse) => {
      const assignmentId = Number(response.notification.request.content.data?.assignment_id);
      if (!Number.isInteger(assignmentId) || assignmentId <= 0) { void refresh(); return; }
      void (async () => {
        try {
          const detail = await request(`marshal/assignments/${assignmentId}`);
          setSelected(detail); selectedRef.current = detail.id; setTab('jobs');
          await refresh();
        } catch { void refresh(); }
      })();
    };
    const received = Notifications.addNotificationReceivedListener(() => { void refresh(); });
    const response = Notifications.addNotificationResponseReceivedListener(handleResponse);
    void Notifications.getLastNotificationResponseAsync().then(last => {
      if (last) { handleResponse(last); void Notifications.clearLastNotificationResponseAsync(); }
    }).catch(() => undefined);
    return () => { received.remove(); response.remove(); };
  }, [session]);

  useEffect(() => { const timer = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(timer); }, []);

  const activeJob = jobs.find(job => ['ACCEPTED', 'EN_ROUTE', 'ON_SCENE', 'INVESTIGATING', 'PENDING_REVIEW'].includes(job.status));
  useEffect(() => {
    let active = true;
    if (!session || !origin) {
      void stopActiveLocationTracking().catch(() => undefined);
      return () => { active = false; };
    }
    if (!activeJob) {
      if (jobsLoaded) void stopActiveLocationTracking().catch(() => undefined);
      return () => { active = false; };
    }
    let foregroundSubscription: Location.LocationSubscription | null = null;
    void startActiveLocationTracking({ origin, token: session.access_token, assignmentId: activeJob.id })
      .then(async result => {
        if (!active || result.background) return;
        const subscription = await Location.watchPositionAsync(
          { accuracy: Location.Accuracy.Balanced, timeInterval: 15000, distanceInterval: 20 },
          location => {
            if (!active) return;
            void request(`marshal/assignments/${activeJob.id}/location`, {
              latitude: location.coords.latitude, longitude: location.coords.longitude,
              accuracy_m: location.coords.accuracy,
              heading: location.coords.heading !== null && location.coords.heading >= 0 ? location.coords.heading : null,
              speed_mps: location.coords.speed !== null && location.coords.speed >= 0 ? location.coords.speed : null,
            }).catch(() => undefined);
          },
        );
        if (active) foregroundSubscription = subscription;
        else subscription.remove();
      })
      .catch(error => { if (active) setError(error instanceof Error ? error.message : 'Unable to start assignment location sharing.'); });
    return () => { active = false; foregroundSubscription?.remove(); };
  }, [session, activeJob?.id, jobsLoaded]);

  useEffect(() => {
    if (!session || !selected || !['ACCEPTED', 'EN_ROUTE', 'ON_SCENE', 'INVESTIGATING', 'PENDING_REVIEW'].includes(selected.status)) { setChat([]); return; }
    let alive = true;
    const poll = async () => {
      try {
        const result = await request(`marshal/assignments/${selected.id}/messages`);
        if (alive) setChat((current: ChatMessage[]) => {
          const byId = new Map(current.map(message => [message.id, message]));
          result.items.forEach((message: ChatMessage) => byId.set(message.id, message));
          return [...byId.values()].sort((a, b) => a.id - b.id).slice(-100);
        });
      } catch { /* the main assignment refresh reports connection issues */ }
    };
    void poll(); const timer = setInterval(() => { if (AppState.currentState === 'active') void poll(); }, 3000);
    return () => { alive = false; clearInterval(timer); };
  }, [session, selected?.id, selected?.status]);

  async function signIn() {
    const next = await request('auth/login', { email: email.trim().toLowerCase(), password }, null);
    await request('marshal/workspace', undefined, next.access_token);
    await SecureStore.setItemAsync(storageKey, JSON.stringify({ origin, session: next }));
    generation.current++; setSession(next); setPassword('');
  }

  async function duty(enabled: boolean) {
    if (!workspace) return;
    await request('dispatch/marshal/availability', { property_id: workspace.property_id, on_duty: enabled, available: enabled }, undefined, 'PUT');
    dutyRef.current = enabled; await refresh();
  }

  async function open(job: Job) { setNote(''); setNearby([]); setSelectedBackups([]); setSelected(await request(`marshal/assignments/${job.id}`)); }

  async function update(action: string) {
    if (!selected) return;
    try {
      await request(`dispatch/offers/${selected.id}/${action === 'accept' || action === 'decline' ? action : 'progress'}`, { expected_version: selected.version, ...(!['accept', 'decline'].includes(action) ? { status: action } : {}) });
    } finally { await refresh(); }
  }

  async function saveNote() {
    if (!selected || !note.trim()) return;
    await request(`marshal/assignments/${selected.id}/notes`, { text: note.trim(), expected_version: selected.version });
    setNote(''); await refresh();
  }

  async function captureEvidence(kind: 'photo' | 'video' | 'library') {
    if (!selected || !origin) return;
    const permission = kind === 'library' ? await ImagePicker.requestMediaLibraryPermissionsAsync() : await ImagePicker.requestCameraPermissionsAsync();
    if (!permission.granted) throw new Error('Allow camera or photo-library access to attach evidence.');
    const options: ImagePicker.ImagePickerOptions = { mediaTypes: kind === 'photo' ? ['images'] : kind === 'video' ? ['videos'] : ['images', 'videos'], quality: .8, ...(kind === 'video' ? { videoMaxDuration: 60 } : {}) };
    const result = kind === 'library' ? await ImagePicker.launchImageLibraryAsync(options) : await ImagePicker.launchCameraAsync(options);
    if (result.canceled || !result.assets[0]) return;
    const asset = result.assets[0];
    const filename = asset.fileName || asset.uri.split('/').pop() || `field-${Date.now()}`;
    const type = asset.mimeType || (filename.toLowerCase().endsWith('.png') ? 'image/png' : filename.toLowerCase().match(/\.(mp4|mov)$/) ? 'video/mp4' : 'image/jpeg');
    const form = new FormData();
    form.append('file', { uri: asset.uri, name: filename, type } as any);
    const response = await fetch(`${origin}/api/v1/marshal/assignments/${selected.id}/evidence`, {
      method: 'POST', headers: { Accept: 'application/json', Authorization: `Bearer ${tokenRef.current}`, 'X-Idempotency-Key': `field-${selected.id}-${Date.now()}-${Math.random().toString(36).slice(2, 12)}` }, body: form,
    });
    if (response.status === 401) { await clearSession(); throw new Error('Please sign in again.'); }
    if (!response.ok) { const body = await response.json().catch(() => null); throw new Error(body?.error?.message || 'Evidence could not be uploaded.'); }
    await refresh();
  }

  async function sendChat() {
    if (!selected || !chatDraft.trim()) return;
    const body = chatDraft.trim(); setChatDraft('');
    await request(`marshal/assignments/${selected.id}/messages`, { body, client_message_id: `msg-${Date.now()}-${Math.random().toString(36).slice(2, 12)}` });
    const result = await request(`marshal/assignments/${selected.id}/messages`);
    setChat(result.items);
  }

  async function findNearby() {
    if (!selected) return;
    const result = await request(`marshal/assignments/${selected.id}/nearby`);
    if (result.location_required) throw new Error('Wait for your active-job location to refresh, then search again.');
    setNearby(result.items);
  }

  async function requestBackup() {
    if (!selected || selectedBackups.length === 0) return;
    await request(`marshal/assignments/${selected.id}/backup`, {
      marshal_profile_ids: selectedBackups,
      idempotency_key: `backup-${selected.id}-${Date.now()}`,
    });
    setNearby([]); setSelectedBackups([]); await refresh();
  }

  async function assignTeamRole(member: TeamMember) {
    if (!selected || !teamRole.trim()) return;
    await request(`marshal/assignments/${selected.id}/team/${member.assignment_id}/role`, { role: teamRole.trim() }, undefined, 'PUT');
    setTeamRole(''); await refresh();
  }

  async function navigate() {
    if (!selected) return;
    const destination = selected.latitude !== null && selected.longitude !== null ? `${selected.latitude},${selected.longitude}` : selected.address;
    if (!destination) throw new Error('No verified destination is available. Contact your dispatcher.');
    await Linking.openURL(`https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent(destination)}&travelmode=driving`);
  }

  const errorNotice = error && <View accessibilityRole="alert" style={s.error}><Text style={s.errorText}>{error}</Text></View>;
  if (restoring) return <View style={s.center}><ActivityIndicator color="#E65324" /><Text style={s.muted}>Restoring your session…</Text></View>;
  if (!session) return <ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={s.login}>
    <View style={s.logo}><Text style={s.logoText}>SP</Text></View><Text style={s.eyebrow}>SECUREPULSE • RESPONSE PARTNER</Text>
    <Text style={s.hero}>Ready when{ '\n' }it matters.</Text><Text style={s.subtitle}>Your next response, one clear step at a time.</Text>
    <View style={s.card}><Text style={s.title}>Marshal sign in</Text><Text style={s.muted}>Use the account provided by your dispatcher.</Text>
      <Text style={s.label}>Email address</Text><TextInput style={s.input} accessibilityLabel="Email address" value={email} onChangeText={setEmail} autoCapitalize="none" keyboardType="email-address" autoComplete="email" />
      <Text style={s.label}>Password</Text><TextInput style={s.input} accessibilityLabel="Password" value={password} onChangeText={setPassword} secureTextEntry autoComplete="current-password" />
      {errorNotice}<Button label={busy ? 'Signing in…' : 'Sign in →'} disabled={busy || !email.trim() || !password} onPress={() => void run(signIn)} />
    </View><Text style={s.footer}>Built for the people who show up.</Text>
  </ScrollView>;

  const pending = jobs.filter(job => job.status === 'OFFERED');
  if (workspace && (showOnboarding || workspace.verification_status !== 'APPROVED')) return <Onboarding key={session.access_token} status={workspace.verification_status} origin={origin!} token={session.access_token} request={request} refresh={refresh} unauthorized={async failedToken => { if (failedToken === tokenRef.current) await clearSession(); }} close={() => setShowOnboarding(false)} signOut={async () => { try { await request('auth/logout', {}); } finally { setShowOnboarding(false); await clearSession(); } }} />;
  const active = jobs.filter(job => job.status !== 'OFFERED');
  return <View style={{ flex: 1 }}><ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={s.content} refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); void run(refresh).finally(() => setRefreshing(false)); }} />}>
    <View style={s.row}><View><Text style={s.eyebrow}>SECUREPULSE MARSHAL</Text><Text style={s.title}>{selected ? 'Your response' : tab === 'history' ? 'Past responses' : tab === 'account' ? 'Your account' : 'Let’s make a difference.'}</Text></View><View style={s.avatar}><Text style={{ fontWeight: '800', color: '#18332B' }}>QRT</Text></View></View>
    <Text style={s.muted}>{workspace?.service_area || workspace?.property_name || 'Connecting…'}{synced ? ` · Updated ${synced}` : ''}</Text>
    {errorNotice}
    <IncomingAlarm offerIds={jobs.filter(job => job.status === 'OFFERED' && Date.parse(job.expires_at) > now).map(job => job.id)} />
    {selected ? <>
      <Button secondary label="← Back to jobs" onPress={() => { selectedRef.current = null; setSelected(null); setNote(''); }} />
      <View style={s.darkCard}><Text style={s.darkEyebrow}>RESPONSE #{selected.id}</Text><Text style={s.whiteTitle}>{readable(selected.incident_type)}</Text><Text style={s.white}>{selected.property_name}</Text><Text style={s.pill}>{names[selected.status] ?? selected.status}</Text></View>
      <View style={s.card}><Text style={s.label}>DESTINATION</Text><Text style={s.title}>{selected.address || 'Address not supplied'}</Text><Text style={s.muted}>{selected.description || 'No additional incident details supplied.'}</Text>
        <Button secondary label="Open directions ↗" disabled={busy || (!selected.address && selected.latitude === null)} onPress={() => void run(navigate)} /></View>
      {selected.team_key && <View style={s.card}><Text style={s.title}>Response team</Text>{selected.team?.map(member => <View key={member.assignment_id} style={s.timeline}><Text style={s.body}>{member.name || `Marshal ${member.marshal_profile_id}`} · {names[member.status] ?? member.status}</Text>{member.role && <Text style={s.muted}>Task: {member.role}</Text>}</View>)}
        {selected.team?.some(member => member.assignment_id !== selected.id && ['OFFERED', 'ACCEPTED', 'EN_ROUTE', 'ON_SCENE', 'INVESTIGATING'].includes(member.status)) && <><TextInput accessibilityLabel="Teammate task" value={teamRole} onChangeText={setTeamRole} placeholder="Task, e.g. check the north entrance" placeholderTextColor="#727C76" style={s.input} /><View style={s.gap}>{selected.team.filter(member => member.assignment_id !== selected.id && ['OFFERED', 'ACCEPTED', 'EN_ROUTE', 'ON_SCENE', 'INVESTIGATING'].includes(member.status)).map(member => <Button key={member.assignment_id} secondary label={`Assign task to ${member.name || 'teammate'}`} disabled={busy || !teamRole.trim()} onPress={() => void run(() => assignTeamRole(member))} />)}</View></>}
      </View>}
      {['ACCEPTED', 'EN_ROUTE', 'ON_SCENE', 'INVESTIGATING'].includes(selected.status) && <View style={s.card}><Text style={s.title}>Need another marshal?</Text><Text style={s.muted}>Find available responders near your latest location and invite them to this incident.</Text><Button secondary label="Find nearby marshals" disabled={busy} onPress={() => void run(findNearby)} />{nearby.map(candidate => <Pressable key={candidate.marshal_profile_id} accessibilityRole="checkbox" accessibilityState={{ checked: selectedBackups.includes(candidate.marshal_profile_id) }} onPress={() => setSelectedBackups(current => current.includes(candidate.marshal_profile_id) ? current.filter(id => id !== candidate.marshal_profile_id) : [...current, candidate.marshal_profile_id])} style={s.row}><Text style={s.body}>{selectedBackups.includes(candidate.marshal_profile_id) ? '☑' : '□'}  {candidate.name || `Marshal ${candidate.marshal_profile_id}`}</Text><Text style={s.muted}>{candidate.distance_m === null ? 'Distance unavailable' : `${(candidate.distance_m / 1000).toFixed(1)} km`}</Text></Pressable>)}{selectedBackups.length > 0 && <Button label={`Request backup (${selectedBackups.length})`} disabled={busy} onPress={() => void run(requestBackup)} />}</View>}
      {['OFFERED', 'ACCEPTED', 'EN_ROUTE', 'ON_SCENE', 'INVESTIGATING', 'PENDING_REVIEW', 'COMPLETED'].includes(selected.status) && <View style={s.card}><Text style={s.title}>Incident evidence</Text><Text style={s.muted}>Review the scene carefully. A person in an image is not a confirmed threat.</Text>
        {selected.evidence?.length ? selected.evidence.map(item => <EvidencePhoto key={`${item.source || 'incident'}:${selected.id}:${item.id}`} assignmentId={selected.id} item={item} origin={origin!} token={session.access_token} request={request} />) : <Text style={s.muted}>No evidence has been attached.</Text>}
        {['ACCEPTED', 'EN_ROUTE', 'ON_SCENE', 'INVESTIGATING'].includes(selected.status) && <View style={s.gap}><Button secondary label="Take photo" disabled={busy} onPress={() => void run(() => captureEvidence('photo'))} /><Button secondary label="Record video" disabled={busy} onPress={() => void run(() => captureEvidence('video'))} /><Button secondary label="Choose from phone" disabled={busy} onPress={() => void run(() => captureEvidence('library'))} /></View>}
      </View>}
      {selected.status === 'OFFERED' ? <View style={s.card}><Text style={s.title}>Can you respond?</Text><Text style={s.muted}>{Math.max(0, Math.ceil((Date.parse(selected.expires_at) - now) / 1000))} seconds left to accept</Text>
        <Button label="Accept response" disabled={busy || Date.parse(selected.expires_at) <= now} onPress={() => void run(() => update('accept'))} />
        <Button secondary label="Decline assignment" disabled={busy} onPress={() => Alert.alert('Decline this assignment?', 'Dispatch will be notified so another responder can be offered this job.', [{ text: 'Keep assignment', style: 'cancel' }, { text: 'Decline', style: 'destructive', onPress: () => void run(() => update('decline')) }])} /></View> : <View style={s.card}><Text style={s.title}>One step at a time</Text>{steps.map((step, index) => <View key={step} style={s.step}><View style={[s.dot, steps.indexOf(selected.status) >= index && s.dotDone]}><Text style={s.dotText}>{steps.indexOf(selected.status) >= index ? '✓' : index + 1}</Text></View><Text style={s.stepText}>{names[step]}</Text></View>)}</View>}
      {['ACCEPTED', 'EN_ROUTE', 'ON_SCENE', 'INVESTIGATING'].includes(selected.status) && <>
        {['ON_SCENE', 'INVESTIGATING'].includes(selected.status) && <View style={s.card}><Text style={s.title}>Response notes</Text><Text style={s.muted}>Record observations, actions, and the outcome. Your notes are visible to the property supervisor.</Text><TextInput accessibilityLabel="Incident note" multiline maxLength={2000} value={note} onChangeText={setNote} placeholder="What did you find?" placeholderTextColor="#727C76" style={[s.input, { minHeight: 110, textAlignVertical: 'top' }]} /><Button secondary label={busy ? 'Please wait…' : 'Save note'} disabled={busy || !note.trim()} onPress={() => void run(saveNote)} /></View>}
        <Button label={selected.status === 'ACCEPTED' ? 'Start journey →' : selected.status === 'EN_ROUTE' ? 'Confirm arrival' : selected.status === 'ON_SCENE' ? 'Begin investigation' : 'Submit investigation for review'} disabled={busy || (selected.status === 'INVESTIGATING' && note.trim().length < 10)} onPress={() => {
          const next = selected.status === 'ACCEPTED' ? 'EN_ROUTE' : selected.status === 'EN_ROUTE' ? 'ON_SCENE' : selected.status === 'ON_SCENE' ? 'INVESTIGATING' : 'PENDING_REVIEW';
          if (next === 'PENDING_REVIEW') void run(async () => { await request(`dispatch/offers/${selected.id}/progress`, { expected_version: selected.version, status: next, review_summary: note.trim() }); setNote(''); await refresh(); });
          else void run(() => update(next));
        }} />
      </>}
      {selected.status === 'PENDING_REVIEW' && <View style={s.card}><Text style={s.title}>Submitted for supervisor review</Text><Text style={s.muted}>You’ll be notified when the supervisor approves closure or returns the investigation.</Text></View>}
      {['ACCEPTED', 'EN_ROUTE', 'ON_SCENE', 'INVESTIGATING', 'PENDING_REVIEW'].includes(selected.status) && <View style={s.card}><Text style={s.title}>Incident chat</Text><Text style={s.muted}>Messages are shared with the response team and property operators.</Text>{chat.map(message => <View key={message.id} style={s.timeline}><Text style={s.label}>{message.mine ? 'You' : message.sender}</Text><Text style={s.body}>{message.body}</Text><Text style={s.muted}>{new Date(message.created_at).toLocaleTimeString()}</Text></View>)}<TextInput accessibilityLabel="Message response team" maxLength={2000} value={chatDraft} onChangeText={setChatDraft} placeholder="Message the team…" placeholderTextColor="#727C76" style={s.input} /><Button label="Send message" disabled={busy || !chatDraft.trim()} onPress={() => void run(sendChat)} /></View>}
      <View style={s.card}><Text style={s.title}>Response timeline</Text>{selected.timeline?.map(event => <View key={event.id} style={s.timeline}><Text style={s.label}>{names[event.status] ?? event.status}</Text>{event.note && <Text style={s.body}>{event.note}</Text>}<Text style={s.muted}>{new Date(event.at).toLocaleString()}</Text></View>)}</View>
    </> : tab === 'jobs' ? <>
      <View style={s.darkCard}><View style={s.row}><View style={{ flex: 1 }}><Text style={s.darkEyebrow}>YOUR SHIFT</Text><Text style={s.whiteTitle}>{workspace?.on_duty ? 'You’re on duty' : 'Take a moment. Get ready.'}</Text></View><Switch accessibilityLabel="On duty" value={workspace?.on_duty ?? false} disabled={busy || !workspace} onValueChange={value => void run(() => duty(value))} trackColor={{ false: '#64746B', true: '#FFB498' }} thumbColor="#FFFFFF" /></View><Text style={s.white}>{workspace?.on_duty ? 'Assignment alerts are enabled here. Active responses share your location in the background when you allow it.' : 'Go on duty when you’re ready to respond.'}</Text></View>
      <View style={s.stats}><View style={s.stat}><Text style={s.number}>{pending.length}</Text><Text style={s.muted}>Incoming</Text></View><View style={s.stat}><Text style={s.number}>{active.length}</Text><Text style={s.muted}>In progress</Text></View></View>
      {pushMessage && <View accessibilityRole="text" style={s.card}><Text style={s.label}>ASSIGNMENT ALERTS</Text><Text style={s.muted}>{pushMessage}</Text></View>}
      <Text style={s.title}>Your assignments</Text>
      {jobs.length === 0 ? <View style={s.card}><Text style={s.emptyIcon}>◎</Text><Text style={s.title}>{workspace?.on_duty ? 'You’re ready for the next call.' : 'Your next response starts here.'}</Text><Text style={s.muted}>{workspace?.on_duty ? 'No active assignments. New jobs appear here automatically while this screen is open.' : 'Switch on duty above when your shift begins.'}</Text></View> : [...pending, ...active].map(job => <JobCard key={job.id} job={job} disabled={busy} open={() => void run(() => open(job))} />)}
    </> : tab === 'history' ? <>
      <Text style={s.subtitle}>A record of your assigned responses.</Text>{history.length ? history.map(job => <JobCard key={job.id} job={job} disabled={busy} open={() => void run(() => open(job))} />) : <View style={s.card}><Text style={s.title}>No past responses yet</Text><Text style={s.muted}>Completed, declined, expired, and cancelled assignments appear here.</Text></View>}
      {moreHistory && <Button secondary label="Load older responses" disabled={busy} onPress={() => void run(async () => { const page = historyPage + 1; const result = await request(`marshal/assignments?history=true&page=${page}`); setHistory(current => [...current, ...result.items]); setHistoryPage(page); setMoreHistory(result.items.length === 20); })} />}
    </> : <View style={s.card}><Text style={s.title}>Response partner</Text><Text style={s.body}>{workspace?.property_name}</Text><Text style={s.muted}>This app shows your assigned response work. Contact your dispatcher for access, reassignment, or assistance.</Text><Button secondary label="Personal details & verification" disabled={busy} onPress={() => setShowOnboarding(true)} /><Button secondary label="Sign out" disabled={busy} onPress={() => void run(async () => {
      let remoteFailed = false;
      try { if (origin) await unregisterMarshalPush(origin, session.access_token); } catch { remoteFailed = true; }
      try { if (workspace) await duty(false); } catch { remoteFailed = true; }
      try { await request('auth/logout', {}); } catch { remoteFailed = true; }
      finally { await clearSession(); }
      if (remoteFailed) setError('Signed out on this phone. Connect to the server to confirm remote sign-out; your duty eligibility expires after five minutes without an update.');
    })} /></View>}
    <Text style={s.footer}>SecurePulse · Every response matters</Text>
  </ScrollView><View style={s.nav}>{([['jobs', '◎', 'Jobs'], ['history', '◷', 'History'], ['account', '○', 'Account']] as const).map(([id, icon, label]) => <Pressable accessibilityRole="tab" accessibilityState={{ selected: tab === id && !selected }} key={id} style={s.navItem} onPress={() => { selectedRef.current = null; setSelected(null); setTab(id); setNote(''); }}><Text style={[s.navIcon, tab === id && { color: '#E65324' }]}>{icon}</Text><Text style={[s.navLabel, tab === id && { color: '#E65324' }]}>{label}</Text></Pressable>)}</View></View>;
}

function JobCard({ job, disabled, open }: { job: Job; disabled: boolean; open: () => void }) {
  return <View style={s.card}><View style={s.row}><Text style={s.tag}>{names[job.status] ?? job.status}</Text><Text style={s.muted}>#{job.id}</Text></View><Text style={s.title}>{readable(job.incident_type)}</Text><Text style={s.body}>{job.property_name}</Text><Text style={s.muted}>{job.address || 'Address not supplied'}</Text>{job.severity && <Text style={s.label}>Priority: {readable(job.severity)}</Text>}<Button label={job.status === 'OFFERED' ? 'Review assignment →' : 'View response →'} secondary={job.status !== 'OFFERED'} disabled={disabled} onPress={open} /></View>;
}

const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: '#F7F8F3' }, content: { padding: 22, gap: 18, paddingBottom: 28 }, login: { padding: 26, paddingTop: 50, gap: 22 }, center: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: 16 },
  row: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 12 }, logo: { width: 58, height: 58, backgroundColor: '#E65324', borderRadius: 18, alignItems: 'center', justifyContent: 'center' }, logoText: { color: '#FFF', fontWeight: '900', fontSize: 24 }, eyebrow: { color: '#64746B', fontWeight: '800', fontSize: 10, letterSpacing: 1.8 }, hero: { fontSize: 43, lineHeight: 48, letterSpacing: -1.8, color: '#18332B', fontWeight: '900' }, subtitle: { fontSize: 17, lineHeight: 25, color: '#64746B' },
  gap: { gap: 8 }, card: { backgroundColor: '#FFF', borderRadius: 22, padding: 20, gap: 14, borderWidth: 1, borderColor: '#E6EAE1' }, darkCard: { backgroundColor: '#183D31', borderRadius: 24, padding: 23, gap: 14 }, darkEyebrow: { color: '#BAD0BC', letterSpacing: 1.8, fontSize: 10, fontWeight: '800' }, whiteTitle: { fontSize: 25, lineHeight: 32, color: '#FFF', fontWeight: '800' }, white: { color: '#D1E0D3', lineHeight: 23, fontSize: 14 }, pill: { alignSelf: 'flex-start', color: '#18332B', backgroundColor: '#D9EBCC', paddingVertical: 8, paddingHorizontal: 12, borderRadius: 10, fontWeight: '700' }, title: { fontSize: 21, lineHeight: 29, fontWeight: '800', color: '#18332B', flexShrink: 1, textTransform: 'capitalize' }, body: { fontSize: 16, color: '#18332B', lineHeight: 24 }, muted: { color: '#64746B', fontSize: 13, lineHeight: 21 }, label: { color: '#40594C', fontSize: 12, fontWeight: '700', lineHeight: 19 }, input: { borderWidth: 1, borderColor: '#D8DFD3', backgroundColor: '#FAFBF8', borderRadius: 13, padding: 16, fontSize: 16, color: '#18332B', minHeight: 54 },
  button: { backgroundColor: '#E65324', borderRadius: 14, paddingVertical: 17, paddingHorizontal: 18, alignItems: 'center', minHeight: 56 }, secondary: { backgroundColor: '#EDF2E8' }, buttonText: { color: '#FFF', fontSize: 16, fontWeight: '800', textAlign: 'center' }, avatar: { backgroundColor: '#E3EBDD', padding: 12, borderRadius: 18 }, stats: { flexDirection: 'row', gap: 14 }, stat: { flex: 1, backgroundColor: '#EBF0E4', padding: 20, borderRadius: 19, gap: 5 }, number: { fontSize: 34, color: '#18332B', fontWeight: '900' }, tag: { color: '#AD3F1D', backgroundColor: '#FFF0E8', padding: 8, borderRadius: 8, fontWeight: '700', fontSize: 12 }, emptyIcon: { color: '#E65324', fontSize: 50 }, footer: { textAlign: 'center', color: '#7C8A7B', fontSize: 12, paddingVertical: 12 }, error: { padding: 16, backgroundColor: '#FDECE6', borderRadius: 14 }, errorText: { color: '#91371E', lineHeight: 22 },
  step: { flexDirection: 'row', gap: 14, alignItems: 'center' }, dot: { width: 32, height: 32, borderRadius: 16, backgroundColor: '#DCE2D5', alignItems: 'center', justifyContent: 'center' }, dotDone: { backgroundColor: '#C8E4BA' }, dotText: { color: '#18332B', fontWeight: '800' }, stepText: { fontSize: 16, color: '#18332B', fontWeight: '600' }, timeline: { borderLeftWidth: 2, borderLeftColor: '#DBE5D5', paddingLeft: 14, gap: 5, paddingBottom: 12 }, nav: { flexDirection: 'row', borderTopWidth: 1, borderColor: '#E5EADD', backgroundColor: '#FFF', paddingVertical: 12 }, navItem: { flex: 1, alignItems: 'center', gap: 4, minHeight: 48 }, navIcon: { fontSize: 24, color: '#7C8A7B' }, navLabel: { fontSize: 11, fontWeight: '800', color: '#7C8A7B' },
});
