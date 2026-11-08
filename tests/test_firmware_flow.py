"""Exercise the CI scripts at their HTTP boundary without booking real hardware."""

import contextlib
from datetime import datetime, timedelta, timezone
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch
import urllib.error

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".github" / "scripts"))
import ecw_client
import flash_firmware
import upload_firmware
import wait_for_booking


def response(payload):
    result = MagicMock()
    result.__enter__.return_value.read.return_value = json.dumps(payload).encode()
    return result


class FirmwareFlowTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.build = self.directory / "build"
        self.build.mkdir()
        self.firmware = self.build / "my-app.bin"
        self.firmware.write_bytes(b"\x00\xff\r\nfirmware\x80")
        self.output = self.directory / "github-output"
        self.output.write_text("")
        env = {
            "ECW_BACKEND_URL": "https://example.test/api/",
            "ECW_API_KEY": "test-token",
            "ECW_BOOKING_ID": "123",
            "ECW_FIRMWARE_CODE": "my_app.bin",
            "ECW_BOOKING_WAIT_TIMEOUT_SECONDS": "30",
            "GITHUB_OUTPUT": str(self.output),
        }
        for target in (patch.dict(os.environ, env), patch.object(upload_firmware, "BUILD_DIR", self.build)):
            target.start()
            self.addCleanup(target.stop)
        self.log = io.StringIO()
        capture = contextlib.redirect_stdout(self.log)
        capture.__enter__()
        self.addCleanup(capture.__exit__, None, None, None)

    def test_upload_only_stores_and_publishes_verified_filename_then_explicit_flash(self):
        replies = [
            response({"status": "okay"}),
            response({"items": [{"filename": "my_app.bin"}]}),
            response({"status": "okay"}),
        ]
        with patch.object(ecw_client.urllib.request, "urlopen", side_effect=replies) as http:
            upload_firmware.main()
            self.assertEqual(http.call_count, 2, "Upload must never issue the flash POST")
            self.assertEqual(self.output.read_text(), "firmware_code=my_app.bin\n")
            self.assertNotIn("confirmed firmware", self.log.getvalue())
            flash_firmware.main()

        upload, listing, flash = [call.args[0] for call in http.call_args_list]
        self.assertEqual([req.get_method() for req in (upload, listing, flash)], ["POST", "GET", "POST"])
        self.assertEqual(upload.full_url, "https://example.test/api/upload?booking_id=123")
        self.assertIn(b'name="file"; filename="my_app.bin"', upload.data)
        self.assertIn(self.firmware.read_bytes(), upload.data)
        boundary = upload.get_header("Content-type").split("boundary=")[1]
        self.assertTrue(upload.data.endswith(f"\r\n--{boundary}--\r\n".encode()))
        self.assertEqual(listing.full_url, "https://example.test/api/v1/artifacts/my-uploads?booking_id=123")
        self.assertEqual(flash.full_url, "https://example.test/api/v1/artifacts/my-uploads?booking_id=123&code=my_app.bin")
        self.assertEqual(http.call_args_list[-1].kwargs["timeout"], 180)
        for req in (upload, listing, flash):
            self.assertEqual(req.get_header("X-api-key"), "test-token")
            self.assertEqual(req.get_header("User-agent"), ecw_client.USER_AGENT)
        self.assertNotIn("test-token", self.log.getvalue())

    def test_upload_uses_safe_name_under_64_characters_and_preserves_bin_extension(self):
        self.firmware.unlink()
        self.firmware = self.build / (("my release-" * 8) + '.bin')
        self.firmware.write_bytes(b"firmware")
        code = ("my_release_" * 8)[:60] + ".bin"
        with patch.object(ecw_client.urllib.request, "urlopen", side_effect=[
            response({"status": "okay"}), response({"items": [{"filename": code}]}),
        ]) as http:
            upload_firmware.main()
        self.assertEqual(len(code), 64)
        self.assertIn(f'filename="{code}"'.encode(), http.call_args_list[0].args[0].data)
        self.assertEqual(self.output.read_text(), f"firmware_code={code}\n")

    def test_missing_multiple_or_empty_binary_stops_before_any_http_call(self):
        with patch.object(ecw_client.urllib.request, "urlopen") as http:
            self.firmware.unlink()
            with self.assertRaises(SystemExit):
                upload_firmware.main()
            self.firmware.write_bytes(b"first")
            extra = self.build / "other.bin"
            extra.write_bytes(b"second")
            with self.assertRaises(SystemExit):
                upload_firmware.main()
            extra.unlink()
            self.firmware.write_bytes(b"")
            with self.assertRaises(SystemExit):
                upload_firmware.main()
            http.assert_not_called()

    def test_unsuccessful_upload_never_lists_or_flashes_or_publishes_a_code(self):
        with patch.object(ecw_client.urllib.request, "urlopen", return_value=response({"status": "failed"})) as http:
            with self.assertRaisesRegex(SystemExit, "upload did not report success"):
                upload_firmware.main()
        self.assertEqual(http.call_count, 1)
        self.assertEqual(self.output.read_text(), "")

    def test_missing_or_malformed_manifest_never_publishes_firmware_code(self):
        for manifest in ({"items": []}, {"items": [{"filename": "old.bin"}]}, {"items": None}, []):
            with self.subTest(manifest=manifest), patch.object(ecw_client.urllib.request, "urlopen", side_effect=[
                response({"status": "okay"}), response(manifest),
            ]) as http:
                with self.assertRaisesRegex(SystemExit, "missing from ECW storage"):
                    upload_firmware.main()
                self.assertEqual(http.call_count, 2)
                self.assertEqual(self.output.read_text(), "")

    def test_upload_http_failure_does_not_retry_or_publish_a_code(self):
        error = urllib.error.HTTPError("https://example.test", 500, "failed", {}, None)
        with patch.object(ecw_client.urllib.request, "urlopen", side_effect=error) as http:
            with self.assertRaises(urllib.error.HTTPError):
                upload_firmware.main()
        self.assertEqual(http.call_count, 1)
        self.assertEqual(self.output.read_text(), "")

    def test_flash_rejects_missing_or_unsafe_code_without_http_calls(self):
        for code in ("", "../firmware.bin", "my-app.bin", "a" * 61 + ".bin", "firmware.hex"):
            with self.subTest(code=code), patch.dict(os.environ, {"ECW_FIRMWARE_CODE": code}), patch.object(ecw_client.urllib.request, "urlopen") as http:
                with self.assertRaises(SystemExit):
                    flash_firmware.main()
                http.assert_not_called()

    def test_flash_200_with_failure_status_fails_the_job(self):
        with patch.object(ecw_client.urllib.request, "urlopen", return_value=response({"status": "failed"})) as http:
            with self.assertRaisesRegex(SystemExit, "flash did not report success"):
                flash_firmware.main()
        self.assertEqual(http.call_count, 1)

    def test_flash_http_failure_is_not_retried_or_reuploaded(self):
        error = urllib.error.HTTPError("https://example.test", 502, "flash failed", {}, None)
        with patch.object(ecw_client.urllib.request, "urlopen", side_effect=error) as http:
            with self.assertRaises(urllib.error.HTTPError):
                flash_firmware.main()
        self.assertEqual(http.call_count, 1)

    def test_wait_requires_active_not_just_confirmed_inside_the_session_window(self):
        now = datetime.now(timezone.utc)
        booking = {"start_utc": (now - timedelta(minutes=1)).isoformat(),
                   "end_utc": (now + timedelta(minutes=5)).isoformat()}
        with patch.object(wait_for_booking, "request_json", side_effect=[
            {**booking, "status": "confirmed"}, {**booking, "status": "active"},
        ]) as get, patch.object(wait_for_booking.time, "sleep") as sleep:
            wait_for_booking.main()
        self.assertEqual(get.call_count, 2)
        sleep.assert_called_once()

    def test_cancelled_booking_stops_waiting_without_uploading(self):
        now = datetime.now(timezone.utc)
        booking = {"status": "cancelled", "start_utc": now.isoformat(),
                   "end_utc": (now + timedelta(minutes=5)).isoformat()}
        with patch.object(wait_for_booking, "request_json", return_value=booking) as get, patch.object(wait_for_booking.time, "sleep") as sleep:
            with self.assertRaisesRegex(SystemExit, "cancelled"):
                wait_for_booking.main()
        get.assert_called_once()
        sleep.assert_not_called()


if __name__ == "__main__":
    unittest.main()
