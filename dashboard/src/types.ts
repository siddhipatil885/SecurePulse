export interface Camera {
  id: string;
  name: string;
  frigateCameraName: string;
  status: 'enabled' | 'disabled';
  lastSeen: string;
}

export interface SecurityEvent {
  id: string;
  cameraId: string;
  type: string;
  objectType?: string;
  timestamp: string;
  confidence?: number;
  severity?: string;
  status?: string;
  metadata?: Record<string, any>;
}

export interface SecurityAlert {
  id: string;
  cameraId: string;
  severity: 'critical' | 'warning' | 'info';
  type: string;
  timestamp: string;
  status: 'active' | 'acknowledged' | 'resolved';
}

export interface BoundingBox {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface PersonTrack {
  trackId: string;
  cameraId: string;
  objectType: 'person';
  firstSeen: string;
  lastSeen: string;
  boundingBox: BoundingBox | null;
  confidence: number;
  frameWidth: number;
  frameHeight: number;
  state: 'ACTIVE' | 'TEMPORARILY_LOST';
  faceVisible: boolean | null;
}

export interface SystemStatus {
  online: boolean;
  activeAlerts: number;
  criticalAlerts: number;
  camerasOnline: number;
  totalCameras: number;
  peopleDetected: number;
}
