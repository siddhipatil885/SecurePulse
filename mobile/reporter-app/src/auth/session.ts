import { z } from 'zod';
import { type Api, ApiError, normalizeError } from '../api/client';
import { tokenSchema, type Profile, type Token } from '../api/types';

export interface SecureStorage { get(): Promise<string | null>; set(value: string): Promise<void>; remove(): Promise<void> }
export interface SessionState { loading: boolean; profile: Profile | null; token: Token | null; message: string | null }
const storedSchema = z.object({ server: z.string(), token: tokenSchema });
export class SessionManager {
  private state: SessionState = { loading: true, profile: null, token: null, message: null };
  private listeners = new Set<() => void>();
  private generation = 0;
  private writes: Promise<void> = Promise.resolve();
  constructor(private api: Api, private storage: SecureStorage, private server: string | null, private clearQueries: () => void) {}
  snapshot = () => this.state;
  subscribe = (listener: () => void) => { this.listeners.add(listener); return () => { this.listeners.delete(listener); }; };
  private update(state: SessionState) { this.state = state; this.listeners.forEach(listener => listener()); }
  private write(operation: () => Promise<void>) { const next = this.writes.catch(() => {}).then(operation); this.writes = next; return next; }
  private clear(message: string | null = null) {
    this.generation++;
    this.update({ loading: false, profile: null, token: null, message });
    this.clearQueries();
    void this.write(() => this.storage.remove()).catch(() => {
      this.update({ ...this.state, message: 'Session ended, but secure storage could not be cleared. Restart and sign out again.' });
    });
  }
  invalidate = (token: string) => { if (this.state.token?.access_token === token) this.clear('Your session has expired. Please sign in again.'); };
  checkExpiry = () => { if (this.state.token && Date.parse(this.state.token.expires_at) <= Date.now()) this.invalidate(this.state.token.access_token); };
  restore = async () => {
    const generation = ++this.generation;
    this.update({ loading: true, profile: null, token: null, message: null });
    try {
      const raw = await this.storage.get();
      if (generation !== this.generation) return;
      if (!raw) { this.update({ loading: false, profile: null, token: null, message: null }); return; }
      const parsed = storedSchema.safeParse(JSON.parse(raw));
      if (!parsed.success || parsed.data.server !== this.server || Date.parse(parsed.data.token.expires_at) <= Date.now()) { this.clear('Please sign in again.'); return; }
      const { token } = parsed.data;
      const profile = await this.api.profile(token.access_token);
      if (generation === this.generation) {
        if (Date.parse(token.expires_at) <= Date.now()) this.clear('Please sign in again.');
        else this.update({ loading: false, profile, token, message: null });
      }
    } catch (error) {
      if (generation !== this.generation) return;
      if (error instanceof ApiError && error.code === 'NETWORK') this.update({ loading: false, profile: null, token: null, message: 'Connect to the server to restore your saved session.' });
      else this.clear('Unable to restore your session. Please sign in again.');
    }
  };
  login = async (email: string, password: string) => {
    const generation = ++this.generation;
    const token = await this.api.login(email, password);
    const profile = await this.api.profile(token.access_token);
    if (generation !== this.generation) return;
    if (Date.parse(token.expires_at) <= Date.now()) throw new ApiError('The server returned an expired session.');
    try { await this.write(() => this.storage.set(JSON.stringify({ server: this.server, token }))); }
    catch { throw new ApiError('Your session could not be stored securely. Please try again.'); }
    if (generation !== this.generation) return;
    this.clearQueries();
    this.update({ loading: false, token, profile, message: null });
  };
  logout = async () => {
    const token = this.state.token?.access_token;
    this.clear();
    if (token) {
      try { await this.api.logout(token); }
      catch (error) {
        if (!this.state.token) this.update({ ...this.state, message: 'Signed out on this device. Server revocation was not confirmed. ' + normalizeError(error).message });
      }
    }
  };
}
