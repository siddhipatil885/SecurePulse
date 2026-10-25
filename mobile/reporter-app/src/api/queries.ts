import { useInfiniteQuery, useQuery } from '@tanstack/react-query';
import { api, useAuth } from '../auth/AuthProvider';
import type { Camera, SecurityEvent } from './types';
export function useCameras() {
  const { propertyId, state } = useAuth();
  return useQuery({ queryKey: ['cameras', state.profile?.id, propertyId], enabled: propertyId !== null && !!state.profile,
    queryFn: ({ signal }) => api.cameras(propertyId!, signal) });
}
export function useEvents() {
  const { propertyId, state } = useAuth();
  return useInfiniteQuery({ queryKey: ['events', state.profile?.id, propertyId], enabled: propertyId !== null && !!state.profile,
    initialPageParam: 1, queryFn: ({ signal, pageParam }) => api.events(propertyId!, pageParam, signal),
    getNextPageParam: page => page.page * page.page_size < page.total ? page.page + 1 : undefined });
}
export function useSummary() {
  const { propertyId, state } = useAuth();
  return useQuery({ queryKey: ['summary', state.profile?.id, propertyId], enabled: propertyId !== null && !!state.profile,
    queryFn: ({ signal }) => api.summary(propertyId!, signal) });
}
export function useDetail(kind: 'camera' | 'event', id: number) {
  const { propertyId, state } = useAuth();
  return useQuery<Camera | SecurityEvent>({ queryKey: [kind, state.profile?.id, propertyId, id], enabled: propertyId !== null && !!state.profile && Number.isSafeInteger(id) && id > 0,
    queryFn: ({ signal }) => kind === 'camera' ? api.camera(propertyId!, id, signal) : api.event(propertyId!, id, signal) });
}
