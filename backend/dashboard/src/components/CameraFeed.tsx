import { useCallback, useEffect, useRef, useState } from 'react';
import type { Camera, PersonTrack } from '../types';
import { apiFetch, ApiError } from '../api';
import './CameraFeed.css';

export default function CameraFeed({ camera, isPrimary, tracks }: { camera: Camera; isPrimary: boolean; tracks: PersonTrack[] }) {
  const [video, setVideo] = useState<HTMLVideoElement | null>(null);
  const [state, setState] = useState('connecting');
  const [retry, setRetry] = useState(0);
  const container = useRef<HTMLDivElement>(null);
  const videoRef = useCallback((element: HTMLVideoElement | null) => setVideo(element), []);
  const fit = import.meta.env.VITE_VIDEO_OBJECT_FIT === 'contain' ? 'contain' : 'cover';
  useEffect(() => {
    if (!video || camera.status === 'disabled') return;
    let disposed = false, attempts = 0;
    let peer: RTCPeerConnection | null = null;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let watchdog: ReturnType<typeof setTimeout> | undefined;
    const abort = new AbortController();
    function failed(message: string, terminal = false) {
      if (disposed) return;
      clearTimeout(watchdog); clearTimeout(timer);
      if (peer) { peer.onconnectionstatechange = null; peer.close(); peer = null; }
      video!.srcObject = null;
      setState(message);
      if (!terminal && ++attempts <= 3) timer = setTimeout(() => void start(), Math.min(15000, 1000 * 2 ** attempts));
    }
    async function start() {
      if (disposed) return;
      setState('connecting');
      const connection = new RTCPeerConnection();
      peer = connection;
      connection.addTransceiver('video', { direction: 'recvonly' });
      watchdog = setTimeout(() => failed('Camera offline; reconnecting'), 20000);
      connection.ontrack = event => {
        if (disposed) return;
        video!.srcObject = event.streams[0] ?? new MediaStream([event.track]);
        event.track.onended = () => failed('Camera offline; reconnecting');
      };
      connection.onconnectionstatechange = () => {
        if (['failed', 'disconnected'].includes(connection.connectionState)) failed('Camera offline; reconnecting');
      };
      try {
        const access = await (await apiFetch(`/frigate/cameras/${encodeURIComponent(camera.id)}/playback-access`, {
          method: 'POST', signal: AbortSignal.any([abort.signal, AbortSignal.timeout(15000)]),
        })).json() as { grant: string; expires_at: string };
        await connection.setLocalDescription(await connection.createOffer());
        const deadline = Date.now() + 5000;
        while (!disposed && connection.iceGatheringState !== 'complete' && Date.now() < deadline) {
          await new Promise(resolve => setTimeout(resolve, 100));
        }
        if (disposed) return;
        const response = await apiFetch(`/frigate/cameras/${encodeURIComponent(camera.id)}/webrtc`, {
          method: 'POST', headers: { 'Content-Type': 'application/sdp', 'X-Playback-Grant': access.grant },
          body: connection.localDescription?.sdp,
          signal: AbortSignal.any([abort.signal, AbortSignal.timeout(15000)]),
        });
        if (!disposed) await connection.setRemoteDescription({ type: 'answer', sdp: await response.text() });
        // Periodically close and renegotiate through the authorized gateway.
        // The gateway currently has no server-side peer revocation contract.
        timer = setTimeout(() => { if (!disposed) setRetry(v => v + 1); }, Math.max(1000, Date.parse(access.expires_at) - Date.now() - 5000));
      } catch (e) {
        const denied = e instanceof ApiError && [401, 403, 404].includes(e.status);
        failed(denied ? 'Playback access expired or forbidden' : 'Live stream unavailable', denied);
      }
    }
    const playing = () => { clearTimeout(watchdog); setState('live'); };
    const stalled = () => failed('Camera offline; reconnecting');
    video.addEventListener('playing', playing); video.addEventListener('stalled', stalled);
    void start();
    return () => {
      disposed = true; abort.abort(); clearTimeout(timer); clearTimeout(watchdog);
      video.removeEventListener('playing', playing); video.removeEventListener('stalled', stalled);
      if (peer) { peer.onconnectionstatechange = null; peer.close(); }
      video.srcObject = null;
    };
  }, [camera.id, camera.status, video, retry]);
  return <div ref={container} className={`camera-feed-container ${isPrimary ? 'primary' : 'secondary'} ${camera.status === 'disabled' ? 'offline' : ''}`}>
    <div className="video-placeholder">
      {camera.status === 'enabled' && <video ref={videoRef} className={`camera-snapshot ${fit}`} autoPlay playsInline muted aria-label={`Live video from ${camera.name}`} />}
      {(camera.status === 'disabled' || state !== 'live') && <div className="offline-message" role="status">{camera.status === 'disabled' ? 'Camera disabled' : state}</div>}
    </div>
    <div className="overlay-top-left"><div className="camera-name">{camera.name} ({camera.id})</div></div>
    <div className="overlay-top-right"><div className={`live-indicator ${state === 'live' ? 'online' : 'offline'}`}><span className="live-dot" />{camera.status === 'disabled' ? 'DISABLED' : state === 'live' ? 'LIVE · MUTED' : 'OFFLINE / CONNECTING'}</div></div>
    <div className="overlay-bottom-left">
      <div className="people-count">Latest person observations: {tracks.length}</div>
      {isPrimary && <div className="people-count">Boxes unavailable on live video: metadata is not frame synchronized.</div>}
      <button disabled={camera.status === 'disabled'} title={camera.status === 'disabled' ? 'Enable this camera in backend configuration before playback' : 'Request new playback access'} onClick={() => setRetry(v => v + 1)}>Reconnect</button>
      <button onClick={() => { void container.current?.requestFullscreen().catch(() => setState('Fullscreen unavailable')); }}>Fullscreen</button>
    </div>
  </div>;
}
