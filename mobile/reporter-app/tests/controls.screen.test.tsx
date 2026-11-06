import React from 'react';
import { Alert } from 'react-native';
import { AssignMarshal } from '../src/components/AssignMarshal';
import { act, fireEvent, render, waitFor, cleanup } from '@testing-library/react-native';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { router } from 'expo-router';
import * as Location from 'expo-location';
import * as ImagePicker from 'expo-image-picker';
import { api, session } from '../src/auth/AuthProvider';
import { registerPush } from '../src/notifications';
import { ProfileScreen } from '../src/screens/ProfileScreen';
import { ReportScreen } from '../src/screens/ReportScreen';
import { SettingsScreen } from '../src/screens/SettingsScreen';
import { HomeScreen } from '../src/screens/HomeScreen';
import { AlertDetailScreen } from '../src/screens/DetailScreens';
import { IncidentDetailScreen, IncidentHistoryScreen } from '../src/screens/IncidentScreens';
import { LiveCamera } from '../src/components/LiveCamera';

let mockFocused = true;
let mockAuth: any;
let mockParams: Record<string, string> = {};
jest.mock('../src/auth/AuthProvider', () => ({
  useAuth: () => mockAuth,
  session: { refreshProfile: jest.fn(), passwordChanged: jest.fn(), logout: jest.fn() },
  api: { updateProfile: jest.fn(), changePassword: jest.fn(), createIncident: jest.fn(), uploadIncidentEvidence: jest.fn(),
    notificationPreferences: jest.fn(), updateNotificationPreference: jest.fn(), testNotification: jest.fn(), notificationTestStatus: jest.fn(),
    liveCamera: jest.fn(), cameras: jest.fn(), events: jest.fn(), summary: jest.fn(), event: jest.fn(), reviewEvent: jest.fn(),
    incidents: jest.fn(), incident: jest.fn(), reporterEvidenceAccess: jest.fn(),
    assignment: jest.fn(), eligibleMarshals: jest.fn(), assignMarshal: jest.fn(), assignMarshals: jest.fn() },
}));
jest.mock('../src/config', () => ({ serverUrl: 'https://camera-host.example.test' }));
jest.mock('../src/notifications', () => ({ registerPush: jest.fn() }));
jest.mock('expo-router', () => ({ router: { push: jest.fn(), replace: jest.fn() }, useLocalSearchParams: () => mockParams }));
jest.mock('@react-navigation/native', () => ({ useIsFocused: () => mockFocused }));
jest.mock('expo-location', () => ({ requestForegroundPermissionsAsync: jest.fn(), getCurrentPositionAsync: jest.fn(), Accuracy: { Balanced: 3 } }));
jest.mock('expo-image-picker', () => ({ launchImageLibraryAsync: jest.fn() }));
jest.mock('expo-video', () => ({
  useVideoPlayer: () => ({ addListener: () => ({ remove: jest.fn() }) }),
  VideoView: ({ accessibilityLabel }: any) => require('react').createElement(require('react-native').View, { accessibilityLabel }),
}));
jest.mock('../src/components/Screen', () => ({ Screen: ({ children }: React.PropsWithChildren) => <>{children}</> }));

let client: QueryClient;
function wrap(children: React.ReactNode) { return <QueryClientProvider client={client}>{children}</QueryClientProvider>; }
beforeEach(() => {
  jest.clearAllMocks(); mockFocused = true; mockParams = {};
  Object.values(api).forEach(method => (method as jest.Mock).mockReset());
  jest.mocked(api.assignment).mockResolvedValue(null);
  jest.mocked(api.eligibleMarshals).mockResolvedValue([]);
  client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity }, mutations: { retry: false } } });
  mockAuth = { propertyId: 1, online: true, selectProperty: jest.fn(), state: { profile: { id: 1, name: 'Test owner', email: 'owner@example.test', properties: [
    { id: 1, name: 'North', role: 'owner' }, { id: 2, name: 'South', role: 'reporter' }, { id: 3, name: 'Marshal site', role: 'marshal' },
  ] } } };
});
afterEach(() => { cleanup(); client.clear(); });

