import { z } from 'zod';
export const propertySchema = z.object({ id: z.number().int().positive(), name: z.string(), role: z.enum(['owner', 'reporter', 'dispatcher', 'marshal']) });
export const profileSchema = z.object({ id: z.number().int().positive(), email: z.string(), name: z.string(), properties: z.array(propertySchema) });
export const tokenSchema = z.object({ access_token: z.string().min(1), token_type: z.literal('bearer'), expires_at: z.string().datetime({ offset: true }) });
export const cameraSchema = z.object({ id: z.number().int(), name: z.string(), location: z.string().nullable(), enabled: z.boolean(), connection_status: z.literal('unknown') });
export const eventSchema = z.object({ id: z.number().int(), camera_id: z.number().int(), event_type: z.string(), object_type: z.string(), confidence: z.number(), timestamp: z.string(), severity: z.string(), status: z.string(), reason: z.string().nullable(), zone: z.string().nullable(), alert_id: z.number().int().positive().nullable().optional(), alert_status: z.string().nullable().optional() });
export const eventPageSchema = z.object({ items: z.array(eventSchema), page: z.number().int().positive(), page_size: z.number().int().positive(), total: z.number().int().nonnegative() });
export const summarySchema = z.object({ camera_count: z.number().int().nonnegative(), event_count: z.number().int().nonnegative(), active_alert_count: z.number().int().nonnegative(), connected_camera_count: z.number().nullable(), active_incident_count: z.number().nullable(), security_status: z.literal('unknown') });
export const incidentEvidenceSchema = z.object({ id: z.number().int().positive(), media_type: z.string(), original_filename: z.string(), byte_size: z.number().int().nonnegative(), created_at: z.string() });
export const incidentTimelineSchema = z.object({ id: z.number().int().positive(), status: z.string(), actor_subject: z.string(), message: z.string(), occurred_at: z.string() });
export const incidentDispatchSchema = z.object({
  assignment_id: z.number().int().positive(), status: z.string(), marshal_profile_id: z.number().int().positive(),
  offered_at: z.string(), expires_at: z.string(), accepted_at: z.string().nullable(),
  closed_at: z.string().nullable(), version: z.number().int().positive(),
});
export const incidentSchema = z.object({
  id: z.number().int().positive(), property_id: z.number().int().positive(), incident_type: z.string(),
  description: z.string().nullable(), address: z.string().nullable(), latitude: z.number().nullable(),
  longitude: z.number().nullable(), location_accuracy: z.number().nullable(), status: z.string(),
  created_at: z.string(), updated_at: z.string(), evidence: z.array(incidentEvidenceSchema),
  dispatch: incidentDispatchSchema.nullable().optional(),
  timeline: z.array(incidentTimelineSchema),
});
export const incidentPageSchema = z.object({ items: z.array(incidentSchema), page: z.number().int().positive(), page_size: z.number().int().positive(), total: z.number().int().nonnegative() });
export const notificationPreferenceSchema = z.object({ category: z.enum(['SECURITY_ALERTS', 'INCIDENT_UPDATES', 'DISPATCH_UPDATES']), enabled: z.boolean(), updated_at: z.string() });
export type Profile = z.infer<typeof profileSchema>;
export type PropertyAccess = z.infer<typeof propertySchema>;
export type Token = z.infer<typeof tokenSchema>;
export type Camera = z.infer<typeof cameraSchema>;
export type SecurityEvent = z.infer<typeof eventSchema>;
export type EventPage = z.infer<typeof eventPageSchema>;
export type ReporterIncident = z.infer<typeof incidentSchema>;
export type IncidentCreate = {
  property_id: number; incident_type: string; description?: string; address?: string;
  latitude?: number; longitude?: number; location_accuracy?: number;
};
export type NotificationPreference = z.infer<typeof notificationPreferenceSchema>;
export const canReport = (property: PropertyAccess) => property.role === 'owner' || property.role === 'reporter';
