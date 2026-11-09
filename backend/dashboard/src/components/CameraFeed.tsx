import React, { useCallback, useEffect, useState } from 'react';
import type { Camera } from '../types';
import type { PersonTrack } from '../types';
import { frigateWebRtcUrl } from '../api';
import DetectionOverlay from './DetectionOverlay';
import './CameraFeed.css';

interface CameraFeedProps {
  propertyId: number;
  camera: Camera;
  isPrimary: boolean;
  tracks: PersonTrack[];
}

const CameraFeed: React.FC<CameraFeedProps> = ({ propertyId, camera, isPrimary, tracks }) => {
  const fitMode: 'cover' | 'contain' = import.meta.env.VITE_VIDEO_OBJECT_FIT === 'contain' ? 'contain' : 'cover';
  const [time, setTime] = useState<Date>(new Date());
  const [videoElement, setVideoElement] = useState<HTMLVideoElement | null>(null);
  const [streamState, setStreamState] = useState<'connecting' | 'live' | 'unavailable'>('connecting');
  const [attempt, setAttempt] = useState(0);
  const setVideoRef = useCallback((element: HTMLVideoElement | null) => {
    setVideoElement(element);
  }, []);
  const liveTracks = tracks.filter((track, index, all) =>
    track.cameraId === camera.id
    && track.objectType === 'person'
    && track.state === 'ACTIVE'
    && all.findIndex((candidate) => candidate.cameraId === camera.id && candidate.trackId === track.trackId) === index,
  );
  
  useEffect(() => {
    const timer = setInterval(() => setTime(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    let disposed = false;
    let peer: RTCPeerConnection | null = null;
    const streamVideo = videoElement;
    const abort = new AbortController();

    const startStream = async () => {
      if (camera.status !== 'enabled' || !streamVideo) return;
      setStreamState('connecting');
      const connection = new RTCPeerConnection();
      peer = connection;
      connection.addTransceiver('video', { direction: 'recvonly' });
      connection.ontrack = (event) => {
        if (!disposed) {
          streamVideo.srcObject = event.streams[0] ?? new MediaStream([event.track]);
        }
      };
      connection.onconnectionstatechange = () => {
        if (!disposed && connection.connectionState === 'failed') {
          setStreamState('unavailable');
        }
      };

      try {
        const offer = await connection.createOffer();
        await connection.setLocalDescription(offer);
        if (connection.iceGatheringState !== 'complete') {
          await new Promise<void>((resolve) => {
            const gatheringComplete = () => {
              if (connection.iceGatheringState === 'complete') {
                window.clearTimeout(timeout);
                connection.removeEventListener('icegatheringstatechange', gatheringComplete);
                resolve();
              }
            };
            const timeout = window.setTimeout(() => {
              connection.removeEventListener('icegatheringstatechange', gatheringComplete);
              resolve();
            }, 8000);
            connection.addEventListener('icegatheringstatechange', gatheringComplete);
            gatheringComplete();
          });
        }
        if (disposed) return;
        const response = await fetch(frigateWebRtcUrl(propertyId, camera.id), {
          method: 'POST',
          credentials: 'include',
          signal: abort.signal,
          headers: { 'Content-Type': 'application/sdp', 'X-Dashboard-Request': '1' },
          body: connection.localDescription?.sdp,
        });
        if (!response.ok) throw new Error(`RTC negotiation failed (${response.status})`);
        if (disposed) return;
        await connection.setRemoteDescription({ type: 'answer', sdp: await response.text() });
      } catch {
        if (!disposed) setStreamState('unavailable');
      }
    };

    void startStream();
    return () => {
      disposed = true;
      abort.abort();
      if (streamVideo) streamVideo.srcObject = null;
      peer?.close();
    };
  }, [propertyId, camera.id, camera.status, videoElement, attempt]);

  return (
    <div data-camera-id={camera.id} data-stream-state={streamState} className={`camera-feed-container ${isPrimary ? 'primary' : 'secondary'} ${camera.status === 'disabled' ? 'offline' : ''}`}>
      <div className="video-placeholder">
        {camera.status === 'enabled' ? (
          <video
            ref={setVideoRef}
            className={`camera-snapshot ${fitMode}`}
            autoPlay
            playsInline
            muted
            onPlaying={() => setStreamState('live')}
            onWaiting={() => setStreamState('connecting')}
            onStalled={() => setStreamState('connecting')}
            onError={() => setStreamState('unavailable')}
            onEnded={() => setStreamState('unavailable')}
            aria-label={`Live video from ${camera.name}`}
          />
        ) : (
          <div className="offline-message">CAMERA DISABLED</div>
        )}
        {camera.status === 'enabled' && streamState !== 'live' && (
          <div className="offline-message">{streamState === 'connecting' ? 'CONNECTING TO CAMERA' : 'LIVE STREAM UNAVAILABLE'}</div>
        )}
        <DetectionOverlay
          video={videoElement}
          tracks={liveTracks}
          debug={import.meta.env.VITE_DEBUG_DETECTIONS === 'true'}
          fitMode={fitMode}
        />
      </div>

      <div className="overlay-top-left">
        <div className="camera-name">{camera.name} ({camera.id})</div>
      </div>

      <div className="overlay-top-right">
        <div className={`live-indicator ${camera.status === 'enabled' ? 'online' : 'offline'}`}>
          <span className="live-dot"></span>
          {camera.status !== 'enabled' ? 'DISABLED' : streamState === 'live' ? 'LIVE' : streamState === 'unavailable' ? 'UNAVAILABLE' : 'CONNECTING'}
        </div>
      </div>

      <div className="overlay-bottom-left">
        <div className="timestamp">
          {time.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' })}<br/>
          {time.toLocaleTimeString('en-GB')}
        </div>
        <div className="people-count">Current people: {liveTracks.length}</div>
      </div>
      {camera.status === 'enabled' && streamState !== 'live' && <button className="retry-camera"
        aria-label={`Retry live video from ${camera.name}`} onClick={() => setAttempt(value => value + 1)}>Retry live video</button>}

    </div>
  );
};

export default CameraFeed;
