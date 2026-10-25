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
});
