# Local environment files

Prepared from the supplied root `env` on 2026-11-05. That source and generated
files are ignored by Git and restricted to the local user. Do not commit them.
Database and broker credentials were retained. Login is enabled with a generated
shared signing secret. Real notification delivery remains disabled.

| File | Used by |
|---|---|
| `backend/deployment/.env` | Canonical Docker Compose stack |
| `backend/.env` | Python backend run directly from `backend/` |
| `backend/dashboard/.env.local` | Vite proxy to the backend |
| `mobile/reporter-app/.env` | Expo's public API origin and optional project ID |

Updated after Neon setup: both runtime files now point to Neon Postgres and Auth.
The original local PostgreSQL settings are preserved in private recovery files;
their data was not copied or deleted. See [the Neon runbook](neon.md) for the
current configuration. Images and videos remain local with explicit storage limits.
Direct Python evidence is under `backend/operational-evidence/media`; Docker uses
its named reporter evidence volume. Choose one backend runtime for normal use;
these evidence locations are separate and are not automatically synchronized.
go2rtc signaling is published only on loopback port 11984 for direct Python use.

## Configure the phone address on the actual backend PC

From the repository root on the main PC, with these private env files copied:

```powershell
python backend/scripts/configure_client_host.py
```

This detects the PC's LAN IPv4 address, sets the authenticated backend's LAN bind,
and updates the dashboard proxy and mobile URL together. It preserves credentials.
It does not start services or modify firewall rules. Use `--host 192.168.x.x` to
override detection if a VPN selects the wrong interface. The phone must reach
this PC on the same network. For an existing HTTPS gateway, use
`--url https://your-api-domain` instead; this updates mobile without opening a bind.
The mobile URL is intentionally empty until this command runs on the correct PC.

Then restart the backend and both client development servers. For Docker, follow
the existing [main-host handoff](main-host-handoff.md) to select the correct project,
back up the database and apply migrations. With a direct Python backend, use the
`uvicorn` command printed by the helper from `backend/`.

`EXPO_PUBLIC_EXPO_PROJECT_ID` stays empty until an actual Expo/EAS project is
available. This does not prevent normal login/reporting, but push registration
requires it and real notification delivery still needs a provider implementation.

## Other host requirements

The env file does not create PostgreSQL roles, change existing database passwords,
create MQTT accounts, start camera publishers, or apply migrations. Preserve the
existing database/broker credentials and password file on the host. If no broker
password file exists, run `backend/scripts/setup_mqtt_auth.ps1` there and enter the
matching passwords from the private deployment env file. Existing password files
are deliberately never overwritten by that script.

There is no Docker executable in the preparation workspace. Settings parsing,
secret consistency and Git exclusions can be verified here; run Compose's actual
interpolation check on the host using `config --quiet` as described in the handoff.
