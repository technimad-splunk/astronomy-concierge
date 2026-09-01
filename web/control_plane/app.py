from __future__ import annotations

import asyncio
import html
import json
import os
import re
import secrets
import subprocess
import sys
import threading
from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from markdown_it import MarkdownIt
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from control_plane.manifest import Scenario
from control_plane.paths import REPO_ROOT
from control_plane.registry import Registry, discover
from control_plane.triggers import TriggerError, TriggerResult, apply_triggers, reset_triggers
from control_plane.verification import (
    DEFAULT_INTERVAL_S,
    DEFAULT_TIMEOUT_S,
    run_verification,
)


APP_DIR = Path(__file__).resolve().parent
TEMPLATES = Jinja2Templates(directory=str(APP_DIR / "templates"))
CSRF_COOKIE = "control_plane_csrf"
CSRF_HEADER = "x-csrf-token"
SECRET_PREFIXES = ("GALILEO_", "SPLUNK_", "OPENAI_")
_SECRET_ENV_LINE_RE = re.compile(r"\b((?:GALILEO|SPLUNK|OPENAI)_[A-Z0-9_]+)\s*=\s*\S+")
_HARNESS_STUB_MESSAGE = "harness-stub"

_STATUS_GLYPH = {
    "pass": "PASS",
    "fail": "FAIL",
    "attested": "ATTESTED",
    "unverifiable": "UNVERIFIED",
    "error": "ERROR",
}


class PlayRequest(BaseModel):
    id: str
    prompt: str | None = None
    session_id: str | None = None
    no_drive: bool = True


class ResetRequest(BaseModel):
    id: str


class VerifyRequest(BaseModel):
    id: str
    timeout: float = Field(default=DEFAULT_TIMEOUT_S, gt=0)
    interval: float = Field(default=DEFAULT_INTERVAL_S, gt=0)


@dataclass
class PlaySummary:
    scenario_id: str
    trigger_applied: bool
    drive_attempted: bool
    exit_code: int


def _load_env() -> None:
    load_dotenv(dotenv_path=REPO_ROOT / ".env")


def _secret_values() -> list[str]:
    values: list[str] = []
    for key, value in os.environ.items():
        if key.startswith(SECRET_PREFIXES) and value:
            values.append(value)
    return values


def _redact_secret_like_content(text: str) -> str:
    redacted = text
    for value in _secret_values():
        redacted = redacted.replace(value, "[REDACTED]")
    return _SECRET_ENV_LINE_RE.sub(r"\1=[REDACTED]", redacted)


def _loopback_origin(request: Request) -> str:
    host = request.headers.get("host", "127.0.0.1")
    return f"{request.url.scheme}://{host}"


def _validate_same_origin(request: Request) -> None:
    expected_origin = _loopback_origin(request)
    origin = request.headers.get("origin")
    if origin and origin != expected_origin:
        raise HTTPException(status_code=403, detail="Cross-origin request rejected.")

    referer = request.headers.get("referer")
    if referer:
        parsed = urlsplit(referer)
        referer_origin = f"{parsed.scheme}://{parsed.netloc}"
        if referer_origin != expected_origin:
            raise HTTPException(status_code=403, detail="Cross-origin request rejected.")


def _ensure_csrf_cookie(response: Response, request: Request) -> str:
    existing = request.cookies.get(CSRF_COOKIE)
    if existing:
        return existing
    token = secrets.token_urlsafe(32)
    response.set_cookie(
        key=CSRF_COOKIE,
        value=token,
        httponly=False,
        samesite="strict",
        secure=False,
        path="/",
    )
    return token


def _enforce_csrf(request: Request) -> None:
    _validate_same_origin(request)
    cookie_token = request.cookies.get(CSRF_COOKIE)
    header_token = request.headers.get(CSRF_HEADER)
    if not cookie_token or not header_token or cookie_token != header_token:
        raise HTTPException(status_code=403, detail="CSRF validation failed.")