it('lets an owner confirm a marshal offer and displays the pending assignment', async () => {
  jest.mocked(api.eligibleMarshals).mockResolvedValue([{ id: 4, user_id: 7, name: 'SecurePulse Marshal', service_area: null, capacity: 1 }, { id: 5, user_id: 8, name: 'Second Marshal', service_area: null, capacity: 1 }]);
  jest.mocked(api.assignMarshals).mockImplementation(async () => {
    jest.mocked(api.assignment).mockResolvedValue({ id: 8, marshal_profile_id: 4, status: 'OFFERED', version: 1, expires_at: new Date().toISOString() });
    return [{ id: 8, status: 'OFFERED' }];
  });
  const confirm = jest.spyOn(Alert, 'alert').mockImplementation(() => {});
  const view = await render(wrap(<AssignMarshal propertyId={1} source="reporter" incidentId={9} status="RECEIVED" />));
  await waitFor(() => expect(view.getByText('Assign marshal')).toBeTruthy());
  await fireEvent.press(view.getByText('Assign marshal'));
  await waitFor(() => expect(view.getByLabelText('Select SecurePulse Marshal')).toBeEnabled());
  await fireEvent.press(view.getByLabelText('Select SecurePulse Marshal'));
  await fireEvent.press(view.getByLabelText('Select Second Marshal'));
  await waitFor(() => expect(view.getByText('Send to 2 marshals')).toBeEnabled());
  await fireEvent.press(view.getByText('Send to 2 marshals'));
  expect(confirm).toHaveBeenCalled();
  expect(api.assignMarshals).not.toHaveBeenCalled();
  await act(async () => { confirm.mock.calls[0]?.[2]?.find(button => button.text === 'Assign')?.onPress?.(); });
  await waitFor(() => expect(api.assignMarshals).toHaveBeenCalledWith(1, 'reporter', 9, [4, 5], expect.any(String)));
  await waitFor(() => expect(view.getByText(/Waiting for the marshal to accept/)).toBeTruthy());
  expect(view.queryByText('Assign marshal')).toBeNull();
  confirm.mockRestore();
});

it('does not expose assignment controls to a reporter', async () => {
  mockAuth.state.profile.properties[0].role = 'reporter';
  const view = await render(wrap(<AssignMarshal propertyId={1} source="reporter" incidentId={9} status="RECEIVED" />));
  expect(view.queryByText('Assign marshal')).toBeNull();
  expect(api.assignment).not.toHaveBeenCalled();
});

it('saves the profile, selects an allowed property, validates password confirmation and signs out', async () => {
  jest.mocked(api.updateProfile).mockResolvedValue({} as any);
  jest.mocked(api.changePassword).mockResolvedValue(undefined as any);
  const view = await render(wrap(<ProfileScreen />));
  await fireEvent.changeText(view.getByLabelText('Profile name'), ' Updated owner ');
  await fireEvent.press(view.getByText('Save name'));
  await waitFor(() => expect(session.refreshProfile).toHaveBeenCalledTimes(1));
  expect(api.updateProfile).toHaveBeenCalledWith('Updated owner');
  await fireEvent.press(view.getByText('Select property'));
  expect(mockAuth.selectProperty).toHaveBeenCalledWith(2);
  expect(view.getByText('Selected property')).toBeDisabled();
  await fireEvent.changeText(view.getByLabelText('Current password'), 'Old-password123');
  await fireEvent.changeText(view.getByLabelText('New password'), 'New-password123');
  await fireEvent.changeText(view.getByLabelText('Confirm new password'), 'different');
  await fireEvent.press(view.getByRole('button', { name: 'Change password' }));
  expect(api.changePassword).not.toHaveBeenCalled();
  expect(view.getByText('New passwords do not match.')).toBeTruthy();
  await fireEvent.changeText(view.getByLabelText('Confirm new password'), 'New-password123');
  await fireEvent.press(view.getByRole('button', { name: 'Change password' }));
  await waitFor(() => expect(session.passwordChanged).toHaveBeenCalledTimes(1));
  await fireEvent.press(view.getByText('Sign out'));
  expect(session.logout).toHaveBeenCalledTimes(1);
});

