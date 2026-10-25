import { Stack } from 'expo-router';
export default function AppLayout() {
  return <Stack screenOptions={{ headerTintColor: '#0f172a', contentStyle: { backgroundColor: '#f8fafc' } }}>
    <Stack.Screen name="index" options={{ title: 'SecurePulse' }} />
    <Stack.Screen name="alerts/index" options={{ title: 'Alerts' }} />
    <Stack.Screen name="alerts/[id]" options={{ title: 'Alert details' }} />
    <Stack.Screen name="cameras/index" options={{ title: 'Cameras' }} />
    <Stack.Screen name="cameras/[id]" options={{ title: 'Camera details' }} />
    <Stack.Screen name="profile" options={{ title: 'Profile' }} />
    <Stack.Screen name="settings" options={{ title: 'Settings' }} />
    <Stack.Screen name="report" options={{ title: 'Report incident' }} />
  </Stack>;
}
