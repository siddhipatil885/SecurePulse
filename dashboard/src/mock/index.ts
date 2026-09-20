import type { Camera, SecurityEvent, SecurityAlert } from '../types';

export const mockCameras: Camera[] = [
  {
    id: 'CAM-01',
    name: 'Main Entrance',
    status: 'online',
    lastSeen: new Date().toISOString(),
    currentActivity: 'normal',
  },
  {
    id: 'CAM-02',
    name: 'Parking Perimeter',
    status: 'online',
    lastSeen: new Date().toISOString(),
    currentActivity: 'person',
  },
  {
    id: 'CAM-03',
    name: 'Lobby',
    status: 'online',
    lastSeen: new Date().toISOString(),
    currentActivity: 'normal',
  },
  {
    id: 'CAM-04',
    name: 'Server Room',
    status: 'online',
    lastSeen: new Date().toISOString(),
    currentActivity: 'restricted',
  },
  {
    id: 'CAM-05',
    name: 'Back Alley',
    status: 'offline',
    lastSeen: new Date(Date.now() - 3600000).toISOString(),
    currentActivity: 'normal',
  },
  {
    id: 'CAM-06',
    name: 'Loading Dock',
    status: 'online',
    lastSeen: new Date().toISOString(),
    currentActivity: 'suspicious',
  }
];

export const mockEvents: SecurityEvent[] = [
  {
    id: 'EVT-001',
    cameraId: 'CAM-03',
    type: 'Person Detected',
    timestamp: new Date(Date.now() - 120000).toISOString(), // 2 mins ago
    confidence: 0.94,
  },
  {
    id: 'EVT-002',
    cameraId: 'CAM-06',
    type: 'Camera Connected',
    timestamp: new Date(Date.now() - 300000).toISOString(), // 5 mins ago
  },
  {
    id: 'EVT-003',
    cameraId: 'CAM-04',
    type: 'Restricted Zone Entry',
    timestamp: new Date(Date.now() - 480000).toISOString(), // 8 mins ago
  },
  {
    id: 'EVT-004',
    cameraId: 'CAM-02',
    type: 'Person Detected',
    timestamp: new Date(Date.now() - 600000).toISOString(), // 10 mins ago
    confidence: 0.88,
  }
];

export const mockAlerts: SecurityAlert[] = [
  {
    id: 'ALT-001',
    cameraId: 'CAM-04',
    severity: 'critical',
    type: 'Restricted Zone Entry',
    timestamp: new Date(Date.now() - 480000).toISOString(),
    status: 'active'
  },
  {
    id: 'ALT-002',
    cameraId: 'CAM-02',
    severity: 'warning',
    type: 'Loitering Detected',
    timestamp: new Date(Date.now() - 600000).toISOString(),
    status: 'active'
  }
];

export const getPriorityCamera = (
  cameras: Camera[],
  _activeAlerts: SecurityAlert[],
  _recentEvents: SecurityEvent[]
): Camera | null => {
  // 1. Critical security alert -> mapped to 'critical' activity
  let priority = cameras.find(c => c.currentActivity === 'critical');
  if (priority) return priority;

  // 2. Restricted-zone activity -> 'restricted'
  priority = cameras.find(c => c.currentActivity === 'restricted');
  if (priority) return priority;

  // 3. Suspicious/unusual activity -> 'suspicious'
  priority = cameras.find(c => c.currentActivity === 'suspicious');
  if (priority) return priority;

  // 4. Person detection -> 'person'
  priority = cameras.find(c => c.currentActivity === 'person');
  if (priority) return priority;

  // 5. Normal activity
  priority = cameras.find(c => c.currentActivity === 'normal' && c.status === 'online');
  if (priority) return priority;

  // 6. Default to the first available camera
  return cameras[0] || null;
};