it('validates reports, handles denied location and removes optional evidence before submitting', async () => {
  jest.mocked(Location.requestForegroundPermissionsAsync).mockResolvedValue({ status: 'denied' } as any);
  jest.mocked(ImagePicker.launchImageLibraryAsync).mockResolvedValue({ canceled: false, assets: [{ uri: 'file:///image.jpg', fileName: 'image.jpg', mimeType: 'image/jpeg' }] } as any);
  jest.mocked(api.createIncident).mockResolvedValue({ id: 12 } as any);
  const view = await render(wrap(<ReportScreen />));
  await fireEvent.press(view.getByText('Confirm and submit report'));
  expect(api.createIncident).not.toHaveBeenCalled();
  await fireEvent.press(view.getByText('Use current location'));
  await waitFor(() => expect(view.getByText('Location permission was denied. Enter the incident address instead.')).toBeTruthy());
  await fireEvent.press(view.getByText('Choose photo or video'));
  await waitFor(() => expect(view.getByText('Attached: image.jpg')).toBeTruthy());
  await fireEvent.press(view.getByText('Remove attachment'));
  expect(view.queryByText('Attached: image.jpg')).toBeNull();
  await fireEvent.press(view.getByText('Theft'));
  await fireEvent.changeText(view.getByLabelText('Incident address'), ' 11 North Street ');
  await fireEvent.changeText(view.getByLabelText('Incident description'), ' Missing package ');
  await fireEvent.press(view.getByText('Confirm and submit report'));
  await waitFor(() => expect(router.replace).toHaveBeenCalledWith({ pathname: '/incidents/[id]', params: { id: '12' } }));
  expect(api.createIncident).toHaveBeenCalledWith(expect.objectContaining({ property_id: 1, incident_type: 'THEFT', address: '11 North Street', description: 'Missing package' }), expect.any(String), expect.any(AbortSignal));
  expect(api.uploadIncidentEvidence).not.toHaveBeenCalled();
});

it('blocks submission until an evidence picker finishes', async () => {
  let finish!: (result: any) => void;
  jest.mocked(ImagePicker.launchImageLibraryAsync).mockImplementation(() => new Promise(resolve => { finish = resolve; }));
  const view = await render(wrap(<ReportScreen />));
  await fireEvent.changeText(view.getByLabelText('Incident address'), '11 North Street');
  await fireEvent.press(view.getByText('Choose photo or video'));
  expect(view.getByText('Please wait…')).toBeDisabled();
  await fireEvent.press(view.getByText('Please wait…'));
  expect(api.createIncident).not.toHaveBeenCalled();
  await act(async () => finish({ canceled: true, assets: null }));
  expect(view.getByText('Confirm and submit report')).toBeEnabled();
});

it('retries notification preferences, handles denied push permissions and retries receipt status', async () => {
  jest.mocked(api.notificationPreferences).mockRejectedValueOnce(new Error('Offline')).mockResolvedValue([]);
  jest.mocked(registerPush).mockRejectedValueOnce(new Error('Notification permission denied.')).mockResolvedValue(undefined as any);
  jest.mocked(api.updateNotificationPreference).mockResolvedValue({ category: 'SECURITY_ALERTS', enabled: true } as any);
  jest.mocked(api.testNotification).mockResolvedValue({ id: 7, status: 'PENDING', message: 'Queued.' });
  jest.mocked(api.notificationTestStatus).mockRejectedValueOnce(new Error('Offline')).mockResolvedValue({ id: 7, status: 'SENT', message: 'Provider hand-off confirmed.' });
  const view = await render(wrap(<SettingsScreen />));
  await waitFor(() => expect(view.getByText('Retry notification preferences')).toBeTruthy());
  await fireEvent.press(view.getByText('Retry notification preferences'));
  const toggle = view.getByLabelText('Security alerts notification preference');
  await waitFor(() => expect(toggle).toBeEnabled());
  await fireEvent(toggle, 'valueChange', true);
  await waitFor(() => expect(view.getByText('Notification permission denied.')).toBeTruthy());
  expect(api.updateNotificationPreference).not.toHaveBeenCalled();
  await fireEvent(toggle, 'valueChange', true);
  await waitFor(() => expect(api.updateNotificationPreference).toHaveBeenCalledWith('SECURITY_ALERTS', true));
  await waitFor(() => expect(view.getByText('Send test notification')).toBeEnabled());
  await fireEvent.press(view.getByText('Send test notification'));
  await waitFor(() => expect(view.getByText('Retry notification status')).toBeTruthy());
  await fireEvent.press(view.getByText('Retry notification status'));
  await waitFor(() => expect(view.getByText('Test status: SENT. Provider hand-off confirmed.')).toBeTruthy());
});

