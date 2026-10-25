import axios, { type AxiosInstance } from 'axios';
import { z } from 'zod';
import { cameraSchema, eventPageSchema, eventSchema, profileSchema, summarySchema, tokenSchema } from './types';

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
    if (status && status >= 500) return new ApiError('The service is unavailable. Please try again later.', status);
    if (!error.response) return new ApiError(error.code === 'ECONNABORTED' ? 'The request timed out. Please retry.' : 'Unable to reach the server. Check your connection.', undefined, 'NETWORK');
    return new ApiError(typeof body?.error?.message === 'string' ? body.error.message : 'The request could not be completed.', status);
  }
  return new ApiError('Something went wrong. Please try again.');
}
export function createApi(baseUrl: string | null, getToken: () => string | null, onUnauthorized: (token: string) => void, transport?: AxiosInstance) {
  const http = transport ?? axios.create({ baseURL: baseUrl ? baseUrl + '/api/v1/' : undefined, timeout: 15_000, headers: { Accept: 'application/json' } });
  async function request<T>(path: string, schema: z.ZodType<T>, options: { body?: unknown; token?: string; public?: boolean; signal?: AbortSignal; params?: Record<string, number> } = {}): Promise<T> {
    if (!baseUrl) throw new ApiError('Configure EXPO_PUBLIC_SERVER_URL with your LAN or deployed server URL.', undefined, 'CONFIG');
    const token = options.public ? null : options.token ?? getToken();
    if (!options.public && !token) throw new ApiError('Please sign in to continue.', 401);
    try {
      const response = await http.request({ url: path, method: options.body === undefined ? 'GET' : 'POST', data: options.body, signal: options.signal, params: options.params, headers: token ? { Authorization: 'Bearer ' + token } : undefined });
      return schema.parse(response.data);
    } catch (error) {
      if (axios.isCancel(error)) throw error;
      const normalized = normalizeError(error);
      if (normalized.status === 401 && token && !options.token) onUnauthorized(token);
      throw normalized;
    }
  }
  return {
    login: (email: string, password: string) => request('auth/login', tokenSchema, { public: true, body: { email: email.trim().toLowerCase(), password } }),
    profile: (token?: string, signal?: AbortSignal) => request('auth/me', profileSchema, { token, signal }),
    logout: (token: string) => request('auth/logout', z.unknown(), { token, body: {} }),
    cameras: (property: number, signal?: AbortSignal) => request('reporter/cameras', z.array(cameraSchema), { params: { property_id: property }, signal }),
    camera: (property: number, id: number, signal?: AbortSignal) => request('reporter/cameras/' + id, cameraSchema, { params: { property_id: property }, signal }),
    events: (property: number, page = 1, signal?: AbortSignal) => request('reporter/events', eventPageSchema, { params: { property_id: property, page, page_size: 20 }, signal }),
    event: (property: number, id: number, signal?: AbortSignal) => request('reporter/events/' + id, eventSchema, { params: { property_id: property }, signal }),
    summary: (property: number, signal?: AbortSignal) => request('reporter/summary', summarySchema, { params: { property_id: property }, signal }),
  };
}
export type Api = ReturnType<typeof createApi>;
