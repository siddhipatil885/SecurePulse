import React, { useLayoutEffect, useState } from 'react';
import type { PersonTrack } from '../types';
import './DetectionOverlay.css';
import { projectBox } from '../geometry';

interface DetectionOverlayProps {
  video: HTMLVideoElement | null;
  tracks: PersonTrack[];
  debug?: boolean;
  fitMode?: 'cover' | 'contain';
}

interface RenderedBox {
  track: PersonTrack;
  left: number;
  top: number;
  width: number;
  height: number;
}

function calculateBoxes(video: HTMLVideoElement | null, tracks: PersonTrack[], fitMode: 'cover' | 'contain'): RenderedBox[] {
  if (!video) return [];
  const container = video.parentElement;
  if (!container) return [];
  const containerWidth = container.clientWidth;
  const containerHeight = container.clientHeight;
  if (!containerWidth || !containerHeight) return [];

  // The video uses object-fit: cover. Its displayed rectangle may extend
  // beyond the container, so map detector coordinates through that rectangle
  // rather than the browser viewport.
  return tracks.flatMap((track) => {
    if (!track.boundingBox) return [];
    const sourceWidth = video.videoWidth || track.frameWidth;
    const sourceHeight = video.videoHeight || track.frameHeight;
    if (!sourceWidth || !sourceHeight) return [];
    const box = projectBox(track.boundingBox, sourceWidth, sourceHeight, containerWidth, containerHeight, fitMode);
    return box ? [{ track, ...box }] : [];
  });
}

const DetectionOverlay: React.FC<DetectionOverlayProps> = ({ video, tracks, debug = false, fitMode = 'cover' }) => {
  const [boxes, setBoxes] = useState<RenderedBox[]>([]);

  useLayoutEffect(() => {
    const update = () => setBoxes(calculateBoxes(video, tracks, fitMode));
    update();
    if (!video) return undefined;
    const observer = new ResizeObserver(update);
    observer.observe(video);
    if (video.parentElement) observer.observe(video.parentElement);
    video.addEventListener('loadedmetadata', update);
    return () => {
      observer.disconnect();
      video.removeEventListener('loadedmetadata', update);
    };
  }, [video, tracks, fitMode]);

  return (
    <div className="detection-overlay" aria-label={`${tracks.length} currently tracked people`}>
      {boxes.map(({ track, left, top, width, height }, index) => (
        <div
          className={`person-box ${track.state === 'TEMPORARILY_LOST' ? 'lost' : ''}`}
          key={track.trackId}
          style={{ left, top, width, height }}
        >
          <span className="person-box-label">Person {index + 1}</span>
          {debug && <span className="person-box-debug">{track.trackId} · {Math.round(track.confidence * 100)}%</span>}
        </div>
      ))}
    </div>
  );
};

export default DetectionOverlay;
