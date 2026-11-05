import { Text, TextInput, View } from 'react-native';
import { useState } from 'react';
import { session, useAuth } from '../auth/AuthProvider';
import { Screen } from '../components/Screen';
import { PrimaryButton } from '../components/PrimaryButton';
import { Notice, ui } from '../components/Content';
import { api } from '../auth/AuthProvider';
import { canReport } from '../api/types';
export function ProfileScreen() {
  const { state, propertyId, selectProperty } = useAuth();
  const [name, setName] = useState(state.profile?.name ?? '');
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  async function saveName() {
    setBusy(true); setMessage(null);
    try { await api.updateProfile(name.trim()); await session.refreshProfile(); setMessage('Profile updated.'); }
    catch (error) { setMessage(error instanceof Error ? error.message : 'Unable to update profile.'); }
    finally { setBusy(false); }
  }
  async function savePassword() {
    setBusy(true); setMessage(null);
    try { await api.changePassword(currentPassword, newPassword); setCurrentPassword(''); setNewPassword(''); session.passwordChanged(); }
    catch (error) { setMessage(error instanceof Error ? error.message : 'Unable to change password.'); }
    finally { setBusy(false); }
  }
  return <Screen><Text style={ui.title}>{state.profile?.name}</Text><Notice>{state.profile?.email}</Notice>
    <Text style={ui.heading}>Profile name</Text>
    <TextInput accessibilityLabel="Profile name" style={ui.input} value={name} onChangeText={setName} maxLength={255} editable={!busy} />
    <PrimaryButton label={busy ? 'Saving…' : 'Save name'} onPress={() => void saveName()} disabled={busy || !name.trim()} />
    <Text style={ui.heading}>Change password</Text>
    <TextInput accessibilityLabel="Current password" style={ui.input} value={currentPassword} onChangeText={setCurrentPassword} secureTextEntry editable={!busy} />
    <TextInput accessibilityLabel="New password" style={ui.input} value={newPassword} onChangeText={setNewPassword} secureTextEntry maxLength={128} editable={!busy} />
    <PrimaryButton label={busy ? 'Saving…' : 'Change password'} onPress={() => void savePassword()} disabled={busy || !currentPassword || newPassword.length < 12} />
    {message && <Text accessibilityRole="alert" style={ui.error}>{message}</Text>}
    <Text style={ui.heading}>Property access</Text>
    {!state.profile?.properties.length && <Notice>No property has been assigned. Contact your administrator.</Notice>}
    {state.profile?.properties.map(property => <View key={property.id} style={ui.card}>
      <Text style={ui.heading}>{property.name}</Text><Notice>Role: {property.role}</Notice>
      {canReport(property) ? <PrimaryButton label={property.id === propertyId ? 'Selected property' : 'Select property'} disabled={property.id === propertyId} onPress={() => selectProperty(property.id)} />
        : <Notice>Use the operator or marshal interface for this membership.</Notice>}
    </View>)}
    <Notice>Signing out also ends your other reporter sessions when the server is reachable.</Notice>
    <PrimaryButton label="Sign out" onPress={() => void session.logout()} />
  </Screen>;
}
