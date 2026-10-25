export interface Camera {
  id: string;
  name: string;
  frigateCameraName: string;
  status: 'enabled' | 'disabled';
  lastSeen: string;
  propertyId: number;
  location: string | null;
  health: 'healthy' | 'degraded' | 'offline' | 'unknown';
}

export interface SecurityEvent {
  id: string;
  cameraId: string;
  type: string;
  propertyId: number;
  reason?: string | null;
  zone?: string | null;
  sourceId?: string | null;
  createdAt?: string | null;
  objectType?: string;
  timestamp: string;
  confidence?: number;
  severity?: string;
  status?: string;
  metadata?: Record<string, unknown>;
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
