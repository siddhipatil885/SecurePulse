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

  const isCritical = camera.currentActivity === 'critical';
  const isWarning = camera.currentActivity === 'suspicious' || camera.currentActivity === 'restricted';
  const hasDetection = camera.currentActivity === 'person';
  
  const activityLabel = isCritical ? 'CRITICAL ALERT' 
                      : camera.currentActivity === 'restricted' ? 'RESTRICTED ZONE'
                      : camera.currentActivity === 'suspicious' ? 'SUSPICIOUS ACTIVITY'
                      : camera.currentActivity === 'person' ? 'PERSON DETECTED'
                      : null;

  return (
    <div className={`camera-feed-container ${isPrimary ? 'primary' : 'secondary'} ${!camera.status.includes('online') ? 'offline' : ''}`}>
      {/* Mock Video Stream Background */}
      <div className="video-placeholder">
        {camera.status === 'online' ? (
          <div className="mock-video-noise"></div>
        ) : (
          <div className="offline-message">CAMERA OFFLINE</div>
        )}
      </div>
      
      {/* Detection Bounding Box (mock) */}
      {camera.status === 'online' && (isCritical || isWarning || hasDetection) && (
        <div className={`detection-box ${isCritical ? 'critical' : isWarning ? 'warning' : 'info'}`}></div>
      )}

      {/* Top Left: Name & Activity */}
      <div className="overlay-top-left">
        <div className="camera-name">{camera.name} ({camera.id})</div>
        {activityLabel && (
          <div className={`activity-label ${isCritical ? 'critical' : isWarning ? 'warning' : 'info'}`}>
            {activityLabel}
          </div>
        )}
      </div>

      {/* Top Right: Status */}
      <div className="overlay-top-right">
        <div className={`live-indicator ${camera.status === 'online' ? 'online' : 'offline'}`}>
          <span className="live-dot"></span>
          {camera.status === 'online' ? 'LIVE' : 'OFFLINE'}
        </div>
      </div>

      {/* Bottom Left: Timestamp */}
      <div className="overlay-bottom-left">
        <div className="timestamp">
          {time.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' })}<br/>
          {time.toLocaleTimeString('en-GB')}
        </div>
      </div>

      {/* Bottom Right: Detection Info */}
      {camera.status === 'online' && hasDetection && (
        <div className="overlay-bottom-right">
          <div className="detection-info">
            PERSON DETECTED<br/>
            <span className="confidence">94%</span>
          </div>
        </div>
      )}
    </div>
  );
};

export default CameraFeed;
