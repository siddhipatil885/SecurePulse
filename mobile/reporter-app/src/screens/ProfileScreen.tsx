import { Text, View } from 'react-native';
import { session, useAuth } from '../auth/AuthProvider';
import { Screen } from '../components/Screen';
import { PrimaryButton } from '../components/PrimaryButton';
import { Notice, ui } from '../components/Content';
export function ProfileScreen() {
  const { state, propertyId, selectProperty } = useAuth();
  return <Screen><Text style={ui.title}>{state.profile?.name}</Text><Notice>{state.profile?.email}</Notice>
    <Text style={ui.heading}>Property access</Text>
    {!state.profile?.properties.length && <Notice>No property has been assigned. Contact your administrator.</Notice>}
    {state.profile?.properties.map(property => <View key={property.id} style={ui.card}>
      <Text style={ui.heading}>{property.name}</Text><Notice>Role: {property.role}</Notice>
      <PrimaryButton label={property.id === propertyId ? 'Selected property' : 'Select property'} disabled={property.id === propertyId} onPress={() => selectProperty(property.id)} />
    </View>)}
    <Notice>Signing out also ends your other reporter sessions when the server is reachable.</Notice>
    <PrimaryButton label="Sign out" onPress={() => void session.logout()} />
  </Screen>;
}
