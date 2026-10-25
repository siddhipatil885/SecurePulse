import React from 'react';
import { Text } from 'react-native';
import { act, renderRouter, screen, testRouter } from 'expo-router/testing-library';
import Layout from '../app/_layout';
import AppLayout from '../app/(app)/_layout';

let mockInitialAuthenticated = false;
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
  '(app)/_layout': AppLayout,
  '(app)/index': () => <Text>Home screen</Text>,
  '(app)/alerts/index': () => <Text>Alerts screen</Text>,
  '(app)/alerts/[id]': () => <Text>Alert detail screen</Text>,
  '(app)/cameras/index': () => <Text>Cameras screen</Text>,
  '(app)/cameras/[id]': () => <Text>Camera detail screen</Text>,
  '(app)/profile': () => <Text>Profile screen</Text>,
  '(app)/settings': () => <Text>Settings screen</Text>,
  '(app)/report': () => <Text>Report screen</Text>,
};

it('redirects an unauthenticated deep link to sign-in', () => {
  mockInitialAuthenticated = false;
  const view = renderRouter(routes, { initialUrl: '/alerts/1' });
  expect(view.getPathname()).toBe('/login');
  expect(screen.getByText('Sign in screen')).toBeTruthy();
});

it('opens protected routes after sign-in and removes their history on logout', () => {
  mockInitialAuthenticated = false;
  const view = renderRouter(routes, { initialUrl: '/login' });
  act(() => mockSetAuthenticated(true));
  expect(view.getPathname()).toBe('/');
  testRouter.push('/alerts');
  testRouter.push('/alerts/42');
  testRouter.back('/alerts');
  testRouter.push('/cameras');
  testRouter.push('/cameras/7');
  testRouter.push('/profile');
  testRouter.push('/settings');
  testRouter.push('/report?eventId=42');
  act(() => mockSetAuthenticated(false));
  expect(view.getPathname()).toBe('/login');
  expect(testRouter.canGoBack()).toBe(false);
});

it('allows an authenticated detail deep link', () => {
  mockInitialAuthenticated = true;
  const view = renderRouter(routes, { initialUrl: '/cameras/7' });
  expect(view.getPathname()).toBe('/cameras/7');
});
