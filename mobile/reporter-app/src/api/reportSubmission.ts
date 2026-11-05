import type { Api } from './client';
import { ApiError } from './client';
import type { IncidentCreate, ReporterIncident } from './types';

export interface ReportAttachment { uri: string; name: string; type: string; requestId?: string }

// One instance represents one logical submission. Network and upload retries
// keep both the request key and the incident already created by the server.
export class ReportSubmission {
  private draft: IncidentCreate | null = null;
  private attachment: ReportAttachment | null = null;
  private key: string | null = null;
  private record: ReporterIncident | null = null;
  private pending: Promise<ReporterIncident> | null = null;

  constructor(private api: Pick<Api, 'createIncident' | 'uploadIncidentEvidence'>,
    private makeKey = () => `${Date.now()}-${Math.random().toString(36).slice(2)}-${Math.random().toString(36).slice(2)}`) {}

  get started() { return this.draft !== null; }
  get incidentId() { return this.record?.id ?? null; }
  get propertyId() { return this.draft?.property_id ?? null; }

  setAttachment(attachment: ReportAttachment | null) {
    if (this.pending) throw new Error('Wait for the current upload to finish.');
    this.attachment = attachment ? { ...attachment, requestId: this.makeKey() } : null;
  }

  submit(draft: IncidentCreate, attachment: ReportAttachment | null, signal?: AbortSignal) {
    if (this.started) throw new Error('This report has already been started. Retry the existing submission.');
    this.draft = { ...draft };
    this.key = this.makeKey();
    this.attachment = attachment ? { ...attachment, requestId: this.makeKey() } : null;
    return this.retry(signal);
  }

  retry(signal?: AbortSignal): Promise<ReporterIncident> {
    if (this.pending) return this.pending;
    const draft = this.draft;
    const key = this.key;
    if (!draft || !key) return Promise.reject(new Error('Start a report before retrying it.'));
    const run = async () => {
      signal?.throwIfAborted();
      if (!this.record) this.record = await this.api.createIncident(draft, key, signal);
      signal?.throwIfAborted();
      if (this.attachment) {
        this.record = await this.api.uploadIncidentEvidence(this.record.id, this.attachment, signal);
        this.attachment = null;
      }
      return this.record;
    };
    this.pending = run().catch(error => {
      // A definitive rejection did not create a record. Let the user correct
      // the draft; ambiguous network failures must retain the original key.
      if (!this.record && error instanceof ApiError && [400, 403, 404, 422].includes(error.status ?? 0)) {
        this.draft = null; this.key = null;
      }
      throw error;
    }).finally(() => { this.pending = null; });
    return this.pending;
  }
}