def _enforce_csrf_query(request: Request, csrf_token: str | None) -> None:
    _validate_same_origin(request)
    cookie_token = request.cookies.get(CSRF_COOKIE)
    if not cookie_token or not csrf_token or cookie_token != csrf_token:
        raise HTTPException(status_code=403, detail="CSRF validation failed.")


def _scenario_payload(s: Scenario) -> dict[str, Any]:
    drive_prompt = ""
    for trigger in s.triggers:
        candidate = trigger.params.get("drive_prompt")
        if isinstance(candidate, str) and candidate.strip():
            drive_prompt = candidate
            break
    triggers = [
        {
            "type": trigger.type,
            "ref": trigger.ref,
            "params": dict(trigger.params),
        }
        for trigger in s.triggers
    ]
    return {
        "id": s.id,
        "title": s.title,
        "message": s.message,
        "order": s.order,
        "is_harness_fixture": s.message == _HARNESS_STUB_MESSAGE,
        "duration_min": s.duration_min,
        "drive_prompt": drive_prompt,
        "quiet_background": s.quiet_background,
        "trigger": triggers[0],
        "triggers": triggers,
        "expected_signals": {
            "galileo": list(s.expected_signals.galileo),
            "splunk": list(s.expected_signals.splunk),
        },
        "talk_track": s.talk_track,
        "reset": s.reset,
    }


@lru_cache(maxsize=1)
def _markdown_renderer() -> MarkdownIt:
    renderer = MarkdownIt("commonmark", {"html": False, "linkify": True, "typographer": True})
    renderer.enable("table")
    renderer.enable("strikethrough")
    return renderer


def _render_markdown_html(content: str) -> str:
    return _markdown_renderer().render(content)


def _scenario_script_payload(s: Scenario) -> dict[str, Any]:
    scenario_root = s.dir.resolve()
    script_path = s.talk_track_path.resolve()
    if script_path != scenario_root and scenario_root not in script_path.parents:
        raise HTTPException(status_code=400, detail=f"Invalid script path for scenario '{s.id}'.")
    if not script_path.is_file():
        raise HTTPException(status_code=404, detail=f"No script found for scenario '{s.id}'.")
    try:
        markdown = script_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Unable to read script for scenario '{s.id}': {exc}",
        ) from exc
    relative_path = script_path.relative_to(scenario_root)
    return {
        "id": s.id,
        "title": s.title,
        "script_path": str(relative_path),
        "script_markdown": markdown,
        "script_html": _render_markdown_html(markdown),
    }


def _scenario_script_document(s: Scenario, payload: dict[str, Any]) -> str:
    safe_title = html.escape(s.title)
    safe_id = html.escape(s.id)
    safe_source = html.escape(payload["script_path"])
    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>{safe_title} Demo Script</title>
    <style>
      :root {{
        color-scheme: light;
      }}
      body {{
        margin: 0;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        line-height: 1.65;
        color: #0f172a;
        background: #f8fafc;
      }}
      main {{
        max-width: 920px;
        margin: 0 auto;
        padding: 2rem 1.25rem 2.5rem;
      }}
      header {{
        margin-bottom: 1.2rem;
        border-bottom: 1px solid #cbd5e1;
        padding-bottom: 0.9rem;
      }}
      h1 {{
        margin: 0 0 0.25rem;
        font-size: 1.8rem;
      }}
      .meta {{
        margin: 0;
        color: #334155;
      }}
      h2, h3, h4 {{
        line-height: 1.3;
        margin: 1.25rem 0 0.6rem;
      }}
      p, li {{
        color: #1e293b;
      }}
      pre {{
        background: #0f172a;
        color: #e2e8f0;
        border: 1px solid #1e293b;
        border-radius: 8px;
        padding: 0.8rem;
        overflow-x: auto;
      }}
      code {{
        background: #e2e8f0;
        border-radius: 4px;
        padding: 0.08rem 0.28rem;
        font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
      }}
      pre code {{
        background: transparent;
        padding: 0;
      }}
      table {{
        width: 100%;
        border-collapse: collapse;
      }}
      th, td {{
        border: 1px solid #cbd5e1;
        padding: 0.45rem 0.55rem;
        text-align: left;
        vertical-align: top;
      }}
      th {{
        background: #e2e8f0;
      }}
      a {{
        color: #1d4ed8;
      }}
    </style>
  </head>
  <body>
    <main>
      <header>
        <h1>{safe_title}</h1>
        <p class="meta">Scenario: {safe_id}</p>
        <p class="meta">Source: {safe_source}</p>
      </header>
      {payload["script_html"]}
    </main>
  </body>
