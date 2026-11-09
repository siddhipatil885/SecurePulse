import axios, { type AxiosInstance } from 'axios';
import { z } from 'zod';
import { cameraSchema, eventPageSchema, eventSchema, incidentPageSchema, incidentSchema, notificationPreferenceSchema, profileSchema, summarySchema, tokenSchema } from './types';
import type { Profile } from './types';
import type { IncidentCreate } from './types';

export class ApiError extends Error {
  constructor(message: string, public readonly status?: number, public readonly code?: string) {
    super(message); this.name = 'ApiError';
  }
}
export function normalizeError(error: unknown): ApiError {
  if (error instanceof ApiError) return error;
  if (error instanceof z.ZodError) return new ApiError('The server returned an unexpected response. Please contact support.', undefined, 'INVALID_RESPONSE');
  if (axios.isAxiosError(error)) {
    const status = error.response?.status;
    const body = error.response?.data;
    if (status === 401) return new ApiError('Your credentials are invalid or your session has expired. Please sign in again.', status);
    if (status === 403) return new ApiError('You do not have permission to view this information.', status);
    if (status === 404) return new ApiError('This resource is unavailable. It may have been removed.', status);
    if (status === 422) return new ApiError('Check the information you entered and try again.', status);
    if (status && status >= 500) {
      if (['PUSH_NOT_CONFIGURED', 'RECOVERY_NOT_CONFIGURED', 'AUTH_CONFIGURATION_ERROR', 'AUTH_DELIVERY_UNAVAILABLE', 'LIVE_UNAVAILABLE'].includes(body?.error?.code) && typeof body?.error?.message === 'string') return new ApiError(body.error.message, status, body.error.code);
      return new ApiError('The service is unavailable. Please try again later.', status);
    }
    if (!error.response) return new ApiError(error.code === 'ECONNABORTED' ? 'The request timed out. Please retry.' : 'Unable to reach the server. Check your connection.', undefined, 'NETWORK');
    return new ApiError(typeof body?.error?.message === 'string' ? body.error.message : 'The request could not be completed.', status);
  }
  return new ApiError('Something went wrong. Please try again.');
}
export function createApi(baseUrl: string | null, getToken: () => string | null, onUnauthorized: (token: string) => void, transport?: AxiosInstance) {
  const http = transport ?? axios.create({ baseURL: baseUrl ? baseUrl + '/api/v1/' : undefined, timeout: 15_000, headers: { Accept: 'application/json' } });
  async function request<T>(path: string, schema: z.ZodType<T>, options: { body?: unknown; token?: string; public?: boolean; signal?: AbortSignal; params?: Record<string, number | string | undefined>; headers?: Record<string, string>; method?: 'GET' | 'POST' | 'PUT' | 'DELETE' } = {}): Promise<T> {
    if (!baseUrl) throw new ApiError('Configure EXPO_PUBLIC_SERVER_URL with your LAN or deployed server URL.', undefined, 'CONFIG');
    const token = options.public ? null : options.token ?? getToken();
    if (!options.public && !token) throw new ApiError('Please sign in to continue.', 401);
    try {
      const response = await http.request({ url: path, method: options.method ?? (options.body === undefined ? 'GET' : 'POST'), data: options.body, signal: options.signal, params: options.params, headers: { ...(token ? { Authorization: 'Bearer ' + token } : {}), ...options.headers } });
      return schema.parse(response.data);
    } catch (error) {
      if (axios.isCancel(error)) throw error;
      const normalized = normalizeError(error);
      if (normalized.status === 401 && token && !options.token) onUnauthorized(token);
      throw normalized;
    }
  }
  return {
    eligibleMarshals: (property: number) => request('dispatch/eligible-marshals', z.array(z.object({ id: z.number(), user_id: z.number(), name: z.string().nullable(), service_area: z.string().nullable(), capacity: z.number() })), { params: { property_id: property } }),
    assignment: (property: number, source: 'camera' | 'reporter', id: number) => request('dispatch/assignment', z.object({ id: z.number(), marshal_profile_id: z.number(), status: z.string(), version: z.number(), expires_at: z.string(), responder_location: z.object({ latitude: z.number(), longitude: z.number(), accuracy_m: z.number().nullable(), heading: z.number().nullable(), speed_mps: z.number().nullable(), updated_at: z.string(), distance_m: z.number().nullable().optional(), eta_seconds: z.number().nullable().optional(), eta_source: z.enum(['gps_speed', 'urban_fallback']).nullable().optional() }).nullable().optional() }).nullable(), { params: { property_id: property, [source === 'camera' ? 'incident_id' : 'reporter_incident_id']: id } }),
    reviewAssignment: (property: number, id: number, expected_version: number, approved: boolean, reason: string) => request('dispatch/offers/' + id + '/review', z.object({ id: z.number(), status: z.string(), version: z.number() }), { params: { property_id: property }, body: { expected_version, approved, reason } }),
    assignmentMessages: (property: number, assignmentId: number) => request(`dispatch/offers/${assignmentId}/messages`, z.object({ items: z.array(z.object({ id: z.number(), sender: z.string(), body: z.string(), created_at: z.string(), mine: z.boolean() })) }), { params: { property_id: property } }),
    sendAssignmentMessage: (property: number, assignmentId: number, body: string, client_message_id: string) => request(`dispatch/offers/${assignmentId}/messages`, z.object({ id: z.number(), body: z.string() }), { params: { property_id: property }, body: { body, client_message_id } }),
    assignmentLocationHistory: (property: number, assignmentId: number) => request('dispatch/assignment/location-history', z.object({ assignment_id: z.number(), retention_hours: z.number(), items: z.array(z.object({ latitude: z.number(), longitude: z.number(), accuracy_m: z.number().nullable(), heading: z.number().nullable(), speed_mps: z.number().nullable(), recorded_at: z.string() })) }), { params: { property_id: property, assignment_id: assignmentId } }),
    assignMarshal: (property: number, source: 'camera' | 'reporter', id: number, marshal: number, key: string) => request('dispatch/offers', z.object({ id: z.number(), status: z.string() }), { body: { property_id: property, [source === 'camera' ? 'incident_id' : 'reporter_incident_id']: id, marshal_profile_id: marshal, expires_in_seconds: 300, idempotency_key: key } }),
    assignMarshals: (property: number, source: 'camera' | 'reporter', id: number, marshals: number[], key: string) => request('dispatch/offers/broadcast', z.array(z.object({ id: z.number(), status: z.string() })), { body: { property_id: property, [source === 'camera' ? 'incident_id' : 'reporter_incident_id']: id, marshal_profile_ids: marshals, expires_in_seconds: 300, idempotency_key: key } }),
    assignTeamMarshals: (property: number, source: 'camera' | 'reporter', id: number, marshals: number[], key: string) => request('dispatch/offers/team', z.array(z.object({ id: z.number(), status: z.string(), team_key: z.string().nullable() })), { body: { property_id: property, [source === 'camera' ? 'incident_id' : 'reporter_incident_id']: id, marshal_profile_ids: marshals, expires_in_seconds: 300, idempotency_key: key } }),
    dispatchNearest: (property: number, incident: number, key: string) => request(`dispatch/reporter-incidents/${incident}/dispatch`, z.object({ status: z.enum(['OFFERED', 'ESCALATED']), reporter_incident_id: z.number(), assignment: z.object({ id: z.number(), status: z.string() }).nullable(), reason: z.string().nullable() }), { body: { property_id: property, expires_in_seconds: 300, correlation_id: key } }),
    requestRecovery: (email: string, purpose: 'password' | 'verification') => request('auth/recovery/request', z.object({ message: z.string() }), { public: true, body: { email, purpose } }),
    verifyEmail: (email: string, code: string) => request('auth/recovery/verify', z.object({ message: z.string() }), { public: true, body: { email, code } }),
    resetPassword: (email: string, code: string, new_password: string) => request('auth/recovery/reset', z.object({ message: z.string() }), { public: true, body: { email, code, new_password } }),
    liveCamera: (property: number, id: number) => request(`reporter/cameras/${id}/live/access`, z.object({ url: z.string(), expires_at: z.string(), expires_in_seconds: z.number().nonnegative() }), { method: 'POST', params: { property_id: property } }),
    login: (email: string, password: string) => request('auth/login', tokenSchema, { public: true, body: { email: email.trim().toLowerCase(), password } }),
    profile: (token?: string, signal?: AbortSignal) => request('auth/me', profileSchema, { token, signal }),
    updateProfile: (name: string) => request<Profile>('auth/profile', profileSchema, { method: 'PUT', body: { name } }),
    changePassword: (current_password: string, new_password: string) =>
      request('auth/password', z.unknown(), { body: { current_password, new_password } }),
    logout: (token: string) => request('auth/logout', z.unknown(), { token, body: {} }),
    cameras: (property: number, signal?: AbortSignal) => request('reporter/cameras', z.array(cameraSchema), { params: { property_id: property }, signal }),
    camera: (property: number, id: number, signal?: AbortSignal) => request('reporter/cameras/' + id, cameraSchema, { params: { property_id: property }, signal }),
    events: (property: number, page = 1, signal?: AbortSignal) => request('reporter/events', eventPageSchema, { params: { property_id: property, page, page_size: 20 }, signal }),
    event: (property: number, id: number, signal?: AbortSignal) => request('reporter/events/' + id, eventSchema, { params: { property_id: property }, signal }),
    reviewEvent: (property: number, id: number, decision: 'CONFIRMED' | 'FALSE_ALARM') =>
      request('reporter/events/' + id + '/review', eventSchema, { method: 'POST', params: { property_id: property }, body: { decision } }),
    summary: (property: number, signal?: AbortSignal) => request('reporter/summary', summarySchema, { params: { property_id: property }, signal }),
    incidents: (page = 1, filters: { status?: string; incident_type?: string; has_active_assignment?: 'true' } = {}, signal?: AbortSignal) =>
      request('reporter/incidents', incidentPageSchema, { params: { page, page_size: 20, include_details: 'false', ...filters }, signal }),
    incident: (id: number, signal?: AbortSignal) => request('reporter/incidents/' + id, incidentSchema, { signal }),
    reporterEvidenceAccess: (incidentId: number, evidenceId: number) =>
      request('reporter/incidents/' + incidentId + '/evidence/' + evidenceId + '/access',
        z.object({ url: z.string(), expires_at: z.string() }), { method: 'POST' }),
    createIncident: (body: IncidentCreate, idempotencyKey: string, signal?: AbortSignal) =>
      request('reporter/incidents', incidentSchema, { body, signal, headers: { 'X-Idempotency-Key': idempotencyKey } }),
    uploadIncidentEvidence: (id: number, asset: { uri: string; name: string; type: string; requestId?: string }, signal?: AbortSignal) => {
      const form = new FormData();
      form.append('file', { uri: asset.uri, name: asset.name, type: asset.type } as unknown as Blob);
      return request('reporter/incidents/' + id + '/evidence', incidentSchema, { body: form, signal,
        headers: asset.requestId ? { 'X-Idempotency-Key': asset.requestId } : undefined });
    },
    registerDevice: (body: { device_id: string; push_token: string; provider: 'expo' }) =>
      request('reporter/devices', z.unknown(), { body }),
    unregisterDevice: (deviceId: string) =>
      request('reporter/devices/' + encodeURIComponent(deviceId), z.unknown(), { method: 'DELETE' }),
    notificationPreferences: () =>
      request('reporter/notification-preferences', z.array(notificationPreferenceSchema)),
    testNotification: (property: number) => request('reporter/notifications/test', z.object({ id: z.number(), status: z.string(), message: z.string() }), { method: 'POST', params: { property_id: property } }),
    notificationTestStatus: (id: number) => request(`reporter/notifications/test/${id}`, z.object({ id: z.number(), status: z.string(), message: z.string() })),
    updateNotificationPreference: (category: string, enabled: boolean) =>
      request('reporter/notification-preferences', notificationPreferenceSchema, {
        method: 'PUT', body: { category, enabled }, headers: { 'Content-Type': 'application/json' },
      }),
  };
}
export type Api = ReturnType<typeof createApi>;
