import React from 'react';
import { Text } from 'react-native';
import { act, renderRouter, screen, testRouter, waitFor } from 'expo-router/testing-library';
import Layout from '../app/_layout';
import AppLayout from '../app/(app)/_layout';

let mockInitialAuthenticated = false;
jest.mock('../src/components/NotificationBridge', () => ({ NotificationBridge: () => null }));
let mockSetAuthenticated: React.Dispatch<React.SetStateAction<boolean>>;
jest.mock('../src/auth/AuthProvider', () => ({
  AuthProvider: ({ children }: React.PropsWithChildren) => children,
  useAuth: () => {
    const [authenticated, setAuthenticated] = require('react').useState(mockInitialAuthenticated);
    mockSetAuthenticated = setAuthenticated;
    return { state: { loading: false, profile: authenticated ? { id: 1 } : null } };
  },
}));
const routes = {
  _layout: Layout,
  login: () => <Text>Sign in screen</Text>,
  recover: () => <Text>Recovery screen</Text>,
  '(app)/_layout': AppLayout,
  '(app)/index': () => <Text>Home screen</Text>,
  '(app)/alerts/index': () => <Text>Alerts screen</Text>,
  '(app)/alerts/[id]': () => <Text>Alert detail screen</Text>,
  '(app)/cameras/index': () => <Text>Cameras screen</Text>,
  '(app)/cameras/[id]': () => <Text>Camera detail screen</Text>,
  '(app)/profile': () => <Text>Profile screen</Text>,
  '(app)/settings': () => <Text>Settings screen</Text>,
  '(app)/report': () => <Text>Report screen</Text>,
  '(app)/incidents/index': () => <Text>Incident history</Text>,
  '(app)/incidents/[id]': () => <Text>Incident detail</Text>,
};

it('redirects an unauthenticated deep link to sign-in', async () => {
  mockInitialAuthenticated = false;
  const view = await renderRouter(routes, { initialUrl: '/alerts/1' });
  await waitFor(() => expect(view.getPathname()).toBe('/login'));
  expect(screen.getByText('Sign in screen')).toBeTruthy();
});

it('opens protected routes after sign-in and removes their history on logout', async () => {
  mockInitialAuthenticated = false;
  const view = await renderRouter(routes, { initialUrl: '/login' });
  await act(() => mockSetAuthenticated(true));
  await waitFor(() => expect(view.getPathname()).toBe('/'));
  await testRouter.push('/alerts');
  await testRouter.push('/alerts/42');
  await testRouter.back('/alerts');
  await testRouter.push('/cameras');
  await testRouter.push('/cameras/7');
  await testRouter.push('/profile');
  await testRouter.push('/settings');
  await testRouter.push('/report?eventId=42');
  await act(() => mockSetAuthenticated(false));
  await waitFor(() => expect(view.getPathname()).toBe('/login'));
  expect(testRouter.canGoBack()).toBe(false);
});

it('allows an authenticated detail deep link', async () => {
  mockInitialAuthenticated = true;
  const view = await renderRouter(routes, { initialUrl: '/cameras/7' });
  await waitFor(() => expect(view.getPathname()).toBe('/cameras/7'));
});

it('allows account recovery before sign-in', async () => {
  mockInitialAuthenticated = false;
  const view = await renderRouter(routes, { initialUrl: '/recover' });
  await waitFor(() => expect(view.getPathname()).toBe('/recover'));
  expect(screen.getByText('Recovery screen')).toBeTruthy();
});
