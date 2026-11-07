import { useEffect, useRef, useState } from 'react';
import { Text, TextInput } from 'react-native';
import * as ImagePicker from 'expo-image-picker';
import * as Location from 'expo-location';
import { useLocalSearchParams } from 'expo-router';
import { Screen } from '../components/Screen';
import { PrimaryButton } from '../components/PrimaryButton';
import { Notice, PropertyBanner, ui } from '../components/Content';
import { api, useAuth } from '../auth/AuthProvider';
import { useQueryClient } from '@tanstack/react-query';
import { router } from 'expo-router';
import { ReportSubmission } from '../api/reportSubmission';

const categories = [
  ['THEFT', 'Theft'], ['BREAK_IN', 'Break-in'], ['SUSPICIOUS_ACTIVITY', 'Suspicious activity'],
  ['ASSAULT', 'Assault or violence'], ['PROPERTY_DAMAGE', 'Property damage'],
  ['FIRE', 'Fire'], ['MEDICAL_EMERGENCY', 'Medical emergency'], ['OTHER', 'Other emergency'],
] as const;

export function ReportScreen() {
  const { eventId } = useLocalSearchParams<{ eventId?: string }>();
  const { propertyId } = useAuth();
  const queryClient = useQueryClient();
  const [type, setType] = useState<string>('SUSPICIOUS_ACTIVITY');
  const [description, setDescription] = useState('');
  const [address, setAddress] = useState('');
  const [location, setLocation] = useState<{ latitude: number; longitude: number; accuracy?: number } | null>(null);
  const [attachment, setAttachment] = useState<{ uri: string; name: string; type: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [locating, setLocating] = useState(false);
  const locationRequest = useRef(0);
  const [error, setError] = useState<string | null>(null);
  const submission = useRef(new ReportSubmission(api)).current;
  const controller = useRef<AbortController | null>(null);
  useEffect(() => () => { controller.current?.abort(); locationRequest.current++; }, []);

  async function useCurrentLocation() {
    if (busy || locating) return;
    const attempt = ++locationRequest.current;
    setLocating(true); setError(null);
    try {
    const permission = await Location.requestForegroundPermissionsAsync();
    if (attempt !== locationRequest.current) return;
    if (permission.status !== 'granted') {
      setError('Location permission was denied. Enter the incident address instead.');
      return;
    }
    const position = await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.Balanced });
    if (submission.started || attempt !== locationRequest.current) return;
    setLocation({ latitude: position.coords.latitude, longitude: position.coords.longitude, accuracy: position.coords.accuracy ?? undefined });
    } catch { if (attempt === locationRequest.current) setError('Unable to read your location. Enter the address instead.'); }
    finally { if (attempt === locationRequest.current) setLocating(false); }
  }
  async function chooseEvidence() {
    if (busy) return;
    setBusy(true); setError(null);
    try {
    const result = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ['images', 'videos'], quality: 0.8 });
    if (!result.canceled && result.assets[0]) {
      const asset = result.assets[0];
      const next = { uri: asset.uri, name: asset.fileName ?? `evidence-${Date.now()}`, type: asset.mimeType ?? 'image/jpeg' };
      if (submission.started) submission.setAttachment(next);
      setAttachment(next);
    }
    } catch { setError('Unable to select evidence. Try another file.'); }
    finally { setBusy(false); }
  }
  async function submit() {
    if (busy) return;
    if (!submission.started && (!propertyId || (!address.trim() && !location) || !type)) {
      setError('Choose an incident type and provide an address or current location.');
      return;
    }
    setBusy(true); setError(null);
    const abort = new AbortController();
    controller.current = abort;
    try {
      const incident = submission.started ? await submission.retry(abort.signal) : await submission.submit({
        property_id: propertyId!, incident_type: type, description: description.trim() || undefined,
        address: address.trim() || undefined, latitude: location?.latitude, longitude: location?.longitude,
        location_accuracy: location?.accuracy,
      }, attachment, abort.signal);
      if (abort.signal.aborted) return;
      await queryClient.invalidateQueries({ queryKey: ['reporter-incidents'] });
      await queryClient.invalidateQueries({ queryKey: ['reporter-incident'] });
      router.replace({ pathname: '/incidents/[id]', params: { id: String(incident.id) } });
    } catch (caught) {
      if (abort.signal.aborted) return;
      setError(caught instanceof Error ? caught.message : 'Unable to submit the incident. Please retry.');
    } finally { if (!abort.signal.aborted) setBusy(false); }
  }
  return <Screen><Text style={ui.title}>Report an incident</Text><PropertyBanner />
    {eventId && <Notice>Opened from alert #{eventId}. This report is separate and requires your confirmation.</Notice>}
    {!propertyId && <Notice>Assign a property before submitting a report.</Notice>}
    {submission.started && <Notice>This submission stays attached to property #{submission.propertyId}. Retrying will not create another report.</Notice>}
    {submission.incidentId && <Notice>Report #{submission.incidentId} is saved. You can retry or replace its attachment, or open the saved report.</Notice>}
    <Text style={ui.heading}>What happened?</Text>
    {categories.map(([value, label]) => <PrimaryButton key={value} disabled={busy || submission.started} variant={type === value ? 'primary' : 'secondary'} label={label} onPress={() => setType(value)} />)}
    <Text style={ui.label}>Description (optional)</Text>
    <TextInput accessibilityLabel="Incident description" editable={!busy && !submission.started} style={[ui.input, { minHeight: 110, textAlignVertical: 'top' }]} multiline maxLength={4000}
      placeholder="Describe what you observed." placeholderTextColor="#64748b" value={description} onChangeText={setDescription} />
    <Text style={ui.heading}>Where did it happen?</Text>
    <TextInput accessibilityLabel="Incident address" editable={!busy && !submission.started} style={ui.input} maxLength={1000} placeholder="Enter the incident address" placeholderTextColor="#64748b"
      value={address} onChangeText={setAddress} />
    <PrimaryButton disabled={busy || submission.started || locating} variant="secondary" label={locating ? 'Finding location…' : location ? `Location captured (${location.latitude.toFixed(5)}, ${location.longitude.toFixed(5)})` : 'Use current location'} onPress={() => void useCurrentLocation()} />
    {locating && <PrimaryButton variant="secondary" label="Cancel location request" onPress={() => { locationRequest.current++; setLocating(false); }} />}
    <Text style={ui.heading}>Evidence (optional)</Text>
    <PrimaryButton disabled={busy} variant="secondary" label={attachment ? `Attached: ${attachment.name}` : 'Choose photo or video'} onPress={() => void chooseEvidence()} />
    {attachment && <PrimaryButton variant="secondary" label="Remove attachment" disabled={busy} onPress={() => { if (submission.started) submission.setAttachment(null); setAttachment(null); }} />}
    {error && <Text accessibilityRole="alert" style={ui.error}>{error}</Text>}
    <Notice>Only submit information you are authorized to share. For immediate danger, contact your official emergency services.</Notice>
    <PrimaryButton label={busy ? 'Please wait…' : submission.started ? 'Retry existing submission' : 'Confirm and submit report'} disabled={busy || (!propertyId && !submission.started)} onPress={() => void submit()} />
    {submission.incidentId && <PrimaryButton variant="secondary" label="Open saved report" disabled={busy} onPress={() => router.replace({ pathname: '/incidents/[id]', params: { id: String(submission.incidentId) } })} />}
  </Screen>;
}
