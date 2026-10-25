import { Stack } from 'expo-router';
import { ActivityIndicator, View } from 'react-native';
import { StatusBar } from 'expo-status-bar';
import { AuthProvider, useAuth } from '../src/auth/AuthProvider';
function Routes() {
  const { state } = useAuth();
  if (state.loading) return <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center' }}><ActivityIndicator accessibilityLabel="Restoring session" /></View>;
  return <><StatusBar style="dark" /><Stack screenOptions={{ headerTintColor: '#0f172a', contentStyle: { backgroundColor: '#f8fafc' } }}>
    <Stack.Protected guard={!state.profile}><Stack.Screen name="login" options={{ title: 'SecurePulse Reporter' }} /></Stack.Protected>
    <Stack.Protected guard={!!state.profile}><Stack.Screen name="(app)" options={{ headerShown: false }} /></Stack.Protected>
  </Stack></>;
}
export default function Layout() { return <AuthProvider><Routes /></AuthProvider>; }
