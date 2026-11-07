import * as SecureStore from 'expo-secure-store';
import Constants from 'expo-constants';
import { Platform } from 'react-native';
import type { Api } from './api/client';
import { expoProjectId } from './config';

export const isExpoGo = Boolean(
  Constants.expoGoConfig || Constants.appOwnership === 'expo' || Constants.expoVersion,
);

export async function loadNotifications(): Promise<typeof import('expo-notifications')> {
  if (Platform.OS === 'web' || isExpoGo) {
    throw new Error('Remote push notifications require a development or release build; they are unavailable in Expo Go.');
  }
  try {
    // Importing this package loads native modules, so defer it until needed.
    return await import('expo-notifications');
  } catch {
    throw new Error('This build does not include native notification support. Rebuild and reinstall the development app to enable push notifications.');
  }
}

export async function registerPush(api: Api, requestPermission = true) {
  if (Platform.OS === 'web') throw new Error('Push notifications require a native development or release build.');
  if (isExpoGo) throw new Error('Remote push notifications require a development or release build; they are unavailable in Expo Go.');
  if (!expoProjectId) throw new Error('Set EXPO_PUBLIC_EXPO_PROJECT_ID and rebuild before enabling push notifications.');
  const Notifications = await loadNotifications();
  if (Platform.OS === 'android') await Notifications.setNotificationChannelAsync('security-updates', {
    name: 'Security and response updates', importance: Notifications.AndroidImportance.HIGH,
  });
  let permission = await Notifications.getPermissionsAsync();
  if (!permission.granted && requestPermission) permission = await Notifications.requestPermissionsAsync();
  if (!permission.granted) {
    if (requestPermission) throw new Error('Notification permission was denied. Enable it in device settings.');
    return;
  }
  const token = await Notifications.getExpoPushTokenAsync({ projectId: expoProjectId });
  const key = 'securepulse.device.id';
  let deviceId = await SecureStore.getItemAsync(key);
  if (!deviceId) {
    deviceId = `${Platform.OS}-${Date.now()}-${Math.random().toString(36).slice(2)}`;
    await SecureStore.setItemAsync(key, deviceId);
  }
  await api.registerDevice({ device_id: deviceId, push_token: token.data, provider: 'expo' });
}