it('starts, stops and releases live video on screen blur, including a late access response', async () => {
  const grant = { url: '/live?grant=fixture', expires_at: new Date(Date.now() + 300000).toISOString() };
  jest.mocked(api.liveCamera).mockResolvedValue(grant);
  const view = await render(wrap(<LiveCamera propertyId={1} cameraId={2} enabled />));
  await fireEvent.press(view.getByText('Start live video'));
  await waitFor(() => expect(view.getByLabelText('Live camera video')).toBeTruthy());
  await fireEvent.press(view.getByText('Stop live video'));
  expect(view.queryByLabelText('Live camera video')).toBeNull();
  let finish!: (result: any) => void;
  jest.mocked(api.liveCamera).mockImplementation(() => new Promise(resolve => { finish = resolve; }));
  await fireEvent.press(view.getByText('Start live video'));
  mockFocused = false;
  await view.rerender(wrap(<LiveCamera propertyId={1} cameraId={2} enabled />));
  await act(async () => finish(grant));
  expect(view.queryByLabelText('Live camera video')).toBeNull();
  expect(view.getByText('Start live video')).toBeDisabled();
  mockFocused = true;
  jest.mocked(api.liveCamera).mockResolvedValue(grant);
  await view.rerender(wrap(<LiveCamera propertyId={1} cameraId={2} enabled />));
  await fireEvent.press(view.getByText('Start live video'));
  await waitFor(() => expect(view.getByLabelText('Live camera video')).toBeTruthy());
  await view.rerender(wrap(<LiveCamera propertyId={1} cameraId={2} enabled={false} />));
  expect(view.queryByLabelText('Live camera video')).toBeNull();
});

it('switches overview queries by property and connects all home navigation controls', async () => {
  let finishNorth!: (result: any) => void;
  jest.mocked(api.summary).mockImplementation(property => property === 1 ? new Promise(resolve => { finishNorth = resolve; })
    : Promise.resolve({ camera_count: 2, connected_camera_count: 2, active_alert_count: 0, active_incident_count: 0, security_status: 'no_active_incidents' } as any));
  jest.mocked(api.events).mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 } as any);
  jest.mocked(api.cameras).mockResolvedValue([]);
  const view = await render(wrap(<HomeScreen />));
  await waitFor(() => expect(api.summary).toHaveBeenCalled());
  mockAuth.propertyId = 2;
  await view.rerender(wrap(<HomeScreen />));
  await waitFor(() => expect(view.getByText(/No active incident records/)).toBeTruthy());
  await act(async () => finishNorth({ camera_count: 99, active_alert_count: 99, security_status: 'attention_required' }));
  expect(view.queryByText('99')).toBeNull();
  expect(view.getByText('South')).toBeTruthy();
  for (const [label, path] of [['Report incident', '/report'], ['Alerts', '/alerts'], ['My incident reports', '/incidents'], ['Cameras', '/cameras'], ['Profile and properties', '/profile'], ['Settings', '/settings']]) {
    await fireEvent.press(view.getByText(label!)); expect(router.push).toHaveBeenLastCalledWith(path);
  }
  const calls = jest.mocked(api.summary).mock.calls.length;
  await fireEvent.press(view.getByText('Refresh overview'));
  await waitFor(() => expect(jest.mocked(api.summary).mock.calls.length).toBeGreaterThan(calls));
});

