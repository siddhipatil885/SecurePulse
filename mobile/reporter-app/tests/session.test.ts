import { describe, expect, it, vi } from 'vitest';
import { SessionManager, type SecureStorage } from '../src/auth/session';
import { ApiError, type Api } from '../src/api/client';
const profile = { id: 1, name: 'Test user', email: 'test@example.test', properties: [{ id: 1, name: 'Test property', role: 'owner' as const }] };
const token = () => ({ access_token: 'test-token', token_type: 'bearer' as const, expires_at: new Date(Date.now() + 60_000).toISOString() });
function fixture() {
  let stored: string | null = null;
  const storage: SecureStorage = { get: vi.fn(async () => stored), set: vi.fn(async value => { stored = value; }), remove: vi.fn(async () => { stored = null; }) };
  const api = { login: vi.fn(async () => token()), profile: vi.fn(async () => profile), logout: vi.fn(async () => {}) } as unknown as Api;
  const clear = vi.fn();
  const session = new SessionManager(api, storage, 'https://server.test', clear);
  return { session, api, storage, clear, stored: () => stored };
}
describe('secure session lifecycle', () => {
  it('does not authenticate an empty session', async () => {
    const { session, api } = fixture(); await session.restore();
    expect(session.snapshot()).toMatchObject({ loading: false, token: null, profile: null });
    expect(api.profile).not.toHaveBeenCalled();
  });
  it('validates profile before storing credentials and restores against server', async () => {
    const { session, storage, api } = fixture();
    await session.login('test@example.test', 'password');
    expect(session.snapshot().profile).toEqual(profile);
    expect(storage.set).toHaveBeenCalledOnce();
    const restored = new SessionManager(api, storage, 'https://server.test', vi.fn());
    await restored.restore();
    expect(restored.snapshot().profile).toEqual(profile);
    expect(api.profile).toHaveBeenCalledWith('test-token');
  });
  it('does not authenticate after failed login or profile validation', async () => {
    const { session, api, storage } = fixture();
    vi.mocked(api.profile).mockRejectedValue(new ApiError('denied', 403));
    await expect(session.login('test', 'wrong')).rejects.toThrow('denied');
    expect(session.snapshot().profile).toBeNull();
    expect(storage.set).not.toHaveBeenCalled();
  });
  it('requires successful secure storage before signing in', async () => {
    const { session, storage } = fixture(); vi.mocked(storage.set).mockRejectedValue(new Error('locked'));
    await expect(session.login('test', 'password')).rejects.toThrow('securely');
    expect(session.snapshot().profile).toBeNull();
  });
  it('rejects expired, malformed, and different-server saved credentials', async () => {
    for (const raw of ['bad json', JSON.stringify({ server: 'https://different.test', token: token() }), JSON.stringify({ server: 'https://server.test', token: { ...token(), expires_at: '2000-01-01T00:00:00Z' } })]) {
      const { session, storage, api } = fixture(); vi.mocked(storage.get).mockResolvedValue(raw);
      await session.restore();
      expect(session.snapshot().profile).toBeNull();
      expect(api.profile).not.toHaveBeenCalled();
    }
  });
  it('retains saved credentials offline but protects screens until server validation', async () => {
    const { session, api, storage } = fixture();
    await session.login('test', 'password');
    vi.mocked(api.profile).mockRejectedValue(new ApiError('offline', undefined, 'NETWORK'));
    const restored = new SessionManager(api, storage, 'https://server.test', vi.fn());
    await restored.restore();
    expect(restored.snapshot().profile).toBeNull();
    expect(restored.snapshot().message).toContain('restore');
    expect(storage.remove).not.toHaveBeenCalled();
  });
  it('expires sessions and clears private query cache', async () => {
    const { session, clear } = fixture(); await session.login('test', 'password');
    vi.useFakeTimers(); vi.setSystemTime(Date.now() + 120_000);
    session.checkExpiry();
    expect(session.snapshot().profile).toBeNull(); expect(clear).toHaveBeenCalledTimes(2);
    vi.useRealTimers();
  });
  it('logs out locally even if server revocation fails', async () => {
    const { session, api, storage } = fixture(); await session.login('test', 'password');
    vi.mocked(api.logout).mockRejectedValue(new ApiError('offline', undefined, 'NETWORK'));
    await session.logout();
    expect(session.snapshot().profile).toBeNull();
    expect(storage.remove).toHaveBeenCalled();
    expect(session.snapshot().message).toContain('revocation was not confirmed');
  });
  it('ignores a stale 401 from a previous session', async () => {
    const { session } = fixture(); await session.login('test', 'password');
    session.invalidate('old-token'); expect(session.snapshot().profile).toEqual(profile);
    session.invalidate('test-token'); expect(session.snapshot().profile).toBeNull();
  });
  it('cannot resurrect a session after logout while secure storage is pending', async () => {
    const { session, storage } = fixture();
    let finish!: () => void;
    vi.mocked(storage.set).mockImplementation(() => new Promise<void>(resolve => { finish = resolve; }));
    const login = session.login('test', 'password');
    await vi.waitFor(() => expect(finish).toBeTypeOf('function'));
    await session.logout(); finish(); await login;
    expect(session.snapshot().profile).toBeNull();
    await vi.waitFor(() => expect(storage.remove).toHaveBeenCalled());
  });
});
