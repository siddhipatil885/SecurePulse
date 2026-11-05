import React, { useLayoutEffect, useState } from 'react';
import type { PersonTrack } from '../types';
import { projectBox } from './overlayGeometry';
import './DetectionOverlay.css';

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

const classColors: Record<string, string> = {
  person: '#2ce6a6',
  bicycle: '#4cc9f0',
  car: '#4cc9f0',
  motorcycle: '#f4a261',
  bus: '#f4a261',
  truck: '#f4a261',
  cat: '#c77dff',
  dog: '#c77dff',
};

function objectColor(objectType: string): string {
  return classColors[objectType.toLowerCase()] ?? '#ffd166';
}

function calculateBoxes(video: HTMLVideoElement | null, tracks: PersonTrack[], fitMode: 'cover' | 'contain'): RenderedBox[] {
  if (!video) return [];
  const container = video.parentElement;
  if (!container) return [];
  const containerWidth = container.clientWidth;
  const containerHeight = container.clientHeight;
  if (!containerWidth || !containerHeight) return [];

  // Backend boxes are already normalized to the detector frame. Map them
  // through the video's displayed rectangle, including cover/contain offsets.
  // Multiplying by detector dimensions again misaligns higher-resolution video.
  return tracks.flatMap((track) => {
    if (!track.boundingBox) return [];
    const sourceWidth = video.videoWidth || track.frameWidth;
    const sourceHeight = video.videoHeight || track.frameHeight;
    if (!sourceWidth || !sourceHeight) return [];
    const box = projectBox(track.boundingBox, containerWidth, containerHeight, sourceWidth, sourceHeight, fitMode);
    return [{
      track,
      left: box.x,
      top: box.y,
      width: box.width,
      height: box.height,
    }];
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
    video.addEventListener('resize', update);
    video.addEventListener('emptied', update);
    return () => {
      observer.disconnect();
      video.removeEventListener('loadedmetadata', update);
      video.removeEventListener('resize', update);
      video.removeEventListener('emptied', update);
    };
  }, [video, tracks, fitMode]);

  return (
    <div className="detection-overlay" aria-label={`${tracks.length} currently tracked objects`}>
      {boxes.map(({ track, left, top, width, height }) => (
        <div
          className={`detection-box detection-box-${track.objectType.toLowerCase().replace(/[^a-z0-9_-]/g, '-')}`}
          key={track.trackId}
          data-track-id={track.trackId}
          style={{ left, top, width, height, '--detection-color': objectColor(track.objectType) } as React.CSSProperties}
        >
          <span className="person-box-label">
            {track.objectType.replace(/(^|\s)\S/g, (letter) => letter.toUpperCase())} {Math.round(track.confidence * 100)}%
          </span>
          {debug && <span className="person-box-debug">{track.trackId} · {Math.round(track.confidence * 100)}%</span>}
        </div>
      ))}
    </div>
  );
};

export default DetectionOverlay;
