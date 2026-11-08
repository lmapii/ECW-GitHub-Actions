"""Explicitly flash the stored MCU image selected by the Upload job."""

from __future__ import annotations

import os
import re

from ecw_client import request_json


def main() -> None:
    backend_url = os.environ["ECW_BACKEND_URL"].rstrip("/")
    api_key = os.environ["ECW_API_KEY"]
    booking_id = int(os.environ["ECW_BOOKING_ID"])
    code = os.environ.get("ECW_FIRMWARE_CODE", "")
    if not re.fullmatch(r"[A-Za-z0-9._]{1,60}\.bin", code):
        raise SystemExit("ECW_FIRMWARE_CODE must be the stored filename returned by Upload.")

    # This side effect is explicit and is never automatically retried. Upload
    # success, a recovered board, or a 200 response alone are not flash success.
    response = request_json(
        f"{backend_url}/v1/artifacts/my-uploads", api_key,
        method="POST", params={"booking_id": booking_id, "code": code}, timeout=180,
    )
    if not isinstance(response, dict) or response.get("status") != "okay":
        raise SystemExit("Firmware flash did not report success; CI tests must not run.")
    print(f"Backend confirmed firmware {code} flashed for booking {booking_id}.")


if __name__ == "__main__":
    main()
