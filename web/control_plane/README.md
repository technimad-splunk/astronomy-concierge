# SE Control-Plane Web UI (Phase 7.4)

Thin FastAPI + SSE web wrapper over the existing `control_plane/` package.

## What this wraps

- Discovery uses `control_plane.registry.discover()` directly.
- Trigger operations use `control_plane.triggers.apply_trigger()` and `reset_trigger()` directly.
- Verification uses `control_plane.verification.run_verification()` directly.
- Agent driving follows the existing CLI seam (`python -m agent`) as a subprocess.

No `control_plane/` internals are modified.

## Endpoints

- `GET /` — lightweight UI.
- `GET /api/list` — discovered scenarios + discovery errors.
- `POST /api/play` — synchronous play (JSON output).
- `GET /api/play/stream` — SSE live stream for play output.
- `POST /api/reset` — reset trigger + optional per-scenario reset script.
- `POST /api/playlist` — compose by message pillar and budget.
- `POST /api/verify` — synchronous verification report (JSON).
- `GET /api/verify/stream` — SSE stream for verify progress/report.
- `GET /healthz` — liveness.

## Security guardrails

- Launch path is `python -m web.control_plane`, which enforces loopback-only bind and rejects non-loopback hosts (including `0.0.0.0`) before server startup.
- UI/API are same-origin only; state-changing actions require CSRF token checks (`SameSite=Strict` cookie + header/query token).
- Baseline security headers are applied (`CSP`, `X-Frame-Options`, `X-Content-Type-Options`, `Referrer-Policy`, `Cache-Control`).
- Secret-safe output: lines are redacted for `GALILEO_*`, `SPLUNK_*`, and `OPENAI_*` patterns/values before being returned to browser streams/responses.

## Run

```sh
scripts/control-plane-web.sh
```

Default bind is `127.0.0.1:${CONTROL_PLANE_WEB_PORT:-8099}`.

## Verification checklist (parent runbook)

1. **Boot/import smoke check**
   - `scripts/control-plane-web.sh --help`
   - `python -c "from web.control_plane.app import create_app; create_app()"`
2. **Loopback enforcement**
   - Expected pass: `scripts/control-plane-web.sh --host 127.0.0.1 --port 8099`
   - Expected fail: `scripts/control-plane-web.sh --host 0.0.0.0 --port 8099`
3. **Registry seam proof (no code edits)**
   - Create `scenarios/<stub-id>/scenario.yaml` (+ minimal required companion files).
   - Call `GET /api/list` and confirm `<stub-id>` appears.
   - Delete the stub scenario folder.
4. **SSE path checks (local only)**
   - `GET /api/play/stream?...` emits trigger/apply + agent subprocess lines.
   - `GET /api/verify/stream?...` emits polling/progress lines and final report event.
5. **CLI fallback unchanged**
   - `scripts/control-plane.sh list` still works.
   - `python -m control_plane list` still works.

Live telemetry/browser demo execution remains in the parent foreground verification loop.
