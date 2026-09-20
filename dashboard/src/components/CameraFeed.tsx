import React, { useState, useEffect } from 'react';
import type { Camera } from '../types';
import './CameraFeed.css';

interface CameraFeedProps {
  camera: Camera;
  isPrimary: boolean;
}

const CameraFeed: React.FC<CameraFeedProps> = ({ camera, isPrimary }) => {
  const [time, setTime] = useState<Date>(new Date());
  
  useEffect(() => {
    const timer = setInterval(() => setTime(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);

  return (
    <div className={`camera-feed-container ${isPrimary ? 'primary' : 'secondary'} ${camera.status === 'disabled' ? 'offline' : ''}`}>
      <div className="video-placeholder">
        {camera.status === 'enabled' ? (
          <div className="offline-message">LIVE STREAM UNAVAILABLE</div>
        ) : (
          <div className="offline-message">CAMERA DISABLED</div>
        )}
      </div>

      <div className="overlay-top-left">
        <div className="camera-name">{camera.name} ({camera.id})</div>
      </div>

      <div className="overlay-top-right">
        <div className={`live-indicator ${camera.status === 'enabled' ? 'online' : 'offline'}`}>
          <span className="live-dot"></span>
          {camera.status === 'enabled' ? 'ENABLED' : 'DISABLED'}
        </div>
      </div>

      <div className="overlay-bottom-left">
        <div className="timestamp">
          {time.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' })}<br/>
          {time.toLocaleTimeString('en-GB')}
        </div>
      </div>

    </div>
  );
};

export default CameraFeed;
