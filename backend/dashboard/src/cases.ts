export type CaseSource = 'camera' | 'reporter';
export interface Assignment {
  id: number; status: string; marshal_profile_id: number; version: number;
  offered_at: string; expires_at: string; accepted_at: string | null; closed_at: string | null;
}
export interface CaseSummary {
  key: string; source: CaseSource; source_id: number; property_id: number;
  incident_type: string; status: string; source_status: string; severity: string | null;
  occurred_at: string; description: string | null; camera_id: number | null;
  latest_assignment: Assignment | null;
}
export interface CaseDetail extends CaseSummary {
  location: { address: string | null; latitude: number | null; longitude: number | null; accuracy_metres: number | null };
  confidence: number | null; zone: string | null; allowed_actions: string[]; dispatch_allowed: boolean;
}
export interface TimelineItem {
  key: string; kind: string; previous_status: string | null; status: string;
  actor_subject: string; reason: string | null; occurred_at: string; assignment_id: number | null;
}
export interface CaseEvidence {
  id: number; kind: string; media_type: string | null; original_filename: string | null;
  byte_size: number | null; occurred_at: string;
}
export interface Marshal { id: number; name: string | null; service_area: string | null; capacity: number }
export interface Page<T> { items: T[]; total: number; page: number; page_size: number }
export interface CaseOverview { total: number; active: number; by_source: Record<CaseSource, number> }
export const casePath = (propertyId: number, item: Pick<CaseSummary, 'source' | 'source_id'>) =>
  `/properties/${propertyId}/cases/${item.source}/${item.source_id}`;
