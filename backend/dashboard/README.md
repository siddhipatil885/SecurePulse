# SecurePulse Dashboard

See [the dashboard integration runbook](../../docs/runbooks/web-dashboard-e2e.md)
for authentication, property filtering, playback grants, tests and acceptance blockers.

The dashboard reads cameras and security events from the backend API. During local
development, Vite proxies `/api` to `http://localhost:8000` by default.

To use another backend URL, set `VITE_BACKEND_URL` for the dev proxy and
`VITE_API_BASE_URL` for browser requests, for example:

```sh
VITE_BACKEND_URL=http://localhost:8000
VITE_API_BASE_URL=/api/v1
npm run dev
```

The UI does not include fallback camera, alert, event, stream, or detection data.
When the API is unavailable it shows an error state.

## Detection overlay

The dashboard loads `/api/v1/tracks` and uses the existing WebSocket to trigger
authorized REST resync. Tracks are asynchronous observations. Live detection
rectangles are suppressed because MQTT coordinates are not synchronized with
browser video frames. The preserved geometry utility supports cover/contain,
mirroring and resize for future frame-linked overlays; its behavior is tested.

Set `VITE_DEBUG_DETECTIONS=true` only for development to display temporary
track IDs and confidence. The normal operator view shows only a Person label
and the current-person count; it never displays or stores facial identities.

This template provides a minimal setup to get React working in Vite with HMR and some Oxlint rules.

Currently, two official plugins are available:

- [@vitejs/plugin-react](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react) uses [Oxc](https://oxc.rs)
- [@vitejs/plugin-react-swc](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react-swc) uses [SWC](https://swc.rs/)

## React Compiler

The React Compiler is not enabled on this template because of its impact on dev & build performances. To add it, see [this documentation](https://react.dev/learn/react-compiler/installation).

## Expanding the Oxlint configuration

If you are developing a production application, we recommend enabling type-aware lint rules by installing `oxlint-tsgolint` and editing `.oxlintrc.json`:

```json
{
  "$schema": "./node_modules/oxlint/configuration_schema.json",
  "plugins": ["react", "typescript", "oxc"],
  "options": {
    "typeAware": true
  },
  "rules": {
    "react/rules-of-hooks": "error",
    "react/only-export-components": ["warn", { "allowConstantExport": true }]
  }
}
```

See the [Oxlint rules documentation](https://oxc.rs/docs/guide/usage/linter/rules) for the full list of rules and categories.
