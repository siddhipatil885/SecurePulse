import { useCallback, useEffect, useRef, useState } from 'react';
import { AppState, Text } from 'react-native';
import { useVideoPlayer, VideoView } from 'expo-video';
import { useIsFocused } from '@react-navigation/native';
import { api } from '../auth/AuthProvider';
import { serverUrl } from '../config';
import { PrimaryButton } from './PrimaryButton';
import { Notice, ui } from './Content';

function Player({ uri, failed }: { uri: string; failed: () => void }) {
  const player = useVideoPlayer({ uri, contentType: 'hls', useCaching: false }, player => player.play());
  useEffect(() => {
    const subscription = player.addListener('statusChange', event => { if (event.status === 'error') failed(); });
    return () => subscription.remove();
  }, [player, failed]);
  return <VideoView accessibilityLabel="Live camera video" player={player} nativeControls contentFit="contain" style={{ width: '100%', height: 250 }} />;
}

export function LiveCamera({ propertyId, cameraId, enabled }: { propertyId: number; cameraId: number; enabled: boolean }) {
  const focused = useIsFocused();
  const [grant, setGrant] = useState<{ url: string; expires_at: string; refreshAfterMs: number } | null>(null);
  const lastExpiry = useRef(0);
  const renewals = useRef(0);
  const [busy, setBusy] = useState(false); const [error, setError] = useState('');
  const generation = useRef(0);
  const stop = useCallback(() => { generation.current++; setGrant(null); setBusy(false); }, []);
  const start = useCallback(async (automatic = false) => {
    if (!enabled || !focused) return;
    const attempt = ++generation.current;
    setBusy(true); setError('');
    try {
      if (!automatic) { lastExpiry.current = 0; renewals.current = 0; }
      else if (++renewals.current > 12) throw new Error('Reopen live video to continue watching.');
      if (!serverUrl) throw new Error('Configure the camera host address first.');
      const requestedAt = performance.now();
      const next = await api.liveCamera(propertyId, cameraId);
      const remainingMs = next.expires_in_seconds * 1000 - (performance.now() - requestedAt);
      if (remainingMs <= 30000 || Date.parse(next.expires_at) <= lastExpiry.current) throw new Error('Live access cannot be extended. Sign in again and reopen the camera.');
      if (attempt === generation.current) {
        lastExpiry.current = Date.parse(next.expires_at);
        setGrant({ ...next, url: serverUrl + next.url, refreshAfterMs: remainingMs - 30000 });
      }
    } catch (error) { if (attempt === generation.current) { setGrant(null); setError(error instanceof Error ? error.message : 'Unable to open live video.'); } }
    finally { if (attempt === generation.current) setBusy(false); }
  }, [propertyId, cameraId, enabled, focused]);
  useEffect(() => { if (!enabled || !focused) stop(); }, [enabled, focused, stop]);
  useEffect(() => {
    const subscription = AppState.addEventListener('change', state => { if (state !== 'active') stop(); });
    return () => { generation.current++; subscription.remove(); };
  }, [stop]);
  useEffect(() => {
    if (!grant) return;
    const timer = setTimeout(() => { void start(true); }, grant.refreshAfterMs);
    return () => clearTimeout(timer);
  }, [grant, start]);
  const failed = useCallback(() => { stop(); setError('Live playback failed. Confirm the host is reachable and the camera supports H.264/H.265 HLS, then retry.'); }, [stop]);
  return <><Text style={ui.heading}>Live camera</Text>
    <Notice>Video streams from your camera host. It is not uploaded to Neon or saved by this player. The host must be online.</Notice>
    {grant && <Player key={grant.url} uri={grant.url} failed={failed} />}
    {error && <Text accessibilityRole="alert" style={ui.error}>{error}</Text>}
    <PrimaryButton label={busy ? 'Connecting…' : grant ? 'Reconnect live video' : 'Start live video'} disabled={!enabled || !focused || busy} onPress={() => void start()} />
    {grant && <PrimaryButton variant="secondary" label="Stop live video" onPress={stop} />}
  </>;
}
