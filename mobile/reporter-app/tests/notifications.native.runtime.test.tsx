import React from 'react';
import { render } from '@testing-library/react-native';
import { NotificationBridge } from '../src/components/NotificationBridge';
import { loadNotifications } from '../src/notifications';

jest.mock('expo-constants', () => ({ __esModule: true, default: { appOwnership: null, expoGoConfig: null, expoVersion: null } }));
jest.mock('expo-secure-store', () => ({}));
jest.mock('../src/config', () => ({ expoProjectId: 'test-project' }));
jest.mock('expo-router', () => ({ router: { push: jest.fn() } }));
jest.mock('../src/auth/AuthProvider', () => ({
  api: { notificationPreferences: jest.fn() }, queryClient: { invalidateQueries: jest.fn() },
  useAuth: () => ({ state: { profile: { id: 1, properties: [] } }, selectProperty: jest.fn() }),
}));
jest.mock('expo-notifications', () => {
  throw new Error("Cannot find native module 'ExpoApplication'");
});

it('keeps the bridge renderable when a native build is missing notification modules', async () => {
  await expect(render(<NotificationBridge />)).resolves.toBeDefined();
});

it('provides a recoverable rebuild message for missing native notification modules', async () => {
  await expect(loadNotifications()).rejects.toThrow('Rebuild and reinstall');
});
