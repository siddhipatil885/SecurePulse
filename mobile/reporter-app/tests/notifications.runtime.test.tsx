import React from 'react';
import { render } from '@testing-library/react-native';
import { NotificationBridge } from '../src/components/NotificationBridge';
import { loadNotifications, registerPush } from '../src/notifications';
import type { Api } from '../src/api/client';

jest.mock('expo-constants', () => ({ __esModule: true, default: { appOwnership: 'expo', expoGoConfig: {} } }));
jest.mock('expo-secure-store', () => ({}));
jest.mock('../src/config', () => ({ expoProjectId: 'test-project' }));
jest.mock('expo-router', () => ({ router: { push: jest.fn() } }));
jest.mock('../src/auth/AuthProvider', () => ({
  api: { notificationPreferences: jest.fn() }, queryClient: { invalidateQueries: jest.fn() },
  useAuth: () => ({ state: { profile: { id: 1, properties: [] } }, selectProperty: jest.fn() }),
}));
jest.mock('expo-notifications', () => {
  throw new Error('Native module must not load in Expo Go');
});

it('loads the bridge without importing unsupported native notifications in Expo Go', async () => {
  await expect(render(<NotificationBridge />)).resolves.toBeDefined();
});

it('rejects push registration before importing the native package in Expo Go', async () => {
  await expect(loadNotifications()).rejects.toThrow('unavailable in Expo Go');
  await expect(registerPush({} as Api)).rejects.toThrow('unavailable in Expo Go');
});
