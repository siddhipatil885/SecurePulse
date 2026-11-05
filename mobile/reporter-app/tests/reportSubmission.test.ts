import { expect, it, vi } from 'vitest';
import { ApiError } from '../src/api/client';
import { ReportSubmission } from '../src/api/reportSubmission';
import type { ReporterIncident } from '../src/api/types';

const draft = { property_id: 1, incident_type: 'THEFT', address: '1 Test Street' };
const incident = { id: 42 } as ReporterIncident;
const attachment = { uri: 'file:///photo.jpg', name: 'photo.jpg', type: 'image/jpeg' };
function fixture() {
  const api = { createIncident: vi.fn().mockResolvedValue(incident), uploadIncidentEvidence: vi.fn().mockResolvedValue(incident) };
  let n = 0;
  return { api, submission: new ReportSubmission(api, () => `request-key-${++n}`) };
}
it('retries a lost creation response with the same key and frozen property', async () => {
  const { api, submission } = fixture();
  api.createIncident.mockRejectedValueOnce(new ApiError('offline', undefined, 'NETWORK'));
  await expect(submission.submit(draft, null)).rejects.toThrow('offline');
  draft.property_id = 2;
  await submission.retry();
  draft.property_id = 1;
  expect(api.createIncident.mock.calls[1]).toEqual(api.createIncident.mock.calls[0]);
  expect(api.createIncident.mock.calls[1]![0].property_id).toBe(1);
});
it('retries only the failed upload, preserving its idempotency key', async () => {
  const { api, submission } = fixture();
  api.uploadIncidentEvidence.mockRejectedValueOnce(new Error('upload interrupted'));
  await expect(submission.submit(draft, attachment)).rejects.toThrow('upload interrupted');
  expect(submission.incidentId).toBe(42);
  await submission.retry();
  expect(api.createIncident).toHaveBeenCalledTimes(1);
  expect(api.uploadIncidentEvidence.mock.calls[1]).toEqual(api.uploadIncidentEvidence.mock.calls[0]);
});
it('deduplicates concurrent retries and lets users remove a failed attachment', async () => {
  const { api, submission } = fixture();
  api.uploadIncidentEvidence.mockRejectedValueOnce(new Error('unsupported'));
  const first = submission.submit(draft, attachment);
  expect(submission.retry()).toBe(first);
  await expect(first).rejects.toThrow('unsupported');
  submission.setAttachment(null);
  await expect(submission.retry()).resolves.toEqual(incident);
  expect(api.uploadIncidentEvidence).toHaveBeenCalledTimes(1);
});
it('allows correction after server validation rejects creation', async () => {
  const { api, submission } = fixture();
  api.createIncident.mockRejectedValueOnce(new ApiError('invalid address', 422));
  await expect(submission.submit(draft, null)).rejects.toThrow('invalid address');
  expect(submission.started).toBe(false);
  await submission.submit({ ...draft, address: 'Corrected address' }, null);
  expect(api.createIncident.mock.calls[1]![1]).not.toBe(api.createIncident.mock.calls[0]![1]);
});
