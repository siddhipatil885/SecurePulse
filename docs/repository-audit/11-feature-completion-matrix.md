# Feature Completion Matrix

## Status rules

- **VERIFIED WORKING:** passed an appropriate runtime/integration check.
- **IMPLEMENTED, UNVERIFIED:** executable implementation exists but was not successfully exercised.
- **PARTIALLY IMPLEMENTED:** only some required implementation layers exist.
- **UI ONLY:** visual implementation exists without demonstrated functionality.
- **CONFIGURED ONLY:** configuration exists without successful runtime proof.
- **NOT IMPLEMENTED:** no required implementation found after repository-wide search.
- **BLOCKED:** validation could not run because of an environment/dependency limitation.

No completion percentage is calculated: the requested system capabilities are not equal-sized, and a percentage would imply unsupported precision.

| Module | Feature | Status | Code Evidence | Test Evidence | Missing Work | Priority |
|---|---|---|---|---|---|---|
| Deployment | Compose topology | PARTIALLY IMPLEMENTED | `docker-compose.yml:3-53` | Docker unavailable | Fix ports/source/env, health checks, verify | P0 |
| Camera | Single RTSP camera input | CONFIGURED ONLY | `frigate.yml:32-44` | Not run | Valid URL substitution and real publisher | P0 |
| Camera | Multi-camera management | NOT IMPLEMENTED | One camera only | None | Registry/config generation/status | P1 |
| Video | MediaMTX restream | CONFIGURED ONLY | Compose `:43-49` | Not run | Pin image, configure source/path/auth | P0 |
| Video | FFmpeg ingestion | CONFIGURED ONLY | `frigate.yml:34-39` | Not run | Correct path, offline/retry proof | P0 |
| Video | Live web/mobile stream | NOT IMPLEMENTED | Ports only at Compose `:23-27` | None | Secure gateway/player/client | P1 |
| AI | CPU object detector | CONFIGURED ONLY | `frigate.yml:8-11` | Not run | Runtime/model validation and metrics | P0 |
| AI | Person detection/filters | CONFIGURED ONLY | `frigate.yml:22-30`, `:45-47` | Not run | Fixture precision/latency test | P0 |
| AI | Vehicle detection | NOT IMPLEMENTED | README planned `:40` | None | Configure/model/test | P3 |
| AI | Object tracking IDs | CONFIGURED ONLY | Frigate person tracking config | Not run | Verify lifecycle/contract to adapter | P1 |
| AI | Face detection | NOT IMPLEMENTED | No source | None | Product/privacy decision first | P3 |
| AI | Face/persistent identity | NOT IMPLEMENTED | README denies/defer `:278`, `:326` | None | Keep out of MVP; governance if reconsidered | P3 |
| AI | GPU acceleration | NOT IMPLEMENTED | CPU detector configured | None | Hardware-specific profile/benchmark | P3 |
| Evidence | Recording/snapshots | CONFIGURED ONLY | `frigate.yml:48-64` | Not run | Persistence, catalog, access, capacity | P1 |
| MQTT | Broker | CONFIGURED ONLY | Compose `:4-13`; Mosquitto config | Not run | Auth/TLS/ACL/health | P0 |
| MQTT | Frigate publication | CONFIGURED ONLY | `frigate.yml:1-6` | Not run | Integration assertion | P0 |
| MQTT | Diagnostic subscriber | IMPLEMENTED, UNVERIFIED | `test_mqtt_subscriber.py:21-60` | AST pass; no runtime | Broker run and assertions | P2 |
| Events | Schema validation/normalization | NOT IMPLEMENTED | JSON print only `:31-41` | None | Versioned Pydantic schema/fixtures | P0 |
| Events | Durable consumption/retry | NOT IMPLEMENTED | QoS 0 utility `:13-18` | None | Durable session/ledger/backoff/DLQ | P0 |
| Events | Deduplication/order handling | NOT IMPLEMENTED | No state | None | Idempotency and revision policy | P0 |
| Engine | Security rule engine | NOT IMPLEMENTED | Empty detection/events placeholders | None | Candidate model/rule API/tests | P0 |
| Engine | Zone/intrusion rule | NOT IMPLEMENTED | README planned `:131-133` | None | Persist zones; geometry tests | P0 |
| Engine | Line crossing/loitering | NOT IMPLEMENTED | README planned `:134-141` | None | Temporal/trajectory engine | P2 |
| Backend | FastAPI app/health | NOT IMPLEMENTED | Dependency only `requirements.txt:1-4` | None | App factory/routes/readiness | P0 |
| Backend | Auth/RBAC/tenant isolation | NOT IMPLEMENTED | No auth source | None | Identity/policy/security tests | P0 |
| Backend | Camera/property APIs | NOT IMPLEMENTED | Placeholders only | None | Models/services/routes | P1 |
| Backend | Incident APIs | NOT IMPLEMENTED | Incident placeholder only | None | Transactional service/routes | P0 |
| Backend | Realtime alerts | NOT IMPLEMENTED | No WebSocket/SSE | None | Auth stream/replay/backpressure | P1 |
| Database | PostgreSQL deployment | NOT IMPLEMENTED | Drivers only `requirements.txt:5-7` | None | Service/config/backups | P0 |
| Database | Domain schema/migrations | NOT IMPLEMENTED | No models/migrations | None | Tables/constraints/indexes/Alembic | P0 |
| Dashboard | Web application | NOT IMPLEMENTED | `.gitkeep` placeholders | None | App scaffold and real integration | P1 |
| Dashboard | Camera/incident UI | NOT IMPLEMENTED | No pages/components | None | Build after contracts | P1 |
| Mobile | Property-owner app | NOT IMPLEMENTED | No mobile files | None | Product/platform/API/app | P2 |
| Mobile | Marshal app | NOT IMPLEMENTED | No mobile files | None | Auth/offers/status/location UI | P1 |
| Dispatch | Marshal model/availability | NOT IMPLEMENTED | No source/schema | None | Domain/API/privacy controls | P1 |
| Dispatch | Assignment/ack/timeout | NOT IMPLEMENTED | README says none `:163-165` | None | Atomic workflow and scheduler | P1 |
| Notifications | Push/SMS/email | NOT IMPLEMENTED | No provider/source | None | Outbox/provider/receipts/retries | P1 |
| Audit | Incident/evidence/audit history | NOT IMPLEMENTED | No DB/application | None | Append-only records/access logs | P1 |
| Security | MQTT authentication | NOT IMPLEMENTED | `allow_anonymous true` | Static finding | Credentials/TLS/ACL/negative tests | P0 |
| Security | API/evidence authorization | NOT IMPLEMENTED | No API | None | Deny-by-default property/role checks | P0 |
| Operations | Health/monitoring/log aggregation | NOT IMPLEMENTED | Restart/stdout only | None | Metrics/logs/traces/alerts/runbooks | P2 |
| Operations | Backups/disaster recovery | NOT IMPLEMENTED | No backup config | None | Backup/restore objectives and drill | P2 |
| CI/CD | Automated quality pipeline | NOT IMPLEMENTED | No workflow | None | Lint/type/test/build/scan gates | P1 |
| Tests | Automated pytest suite | NOT IMPLEMENTED | Manual script only | Zero collected | Unit/integration/security/E2E tests | P0 |

“BLOCKED” applies specifically to runtime validation of Docker/Frigate/MQTT because Docker is absent; it does not replace the implementation statuses above. See `10-testing-audit.md`.

