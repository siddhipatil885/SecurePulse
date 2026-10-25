# Audit Evidence Index

## Source evidence map

| Major finding | Primary repository evidence | Supporting command/check | Limitation |
|---|---|---|---|
| Project is explicitly early/planned | `README.md:15`, `:33-52`, `:284-315` | Full file inspection | README may lag external work |
| Three-service Phase 1 topology | `ai-cctv/deployment/docker-compose.yml:3-53` | `git ls-files`, line inspection | Docker unavailable |
| Host port 8554 conflict | Compose `:25`, `:49` | Static comparison | Runtime error not captured locally |
| MediaMTX has no sample publisher/source | Compose `:43-49`; no other config/source file | Repository-wide `rg --files` and search | External manual publisher could exist but is undocumented |
| Stream placeholder likely invalid | `frigate.yml:36`; Compose `:36-39` | Compared with authoritative Frigate substitution docs | Pinned-image runtime validation blocked |
| Single CPU/person camera config | `frigate.yml:8-11`, `:22-47` | Full config inspection | Detection not run |
| Recording/snapshots configured | `frigate.yml:48-64`; Compose `:31` | Full config inspection | Files not produced during audit |
| Frigate MQTT configured | `frigate.yml:1-6` | Full config inspection | Broker/event flow not run |
| Anonymous MQTT | `mosquitto.conf:1-5`; Compose `:8-13` | Static security review | Host firewall unknown |
| Subscriber only prints | `test_mqtt_subscriber.py:31-41` | AST parse PASS | Broker unavailable/not started |
| QoS 0/no durability logic | Subscriber `:13-18`, `:44-60` | Source trace | Upstream Frigate publish QoS not runtime captured |
| No security engine | Empty `detection/events/zones` placeholders | Repository-wide search | External repository/service unknown |
| No FastAPI backend/endpoints | `requirements.txt:1-9`; all `backend/app` files are `.gitkeep` | File inventory and symbol search | External/unpushed code unknown |
| No app database/schema | Requirements `:5-7`; empty database placeholder | Search for models/SQL/migrations/DB config | Frigate internal DB intentionally excluded |
| No dashboard | Dashboard `.gitkeep` files; no Node manifest | File inventory/search | External design not audited |
| No mobile apps | No mobile manifests/source | File inventory/search | Separate repository unknown |
| No dispatch/notifications | `README.md:163-165`; no code/schema | Repository-wide search | External provider/project unknown |
| Privileged/broad USB mapping | Compose `:18-22`; CPU config `frigate.yml:8-11` | Static security review | Runtime host controls unknown |
| Frigate DB persistence unclear | `frigate.yml:13-14`; Compose `:28-35` | Volume/path comparison | Container image behavior not run |
| No automated tests | Manual script contents | `pytest --collect-only`: zero tests | Dependencies/services not installed/launched |
| Python syntax valid | `test_mqtt_subscriber.py` | AST parse PASS under Python 3.14.7 | Semantic/runtime behavior unverified |
| No CI/CD/IaC beyond Compose | Complete tracked-file inventory | `git ls-files`; `rg --files` | External CI configuration unknown |
| Two visible commits/one branch | Git metadata | `git branch -a -vv`, `git log -n 20 --stat` | Remote access/unpushed branches unknown |

## Commands and outcomes

Commands were executed from repository root on 2026-10-13 (Asia/Calcutta).

| Purpose | Command family | Outcome |
|---|---|---|
| File discovery | `rg --files` with generated-directory exclusions | Located seven substantive files plus placeholders |
| Tracked inventory | `git ls-files -s` | 24 pre-audit tracked files |
| Directory discovery | PowerShell recursive directory listing excluding `.git` | Confirmed empty module structure |
| Content search | `rg -n -i` for architecture/security/database/backend markers | Found config/docs/subscriber only |
| Git state | `git status --short --branch` | Clean, `main...origin/main` before reports |
| Branches | `git branch -a -vv` | Local/remote main only, same revision |
| History | `git log ... --stat` | Two commits dated 2026-09-12 |
| Syntax | Python AST parse | PASS |
| Test discovery | `python -m pytest --collect-only -q -p no:cacheprovider ai-cctv/tests` | No tests collected in 0.18s |
| Docker checks | `docker --version`, `docker compose version/config` | BLOCKED: command not found |

No service was started, package installed, database changed, migration run, network camera contacted, or external operational system modified.

## External reference used for interpretation

The repository's placeholder semantics were checked against the official Frigate configuration documentation, which specifies `{FRIGATE_*}` substitution for supported fields. This supports—but does not replace the blocked runtime test—of the stream-path finding: <https://docs.frigate.video/configuration/config/#environment-variable-substitution>.

## Evidence quality scale

- **Direct:** source/config statement or successful local command.
- **Static inference:** deterministic relationship between repository artifacts (for example duplicate host-port binding).
- **Runtime unverified:** configuration exists but Docker/services were unavailable.
- **External unknown:** could exist outside this repository; not credited as implemented.

All feature classifications in `11-feature-completion-matrix.md` follow this evidence scale. No runtime feature is marked VERIFIED WORKING.

