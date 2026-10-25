import type { Camera, PersonTrack, SecurityAlert, SecurityEvent } from './types';

export interface ApiCamera {
  id: number; property_id: number; name: string; frigate_camera_name: string;
  location: string | null; enabled: boolean; health_status: string | null;
  health_observed_at: string | null;
}
export interface ApiEvent {
  id: number; property_id: number; camera_id: number; event_type: string;
  object_type: string; confidence: number; timestamp: string; severity: string;
  status: string; reason: string | null; zone: string | null;
  frigate_event_id: string | null; created_at: string | null; metadata: Record<string, unknown>;
}
interface EventPage { items: ApiEvent[]; total: number }
export interface ApiTrack {
  track_id: string; camera_id: string; object_type: 'person'; first_seen: string;
  last_seen: string; bounding_box: PersonTrack['boundingBox']; confidence: number;
  frame_width: number; frame_height: number; state: PersonTrack['state']; face_visible: boolean | null;
}
export interface Property { id: number; name: string; active: boolean }
export interface HistoryEntry {
  id: number; previous_status: string | null; new_status: string; actor_subject: string;
  reason: string | null; correlation_id: string; occurred_at: string;
}
export interface Evidence { id: number; type: string; timestamp: string }
export interface DashboardData {
  cameras: Camera[]; events: SecurityEvent[]; alerts: SecurityAlert[];
  tracksByCamera: Record<string, PersonTrack[]>; properties: Property[];
  session: { subject: string; scopes: string[]; property_ids: number[] | null };
}
export class ApiError extends Error {
  status: number;
  constructor(status: number) { super(`Backend request failed (${status})`); this.status = status; }
}
export const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL ?? '/api/v1').replace(/\/$/, '');
let accessToken = ''; // memory only: never build-time env, localStorage, or URL
export function setAccessToken(token: string) { accessToken = token; }
export function socketProtocols(): string[] { return accessToken ? ['securepulse.v1', `bearer.${accessToken}`] : ['securepulse.v1']; }
export function socketUrl(): string {
  const url = new URL(import.meta.env.VITE_WS_URL ?? `${apiBaseUrl}/events/stream`, window.location.href);
  url.protocol = url.protocol === 'https:' || url.protocol === 'wss:' ? 'wss:' : 'ws:';
  return url.href;
}
export async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers);
  if (accessToken) headers.set('Authorization', `Bearer ${accessToken}`);
  const response = await fetch(`${apiBaseUrl}${path}`, {
    ...init, headers, cache: 'no-store', signal: init.signal ?? AbortSignal.timeout(15000),
  });
  if (!response.ok) throw new ApiError(response.status);
  return response;
}
export async function get<T>(path: string, signal?: AbortSignal): Promise<T> {
  return (await apiFetch(path, { signal })).json() as Promise<T>;
}
export function mapTrack(t: ApiTrack): PersonTrack {
  return { trackId: t.track_id, cameraId: String(t.camera_id), objectType: t.object_type,
    firstSeen: t.first_seen, lastSeen: t.last_seen, boundingBox: t.bounding_box,
    confidence: t.confidence, frameWidth: t.frame_width, frameHeight: t.frame_height,
    state: t.state, faceVisible: t.face_visible };
}
export function mapCamera(c: ApiCamera): Camera {
  const fresh = c.health_observed_at && Date.now() - Date.parse(c.health_observed_at) < 90000;
  const status = c.health_status?.toLowerCase();
  const health = !c.enabled ? 'offline' : !fresh ? 'unknown'
    : status === 'online' || status === 'healthy' ? 'healthy'
    : status === 'offline' ? 'offline' : status === 'degraded' ? 'degraded' : 'unknown';
  return { id: String(c.id), propertyId: c.property_id, name: c.name, location: c.location,
    frigateCameraName: c.frigate_camera_name, status: c.enabled ? 'enabled' : 'disabled',
    lastSeen: c.health_observed_at ?? '', health };
}
export function mapEvent(e: ApiEvent): SecurityEvent {
  return { id: String(e.id), propertyId: e.property_id, cameraId: String(e.camera_id),
    type: e.event_type, objectType: e.object_type, timestamp: e.timestamp,
    confidence: e.confidence, severity: e.severity, status: e.status, metadata: e.metadata,
    reason: e.reason, zone: e.zone, sourceId: e.frigate_event_id, createdAt: e.created_at };
}
export function isActive(e: SecurityEvent) { return ['OPEN', 'ACKNOWLEDGED'].includes(e.status?.toUpperCase() ?? ''); }
export function mapAlert(e: SecurityEvent): SecurityAlert {
  return { id: e.id, cameraId: e.cameraId, type: e.type, timestamp: e.timestamp,
    severity: e.severity?.toUpperCase() === 'CRITICAL' ? 'critical' : 'warning',
    status: e.status?.toUpperCase() === 'ACKNOWLEDGED' ? 'acknowledged' : 'active' };
}
export function alertsFrom(events: SecurityEvent[]) {
  return events.filter(e => isActive(e) && ['HIGH', 'CRITICAL'].includes(e.severity?.toUpperCase() ?? '')).map(mapAlert);
}
export async function fetchDashboardData(signal?: AbortSignal): Promise<DashboardData> {
  const [properties, session, apiTracks] = await Promise.all([
    get<Property[]>('/properties', signal), get<DashboardData['session']>('/dashboard/session', signal),
    get<Record<string, ApiTrack[]>>('/tracks', signal),
  ]);
  const cameras: Camera[] = [], events: SecurityEvent[] = [];
  for (let page = 1; ; page++) {
    if (page > 100) throw new Error('Camera pagination limit reached; narrow backend access');
    const batch = await get<ApiCamera[]>(`/cameras?page=${page}&page_size=100`, signal);
    cameras.push(...batch.map(mapCamera));
    if (batch.length < 100) break;
  }
  for (let page = 1; ; page++) {
    if (page > 100) throw new Error('Incident pagination limit reached; aggregate endpoint required');
    const batch = await get<EventPage>(`/incidents?page=${page}&page_size=100`, signal);
    events.push(...batch.items.map(mapEvent));
    if (events.length >= batch.total) break;
    if (!batch.items.length) throw new Error('Incident pagination changed; retry');
  }
  const uniqueEvents = [...new Map(events.map(e => [e.id, e])).values()];
  return { cameras, events: uniqueEvents, alerts: alertsFrom(uniqueEvents), properties, session,
    tracksByCamera: Object.fromEntries(Object.entries(apiTracks).map(([id, t]) => [id, t.map(mapTrack)])) };
}
export async function readiness(signal?: AbortSignal): Promise<{ status: string; checks: Record<string, string> }> {
  const url = new URL(apiBaseUrl, window.location.href);
  url.pathname = '/health/ready';
  const response = await fetch(url, { signal: signal ?? AbortSignal.timeout(10000), cache: 'no-store' });
  if (response.status !== 503 && !response.ok) throw new ApiError(response.status);
  return response.json();
}
export async function evidenceBlob(id: number): Promise<{ url: string; type: string }> {
  const grant = await (await apiFetch(`/evidence/${id}/access`, { method: 'POST' })).json() as { url: string };
  const url = new URL(grant.url, new URL(apiBaseUrl, window.location.href));
  if (url.pathname !== `/api/v1/evidence/${id}/content`) throw new Error('Invalid evidence grant');
  const response = await apiFetch(`/evidence/${id}/content${url.search}`);
  const blob = await response.blob();
  return { url: URL.createObjectURL(blob), type: blob.type };
}
