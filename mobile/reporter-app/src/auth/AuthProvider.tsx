import { createContext, useContext, useEffect, useState, useSyncExternalStore, type PropsWithChildren } from 'react';
import { AppState, Platform } from 'react-native';
import * as SecureStore from 'expo-secure-store';
import { QueryClient, QueryClientProvider, focusManager, onlineManager } from '@tanstack/react-query';
import NetInfo from '@react-native-community/netinfo';
import { createApi, ApiError } from '../api/client';
import { serverUrl } from '../config';
import { SessionManager } from './session';

export const queryClient = new QueryClient({ defaultOptions: { queries: { staleTime: 30_000, gcTime: 300_000, retry: (count, error) => count < 1 && !(error instanceof ApiError && error.status && error.status < 500) }, mutations: { retry: false } } });
const storageKey = 'securepulse.reporter.session.v2';
const storage = {
  async get() { return Platform.OS === 'web' ? null : SecureStore.getItemAsync(storageKey); },
  async set(value: string) { if (Platform.OS === 'web') throw new Error('Native secure storage required'); await SecureStore.setItemAsync(storageKey, value, { keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY }); },
  async remove() { if (Platform.OS !== 'web') await SecureStore.deleteItemAsync(storageKey); },
};
export const api = createApi(serverUrl, () => session.snapshot().token?.access_token ?? null, token => session.invalidate(token));
export const session: SessionManager = new SessionManager(api, storage, serverUrl, () => { void queryClient.cancelQueries(); queryClient.clear(); });
const AuthContext = createContext<{ state: ReturnType<typeof session.snapshot>; propertyId: number | null; selectProperty: (id: number) => void; online: boolean } | null>(null);
export function AuthProvider({ children }: PropsWithChildren) {
  const state = useSyncExternalStore(session.subscribe, session.snapshot);
  const [selected, setSelected] = useState<number | null>(null);
  const [online, setOnline] = useState(true);
  const propertyId = state.profile?.properties.find(p => p.id === selected)?.id ?? state.profile?.properties[0]?.id ?? null;
  useEffect(() => { void session.restore(); }, []);
  useEffect(() => {
    if (!state.profile) setSelected(null);
    const timer = setInterval(session.checkExpiry, 1000);
    return () => clearInterval(timer);
  }, [state.profile]);
  useEffect(() => {
    const unsubscribe = NetInfo.addEventListener(info => {
      const connected = info.isConnected !== false && info.isInternetReachable !== false;
      setOnline(connected); onlineManager.setOnline(connected);
    });
    const listener = AppState.addEventListener('change', status => {
      session.checkExpiry(); focusManager.setFocused(status === 'active');
    });
    return () => { unsubscribe(); listener.remove(); };
  }, []);
  return <QueryClientProvider client={queryClient}><AuthContext.Provider value={{ state, propertyId, selectProperty: setSelected, online }}>{children}</AuthContext.Provider></QueryClientProvider>;
}
export function useAuth() { const auth = useContext(AuthContext); if (!auth) throw new Error('AuthProvider is required'); return auth; }
