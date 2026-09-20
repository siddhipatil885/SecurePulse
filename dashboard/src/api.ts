import type { Camera, SecurityAlert, SecurityEvent } from './types';

interface ApiCamera {
  id: number;
  name: string;
  location: string | null;
  enabled: boolean;
  created_at: string | null;
  updated_at: string | null;
}

interface ApiEvent {
  id: number;
  camera_id: number;
  event_type: string;
  object_type: string;
  confidence: number;
  timestamp: string;
  severity: string;
  status: string;
  reason: string | null;
  metadata: Record<string, unknown>;
}

interface EventPage {
  items: ApiEvent[];
}

export interface DashboardData {
  cameras: Camera[];
  events: SecurityEvent[];
  alerts: SecurityAlert[];
}

const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL ?? '/api/v1').replace(/\/$/, '');

async function get<T>(path: string): Promise<T> {
  const response = await fetch(`${apiBaseUrl}${path}`);
  if (!response.ok) {
    throw new Error(`API request failed: ${response.status} ${response.statusText}`);
  }
  return response.json() as Promise<T>;
}

function mapCamera(camera: ApiCamera): Camera {
  return {
    id: String(camera.id),
    name: camera.name,
    status: camera.enabled ? 'enabled' : 'disabled',
    lastSeen: camera.updated_at ?? camera.created_at ?? '',
  };
}

function mapEvent(event: ApiEvent): SecurityEvent {
  return {
    id: String(event.id),
    cameraId: String(event.camera_id),
    type: event.event_type,
    objectType: event.object_type,
    timestamp: event.timestamp,
    confidence: event.confidence,
    severity: event.severity,
    status: event.status,
    metadata: event.metadata,
  };
}

function mapAlert(event: SecurityEvent): SecurityAlert {
  const severity = event.severity?.toLowerCase();
  const status = event.status?.toLowerCase();
  return {
    id: event.id,
    cameraId: event.cameraId,
    severity: severity === 'critical' ? 'critical' : severity === 'high' ? 'warning' : 'info',
    type: event.type,
    timestamp: event.timestamp,
    status: status === 'resolved' ? 'resolved' : status === 'acknowledged' ? 'acknowledged' : 'active',
  };
}

export async function fetchDashboardData(): Promise<DashboardData> {
  const [apiCameras, eventPage] = await Promise.all([
    get<ApiCamera[]>('/cameras?enabled=true'),
    get<EventPage>('/events?page=1&page_size=100'),
  ]);
  const events = eventPage.items.map(mapEvent);
  const alerts = events
    .filter((event) => event.status?.toLowerCase() !== 'resolved')
    .filter((event) => ['high', 'critical'].includes(event.severity?.toLowerCase() ?? ''))
    .map(mapAlert);

  return {
    cameras: apiCameras.map(mapCamera),
    events,
    alerts,
  };
}