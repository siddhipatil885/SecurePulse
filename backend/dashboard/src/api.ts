import type { Camera, PersonTrack, SecurityAlert, SecurityEvent } from './types';
import type { CaseOverview } from './cases';

interface ApiCamera {
  id: number;
  name: string;
  frigate_camera_name: string;
  location: string | null;
  enabled: boolean;
  created_at: string | null;
  updated_at: string | null;
  health_status?: string | null;
  health_observed_at?: string | null;
}

interface ApiEvent {
  id: number;
  property_id: number;
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
  overview: { total_incidents: number; active_incidents: number; critical_incidents: number };
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

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) { super(message); this.status = status; }
}

export const dashboardBase = `${apiBaseUrl}/dashboard`;
let sessionVersion = 0;
export function resetSessionRequests() { sessionVersion += 1; }

export async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const version = sessionVersion;
  const response = await fetch(`${dashboardBase}${path}`, {
    ...options, credentials: 'include',
    headers: { 'X-Dashboard-Request': '1', ...(options.body ? { 'Content-Type': 'application/json' } : {}), ...options.headers },
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    const message = data.error?.message ?? (Array.isArray(data.detail)
      ? data.detail.map((item: { msg: string }) => item.msg).join('. ') : 'Unable to complete this request. Please try again.');
    if (!options.signal?.aborted && version === sessionVersion && path.startsWith('/properties')) {
      if (response.status === 401) window.dispatchEvent(new Event('dashboard-session-expired'));
      if (response.status === 403) window.dispatchEvent(new Event('dashboard-access-changed'));
    }
    throw new ApiError(message, response.status);
  }
  return response.status === 204 ? undefined as T : response.json() as Promise<T>;
}

function mapCamera(camera: ApiCamera): Camera {
  return {
    id: String(camera.id),
    name: camera.name,
    frigateCameraName: camera.frigate_camera_name,
    status: camera.enabled ? 'enabled' : 'disabled',
    lastSeen: camera.updated_at ?? camera.created_at ?? '',
    healthStatus: camera.health_status ?? 'unknown',
  };
}

export function mapEvent(event: ApiEvent): SecurityEvent {
  return {
    id: String(event.id),
    propertyId: event.property_id,
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
    status: ['resolved', 'dismissed', 'closed'].includes(status ?? '') ? 'resolved' : status === 'acknowledged' ? 'acknowledged' : 'active',
  };
}

export async function fetchDashboardData(propertyId: number, signal?: AbortSignal, unified = false): Promise<DashboardData> {
  const base = `/properties/${propertyId}`;
  const [apiCameras, eventPage, apiTracks, cameraOverview, caseOverview] = await Promise.all([
    request<ApiCamera[]>(`${base}/cameras`, { signal }),
    request<EventPage>(`${base}/incidents`, { signal }),
    request<Record<string, ApiTrack[]>>(`${base}/tracks`, { signal }),
    request<DashboardData['overview']>(`${base}/overview`, { signal }),
    unified ? request<CaseOverview>(`${base}/cases/overview`, { signal }) : Promise.resolve(null),
  ]);
  const events = eventPage.items.map(mapEvent);
  const alerts = events
    .filter((event) => ['OPEN', 'ACKNOWLEDGED'].includes(event.status ?? ''))
    .filter((event) => ['high', 'critical'].includes(event.severity?.toLowerCase() ?? ''))
    .map(mapAlert);

  return {
    overview: caseOverview ? { total_incidents: caseOverview.total, active_incidents: caseOverview.active,
      critical_incidents: cameraOverview.critical_incidents } : cameraOverview,
    cameras: apiCameras.map(mapCamera),
    events,
    alerts,
    tracksByCamera: Object.fromEntries(
      Object.entries(apiTracks).map(([cameraId, tracks]) => [cameraId, tracks.map(mapTrack)]),
    ),
  };
}

export function frigateWebRtcUrl(propertyId: number, cameraId: string): string {
  return `${dashboardBase}/properties/${propertyId}/cameras/${encodeURIComponent(cameraId)}/webrtc`;
}

export interface PropertyAccess { id: number; name: string; address: string | null; role: 'owner' | 'dispatcher' | 'reporter' }
export interface Profile { id: number; name: string; email: string; properties: PropertyAccess[] }
export interface IncidentHistory { id: number; previous_status: string | null; new_status: string; actor_subject: string; reason: string; occurred_at: string }
export interface Evidence { id: number; type: string; timestamp: string }
export interface IncidentRecord extends ApiEvent { zone: string | null }
export type IncidentAction = 'acknowledge' | 'resolve' | 'dismiss' | 'reopen';

export function allowedActions(status: string): IncidentAction[] {
  if (status === 'OPEN') return ['acknowledge', 'resolve', 'dismiss'];
  if (status === 'ACKNOWLEDGED') return ['resolve', 'dismiss'];
  if (status === 'UNCLASSIFIED') return ['dismiss'];
  if (['RESOLVED', 'DISMISSED', 'CLOSED'].includes(status)) return ['reopen'];
  return [];
}
