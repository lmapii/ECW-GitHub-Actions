"""CSV values use the same columns, units, layouts and rounding as the frontend."""

from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".github" / "scripts"))
import hil_csv


class HilCsvTests(unittest.TestCase):
    def read(self, sensor, content):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "data.csv"
            path.write_text(content, encoding="utf-8")
            return hil_csv.read_csv(path, hil_csv.sensor_profile(sensor))

    def test_frontend_export_bme280_units_and_channel_order(self):
        words, samples = self.read("BME280", "sample,temperature_c,humidity_pct,pressure_hpa\r\n0,25,50,1013.25\r\n")
        self.assertEqual(words, [0x4100, 0x3200, 0x3F54])
        self.assertEqual(samples, 1)

    def test_reordered_named_columns_and_ignored_sample_numbers(self):
        words, _ = self.read("BME280", "index,Pressure (hPa),temp,Humidity (%)\n45,1013.25,25,50\n")
        self.assertEqual(words, [0x4100, 0x3200, 0x3F54])

    def test_semicolon_decimal_comma_and_unicode_minus(self):
        words, _ = self.read("ADXL345", "sample;x_g;y_g;z_g\n0;−1,5;0,5;1\n")
        self.assertEqual(words, [0xFE80, 0x0080, 0x0100])

    def test_headerless_and_tab_delimited_csv(self):
        for text in ("-1,0,1\n", "8,-1,0,1\n", "sample\tx\ty\tz\n8\t-1\t0\t1\n"):
            with self.subTest(text=text):
                self.assertEqual(self.read("ADXL345", text)[0], [0xFF00, 0, 0x0100])

    def test_adc_and_mic3_use_low_word_first_and_saturate_full_scale(self):
        for name in ("MCP3565R", "Pmod MIC3", "MIC3"):
            with self.subTest(sensor=name):
                words, _ = self.read(name, "sample,voltage_v\n0,1.2\n1,-1.2\n2,2.4\n3,-2.4\n")
                self.assertEqual(words, [0, 0x4000, 0, 0xC000, 0xFFFF, 0x7FFF, 0, 0x8000])

    def test_rounds_signed_half_values_like_javascript(self):
        self.assertEqual(self.read("ADXL345", "x,y,z\n-0.001953125,0.001953125,0\n")[0], [0, 1, 0])

    def test_blank_channels_are_zero_words_like_frontend_send(self):
        words, _ = self.read("BME280", "sample,temperature_c,humidity_pct,pressure_hpa\n0,25,,1013.25\n")
        self.assertEqual(words, [0x4100, 0, 0x3F54])

    def test_out_of_range_and_non_numeric_values_fail_before_sending(self):
        for value in ("86", "-41", "NaN", "Infinity", "1e999", "oops"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.read("BME280", f"sample,temperature_c\n0,{value}\n")

    def test_overlong_csv_fails_instead_of_silently_dropping_samples(self):
        with self.assertRaisesRegex(ValueError, "supports 5376"):
            self.read("ADXL345", "x,y,z\n" + "0,0,0\n" * 5377)

    def test_empty_or_header_only_files_fail(self):
        for text in ("", "sample,x,y,z\n", "sample,x,y,z\n0,,,\n"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                self.read("ADXL345", text)

    def test_example_files_all_contain_100_frontend_format_samples(self):
        root = Path(__file__).resolve().parent / "fixtures/hil"
        for name in ("BME280", "ADXL345", "MCP3565R", "Pmod MIC3"):
            profile = hil_csv.sensor_profile(name)
            with self.subTest(sensor=name):
                _, samples = hil_csv.read_csv(root / (profile["id"] + ".csv"), profile)
                self.assertEqual(samples, 100)


if __name__ == "__main__":
    unittest.main()
