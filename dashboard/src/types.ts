export interface Camera {
  id: string;
  name: string;
  status: 'online' | 'offline';
  streamUrl?: string;
  lastSeen: string;
  currentActivity: 'normal' | 'person' | 'suspicious' | 'restricted' | 'critical';
}

export interface SecurityEvent {
  id: string;
  cameraId: string;
  type: string;
  timestamp: string;
  confidence?: number;
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

export interface Detection {
  id: string;
  label: string;
  confidence: number;
  box: [number, number, number, number]; // [x, y, width, height] as percentages
}

export interface SystemStatus {
  online: boolean;
  activeAlerts: number;
  criticalAlerts: number;
  camerasOnline: number;
  totalCameras: number;
  peopleDetected: number;
}
