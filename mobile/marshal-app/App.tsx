import React, { useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Alert, AppState, Linking, Pressable, RefreshControl, ScrollView, StyleSheet, Switch, Text, TextInput, View } from 'react-native';
import { SafeAreaProvider, SafeAreaView } from 'react-native-safe-area-context';
import { StatusBar } from 'expo-status-bar';
import * as SecureStore from 'expo-secure-store';
import * as Location from 'expo-location';
import { IncomingAlarm } from './IncomingAlarm';
import { EvidencePhoto, type Evidence } from './EvidencePhoto';
import { Onboarding } from './Onboarding';

type Workspace = { property_id: number; property_name: string; service_area: string | null; on_duty: boolean; available: boolean; verification_status: string };
type Job = { id: number; property_name: string; status: string; version: number; incident_type: string; severity: string | null; description: string | null; address: string | null; latitude: number | null; longitude: number | null; expires_at: string; evidence?: Evidence[]; timeline?: { id: number; status: string; note: string | null; at: string }[] };
type Session = { access_token: string; expires_at: string };
const origin = process.env.EXPO_PUBLIC_SERVER_URL?.trim().replace(/\/+$/, '');
const storageKey = 'securepulse.marshal.session.v1';
const names: Record<string, string> = { OFFERED: 'New assignment', ACCEPTED: 'Accepted', EN_ROUTE: 'On the way', ON_SCENE: 'At the property', COMPLETED: 'Resolved', DECLINED: 'Declined', EXPIRED: 'Offer expired', CANCELLED: 'Cancelled' };
const steps = ['ACCEPTED', 'EN_ROUTE', 'ON_SCENE', 'COMPLETED'];
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
  const [history, setHistory] = useState<Job[]>([]);
  const [historyPage, setHistoryPage] = useState(1);
  const [moreHistory, setMoreHistory] = useState(false);
  const [selected, setSelected] = useState<Job | null>(null);
  const [tab, setTab] = useState<'jobs' | 'history' | 'account'>('jobs');
  const [showOnboarding, setShowOnboarding] = useState(false);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [note, setNote] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [synced, setSynced] = useState<string | null>(null);
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
    setSession(null); setWorkspace(null); setJobs([]); setHistory([]); setSelected(null); setNote(''); setSynced(null);
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
    if (nextWorkspace.verification_status !== 'APPROVED') dutyRef.current = false;
    setWorkspace(nextWorkspace); setJobs(active.items);
    setHistory(previous => historyPageRef.current > 1
      ? [...past.items, ...previous.filter(job => !past.items.some((latest: Job) => latest.id === job.id))]
      : past.items);
    if (historyPageRef.current === 1) setMoreHistory(past.items.length === 20);
    if (detail && selectedRef.current === detail.id) setSelected(detail);
    setSynced(new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }));
  }

  async function run(action: () => Promise<void>) {
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
          await request('marshal/workspace', undefined, parsed.session.access_token);
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
        await refresh();
        if (dutyRef.current && workspace?.property_id) await request('dispatch/marshal/availability', { property_id: workspace.property_id, on_duty: true, available: true }, undefined, 'PUT');
        if (active) setError(null);
      } catch (e) { if (active) setError(e instanceof Error ? e.message : 'Unable to refresh.'); }
    };
    void poll();
    const timer = setInterval(() => { void poll(); }, 10000);
    const listener = AppState.addEventListener('change', state => { if (state === 'active') void poll(); });
    return () => { active = false; clearInterval(timer); listener.remove(); };
  }, [session, workspace?.property_id]);

  useEffect(() => { const timer = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(timer); }, []);

  useEffect(() => {
    if (!session || !selected || !['ACCEPTED', 'EN_ROUTE', 'ON_SCENE'].includes(selected.status)) return;
    let active = true;
    let subscription: Location.LocationSubscription | null = null;
    void (async () => {
      const permission = await Location.requestForegroundPermissionsAsync();
      if (!active) return;
      if (permission.status !== Location.PermissionStatus.GRANTED) {
        setError('Location permission is required to share your live position during an active assignment.');
        return;
      }
      subscription = await Location.watchPositionAsync(
        { accuracy: Location.Accuracy.Balanced, timeInterval: 5000, distanceInterval: 10 },
        location => {
          if (!active) return;
          void request(`marshal/assignments/${selected.id}/location`, {
            latitude: location.coords.latitude,
            longitude: location.coords.longitude,
            accuracy_m: location.coords.accuracy,
            heading: location.coords.heading,
            speed_mps: location.coords.speed,
          }).catch(() => undefined);
        },
      );
    })().catch(() => {
      if (active) setError('Unable to start live location sharing. Check device location settings.');
    });
    return () => {
      active = false;
      subscription?.remove();
    };
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

  async function open(job: Job) { setNote(''); setSelected(await request(`marshal/assignments/${job.id}`)); }

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
  if (workspace && (showOnboarding || workspace.verification_status !== 'APPROVED')) return <Onboarding key={session.access_token} status={workspace.verification_status} origin={origin!} token={session.access_token} request={request} refresh={refresh} close={() => setShowOnboarding(false)} signOut={async () => { try { await request('auth/logout', {}); } finally { setShowOnboarding(false); await clearSession(); } }} />;
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
      {['OFFERED', 'ACCEPTED', 'EN_ROUTE', 'ON_SCENE', 'COMPLETED'].includes(selected.status) && <View style={s.card}><Text style={s.title}>Incident evidence</Text><Text style={s.muted}>Review the captured scene before responding. A person in an image is not a confirmed threat.</Text>
        {selected.evidence?.length ? selected.evidence.map(item => item.media_type.startsWith('image/')
          ? <EvidencePhoto key={`${selected.id}:${item.id}`} assignmentId={selected.id} item={item} origin={origin!} token={session.access_token} request={request} />
          : <Text key={item.id} style={s.muted}>{item.name} · Video evidence (review through the command center)</Text>) : <Text style={s.muted}>No incident photos have been attached.</Text>}
      </View>}
      {selected.status === 'OFFERED' ? <View style={s.card}><Text style={s.title}>Can you respond?</Text><Text style={s.muted}>{Math.max(0, Math.ceil((Date.parse(selected.expires_at) - now) / 1000))} seconds left to accept</Text>
        <Button label="Accept response" disabled={busy || Date.parse(selected.expires_at) <= now} onPress={() => void run(() => update('accept'))} />
        <Button secondary label="Decline assignment" disabled={busy} onPress={() => Alert.alert('Decline this assignment?', 'Dispatch will be notified so another responder can be offered this job.', [{ text: 'Keep assignment', style: 'cancel' }, { text: 'Decline', style: 'destructive', onPress: () => void run(() => update('decline')) }])} /></View> : <View style={s.card}><Text style={s.title}>One step at a time</Text>{steps.map((step, index) => <View key={step} style={s.step}><View style={[s.dot, steps.indexOf(selected.status) >= index && s.dotDone]}><Text style={s.dotText}>{steps.indexOf(selected.status) >= index ? '✓' : index + 1}</Text></View><Text style={s.stepText}>{names[step]}</Text></View>)}</View>}
      {['ACCEPTED', 'EN_ROUTE', 'ON_SCENE'].includes(selected.status) && <>
        <View style={s.card}><Text style={s.title}>{selected.status === 'ON_SCENE' ? 'Investigation & resolution' : 'Response notes'}</Text><Text style={s.muted}>Record what you observed and the action taken. Saved notes appear in the incident timeline.</Text><TextInput accessibilityLabel="Incident note" multiline maxLength={2000} value={note} onChangeText={setNote} placeholder="What did you find?" placeholderTextColor="#727C76" style={[s.input, { minHeight: 110, textAlignVertical: 'top' }]} /><Button secondary label={busy ? 'Please wait…' : 'Save note'} disabled={busy || !note.trim()} onPress={() => void run(saveNote)} /></View>
        <Button label={selected.status === 'ACCEPTED' ? 'Start journey →' : selected.status === 'EN_ROUTE' ? 'I’ve reached the property' : 'Resolve incident ✓'} disabled={busy} onPress={() => {
          if (selected.status === 'ON_SCENE') {
            if (!selected.timeline?.some(event => event.note && event.status === 'ON_SCENE')) { setError('Save an investigation and resolution note before resolving.'); return; }
            Alert.alert('Resolve this incident?', 'Confirm you have investigated and recorded the outcome. Dispatch will see the incident as resolved.', [{ text: 'Keep investigating', style: 'cancel' }, { text: 'Resolve', onPress: () => void run(() => update('COMPLETED')) }]);
          } else void run(() => update(selected.status === 'ACCEPTED' ? 'EN_ROUTE' : 'ON_SCENE'));
        }} />
      </>}
      <View style={s.card}><Text style={s.title}>Response timeline</Text>{selected.timeline?.map(event => <View key={event.id} style={s.timeline}><Text style={s.label}>{names[event.status] ?? event.status}</Text>{event.note && <Text style={s.body}>{event.note}</Text>}<Text style={s.muted}>{new Date(event.at).toLocaleString()}</Text></View>)}</View>
    </> : tab === 'jobs' ? <>
      <View style={s.darkCard}><View style={s.row}><View style={{ flex: 1 }}><Text style={s.darkEyebrow}>YOUR SHIFT</Text><Text style={s.whiteTitle}>{workspace?.on_duty ? 'You’re on duty' : 'Take a moment. Get ready.'}</Text></View><Switch accessibilityLabel="On duty" value={workspace?.on_duty ?? false} disabled={busy || !workspace} onValueChange={value => void run(() => duty(value))} trackColor={{ false: '#64746B', true: '#FFB498' }} thumbColor="#FFFFFF" /></View><Text style={s.white}>{workspace?.on_duty ? 'Keep the app open to receive and refresh assignments.' : 'Go on duty when you’re ready to respond.'}</Text></View>
      <View style={s.stats}><View style={s.stat}><Text style={s.number}>{pending.length}</Text><Text style={s.muted}>Incoming</Text></View><View style={s.stat}><Text style={s.number}>{active.length}</Text><Text style={s.muted}>In progress</Text></View></View>
      <Text style={s.title}>Your assignments</Text>
      {jobs.length === 0 ? <View style={s.card}><Text style={s.emptyIcon}>◎</Text><Text style={s.title}>{workspace?.on_duty ? 'You’re ready for the next call.' : 'Your next response starts here.'}</Text><Text style={s.muted}>{workspace?.on_duty ? 'No active assignments. New jobs appear here automatically while this screen is open.' : 'Switch on duty above when your shift begins.'}</Text></View> : [...pending, ...active].map(job => <JobCard key={job.id} job={job} disabled={busy} open={() => void run(() => open(job))} />)}
    </> : tab === 'history' ? <>
      <Text style={s.subtitle}>A record of your assigned responses.</Text>{history.length ? history.map(job => <JobCard key={job.id} job={job} disabled={busy} open={() => void run(() => open(job))} />) : <View style={s.card}><Text style={s.title}>No past responses yet</Text><Text style={s.muted}>Completed, declined, expired, and cancelled assignments appear here.</Text></View>}
      {moreHistory && <Button secondary label="Load older responses" disabled={busy} onPress={() => void run(async () => { const page = historyPage + 1; const result = await request(`marshal/assignments?history=true&page=${page}`); setHistory(current => [...current, ...result.items]); setHistoryPage(page); setMoreHistory(result.items.length === 20); })} />}
    </> : <View style={s.card}><Text style={s.title}>Response partner</Text><Text style={s.body}>{workspace?.property_name}</Text><Text style={s.muted}>This app shows your assigned response work. Contact your dispatcher for access, reassignment, or assistance.</Text><Button secondary label="Personal details & verification" disabled={busy} onPress={() => setShowOnboarding(true)} /><Button secondary label="Sign out" disabled={busy} onPress={() => void run(async () => {
      let remoteFailed = false;
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
  card: { backgroundColor: '#FFF', borderRadius: 22, padding: 20, gap: 14, borderWidth: 1, borderColor: '#E6EAE1' }, darkCard: { backgroundColor: '#183D31', borderRadius: 24, padding: 23, gap: 14 }, darkEyebrow: { color: '#BAD0BC', letterSpacing: 1.8, fontSize: 10, fontWeight: '800' }, whiteTitle: { fontSize: 25, lineHeight: 32, color: '#FFF', fontWeight: '800' }, white: { color: '#D1E0D3', lineHeight: 23, fontSize: 14 }, pill: { alignSelf: 'flex-start', color: '#18332B', backgroundColor: '#D9EBCC', paddingVertical: 8, paddingHorizontal: 12, borderRadius: 10, fontWeight: '700' }, title: { fontSize: 21, lineHeight: 29, fontWeight: '800', color: '#18332B', flexShrink: 1, textTransform: 'capitalize' }, body: { fontSize: 16, color: '#18332B', lineHeight: 24 }, muted: { color: '#64746B', fontSize: 13, lineHeight: 21 }, label: { color: '#40594C', fontSize: 12, fontWeight: '700', lineHeight: 19 }, input: { borderWidth: 1, borderColor: '#D8DFD3', backgroundColor: '#FAFBF8', borderRadius: 13, padding: 16, fontSize: 16, color: '#18332B', minHeight: 54 },
  button: { backgroundColor: '#E65324', borderRadius: 14, paddingVertical: 17, paddingHorizontal: 18, alignItems: 'center', minHeight: 56 }, secondary: { backgroundColor: '#EDF2E8' }, buttonText: { color: '#FFF', fontSize: 16, fontWeight: '800', textAlign: 'center' }, avatar: { backgroundColor: '#E3EBDD', padding: 12, borderRadius: 18 }, stats: { flexDirection: 'row', gap: 14 }, stat: { flex: 1, backgroundColor: '#EBF0E4', padding: 20, borderRadius: 19, gap: 5 }, number: { fontSize: 34, color: '#18332B', fontWeight: '900' }, tag: { color: '#AD3F1D', backgroundColor: '#FFF0E8', padding: 8, borderRadius: 8, fontWeight: '700', fontSize: 12 }, emptyIcon: { color: '#E65324', fontSize: 50 }, footer: { textAlign: 'center', color: '#7C8A7B', fontSize: 12, paddingVertical: 12 }, error: { padding: 16, backgroundColor: '#FDECE6', borderRadius: 14 }, errorText: { color: '#91371E', lineHeight: 22 },
  step: { flexDirection: 'row', gap: 14, alignItems: 'center' }, dot: { width: 32, height: 32, borderRadius: 16, backgroundColor: '#DCE2D5', alignItems: 'center', justifyContent: 'center' }, dotDone: { backgroundColor: '#C8E4BA' }, dotText: { color: '#18332B', fontWeight: '800' }, stepText: { fontSize: 16, color: '#18332B', fontWeight: '600' }, timeline: { borderLeftWidth: 2, borderLeftColor: '#DBE5D5', paddingLeft: 14, gap: 5, paddingBottom: 12 }, nav: { flexDirection: 'row', borderTopWidth: 1, borderColor: '#E5EADD', backgroundColor: '#FFF', paddingVertical: 12 }, navItem: { flex: 1, alignItems: 'center', gap: 4, minHeight: 48 }, navIcon: { fontSize: 24, color: '#7C8A7B' }, navLabel: { fontSize: 11, fontWeight: '800', color: '#7C8A7B' },
});
