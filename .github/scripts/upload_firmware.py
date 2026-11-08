"""Upload the build's single .bin to ECW storage without programming the board."""

from __future__ import annotations

import os
import re
from pathlib import Path

from ecw_client import request_json, upload_file, write_github_output

BUILD_DIR = Path("build")


def main() -> str:
    backend_url = os.environ["ECW_BACKEND_URL"].rstrip("/")
    api_key = os.environ["ECW_API_KEY"]
    booking_id = int(os.environ["ECW_BOOKING_ID"])
    bin_files = sorted(path for path in BUILD_DIR.glob("*.bin") if path.is_file())
    if len(bin_files) != 1:
        raise SystemExit("build/ must contain exactly one .bin file before uploading.")
    firmware = bin_files[0]
    if firmware.stat().st_size == 0:
        raise SystemExit("The firmware .bin file is empty.")

    # Send a backend-safe basename ourselves, preserving the extension and the
    # backend's 64-character limit. Flash must use this name, not the local one.
    code = re.sub(r"[^A-Za-z0-9._]", "_", firmware.stem)[:60] + ".bin"
    response = upload_file(
        f"{backend_url}/upload", api_key, firmware, code,
        params={"booking_id": booking_id},
    )
    if not isinstance(response, dict) or response.get("status") != "okay":
        raise SystemExit("Firmware upload did not report success; no flash was requested.")

    manifest = request_json(
        f"{backend_url}/v1/artifacts/my-uploads", api_key,
        params={"booking_id": booking_id},
    )
    items = manifest.get("items", []) if isinstance(manifest, dict) else []
    if not isinstance(items, list) or not any(
        isinstance(item, dict) and item.get("filename") == code for item in items
    ):
        raise SystemExit("Uploaded firmware is missing from ECW storage; no flash was requested.")

    write_github_output("firmware_code", code)
    print(f"Uploaded {firmware.name} as {code} to ECW storage. The board has not been flashed.")
    return code


if __name__ == "__main__":
    main()
