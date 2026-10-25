import type { Camera, PersonTrack, SecurityAlert, SecurityEvent } from './types';

interface ApiCamera {
  id: number;
  name: string;
  frigate_camera_name: string;
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

interface ApiTrack {
  track_id: string;
  camera_id: string;
  object_type: 'person';
  first_seen: string;
  last_seen: string;
  bounding_box: PersonTrack['boundingBox'];
  confidence: number;
  frame_width: number;
  frame_height: number;
  state: PersonTrack['state'];
  face_visible: boolean | null;
}

export interface DashboardData {
  cameras: Camera[];
  events: SecurityEvent[];
  alerts: SecurityAlert[];
  tracksByCamera: Record<string, PersonTrack[]>;
}

export function mapTrack(track: ApiTrack): PersonTrack {
  return {
    trackId: track.track_id,
    cameraId: String(track.camera_id),
    objectType: track.object_type,
    firstSeen: track.first_seen,
    lastSeen: track.last_seen,
    boundingBox: track.bounding_box,
    confidence: track.confidence,
    frameWidth: track.frame_width,
    frameHeight: track.frame_height,
    state: track.state,
    faceVisible: track.face_visible,
  };
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
    frigateCameraName: camera.frigate_camera_name,
    status: camera.enabled ? 'enabled' : 'disabled',
    lastSeen: camera.updated_at ?? camera.created_at ?? '',
  };
}

export function mapEvent(event: ApiEvent): SecurityEvent {
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

export function mapAlert(event: SecurityEvent): SecurityAlert {
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
  const [apiCameras, eventPage, apiTracks] = await Promise.all([
    get<ApiCamera[]>('/cameras?enabled=true'),
    get<EventPage>('/events?page=1&page_size=100'),
    get<Record<string, ApiTrack[]>>('/tracks'),
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
    tracksByCamera: Object.fromEntries(
      Object.entries(apiTracks).map(([cameraId, tracks]) => [cameraId, tracks.map(mapTrack)]),
    ),
  };
}

export function frigateWebRtcUrl(cameraId: string): string {
  return `${apiBaseUrl}/frigate/cameras/${encodeURIComponent(cameraId)}/webrtc`;
}
