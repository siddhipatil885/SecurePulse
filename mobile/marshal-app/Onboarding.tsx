import { useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Alert, Image, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import * as ImagePicker from 'expo-image-picker';

type Asset = { uri: string; name: string; type: string };
type Request = (path: string, body?: unknown, token?: string | null, method?: string) => Promise<any>;
const initial = { legal_name: '', date_of_birth: '', phone: '', address: '', id_type: 'DRIVING_LICENCE', id_number: '', emergency_name: '', emergency_phone: '', emergency_relationship: 'spouse', consent: false, emergency_contact_informed: false };
const identities = [['DRIVING_LICENCE', 'Driving licence'], ['PASSPORT', 'Passport'], ['VOTER_ID', 'Voter ID']] as const;

export function Onboarding({ status, origin, token, request, refresh, signOut, close, unauthorized }: { status: string; origin: string; token: string; request: Request; refresh: () => Promise<unknown>; signOut: () => Promise<void>; close?: () => void; unauthorized: (token: string) => Promise<void> }) {
  const [step, setStep] = useState(0);
  const [details, setDetails] = useState(initial);
  const [assets, setAssets] = useState<Record<string, Asset>>({});
  const [summary, setSummary] = useState<{ status: string; review_note?: string; id_last_four?: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const requestRef = useRef(request); requestRef.current = request;
  const secureUpload = origin.startsWith('https://');
  useEffect(() => { let active = true; void requestRef.current('marshal/onboarding').then(value => { if (active) setSummary(value); }).catch(() => { if (active) setError('Unable to load your onboarding status. Pull to refresh after reconnecting.'); }); return () => { active = false; }; }, [status]);
  async function run(action: () => Promise<void>) { setBusy(true); setError(null); try { await action(); } catch (e) { setError(e instanceof Error ? e.message : 'Please try again.'); } finally { setBusy(false); } }
  const field = (key: keyof typeof initial, label: string, options: { placeholder?: string; phone?: boolean; multiline?: boolean; secret?: boolean } = {}) => <View style={{ gap: 7 }}><Text style={s.label}>{label}</Text><TextInput accessibilityLabel={label} value={String(details[key])} onChangeText={value => setDetails(current => ({ ...current, [key]: value }))} editable={!busy} style={[s.input, options.multiline && { minHeight: 95, textAlignVertical: 'top' }]} placeholder={options.placeholder} placeholderTextColor="#78867C" keyboardType={options.phone ? 'phone-pad' : 'default'} multiline={options.multiline} secureTextEntry={options.secret} autoCapitalize={key === 'id_number' ? 'characters' : 'none'} maxLength={key === 'address' ? 1000 : key === 'id_number' ? 32 : 120} /></View>;
  async function pick(kind: string, camera: boolean) {
    const permission = camera ? await ImagePicker.requestCameraPermissionsAsync() : await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!permission.granted) throw new Error('Allow camera or photo access to attach your documents.');
    const options: ImagePicker.ImagePickerOptions = { mediaTypes: ['images'], allowsEditing: camera, aspect: [1, 1], quality: .6 };
    const result = camera ? await ImagePicker.launchCameraAsync(options) : await ImagePicker.launchImageLibraryAsync(options);
    if (!result.canceled && result.assets[0]) {
      const asset = result.assets[0];
      if (asset.fileSize && asset.fileSize > 3_000_000) throw new Error('Choose a clear image smaller than 3 MB.');
      const type = asset.mimeType || 'image/jpeg';
      if (!['image/jpeg', 'image/png'].includes(type)) throw new Error('Choose a JPG or PNG image.');
      setAssets(current => ({ ...current, [kind]: { uri: asset.uri, type, name: `${kind}.${type === 'image/png' ? 'png' : 'jpg'}` } }));
    }
  }
  async function submit() {
    if (!secureUpload) throw new Error('Connect to your organization’s HTTPS server before uploading identity documents.');
    if (!details.consent || !details.emergency_contact_informed) throw new Error('Please read and confirm both consent statements.');
    if (!assets.portrait || !assets.id_front) throw new Error('Add a clear face photo and your government ID photo.');
    const form = new FormData(); form.append('details', JSON.stringify(details));
    Object.entries(assets).forEach(([key, asset]) => form.append(key, asset as unknown as Blob));
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 30000);
    try {
      const response = await fetch(`${origin}/api/v1/marshal/onboarding`, { method: 'POST', headers: { Authorization: `Bearer ${token}` }, body: form, signal: controller.signal });
      if (response.status === 401) { await unauthorized(token); throw new Error('Please sign in again.'); }
      if (!response.ok) { const result = await response.json().catch(() => null); throw new Error(result?.error?.message || 'Submission failed. Check your connection and try again.'); }
      setDetails(initial); setAssets({}); setSummary({ status: 'PENDING' }); await refresh();
    } catch (e) {
      if (e instanceof Error && e.name === 'AbortError') throw new Error('Upload timed out. Reconnect and check your status before retrying.');
      throw e;
    } finally { clearTimeout(timeout); }
  }
  function next() {
    if (step === 0 && (!details.legal_name.trim() || !/^\d{4}-\d{2}-\d{2}$/.test(details.date_of_birth) || !details.phone || details.address.trim().length < 10)) { setError('Complete your name, birth date (YYYY-MM-DD), phone and address.'); return; }
    if (step === 1 && (!details.id_number.trim() || !assets.portrait || !assets.id_front)) { setError('Add your ID number, a clear face photo and the ID front.'); return; }
    setError(null); setStep(value => value + 1);
  }
  const reviewing = (summary?.status ?? status) === 'PENDING';
  const approved = (summary?.status ?? status) === 'APPROVED';
  return <ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={s.screen}>
    <Text style={s.eyebrow}>SECUREPULSE • RESPONSE PARTNER</Text><Text style={s.hero}>{reviewing ? 'You’re nearly ready.' : approved ? 'Your profile is approved.' : 'Let’s get you ready.'}</Text>
    <Text style={s.body}>A complete, reviewed profile helps us trust the people responding to each incident.</Text>
    {error && <Text accessibilityRole="alert" style={s.error}>{error}</Text>}
    {!secureUpload && <Text style={s.body}>Identity submission needs a secure HTTPS connection. You can review the form now; ask your administrator to configure a secure server before uploading personal documents.</Text>}
    {approved && close && <Button label="Back to jobs" disabled={busy} onPress={close} />}
    {reviewing || approved ? <View style={s.card}><Text style={s.title}>{reviewing ? 'Waiting for administrator review' : 'Approved for duty'}</Text><Text style={s.body}>{reviewing ? 'Your details and documents were submitted securely. Your administrator will check your ID, photo and contact details before you can go on duty.' : 'Your administrator has approved your profile.'}</Text><Button label="Check status" disabled={busy} onPress={() => void run(async () => { setSummary(await request('marshal/onboarding')); await refresh(); })} /></View> : <>
      {summary?.review_note && <View style={s.card}><Text style={s.title}>Please update your submission</Text><Text style={s.body}>{summary.review_note}</Text></View>}
      <View style={s.steps}>{['About you', 'Identity', 'Emergency contact'].map((label, index) => <Text key={label} style={[s.step, step === index && { color: '#E65324', fontWeight: '800' }]}>{index + 1}. {label}</Text>)}</View>
      <View style={s.card}>
        {step === 0 && <><Text style={s.title}>Your personal details</Text>{field('legal_name', 'Full name as on ID')}{field('date_of_birth', 'Date of birth', { placeholder: 'YYYY-MM-DD · age 18 or above' })}{field('phone', 'Your mobile number', { phone: true, placeholder: '+91 9876543210' })}{field('address', 'Residential address', { multiline: true })}</>}
        {step === 1 && <><Text style={s.title}>Your government ID</Text><Text style={s.body}>Choose a passport, driving licence or voter ID. Do not enter or upload Aadhaar in this photo-review flow.</Text><View style={s.choices}>{identities.map(([value, label]) => <Pressable accessibilityRole="radio" accessibilityState={{ selected: details.id_type === value }} key={value} style={[s.choice, details.id_type === value && s.selected]} disabled={busy} onPress={() => setDetails(current => ({ ...current, id_type: value, id_number: '' }))}><Text>{label}</Text></Pressable>)}</View>{field('id_number', 'Government ID number', { secret: true })}
          {([['portrait', 'Clear face photo'], ['id_front', 'Government ID front'], ['id_back', 'ID back (optional)']] as const).map(([kind, label]) => <View style={s.upload} key={kind}><Text style={s.label}>{label}</Text><Text style={s.body}>JPG or PNG, under 3 MB. Keep the image sharp, well lit and readable.</Text>{assets[kind] && <Image accessibilityLabel={label} source={{ uri: assets[kind].uri }} style={{ width: '100%', height: 140, borderRadius: 12 }} resizeMode="contain" />}<Button label={assets[kind] ? `Replace ${label.toLowerCase()}` : `Add ${label.toLowerCase()}`} disabled={busy} onPress={() => void run(() => pick(kind, false))} />{kind === 'portrait' && <Button label="Take face photo" disabled={busy} onPress={() => void run(() => pick(kind, true))} />}</View>)}
        </>}
        {step === 2 && <><Text style={s.title}>Who should we contact?</Text><Text style={s.body}>Choose a spouse, parent, sibling or trusted contact who can be reached in an emergency.</Text>{field('emergency_name', 'Emergency contact full name')}{field('emergency_phone', 'Emergency contact mobile number', { phone: true })}<View style={s.choices}>{['spouse', 'parent', 'sibling', 'friend', 'other'].map(value => <Pressable accessibilityRole="radio" accessibilityState={{ selected: details.emergency_relationship === value }} key={value} disabled={busy} style={[s.choice, details.emergency_relationship === value && s.selected]} onPress={() => setDetails(current => ({ ...current, emergency_relationship: value }))}><Text style={{ textTransform: 'capitalize' }}>{value}</Text></Pressable>)}</View>
          <Text style={s.body}>Your administrator uses these details for responder identity checks and emergency coordination. ID documents are private and are not shared with property owners or other marshals. This is manual review, not government e-KYC or a phone OTP check. You can withdraw the submission below; after withdrawal you cannot go on duty until a new submission is approved.</Text>
          {([['consent', 'I agree to collection and administrator review of these details and documents for marshal onboarding.'], ['emergency_contact_informed', 'I have informed my emergency contact and have their permission to provide their details.']] as const).map(([key, label]) => <Pressable key={key} accessibilityRole="checkbox" accessibilityState={{ checked: details[key] }} disabled={busy} onPress={() => setDetails(current => ({ ...current, [key]: !current[key] }))} style={s.upload}><Text style={s.body}>{details[key] ? '☑' : '☐'} {label}</Text></Pressable>)}
        </>}
        {step > 0 && <Button label="Back" disabled={busy} onPress={() => { setError(null); setStep(value => value - 1); }} />}
        <Button label={busy ? 'Please wait…' : step === 2 ? 'Submit for review' : 'Continue →'} disabled={busy || (step === 2 && !secureUpload)} onPress={() => step === 2 ? void run(submit) : next()} />
      </View>
    </>}
    {summary && summary.status !== 'REQUIRED' && <Button label="Withdraw submission and delete documents" disabled={busy} onPress={() => Alert.alert('Withdraw your onboarding?', 'Your stored details and documents will be removed from active storage and you will be unable to go on duty until a new submission is approved.', [{ text: 'Keep submission', style: 'cancel' }, { text: 'Withdraw', style: 'destructive', onPress: () => void run(async () => { await request('marshal/onboarding', undefined, undefined, 'DELETE'); setSummary({ status: 'REQUIRED' }); setDetails(initial); setAssets({}); setStep(0); await refresh(); }) }])} />}
    <Button label="Sign out" disabled={busy} onPress={() => void run(signOut)} />
    {busy && <ActivityIndicator color="#E65324" />}
  </ScrollView>;
}

