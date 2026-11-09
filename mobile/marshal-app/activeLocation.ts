import * as Location from 'expo-location';
import * as SecureStore from 'expo-secure-store';
import * as TaskManager from 'expo-task-manager';
import Constants from 'expo-constants';

const TASK = 'securepulse-marshal-active-response-location';
const STATE_KEY = 'securepulse.marshal.active-location.v1';

type TrackingState = { origin: string; token: string; assignmentId: number };

TaskManager.defineTask(TASK, async ({ data, error }) => {
  if (error || !data) return;
  const locations = (data as { locations?: Location.LocationObject[] }).locations;
  const location = locations?.at(-1);
  if (!location) return;
  const stateText = await SecureStore.getItemAsync(STATE_KEY);
  if (!stateText) return;
  const state = JSON.parse(stateText) as TrackingState;
  const { latitude, longitude, accuracy, heading, speed } = location.coords;
  await fetch(`${state.origin}/api/v1/marshal/assignments/${state.assignmentId}/location`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${state.token}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({
      latitude, longitude, accuracy_m: accuracy,
      heading: heading !== null && heading >= 0 ? heading : null,
      speed_mps: speed !== null && speed >= 0 ? speed : null,
    }),
  }).catch(() => undefined);
});

export async function startActiveLocationTracking(state: TrackingState) {
  const foreground = await Location.requestForegroundPermissionsAsync();
  if (!foreground.granted) throw new Error('Allow location while using the app to share your position during an active response.');
  await SecureStore.setItemAsync(STATE_KEY, JSON.stringify(state));
  if (Constants.appOwnership === 'expo') {
    return { background: false };
  }
  const background = await Location.requestBackgroundPermissionsAsync();
  if (!background.granted) {
    if (await Location.hasStartedLocationUpdatesAsync(TASK)) await Location.stopLocationUpdatesAsync(TASK);
    return { background: false };
  }
  const options: Location.LocationTaskOptions = {
    accuracy: Location.Accuracy.Balanced,
    timeInterval: 15000,
    distanceInterval: 20,
    deferredUpdatesInterval: 15000,
    pausesUpdatesAutomatically: false,
    showsBackgroundLocationIndicator: true,
    foregroundService: {
      notificationTitle: 'SecurePulse response active',
      notificationBody: 'Sharing your live position with your dispatcher.',
      notificationColor: '#E65324',
      killServiceOnDestroy: false,
    },
  };
  if (await Location.hasStartedLocationUpdatesAsync(TASK)) await Location.stopLocationUpdatesAsync(TASK);
  await Location.startLocationUpdatesAsync(TASK, options);
  return { background: true };
}

export async function stopActiveLocationTracking() {
  if (await Location.hasStartedLocationUpdatesAsync(TASK)) await Location.stopLocationUpdatesAsync(TASK);
  await SecureStore.deleteItemAsync(STATE_KEY);
}