</html>
"""


def _registry_payload(reg: Registry, *, include_fixtures: bool = False) -> dict[str, Any]:
    scenarios = [
        s
        for s in reg.scenarios
        if include_fixtures or s.message != _HARNESS_STUB_MESSAGE
    ]
    return {
        "scenarios": [_scenario_payload(s) for s in scenarios],
        "errors": [{"folder": str(e.folder), "error": e.error} for e in reg.errors],
    }


def _runbook_payload() -> dict[str, Any]:
    runbook_path = REPO_ROOT / "docs" / "runbook.md"
    source_path = str(runbook_path.relative_to(REPO_ROOT))
    if not runbook_path.is_file():
        return {
            "available": False,
            "title": "Phase-6 SE Runbook",
            "source_path": source_path,
            "markdown": "",
            "html": "",
            "detail": "Runbook not available yet. Add docs/runbook.md to enable this view.",
        }
    try:
        markdown = runbook_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Unable to read runbook: {exc}") from exc
    return {
        "available": True,
        "title": "Phase-6 SE Runbook",
        "source_path": source_path,
        "markdown": markdown,
        "html": _render_markdown_html(markdown),
    }


def _trigger_result_lines(result: TriggerResult) -> list[str]:
    lines = [
        f"[{result.action}] {result.type} (ref={result.ref})",
        result.summary,
    ]
    if result.before or result.after:
        lines.append(f"state: {result.before!r} -> {result.after!r}")
    lines.extend(result.details)
    return lines


def _run_loadgen(action: str, emit: Callable[[str], None]) -> bool:
    script = REPO_ROOT / "scripts" / "loadgen.sh"
    if not script.is_file():
        emit(f"WARNING: {script} not found; skipping load-generator {action}.")
        return False
    proc = subprocess.run(
        ["bash", str(script), action],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    output = (proc.stdout or "") + (proc.stderr or "")
    for line in output.splitlines():
        emit(_redact_secret_like_content(line))
    return proc.returncode == 0


def _stream_agent(prompt: str, session_id: str, emit: Callable[[str], None]) -> int:
    cmd = [sys.executable, "-m", "agent", "--prompt", prompt, "--session-id", session_id]
    emit(f"Driving agent (session={session_id})")
    proc = subprocess.Popen(
        cmd,
        cwd=str(REPO_ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    assert proc.stdout is not None
    for raw_line in proc.stdout:
        emit(_redact_secret_like_content(raw_line.rstrip()))
    return proc.wait()


def _run_play(req: PlayRequest, emit: Callable[[str], None]) -> PlaySummary:
    reg = discover()
    try:
        scenario = reg.get(req.id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    emit(f"Playing '{scenario.id}' — {scenario.title}")
    trigger_labels = ", ".join(f"{t.type}(ref={t.ref})" for t in scenario.triggers)
    emit(f"message={scenario.message} trigger={trigger_labels}")

    if scenario.quiet_background:
        emit("Quiet-background mode enabled: draining load-generator.")
        if not _run_loadgen("quiet", emit):
            emit("WARNING: load-generator quiet action returned non-zero; continuing.")

    try:
        trigger_results = apply_triggers(scenario)
    except TriggerError as exc:
        raise HTTPException(status_code=500, detail=f"trigger apply failed: {exc}") from exc

    emit("Trigger(s) applied:")
    for trigger_result in trigger_results:
        for line in _trigger_result_lines(trigger_result):
            emit(line)

    prompt = req.prompt
    if not prompt:
        for trigger in scenario.triggers:
            candidate = trigger.params.get("drive_prompt")
            if isinstance(candidate, str) and candidate.strip():
                prompt = candidate
                break
    if req.no_drive or not prompt:
        if not req.no_drive and not prompt:
            emit("No prompt configured; trigger applied only.")
        return PlaySummary(
            scenario_id=scenario.id,
            trigger_applied=True,
            drive_attempted=False,
            exit_code=0,
        )

    session_id = req.session_id or f"play-{scenario.id}"
    exit_code = _stream_agent(prompt=prompt, session_id=session_id, emit=emit)
    if exit_code != 0:
        emit(f"WARNING: agent exited with code {exit_code}.")
    return PlaySummary(
        scenario_id=scenario.id,
        trigger_applied=True,
        drive_attempted=True,
        exit_code=exit_code,
    )


def _run_reset(req: ResetRequest, emit: Callable[[str], None]) -> int:
    reg = discover()
    try:
        scenario = reg.get(req.id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    emit(f"Resetting '{scenario.id}' — {scenario.title}")
    rc = 0

    try:
        results = reset_triggers(scenario)
        emit("Trigger(s) reset:")
        for result in results:
            for line in _trigger_result_lines(result):
                emit(line)
    except TriggerError as exc:
        emit(f"ERROR: trigger reset failed: {exc}")
        rc = 1

    reset_script = scenario.reset_path(REPO_ROOT)
    if reset_script.is_file():
        emit(f"Running per-scenario reset script: {reset_script}")
        proc = subprocess.run(
            ["bash", str(reset_script)],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
        )
        output = (proc.stdout or "") + (proc.stderr or "")
        for line in output.splitlines():
            emit(_redact_secret_like_content(line))
        if proc.returncode != 0:
            emit(f"WARNING: reset script exited with {proc.returncode}.")
            rc = rc or proc.returncode
    else:
        emit("No reset.sh found; trigger-level reset is authoritative.")

    emit("Restoring load-generator (idempotent).")
    if not _run_loadgen("restore", emit):
        emit("WARNING: load-generator restore action returned non-zero; continuing.")
    return rc


def create_app() -> FastAPI:
    _load_env()

    app = FastAPI(title="SE Control-Plane Web UI", version="0.1.0")
    app.mount("/static", StaticFiles(directory=str(APP_DIR / "static")), name="static")

    @app.middleware("http")
    async def apply_security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self'; "
            "img-src 'self' data:; "
            "connect-src 'self'; "
            "object-src 'none'; "
            "frame-ancestors 'none'; "
            "base-uri 'self'; "
            "form-action 'self'"
        )
        return response

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request):
        response = TEMPLATES.TemplateResponse(
            request,
            "index.html",
            {
                "default_timeout": DEFAULT_TIMEOUT_S,
                "default_interval": DEFAULT_INTERVAL_S,
            },
        )
        _ensure_csrf_cookie(response, request)
        return response

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/list")
    async def api_list(include_fixtures: bool = False) -> dict[str, Any]:
        return _registry_payload(discover(), include_fixtures=include_fixtures)

    @app.get("/api/scenarios/{scenario_id}/script")
    async def api_scenario_script(scenario_id: str) -> dict[str, Any]:
        reg = discover()
        try:
            scenario = reg.get(scenario_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return _scenario_script_payload(scenario)

    @app.get("/scenarios/{scenario_id}/script.html", response_class=HTMLResponse)
    async def scenario_script_document(scenario_id: str) -> HTMLResponse:
        reg = discover()
        try:
            scenario = reg.get(scenario_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        payload = _scenario_script_payload(scenario)
        return HTMLResponse(content=_scenario_script_document(scenario, payload))

    @app.get("/api/runbook")
    async def api_runbook() -> dict[str, Any]:
        return _runbook_payload()

    @app.post("/api/play")
    async def api_play(request: Request, payload: PlayRequest):
        _enforce_csrf(request)
        lines: list[str] = []
        summary = _run_play(payload, lines.append)
        return {
            "summary": asdict(summary),
            "output": [_redact_secret_like_content(line) for line in lines],
        }

    @app.get("/api/play/stream")
    async def api_play_stream(
        id: str,
        request: Request,
        prompt: str | None = None,
        session_id: str | None = None,
        no_drive: bool = True,
        csrf_token: str | None = None,
    ):
        _enforce_csrf_query(request, csrf_token)
        req = PlayRequest(id=id, prompt=prompt, session_id=session_id, no_drive=no_drive)
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[tuple[str, str] | None] = asyncio.Queue()

        def emit(message: str) -> None:
            loop.call_soon_threadsafe(queue.put_nowait, ("log", _redact_secret_like_content(message)))

        def worker() -> None:
            try:
                summary = _run_play(req, emit)
                payload = {
                    "ok": summary.exit_code == 0,
                    "summary": asdict(summary),
                }
                loop.call_soon_threadsafe(queue.put_nowait, ("done", json.dumps(payload)))
            except HTTPException as exc:
                payload = {"status": exc.status_code, "detail": exc.detail}
                loop.call_soon_threadsafe(queue.put_nowait, ("error", json.dumps(payload)))
            except Exception as exc:  # pragma: no cover - defensive
                payload = {"status": 500, "detail": _redact_secret_like_content(str(exc))}
                loop.call_soon_threadsafe(queue.put_nowait, ("error", json.dumps(payload)))
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, None)

        threading.Thread(target=worker, daemon=True).start()

        async def event_gen():
            while True:
                item = await queue.get()
                if item is None:
                    break
                event, data = item
                yield {"event": event, "data": data}

        return EventSourceResponse(event_gen())

    @app.post("/api/reset")
    async def api_reset(request: Request, payload: ResetRequest):
        _enforce_csrf(request)
        lines: list[str] = []
        exit_code = _run_reset(payload, lines.append)
        return {"ok": exit_code == 0, "exit_code": exit_code, "output": lines}

    @app.post("/api/verify")
    async def api_verify(request: Request, payload: VerifyRequest):
        _enforce_csrf(request)
        reg = discover()
        try:
            scenario = reg.get(payload.id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        report = run_verification(
            scenario,
            timeout_s=payload.timeout,
            interval_s=payload.interval,
        )
        return {
            "overall_pass": report.overall_pass,
            "scenario_id": report.scenario_id,
            "results": [asdict(r) for r in report.results],
        }

    @app.get("/api/verify/stream")
    async def api_verify_stream(
        request: Request,
        id: str,
        timeout: float = DEFAULT_TIMEOUT_S,
        interval: float = DEFAULT_INTERVAL_S,
        csrf_token: str | None = None,
    ):
        _enforce_csrf_query(request, csrf_token)
        reg = discover()
        try:
            scenario = reg.get(id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        interval = max(interval, 0.1)

        async def event_gen():
            yield {
                "event": "log",
                "data": f"Verifying '{scenario.id}' (timeout={timeout}s, interval={interval}s)",
            }
            verify_task = asyncio.create_task(
                asyncio.to_thread(
                    run_verification,
                    scenario,
                    timeout_s=timeout,
                    interval_s=interval,
                )
            )
            while not verify_task.done():
                yield {"event": "log", "data": "Polling Galileo/Splunk verification hooks..."}
                await asyncio.sleep(interval)

            report = await verify_task
            for result in report.results:
                detail = f"{result.backend}:{result.signal} -> {_STATUS_GLYPH[result.status]}"
                yield {"event": "log", "data": detail}
                if result.detail:
                    for line in result.detail.splitlines():
                        yield {"event": "log", "data": _redact_secret_like_content(line)}

            summary = {
                "overall_pass": report.overall_pass,
                "scenario_id": report.scenario_id,
                "totals": {
                    "pass": len(report.passed),
                    "fail_error": len(report.failed),
                    "attested": len(report.attested),
                    "unverified": len(report.unverifiable),
                },
            }
            yield {"event": "done", "data": json.dumps(summary)}

        return EventSourceResponse(event_gen())

    @app.exception_handler(HTTPException)
    async def http_error_handler(_: Request, exc: HTTPException):
        return JSONResponse(status_code=exc.status_code, content={"detail": str(exc.detail)})

    return app