function Button({ label, disabled, onPress }: { label: string; disabled: boolean; onPress: () => void }) { return <Pressable accessibilityRole="button" accessibilityState={{ disabled }} disabled={disabled} onPress={onPress} style={[s.button, disabled && { opacity: .5 }]}><Text style={s.buttonText}>{label}</Text></Pressable>; }
const s = StyleSheet.create({ screen: { padding: 24, gap: 20 }, eyebrow: { fontSize: 10, letterSpacing: 1.5, fontWeight: '800', color: '#64746B' }, hero: { fontSize: 34, fontWeight: '900', color: '#18332B' }, body: { color: '#496052', fontSize: 14, lineHeight: 23 }, title: { fontSize: 22, color: '#18332B', fontWeight: '800' }, label: { fontSize: 14, color: '#18332B', fontWeight: '700' }, card: { padding: 20, backgroundColor: '#FFF', borderRadius: 22, gap: 18 }, input: { minHeight: 54, borderWidth: 1, borderColor: '#D8DFD3', borderRadius: 12, padding: 14, fontSize: 16, color: '#18332B' }, steps: { flexDirection: 'row', flexWrap: 'wrap', gap: 14 }, step: { color: '#64746B', fontSize: 12 }, button: { minHeight: 54, padding: 16, backgroundColor: '#E65324', borderRadius: 13, justifyContent: 'center' }, buttonText: { color: '#FFF', textAlign: 'center', fontWeight: '800', fontSize: 15 }, choices: { flexDirection: 'row', flexWrap: 'wrap', gap: 10 }, choice: { padding: 12, backgroundColor: '#EDF2E8', borderRadius: 12 }, selected: { borderWidth: 2, borderColor: '#E65324' }, upload: { padding: 15, gap: 12, backgroundColor: '#F7F8F3', borderRadius: 14 }, error: { color: '#91371E', backgroundColor: '#FDECE6', padding: 15, borderRadius: 12, lineHeight: 22 } });