it.each([['Confirm threat', 'CONFIRMED'], ['Dismiss as false alarm', 'FALSE_ALARM']] as const)('reviews an alert using %s and refreshes property data', async (label, decision) => {
  mockParams = { id: '1' };
  const event = { id: 1, camera_id: 1, event_type: 'INTRUSION', timestamp: new Date().toISOString(), severity: 'HIGH', status: 'OPEN', reason: null, zone: null, alert_id: 1, alert_status: 'ACTIVE' };
  jest.mocked(api.event).mockImplementation(async () => ({ ...event } as any));
  jest.mocked(api.cameras).mockResolvedValue([]);
  jest.mocked(api.reviewEvent).mockImplementation(async () => { event.alert_status = decision; return {} as any; });
  client.setQueryData(['summary', 1, 1], { active_alert_count: 1 });
  const view = await render(wrap(<AlertDetailScreen />));
  await waitFor(() => expect(view.getByText(label)).toBeTruthy());
  await fireEvent.press(view.getByText(label));
  await waitFor(() => expect(view.getByText(`Alert review status: ${decision}.`)).toBeTruthy());
  expect(api.reviewEvent).toHaveBeenCalledWith(1, 1, decision);
  expect(client.getQueryState(['summary', 1, 1])?.isInvalidated).toBe(true);
  await fireEvent.press(view.getByText('Report incident'));
  expect(router.push).toHaveBeenCalledWith({ pathname: '/report', params: { eventId: 1 } });
});

it('filters incident history, loads the next page and opens the chosen report', async () => {
  jest.mocked(api.incidents).mockImplementation(async (page, filters) => ({ items: [{ id: page, incident_type: 'THEFT', status: filters?.status ?? 'RECEIVED' }], total: 2, page, page_size: 1 } as any));
  const view = await render(wrap(<IncidentHistoryScreen />));
  await waitFor(() => expect(view.getByLabelText('Open incident 1')).toBeTruthy());
  await fireEvent.press(view.getByText('Load more'));
  await waitFor(() => expect(view.getByLabelText('Open incident 2')).toBeTruthy());
  expect(view.queryByText('Load more')).toBeNull();
  await fireEvent.press(view.getByLabelText('Open incident 2'));
  expect(router.push).toHaveBeenCalledWith({ pathname: '/incidents/[id]', params: { id: 2 } });
  await fireEvent.press(view.getByText('With active assignment'));
  await waitFor(() => expect(api.incidents).toHaveBeenLastCalledWith(1, { has_active_assignment: 'true' }, expect.any(AbortSignal)));
  await fireEvent.press(view.getByText('RESOLVED', { exact: true }));
  await waitFor(() => expect(api.incidents).toHaveBeenLastCalledWith(1, { status: 'RESOLVED' }, expect.any(AbortSignal)));
});

it('opens evidence, shows a failed preview and requests fresh access on retry', async () => {
  mockParams = { id: '9' }; mockAuth.state.token = { access_token: 'test-session-token' };
  jest.mocked(api.incident).mockResolvedValue({ id: 9, status: 'RECEIVED', incident_type: 'THEFT', address: '11 North Street', created_at: new Date().toISOString(), timeline: [], dispatch: null,
    evidence: [{ id: 10, original_filename: 'snapshot.jpg', media_type: 'image/jpeg', byte_size: 1024 }] } as any);
  jest.mocked(api.reporterEvidenceAccess).mockResolvedValue({ url: '/evidence/10?grant=fixture', expires_at: new Date(Date.now() + 300000).toISOString() } as any);
  const view = await render(wrap(<IncidentDetailScreen />));
  await waitFor(() => expect(view.getByText('View image')).toBeTruthy());
  await fireEvent.press(view.getByText('View image'));
  await waitFor(() => expect(view.getByLabelText('snapshot.jpg')).toBeTruthy());
  await fireEvent(view.getByLabelText('snapshot.jpg'), 'error');
  expect(view.queryByLabelText('snapshot.jpg')).toBeNull();
  expect(view.getByText('Evidence access expired or the file is unavailable. Request the preview again.')).toBeTruthy();
  await fireEvent.press(view.getByText('View image'));
  await waitFor(() => expect(api.reporterEvidenceAccess).toHaveBeenCalledTimes(2));
  expect(api.reporterEvidenceAccess).toHaveBeenLastCalledWith(9, 10);
});
