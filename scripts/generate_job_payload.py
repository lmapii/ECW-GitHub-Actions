#!/usr/bin/env python3
"""Scaffolds a new .github/user/jobs/NN_<label>.json CI job file.

CI jobs run in the order they're created; .github/scripts/create_jobs.py
reads every .github/user/jobs/*.json file in sorted filename order, so each
file's name carries a leading "NN_" ordering prefix (01_, 02_, ...). This
script figures out the next free prefix, asks for the job's fields
interactively (or takes them as flags for scripting/CI use), and writes the
file -- so you never have to hand-write the JSON shape or manage the prefix
yourself.

See docs/04-jobs.md for the full job/command schema this produces, and what
each field means.

Interactive usage:
    python3 scripts/generate_job_payload.py

Non-interactive usage (one command, scriptable):
    python3 scripts/generate_job_payload.py \
        --label serial \
        --request-id gha-serial-001 \
        --name "Serial capture" \
        --duration-seconds 10 \
        --command '{"id":"mcu-serial","name":"MCU serial capture","command":"mcu.serial_log","attempts":1,"timeout_ms":2000,"parameters":{"filename":"gha-mcu.log"}}'

Repeat --command to add more than one command to the same job. Add
--jobs-dir to target a different jobs/ folder (default: .github/user/jobs).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

DEFAULT_JOBS_DIR = Path(".github/user/jobs")
_LABEL_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


def _nextPrefix(jobs_dir: Path) -> str:
    """Find the next free two-digit ordering prefix in jobs_dir."""
    used = set()
    if jobs_dir.exists():
        for existing in jobs_dir.glob("*.json"):
            prefix, _, _rest = existing.stem.partition("_")
            if prefix.isdigit():
                used.add(int(prefix))
    next_n = 1
    while next_n in used:
        next_n += 1
    return f"{next_n:02d}"


def _promptCommand() -> dict:
    print("\n  New command (leave 'command' empty to stop adding commands):")
    command = input("    command (e.g. delay, mcu.serial_log, camera.screenshot): ").strip()
    if not command:
        return {}

    command_id = input("    id (short, unique within this job): ").strip()
    name = input("    name (human-readable): ").strip()
    attempts = input("    attempts [1]: ").strip() or "1"
    timeout_ms = input("    timeout_ms [5000]: ").strip() or "5000"
    parameters_raw = input(
        "    parameters as JSON object, or leave empty [{}]: "
    ).strip()
    parameters = json.loads(parameters_raw) if parameters_raw else {}

    entry = {
        "id": command_id,
        "name": name,
        "command": command,
        "attempts": int(attempts),
        "timeout_ms": int(timeout_ms),
    }
    if parameters:
        entry["parameters"] = parameters
    return entry


def _interactiveSpec() -> tuple[str, dict]:
    label = input("Job label (used in the filename, e.g. 'serial'): ").strip()
    request_id = input("request_id (unique per job, e.g. 'gha-serial-001'): ").strip()
    name = input("name (human-readable job name): ").strip()
    duration_seconds = input("duration_seconds [10]: ").strip() or "10"

    commands = []
    while True:
        command = _promptCommand()
        if not command:
            break
        commands.append(command)

    if not commands:
        raise SystemExit("A job needs at least one command.")

    spec = {
        "request_id": request_id,
        "name": name,
        "duration_seconds": int(duration_seconds),
        "commands": commands,
    }
    return label, spec


def _flagSpec(args: argparse.Namespace) -> tuple[str, dict]:
    if not args.commands:
        raise SystemExit("--command is required at least once in non-interactive mode.")
    commands = [json.loads(raw) for raw in args.commands]
    spec = {
        "request_id": args.request_id,
        "name": args.name,
        "duration_seconds": args.duration_seconds,
        "commands": commands,
    }
    return args.label, spec


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--jobs-dir", type=Path, default=DEFAULT_JOBS_DIR)
    parser.add_argument("--label", help="Filename label, e.g. 'serial' -> 02_serial.json")
    parser.add_argument("--request-id")
    parser.add_argument("--name")
    parser.add_argument("--duration-seconds", type=int, default=10)
    parser.add_argument(
        "--command",
        dest="commands",
        action="append",
        help="One command as a JSON object; repeat for multiple commands.",
    )
    args = parser.parse_args()

    non_interactive = bool(args.label or args.request_id or args.commands)
    if non_interactive:
        if not (args.label and args.request_id and args.name):
            raise SystemExit("--label, --request-id, and --name are all required together.")
        label, spec = _flagSpec(args)
    else:
        label, spec = _interactiveSpec()

    if not _LABEL_PATTERN.match(label):
        raise SystemExit(
            f"Invalid label '{label}': use lowercase letters, digits, '_' or '-', starting with a letter/digit."
        )

    args.jobs_dir.mkdir(parents=True, exist_ok=True)
    prefix = _nextPrefix(args.jobs_dir)
    out_path = args.jobs_dir / f"{prefix}_{label}.json"
    if out_path.exists():
        raise SystemExit(f"{out_path} already exists.")

    out_path.write_text(json.dumps(spec, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
