import { describe, expect, it, vi } from 'vitest';
import axios, { AxiosError, AxiosHeaders, type AxiosResponse } from 'axios';
import { createApi, normalizeError } from '../src/api/client';
import { parseServerUrl } from '../src/config';
describe('API contract', () => {
  it('requires an explicit LAN or deployment URL without embedded credentials', () => {
    for (const url of [undefined, '', 'http://localhost:8000', 'http://127.0.0.1:8000', 'https://u:p@server.test', 'file:///tmp/file', 'https://server.test?token=secret']) expect(parseServerUrl(url)).toBeNull();
    expect(parseServerUrl('http://192.168.1.100:8000/')).toBe('http://192.168.1.100:8000');
    expect(parseServerUrl('https://server.test/')).toBe('https://server.test');
  });
  it('sends only the current token and a property scope, and validates responses', async () => {
    const http = axios.create();
    const request = vi.spyOn(http, 'request').mockResolvedValue({ data: [] });
    const api = createApi('https://server.test', () => 'current', vi.fn(), http);
    await api.cameras(42);
    expect(request).toHaveBeenCalledWith(expect.objectContaining({ url: 'reporter/cameras', params: { property_id: 42 }, headers: { Authorization: 'Bearer current' } }));
    request.mockResolvedValue({ data: [{ id: 1 }] });
    await expect(api.cameras(42)).rejects.toMatchObject({ code: 'INVALID_RESPONSE' });
  });
  it('does not request protected data when unauthenticated or unconfigured', async () => {
    const http = axios.create(); const spy = vi.spyOn(http, 'request');
    await expect(createApi(null, () => 'token', vi.fn(), http).cameras(1)).rejects.toMatchObject({ code: 'CONFIG' });
    await expect(createApi('https://server.test', () => null, vi.fn(), http).cameras(1)).rejects.toMatchObject({ status: 401 });
    expect(spy).not.toHaveBeenCalled();
  });
  it('invalidates on protected 401, but not on login failure or 403', async () => {
    const http = axios.create(); const unauthorized = vi.fn();
    const response = (status: number) => new AxiosError('failed', 'ERR_BAD_REQUEST', undefined, undefined, { status, data: { error: { message: 'denied' } }, headers: {}, config: { headers: new AxiosHeaders() }, statusText: '' } as AxiosResponse);
    const spy = vi.spyOn(http, 'request').mockRejectedValue(response(401));
    const api = createApi('https://server.test', () => 'current', unauthorized, http);
    await expect(api.cameras(1)).rejects.toMatchObject({ status: 401 }); expect(unauthorized).toHaveBeenCalledWith('current');
    unauthorized.mockClear();
    await expect(api.login('name', 'password')).rejects.toMatchObject({ status: 401 }); expect(unauthorized).not.toHaveBeenCalled();
    spy.mockRejectedValue(response(403));
    await expect(api.events(1)).rejects.toMatchObject({ status: 403 }); expect(unauthorized).not.toHaveBeenCalled();
  });
  it('classifies offline and timeout errors without leaking Axios config', () => {
    expect(normalizeError(new AxiosError('password=secret', 'ECONNABORTED')).message).toContain('timed out');
    expect(normalizeError(new AxiosError('password=secret', 'ERR_NETWORK'))).toMatchObject({ code: 'NETWORK' });
    expect(normalizeError(new Error('secret')).message).not.toContain('secret');
  });
  it('creates an idempotent reporter incident and uploads evidence with the bearer token', async () => {
    const http = axios.create();
    const request = vi.spyOn(http, 'request')
      .mockResolvedValueOnce({ data: {
        id: 8, property_id: 42, incident_type: 'THEFT', description: null, address: '1 Test Street',
        latitude: null, longitude: null, location_accuracy: null, status: 'RECEIVED',
        created_at: '2026-11-04T10:00:00Z', updated_at: '2026-11-04T10:00:00Z', evidence: [], timeline: [],
      } })
      .mockResolvedValueOnce({ data: {
        id: 8, property_id: 42, incident_type: 'THEFT', description: null, address: '1 Test Street',
        latitude: null, longitude: null, location_accuracy: null, status: 'RECEIVED',
        created_at: '2026-11-04T10:00:00Z', updated_at: '2026-11-04T10:00:00Z',
        evidence: [{ id: 2, media_type: 'image/jpeg', original_filename: 'photo.jpg', byte_size: 4, created_at: '2026-11-04T10:00:01Z' }],
        timeline: [],
      } });
    const api = createApi('https://server.test', () => 'current', vi.fn(), http);
    const incident = await api.createIncident({ property_id: 42, incident_type: 'THEFT', address: '1 Test Street' }, 'idempotency-key-123');
    expect(incident.id).toBe(8);
    await api.uploadIncidentEvidence(8, { uri: 'file:///photo.jpg', name: 'photo.jpg', type: 'image/jpeg' });
    expect(request).toHaveBeenNthCalledWith(1, expect.objectContaining({
      url: 'reporter/incidents', headers: expect.objectContaining({ Authorization: expect.any(String), 'X-Idempotency-Key': 'idempotency-key-123' }),
    }));
    expect(request).toHaveBeenNthCalledWith(2, expect.objectContaining({
      url: 'reporter/incidents/8/evidence', headers: expect.objectContaining({ Authorization: expect.any(String) }),
    }));
  });
  it('reads and updates all notification preference categories', async () => {
    const http = axios.create();
    const request = vi.spyOn(http, 'request')
      .mockResolvedValueOnce({ data: [{ category: 'SECURITY_ALERTS', enabled: true, updated_at: '2026-11-04T10:00:00Z' }] })
      .mockResolvedValueOnce({ data: { category: 'DISPATCH_UPDATES', enabled: false, updated_at: '2026-11-04T10:00:00Z' } });
    const api = createApi('https://server.test', () => 'current', vi.fn(), http);
    expect((await api.notificationPreferences()).at(0)?.enabled).toBe(true);
    expect((await api.updateNotificationPreference('DISPATCH_UPDATES', false)).enabled).toBe(false);
    expect(request).toHaveBeenLastCalledWith(expect.objectContaining({ method: 'PUT' }));
  });
});
