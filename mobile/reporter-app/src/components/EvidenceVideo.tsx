import { useEffect } from 'react';
import { useVideoPlayer, VideoView } from 'expo-video';

export function EvidenceVideo({ uri, token, onError }: { uri: string; token: string; onError: () => void }) {
  const player = useVideoPlayer({ uri, headers: { Authorization: `Bearer ${token}` }, useCaching: false });
  useEffect(() => {
    const listener = player.addListener('statusChange', event => { if (event.status === 'error') onError(); });
    return () => listener.remove();
  }, [player, onError]);
  return <VideoView player={player} nativeControls contentFit="contain" style={{ width: '100%', height: 240 }} />;
}
