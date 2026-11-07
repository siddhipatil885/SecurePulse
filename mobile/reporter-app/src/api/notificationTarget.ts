import { z } from 'zod';
const schema = z.object({ user_id: z.number().int().positive(), property_id: z.number().int().positive(),
  kind: z.enum(['reporter_incident', 'camera_event', 'home']), id: z.number().int().positive().nullable().optional() });

export function notificationTarget(data: unknown, userId: number, properties: { id: number; role: string }[]) {
  const parsed = schema.safeParse(data);
  if (!parsed.success || parsed.data.user_id !== userId || !properties.some(p => p.id === parsed.data.property_id && ['owner', 'reporter'].includes(p.role))) return null;
  const item = parsed.data;
  if (item.kind === 'home') return { propertyId: item.property_id, pathname: '/' as const };
  if (!item.id) return null;
  return { propertyId: item.property_id, pathname: item.kind === 'reporter_incident' ? '/incidents/[id]' as const : '/alerts/[id]' as const, id: String(item.id) };
}
