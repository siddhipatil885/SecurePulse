# Open Questions and Human Verification Items

These questions cannot be answered from the repository. They should be resolved before architecture is treated as committed.

## Product and operational scope

1. What constitutes an incident versus an informational detection, and who may dismiss/escalate/resolve it?
2. Which jurisdictions, properties, users, responder organizations, and legal retention rules are in pilot scope?
3. Is “marshal/QRT” an internal workforce, a contracted provider, or public emergency services? What authority and SLA exist?
4. What response is expected when no marshal is available, and may the system contact police/fire/medical services automatically?
5. What are the accepted detection-to-alert, alert-to-acknowledgment, availability, RPO, and RTO targets?

## Camera and AI

6. Which real camera models/codecs/resolutions/RTSP auth schemes must be supported? Is ONVIF discovery/control required?
7. What was intended to publish media into `rtsp-sim`, and is a redistributable test clip available?
8. Was the Phase 1 stack ever run successfully? If so, where are logs, exact Docker/OS versions, and captured MQTT payloads?
9. Which Frigate event revisions/topics are authoritative, and what happens on Frigate upgrades?
10. Are restricted zones authored in Frigate or SecurePulse? Who owns coordinate transforms after stream resolution changes?
11. What labeled validation set establishes acceptable day/night precision, recall, false-alert rate, and latency?
12. Is persistent identity deliberately out of scope? The README says face matching is absent and cross-camera re-identification deferred (`README.md:278`, `:326`).

## Platform and data

13. Is PostgreSQL definitive, or does the README's older Firebase mention still reflect a decision (`README.md:206-208`)?
14. What is the tenant hierarchy: organization → property → perimeter → camera → zone?
15. Which identity provider and roles are required? Can a person hold owner and marshal roles across different properties?
16. Where will media live in pilot/production, how will application evidence reference Frigate files, and who can export/delete/legal-hold it?
17. What source-event and incident retention periods apply, independent of video retention?
18. Is an MQTT broker the durable event backbone, or should a durable queue/log receive normalized events?

## Dispatch and notifications

19. How is marshal eligibility calculated—distance, service area, skill, organization, shift, load, or manual dispatcher?
20. What offer timeout/retry/escalation rules and maximum simultaneous assignments apply?
21. Which push/SMS/email providers and countries are allowed? What delivery telemetry and cost limits are required?
22. Is location continuous, on-duty only, or incident-only? What precision, freshness, retention, and consent rules apply?
23. What evidence/notes are required to resolve an incident, and who can reopen it?

## Deployment and ownership

24. What are the target OS/hardware profiles? Current Compose includes Linux device mounts but the audit host is Windows (`docker-compose.yml:21-22`, `:29`).
25. Is deployment per property, regional, or centralized? Are cameras permitted to communicate outside local networks?
26. What environments, domains, certificates, secret manager, monitoring, backup system, and on-call team exist?
27. Is there unpushed or inaccessible work on other machines/branches? Only two commits and `main` were visible.
28. Who owns each upstream version upgrade and its contract/regression testing?
29. Are there brand/design/mobile-platform requirements not committed to this repository?
30. What security/privacy threat model and data-protection impact assessment have been approved?

## Evidence requested from the team

- A successful Compose startup log and service health output.
- A sanitized real Frigate `new`/`update`/`end` event set and topic/QoS capture.
- A test-camera compatibility list and sample clip rights statement.
- Current PRD, API/data diagrams, threat model, deployment diagram, and retention policy.
- Any external backend, Firebase project, mobile repository, design prototype, CI project, or infrastructure repository not visible here.

