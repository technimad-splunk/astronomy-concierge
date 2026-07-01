"""The SE control-plane CLI — ``list / play / reset / verify``.

A stable seam (demo-design §7.2): adding scenarios never changes this file.
Run via ``python -m control_plane <cmd>`` or ``scripts/control-plane.sh <cmd>``.

- ``list``              — show every drop-in scenario the registry discovered.
- ``play <id>``         — apply the scenario's trigger. For agent-side triggers,
                          the CLI prints guidance to drive via concierge web chat.
- ``reset <id>``        — trigger-level reset (authoritative) + the per-scenario
                          ``reset.sh`` if present; restores baseline.
- ``verify <id>``       — run the ``expected_signals`` auto-verification hook and
                          print a pass/fail report (Galileo real, live-queried;
                          Splunk reported as operator-attested with embedded
                          evidence — the ingest-only token can't query APM).
No secrets are printed — only what state changed and which backends were used.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

from .manifest import Scenario
from .paths import REPO_ROOT
from .registry import Registry, discover
from .triggers import TriggerError, apply_trigger, reset_trigger
from .verification import DEFAULT_INTERVAL_S, DEFAULT_TIMEOUT_S, run_verification

_STATUS_GLYPH = {
    "pass": "PASS",
    "fail": "FAIL",
    "attested": "ATTESTED",
    "unverifiable": "UNVERIFIED",
    "error": "ERROR",
}


def _load_env() -> None:
    load_dotenv(dotenv_path=REPO_ROOT / ".env")


def _print_trigger_result(result) -> None:
    print(f"  [{result.action}] {result.type} (ref={result.ref})")
    print(f"    {result.summary}")
    if result.before or result.after:
        print(f"    state: {result.before!r} -> {result.after!r}")
    for d in result.details:
        print(f"    {d}")


# --- list --------------------------------------------------------------------
def cmd_list(reg: Registry, args: argparse.Namespace) -> int:
    if not reg.scenarios and not reg.errors:
        print("No scenarios discovered under scenarios/*/scenario.yaml.")
        return 0
    print(f"Discovered {len(reg.scenarios)} scenario(s):\n")
    for s in reg.scenarios:
        g = ",".join(s.expected_signals.galileo) or "-"
        sp = ",".join(s.expected_signals.splunk) or "-"
        quiet = "  quiet_bg" if s.quiet_background else ""
        print(f"  {s.id}")
        print(f"      title    : {s.title}")
        print(f"      message  : {s.message}   duration: {s.duration_min} min{quiet}")
        print(f"      trigger  : {s.trigger.type} (ref={s.trigger.ref})")
        print(f"      signals  : galileo=[{g}] splunk=[{sp}]")
    if reg.errors:
        print(f"\n{len(reg.errors)} folder(s) failed to load:")
        for e in reg.errors:
            print(f"  ! {e.folder.name}: {e.error}")
    return 0


# --- play --------------------------------------------------------------------
def _drive_agent(scenario: Scenario, prompt: str, session_id: str) -> int:
    print(f"\nDriving the agent (session={session_id}):")
    print(f"  prompt: {prompt}")
    cmd = [sys.executable, "-m", "agent", "--prompt", prompt, "--session-id", session_id]
    proc = subprocess.run(cmd, cwd=str(REPO_ROOT))
    return proc.returncode


def _run_loadgen(action: str) -> bool:
    """Run ``scripts/loadgen.sh <action>``; return True on success."""
    script = REPO_ROOT / "scripts" / "loadgen.sh"
    if not script.is_file():
        print(f"  WARNING: {script} not found; skipping load-generator {action}.",
              file=sys.stderr)
        return False
    proc = subprocess.run(["bash", str(script), action], cwd=str(REPO_ROOT))
    return proc.returncode == 0


def cmd_play(reg: Registry, args: argparse.Namespace) -> int:
    try:
        scenario = reg.get(args.id)
    except KeyError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(f"Playing '{scenario.id}' — {scenario.title}")
    print(f"  message: {scenario.message}   trigger: {scenario.trigger.type}")

    if scenario.quiet_background:
        print("\nQuiet-background mode: draining the load-generator...")
        if not _run_loadgen("quiet"):
            print("  WARNING: load-generator drain returned non-zero; continuing.",
                  file=sys.stderr)

    try:
        result = apply_trigger(scenario)
    except TriggerError as exc:
        print(f"\nFATAL: trigger apply failed: {exc}", file=sys.stderr)
        return 1
    print("\nTrigger applied:")
    _print_trigger_result(result)

    prompt = args.prompt or scenario.trigger.params.get("drive_prompt")
    if scenario.trigger.type in {"tool_fault", "prompt_overlay", "rag_corpus"}:
        print(
            "\nAgent-side trigger applied on the running concierge service. "
            "Drive this scenario via the concierge web chat."
        )
        if prompt:
            print(f"\nDrive prompt:\n  {prompt}")
        else:
            print(
                "\nNo drive prompt is declared. Use the scenario caption talk track to "
                "drive the conversation in the web chat."
            )
        return 0

    if args.no_drive or not prompt:
        if not prompt and not args.no_drive:
            print(
                "\n(No --prompt and no trigger.params.drive_prompt — trigger applied only. "
                "Run the agent with your known-good prompt to drive the scenario, then "
                f"`verify {scenario.id}`.)"
            )
        return 0
    session_id = args.session_id or f"play-{scenario.id}"
    rc = _drive_agent(scenario, prompt, session_id)
    if rc != 0:
        print(f"\nWARNING: agent run exited {rc}.", file=sys.stderr)
    return rc


# --- reset -------------------------------------------------------------------
def cmd_reset(reg: Registry, args: argparse.Namespace) -> int:
    try:
        scenario = reg.get(args.id)
    except KeyError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(f"Resetting '{scenario.id}' — {scenario.title}")
    rc = 0
    try:
        result = reset_trigger(scenario)
        print("\nTrigger reset:")
        _print_trigger_result(result)
    except TriggerError as exc:
        print(f"\nERROR: trigger reset failed: {exc}", file=sys.stderr)
        rc = 1

    reset_script = scenario.reset_path(REPO_ROOT)
    if reset_script.is_file():
        print(f"\nRunning per-scenario reset script: {reset_script}")
        proc = subprocess.run(["bash", str(reset_script)], cwd=str(REPO_ROOT))
        if proc.returncode != 0:
            print(f"WARNING: reset.sh exited {proc.returncode}.", file=sys.stderr)
            rc = rc or proc.returncode
    else:
        print(f"\n(no reset.sh at {reset_script}; trigger-level reset is authoritative.)")

    print("\nRestoring load-generator (idempotent)...")
    if not _run_loadgen("restore"):
        print("  WARNING: load-generator restore returned non-zero; continuing.",
              file=sys.stderr)

    return rc


# --- verify ------------------------------------------------------------------
def cmd_verify(reg: Registry, args: argparse.Namespace) -> int:
    try:
        scenario = reg.get(args.id)
    except KeyError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if scenario.expected_signals.is_empty():
        print(f"'{scenario.id}' declares no expected_signals — nothing to verify.")
        return 0
    print(f"Verifying expected_signals for '{scenario.id}' "
          f"(timeout={args.timeout}s, poll every {args.interval}s)...\n")
    report = run_verification(scenario, timeout_s=args.timeout, interval_s=args.interval)
    for r in report.results:
        print(f"  [{_STATUS_GLYPH[r.status]:10}] {r.backend}:{r.signal}")
        if r.detail:
            # Indent every line so multi-line evidence (e.g. an attestation
            # block) stays aligned under its signal.
            for line in r.detail.splitlines():
                print(f"               {line}")
    print(
        f"\nSummary: {len(report.passed)} pass, {len(report.failed)} fail/error, "
        f"{len(report.attested)} attested, {len(report.unverifiable)} unverified."
    )
    overall = "PASS" if report.overall_pass else "FAIL"
    print(
        f"Overall: {overall}  (attested = operator-verified out-of-band; "
        "attested/unverified signals do not fail the run)"
    )
    return 0 if report.overall_pass else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="control_plane",
        description="SE control plane for the Galileo x Splunk scenario harness.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="list discovered scenarios")

    p_play = sub.add_parser(
        "play", help="apply a scenario trigger (agent-side triggers are web-driven)"
    )
    p_play.add_argument("id")
    p_play.add_argument("--prompt", help="prompt to drive the agent with after applying the trigger")
    p_play.add_argument("--session-id", help="session id for the agent run")
    p_play.add_argument("--no-drive", action="store_true", help="apply the trigger only; do not run the agent")

    p_reset = sub.add_parser("reset", help="reset a scenario (trigger reset + reset.sh)")
    p_reset.add_argument("id")

    p_verify = sub.add_parser("verify", help="auto-verify a scenario's expected_signals")
    p_verify.add_argument("id")
    p_verify.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_S, help="poll timeout seconds")
    p_verify.add_argument("--interval", type=float, default=DEFAULT_INTERVAL_S, help="poll interval seconds")

    return parser


def main(argv: list[str] | None = None) -> int:
    _load_env()
    parser = build_parser()
    args = parser.parse_args(argv)
    reg = discover()

    dispatch = {
        "list": cmd_list,
        "play": cmd_play,
        "reset": cmd_reset,
        "verify": cmd_verify,
    }
    return dispatch[args.command](reg, args)


if __name__ == "__main__":
    raise SystemExit(main())
