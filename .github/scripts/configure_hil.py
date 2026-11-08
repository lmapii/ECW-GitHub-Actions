"""Select one HIL sensor, prepare it, wait for active, then send frontend CSV values."""

from __future__ import annotations

import json
import os
from pathlib import Path
import queue
import threading
import time

from ecw_client import request_json
from hil_csv import read_csv, sensor_profile

HIL_DIR = Path(".github/user/hil")
ARTIFACT_DIR = Path("artifacts")
PREPARE_TIMEOUT_SECONDS = 180
MAX_WORDS_PER_REQUEST = 128


def okay(response, operation):
    if not isinstance(response, dict) or response.get("status") != "okay":
        raise RuntimeError(f"HIL {operation} did not report success.")


def prepare_and_wait(backend_url, api_key, booking_id, configuration_id,
                     *, timeout=PREPARE_TIMEOUT_SECONDS):
    """Wait for the same programming/activation response used by the frontend."""
    deadline = time.monotonic() + timeout
    results = queue.Queue(maxsize=1)

    def remaining():
        value = deadline - time.monotonic()
        if value <= 0:
            raise TimeoutError("HIL preparation did not become active within 180 seconds.")
        return value

    def run():
        try:
            context = {"booking_id": booking_id, "configuration_id": configuration_id}
            response = request_json(f"{backend_url}/v1/peripheral-prepare", api_key,
                                    method="POST", params=context, timeout=remaining())
            okay(response, "preparation")
            remaining()
            results.put((response, None))
        except Exception as error:
            results.put((None, error))

    # A slow response body cannot extend the client deadline. A timed-out worker
    # cannot send CSV values or issue a second preparation request. The existing
    # API returns success only after image preparation and activation succeed.
    worker = threading.Thread(target=run, daemon=True, name="hil-preparation")
    worker.start()
    try:
        state, error = results.get(timeout=max(0, deadline - time.monotonic()))
    except queue.Empty:
        raise TimeoutError("HIL preparation did not become active within 180 seconds.") from None
    if time.monotonic() > deadline:
        raise TimeoutError("HIL preparation did not become active within 180 seconds.")
    if error is not None:
        raise error
    return state


def configure(report):
    name = os.environ.get("HIL_SENSOR_NAME", "").strip()
    if not name:
        report["status"] = "skipped"
        print("Configure HIL skipped: HIL_SENSOR_NAME is not set.")
        return
    profile = sensor_profile(name)
    filename = os.environ.get("HIL_CSV_FILE", "").strip() or f"{profile['id']}.csv"
    # User paths are relative to .github/user/hil/, never arbitrary host files.
    path = (HIL_DIR / filename).resolve()
    if not path.is_relative_to(HIL_DIR.resolve()) or not path.is_file():
        raise ValueError("HIL_CSV_FILE must name an existing file under .github/user/hil/.")
    words, samples = read_csv(path, profile)
    backend_url = os.environ["ECW_BACKEND_URL"].rstrip("/")
    api_key = os.environ["ECW_API_KEY"]
    booking_id = int(os.environ["ECW_BOOKING_ID"])
    available = request_json(f"{backend_url}/v1/peripherals-list", api_key,
                             params={"booking_id": booking_id})
    if not isinstance(available, list):
        raise RuntimeError("HIL sensor list response is invalid.")
    matches = [row for row in available if str(row.get("name", "")).strip().casefold() == name.casefold()]
    if len(matches) != 1:
        raise ValueError(f"HIL_SENSOR_NAME must match exactly one available sensor name: {name!r}.")
    sensor_id = matches[0]["id"]
    context = {"booking_id": booking_id}
    selected = request_json(f"{backend_url}/v1/peripherals", api_key, params=context)
    if not isinstance(selected, list):
        raise RuntimeError("HIL selection response is invalid.")
    if len(selected) != 1 or selected[0].get("id") != sensor_id:
        configs = {str(sensor_id): {"name": "ci_hil", "elements": []}}
        okay(request_json(f"{backend_url}/v1/peripherals", api_key, method="PUT",
                          params={**context, "peripheral_config": json.dumps(configs)},
                          body=[sensor_id]), "selection")
        selected = request_json(f"{backend_url}/v1/peripherals", api_key, params=context)
    if (not isinstance(selected, list) or len(selected) != 1 or selected[0].get("id") != sensor_id
            or not isinstance(selected[0].get("configuration_id"), int)):
        raise RuntimeError("HIL selection is missing its saved configuration ID.")
    configuration_id = selected[0]["configuration_id"]
    report.update(sensor=name, csv=filename, samples=samples, words=len(words),
                  booking_id=booking_id, configuration_id=configuration_id, sent_words=0)
    report["readiness"] = prepare_and_wait(backend_url, api_key, booking_id, configuration_id)
    for address in range(0, len(words), MAX_WORDS_PER_REQUEST):
        chunk = words[address:address + MAX_WORDS_PER_REQUEST]
        okay(request_json(f"{backend_url}/v1/peripheral-program-value", api_key, method="POST",
                          params={**context, "configuration_id": configuration_id},
                          body={"address": address, "type": "string",
                                "value": "\n".join(f"{word:04X}" for word in chunk)}, timeout=30),
             "CSV value write")
        report["sent_words"] += len(chunk)
    report["status"] = "succeeded"
    print(f"HIL {name} active: {samples} CSV samples ({len(words)} words) sent and verified.")


def main():
    report = {"status": "configuring"}
    try:
        configure(report)
    except Exception as error:
        report.update(status="failed", error=str(error))
        raise SystemExit(f"Configure HIL failed: {error}") from None
    finally:
        ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
        (ARTIFACT_DIR / "hil-configuration.json").write_text(
            json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
