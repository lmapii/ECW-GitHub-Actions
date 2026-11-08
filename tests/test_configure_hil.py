"""HIL cannot send data or reach firmware upload before recorded activation."""

import contextlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".github" / "scripts"))
import configure_hil
import upload_and_flash


class ConfigureHilTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.csv = self.directory / "bme280.csv"
        self.csv.write_text("sample,temperature_c,humidity_pct,pressure_hpa\n0,25,50,1013.25\n")
        self.calls = []
        self.selected = []
        for patcher in (
            patch.dict(os.environ, {"HIL_SENSOR_NAME": "BME280", "HIL_CSV_FILE": "",
                                    "ECW_BACKEND_URL": "https://example.test/api/",
                                    "ECW_API_KEY": "test-token", "ECW_BOOKING_ID": "123"}),
            patch.object(configure_hil, "HIL_DIR", self.directory),
            patch.object(configure_hil, "ARTIFACT_DIR", self.directory / "artifacts"),
            patch.object(configure_hil, "request_json", side_effect=self.request),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        capture = contextlib.redirect_stdout(io.StringIO())
        capture.__enter__()
        self.addCleanup(capture.__exit__, None, None, None)

    def request(self, url, key, **kwargs):
        self.calls.append((url, kwargs))
        self.assertEqual(key, "test-token")
        if url.endswith("/peripherals-list"):
            return [{"id": 5, "name": "BME280"}]
        if url.endswith("/peripherals"):
            if kwargs.get("method") == "PUT":
                self.assertEqual(kwargs["body"], [5])
                self.selected = [{"id": 5, "configuration_id": 456}]
                return {"status": "okay"}
            return self.selected
        if url.endswith("/peripheral-prepare") or url.endswith("/peripheral-program-value"):
            return {"status": "okay"}
        raise AssertionError(f"Unexpected API: {url}")

    def report(self):
        return json.loads((self.directory / "artifacts/hil-configuration.json").read_text())

    def test_uses_frontend_apis_to_prepare_then_send_physical_values(self):
        configure_hil.main()
        self.assertEqual([url.removeprefix("https://example.test/api") for url, _ in self.calls],
                         ["/v1/peripherals-list", "/v1/peripherals", "/v1/peripherals",
                          "/v1/peripherals", "/v1/peripheral-prepare", "/v1/peripheral-program-value"])
        self.assertEqual(self.calls[-1][1]["body"], {"address": 0, "type": "string", "value": "4100\n3200\n3F54"})
        self.assertEqual(self.report()["status"], "succeeded")
        self.assertEqual(self.report()["sent_words"], 3)

    def test_existing_selection_keeps_its_configuration_id(self):
        self.selected = [{"id": 5, "configuration_id": 456}]
        configure_hil.main()
        self.assertFalse(any(options.get("method") == "PUT" for _, options in self.calls))

    def test_blank_sensor_variable_skips_without_api_calls(self):
        with patch.dict(os.environ, {"HIL_SENSOR_NAME": ""}):
            configure_hil.main()
        self.assertEqual(self.calls, [])
        self.assertEqual(self.report()["status"], "skipped")

    def test_invalid_csv_never_selects_or_programs_anything(self):
        self.csv.write_text("sample,temperature_c\n0,200\n")
        with self.assertRaisesRegex(SystemExit, "outside"):
            configure_hil.main()
        self.assertEqual(self.calls, [])

    def test_csv_path_cannot_escape_user_hil_directory(self):
        with patch.dict(os.environ, {"HIL_CSV_FILE": "../private.csv"}):
            with self.assertRaisesRegex(SystemExit, "under .github/user/hil"):
                configure_hil.main()
        self.assertEqual(self.calls, [])

    def test_failed_preparation_never_sends_values(self):
        original = self.request
        def failed(url, *args, **kwargs):
            if url.endswith("/peripheral-prepare"):
                return {"status": "failed"}
            return original(url, *args, **kwargs)
        with patch.object(configure_hil, "request_json", side_effect=failed):
            with self.assertRaisesRegex(SystemExit, "preparation did not report success"):
                configure_hil.main()
        self.assertFalse(any(url.endswith("/peripheral-program-value") for url, _ in self.calls))

    def test_empty_preparation_response_never_sends_values(self):
        original = self.request
        def empty(url, *args, **kwargs):
            if url.endswith("/peripheral-prepare"):
                return {}
            return original(url, *args, **kwargs)
        with patch.object(configure_hil, "request_json", side_effect=empty):
            with self.assertRaisesRegex(SystemExit, "preparation did not report success"):
                configure_hil.main()
        self.assertFalse(any(url.endswith("/peripheral-program-value") for url, _ in self.calls))

    def test_preparation_timeout_prevents_csv_and_firmware_upload(self):
        original = configure_hil.prepare_and_wait
        release = threading.Event()
        api_request = self.request
        def blocked(url, *args, **kwargs):
            if url.endswith("/peripheral-prepare"):
                release.wait(2)
                return {"status": "okay"}
            return api_request(url, *args, **kwargs)
        try:
            with patch.object(configure_hil, "request_json", side_effect=blocked), patch.object(
                configure_hil, "prepare_and_wait", side_effect=lambda *args: original(*args, timeout=0.03)
            ):
                with self.assertRaisesRegex(SystemExit, "180 seconds"):
                    configure_hil.main()
            self.assertEqual(configure_hil.PREPARE_TIMEOUT_SECONDS, 180)
            self.assertFalse(any(url.endswith("/peripheral-program-value") for url, _ in self.calls))
        finally:
            release.set()

    def test_slow_preparation_request_cannot_extend_the_absolute_deadline(self):
        blocked = threading.Event()
        def slow(*_args, **_kwargs):
            blocked.wait(2)
            return {"status": "okay"}
        started = time.monotonic()
        try:
            with patch.object(configure_hil, "request_json", side_effect=slow):
                with self.assertRaises(TimeoutError):
                    configure_hil.prepare_and_wait("https://example.test/api", "test-token", 123, 456, timeout=0.03)
            self.assertLess(time.monotonic() - started, 0.5)
        finally:
            blocked.set()

    def test_100_samples_are_sent_as_consecutive_batches_of_at_most_128_words(self):
        self.csv.write_text("sample,temperature_c,humidity_pct,pressure_hpa\n" + "0,25,50,1013.25\n" * 100)
        configure_hil.main()
        writes = [options["body"] for url, options in self.calls if url.endswith("/peripheral-program-value")]
        self.assertEqual([body["address"] for body in writes], [0, 128, 256])
        self.assertEqual([len(body["value"].splitlines()) for body in writes], [128, 128, 44])

    def test_value_write_failure_stops_without_retry(self):
        original = self.request
        writes = []
        def failed(url, *args, **kwargs):
            if url.endswith("/peripheral-program-value"):
                writes.append(kwargs)
                return {"status": "failed"}
            return original(url, *args, **kwargs)
        self.csv.write_text("sample,temperature_c,humidity_pct,pressure_hpa\n" + "0,25,50,1013.25\n" * 100)
        with patch.object(configure_hil, "request_json", side_effect=failed):
            with self.assertRaisesRegex(SystemExit, "CSV value write"):
                configure_hil.main()
        self.assertEqual(len(writes), 1)
        self.assertEqual(self.report()["status"], "failed")

    def test_upload_step_runs_explicit_flash_only_after_upload_returns_its_stored_name(self):
        calls = []
        with patch.object(upload_and_flash.upload_firmware, "main", side_effect=lambda: calls.append("upload") or "stored.bin"), patch.object(upload_and_flash.flash_firmware, "main", side_effect=lambda: calls.append(os.environ["ECW_FIRMWARE_CODE"])):
            upload_and_flash.main()
        self.assertEqual(calls, ["upload", "stored.bin"])

    def test_upload_failure_prevents_explicit_flash_in_upload_step(self):
        with patch.object(upload_and_flash.upload_firmware, "main", side_effect=SystemExit("upload failed")), patch.object(upload_and_flash.flash_firmware, "main") as flash:
            with self.assertRaises(SystemExit):
                upload_and_flash.main()
            flash.assert_not_called()


if __name__ == "__main__":
    unittest.main()
