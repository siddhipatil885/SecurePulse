import { useEffect, useRef, useState } from 'react';
import { Image, Pressable, Text, View } from 'react-native';
import { VideoView, useVideoPlayer } from 'expo-video';

export type Evidence = { id: number; name: string; media_type: string; source?: 'incident' | 'marshal' };
export function EvidencePhoto({ assignmentId, item, origin, token, request }: {
  assignmentId: number; item: Evidence; origin: string; token: string;
  request: (path: string, body?: unknown) => Promise<any>;
}) {
  const [url, setUrl] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  const [loading, setLoading] = useState(false);
  const currentRequest = useRef(request); currentRequest.current = request;
  const revision = useRef(0);
  const player = useVideoPlayer(url && item.media_type.startsWith('video/') ? { uri: url, headers: { Authorization: `Bearer ${token}` } } : null, instance => { instance.loop = false; });
  async function load() {
    const current = ++revision.current;
    setLoading(true); setFailed(false); setUrl(null);
    try {
      const query = item.source === 'marshal' ? '?source=marshal' : '';
      const grant = await currentRequest.current(`marshal/assignments/${assignmentId}/evidence/${item.id}/access${query}`, {});
      if (current !== revision.current) return;
      if (!grant.url.startsWith(`/api/v1/marshal/assignments/${assignmentId}/evidence/${item.id}/content?`)) throw new Error('Unexpected media address');
      setUrl(origin + grant.url);
    } catch { if (current === revision.current) setFailed(true); }
    finally { if (current === revision.current) setLoading(false); }
  }
  useEffect(() => { void load(); return () => { revision.current++; }; }, [assignmentId, item.id]);
  return <View style={{ gap: 12 }}><Text style={{ fontWeight: '700' }}>{item.name}</Text>
    {loading && <Text>Loading evidence…</Text>}
    {url && !failed && (item.media_type.startsWith('video/')
      ? <VideoView player={player} style={{ width: '100%', height: 250, borderRadius: 14 }} nativeControls contentFit="contain" />
      : <Image accessibilityLabel={item.name} source={{ uri: url, headers: { Authorization: `Bearer ${token}` } }} style={{ width: '100%', height: 250, borderRadius: 14 }} resizeMode="contain" onError={() => { setFailed(true); setUrl(null); }} />)}
    {failed && <><Text>This evidence is unavailable or its access has expired.</Text><Pressable accessibilityRole="button" onPress={() => void load()} style={{ padding: 14, backgroundColor: '#EDF2E8', borderRadius: 10 }}><Text>Retry evidence</Text></Pressable></>}
  </View>;
}
