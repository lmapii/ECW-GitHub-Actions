# CI jobs

Everything about *what* runs against the booked board -- how many jobs,
what each one does, in what order -- is data, not workflow logic. It lives
entirely in `.github/user/jobs/*.json`.

## How jobs get created and run

1. `.github/scripts/create_jobs.py` reads every `*.json` file in
   `.github/user/jobs/`, in sorted filename order, and `POST`s each one to
   `/v1/ci/jobs` against your active booking.
2. The ECW backend runs CI jobs for a booking **in the order they were
   created** -- so filenames carry a leading two-digit ordering prefix
   (`01_`, `02_`, ...) that's stripped to produce each job's *label* (used
   for artifact filenames and internal bookkeeping). `01_wait.json` runs
   before `02_serial.json`, regardless of alphabetical filename order
   without the prefix.
3. `.github/scripts/poll_jobs.py` polls every created job to a terminal
   status (`succeeded`, `failed`, `cancelled`, `invalid`), writes each
   job's logs/results/summary as workflow artifacts, and fails the `Test`
   job if any CI job didn't succeed.

Add, remove, or reorder a job by adding, removing, or renaming a file --
`create_jobs.py` itself never needs to change.

## File shape

```json
{
  "request_id": "gha-serial-001",
  "name": "GitHub Actions serial job",
  "duration_seconds": 10,
  "commands": [
    {
      "id": "mcu-serial",
      "name": "MCU serial capture",
      "command": "mcu.serial_log",
      "attempts": 1,
      "timeout_ms": 2000,
      "parameters": { "filename": "gha-mcu.log" }
    }
  ]
}
```

| Field | Meaning |
| --- | --- |
| `request_id` | Your own idempotency/tracing key. Keep it unique per job. |
| `name` | Human-readable job name, shown in the ECW UI/API. |
| `duration_seconds` | Expected/allotted duration for the job. |
| `commands` | List of one or more commands, run in order, within this one job. |

Each command:

| Field | Meaning |
| --- | --- |
| `id` | Short, unique within this job's `commands` list. |
| `name` | Human-readable. |
| `command` | One of the backend's registered command names -- see below. |
| `attempts` | How many times to retry this command on failure. |
| `timeout_ms` | Per-attempt timeout. |
| `parameters` | Optional, command-specific arguments (e.g. an output filename). |

There is no nested `do`/`wait`/`expect`/`on_failure` schema -- commands are
flat and keyed by name.

## Commands this template's example jobs use

The three example files in this repo (`01_wait.json`, `02_serial.json`,
`03_camera.json`) exercise:

| Command | What it does | `parameters` |
| --- | --- | --- |
| `delay` | Waits, does nothing else. Useful as a settling buffer, e.g. right after flashing. | none |
| `mcu.serial_log` | Captures serial output from the board's MCU. | `filename` |
| `mpu.serial_log` | Captures serial output from the board's MPU, if it has one. | `filename` |
| `camera.screenshot` | Captures a still image from the board's assigned camera. | `filename` |

The full, authoritative list of supported commands lives in the ECW
backend itself (`_COMMAND_REGISTRY` in its `api/ci_jobs.py`) and can grow
independently of this template -- ask your ECW backend maintainers for the
current list for your deployment, or just try a command name: an
unsupported one is rejected by `POST /v1/ci/jobs` with a clear 4xx error
before any job is created.

## Scaffolding a new job file

Requirements: **Python 3.10+** on whatever machine you run it from (your
own laptop, most likely -- this script is a local authoring tool, it is
never invoked by the workflow itself). No third-party packages -- standard
library only, so no virtualenv/`pip install` step needed. Check your
version with `python3 --version` first if you're not sure.

```bash
python3 scripts/generate_job_payload.py
```

Prompts for the job's label, `request_id`, `name`, `duration_seconds`, and
one or more commands, then writes `.github/user/jobs/NN_<label>.json` with
the next free ordering prefix automatically. For scripting/CI use, pass
everything as flags instead -- run `python3 scripts/generate_job_payload.py
--help` for the non-interactive form.

### Example non-interactive invocation

```bash
python3 scripts/generate_job_payload.py \
  --label reset \
  --request-id gha-reset-001 \
  --name "GitHub Actions reset job" \
  --duration-seconds 5 \
  --command '{"id": "hard-reset", "name": "Hard reset the board", "command": "board.reset", "attempts": 1, "timeout_ms": 3000}'
```

Writes `.github/user/jobs/04_reset.json` (assuming `01`-`03` are already
taken, per the worked example in this repo) -- pass `--command` more than
once to add multiple commands to the same job.
