import { expect, it } from 'vitest';
import { notificationTarget } from '../src/api/notificationTarget';

const properties = [{ id: 1, role: 'reporter' }, { id: 2, role: 'marshal' }];
it('routes signed-in users only to their authorized property and record', () => {
  const data = { user_id: 7, property_id: 1, kind: 'reporter_incident', id: 42 };
  expect(notificationTarget(data, 7, properties)).toEqual({ propertyId: 1, pathname: '/incidents/[id]', id: '42' });
  expect(notificationTarget(data, 8, properties)).toBeNull();
  expect(notificationTarget({ ...data, property_id: 3 }, 7, properties)).toBeNull();
  expect(notificationTarget({ ...data, property_id: 2 }, 7, properties)).toBeNull();
});
it('rejects arbitrary URLs, invalid IDs and unknown notification routes', () => {
  for (const data of [null, { url: 'https://external.test' },
    { user_id: 7, property_id: 1, kind: 'camera_event', id: -1 },
    { user_id: 7, property_id: 1, kind: 'external', id: 1 }]) expect(notificationTarget(data, 7, properties)).toBeNull();
});
