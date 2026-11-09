import Constants from 'expo-constants';
import * as Notifications from 'expo-notifications';
import * as SecureStore from 'expo-secure-store';
import { Platform } from 'react-native';

const DEVICE_KEY = 'securepulse.marshal.device.v1';
const CHANNEL = 'dispatch-alerts';

Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowAlert: true,
    shouldShowBanner: true,
    shouldShowList: true,
    shouldPlaySound: true,
    shouldSetBadge: true,
  }),
});

export async function registerMarshalPush(origin: string, token: string) {
  const projectId = Constants.easConfig?.projectId ?? Constants.expoConfig?.extra?.eas?.projectId;
  if (!projectId) throw new Error('Push alerts need an Expo project ID. Set EXPO_PUBLIC_EXPO_PROJECT_ID and rebuild the marshal app.');
  if (Platform.OS === 'android') {
    await Notifications.setNotificationChannelAsync(CHANNEL, {
      name: 'Urgent marshal assignments',
      description: 'New response offers that need a quick decision',
      importance: Notifications.AndroidImportance.MAX,
      sound: 'assignment-alarm.wav',
      vibrationPattern: [0, 500, 250, 500, 250, 800],
      lockscreenVisibility: Notifications.AndroidNotificationVisibility.PUBLIC,
    });
  }
  let permission = await Notifications.getPermissionsAsync();
  if (!permission.granted) permission = await Notifications.requestPermissionsAsync();
  if (!permission.granted) throw new Error('Enable notifications in phone settings to receive assignment alerts.');

  const pushToken = await Notifications.getExpoPushTokenAsync({ projectId });
  let deviceId = await SecureStore.getItemAsync(DEVICE_KEY);
  if (!deviceId) {
    deviceId = `${Platform.OS}-${Date.now()}-${Math.random().toString(36).slice(2)}`;
    await SecureStore.setItemAsync(DEVICE_KEY, deviceId);
  }
  const headers = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' };
  const registered = await fetch(`${origin}/api/v1/reporter/devices`, {
    method: 'POST', headers,
    body: JSON.stringify({ device_id: deviceId, push_token: pushToken.data, provider: 'expo' }),
  });
  if (!registered.ok) throw new Error('Could not register this phone for assignment alerts.');
  const preference = await fetch(`${origin}/api/v1/reporter/notification-preferences`, {
    method: 'PUT', headers,
    body: JSON.stringify({ category: 'DISPATCH_UPDATES', enabled: true }),
  });
  if (!preference.ok) throw new Error('Could not enable assignment alerts for this phone.');
}

export async function unregisterMarshalPush(origin: string, token: string) {
  const deviceId = await SecureStore.getItemAsync(DEVICE_KEY);
  if (deviceId) {
    await fetch(`${origin}/api/v1/reporter/devices/${encodeURIComponent(deviceId)}`, {
      method: 'DELETE', headers: { Authorization: `Bearer ${token}` },
    });
  }
  await SecureStore.deleteItemAsync(DEVICE_KEY);
}

export { CHANNEL as DISPATCH_NOTIFICATION_CHANNEL };
