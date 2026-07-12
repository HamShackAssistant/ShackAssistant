"""Unit tests for DX Cluster spot parsing."""

from __future__ import annotations

import unittest

from modules.station_watch.dx_spot_parser import (
    DxSpot,
    frequency_khz_to_band,
    infer_mode,
    infer_mode_from_frequency_khz,
    is_login_prompt,
    is_partial_login_prompt,
    normalize_callsign,
    parse_spot_line,
    resolve_mode,
)


class DxSpotParserTests(unittest.TestCase):
    def test_standard_dxspider_spot(self) -> None:
        line = "DX de W3LPL:     14074.0  VB7F        FT8 CQ                     2026Z"
        spot = parse_spot_line(line)

        assert spot is not None
        self.assertEqual(spot.spotter, "W3LPL")
        self.assertEqual(spot.frequency_khz, 14074.0)
        self.assertEqual(spot.callsign, "VB7F")
        self.assertEqual(spot.comment, "FT8 CQ")
        self.assertEqual(spot.time_utc, "2026Z")
        self.assertEqual(spot.band, "20m")
        self.assertEqual(spot.mode, "FT8")
        self.assertEqual(spot.raw_line, line)

    def test_variable_whitespace(self) -> None:
        line = "DX de N4XYZ:      7025.5  W4C         CQ                         0132Z"
        spot = parse_spot_line(line)

        assert spot is not None
        self.assertEqual(spot.spotter, "N4XYZ")
        self.assertEqual(spot.callsign, "W4C")
        self.assertEqual(spot.comment, "CQ")
        self.assertEqual(spot.mode, "UNKNOWN")

    def test_ft8_mode_inference(self) -> None:
        self.assertEqual(infer_mode("FT8 CQ"), "FT8")

    def test_ft4_mode_inference(self) -> None:
        self.assertEqual(infer_mode("FT4 TEST"), "FT4")

    def test_cw_mode_inference(self) -> None:
        self.assertEqual(infer_mode("CW TEST"), "CW")

    def test_unknown_mode(self) -> None:
        self.assertEqual(infer_mode("CQ TEST"), "UNKNOWN")

    def test_frequency_ft8_inference(self) -> None:
        self.assertEqual(infer_mode_from_frequency_khz(21074.0), "FT8")
        self.assertEqual(infer_mode_from_frequency_khz(14074.0), "FT8")

    def test_frequency_ft4_inference(self) -> None:
        self.assertEqual(infer_mode_from_frequency_khz(14080.0), "FT4")

    def test_comment_overrides_frequency_inference(self) -> None:
        self.assertEqual(resolve_mode("FT4 special", 14074.0), "FT4")

    def test_voice_segment_frequency_remains_unknown(self) -> None:
        self.assertEqual(infer_mode_from_frequency_khz(14200.0), "UNKNOWN")
        self.assertEqual(resolve_mode("CQ special event", 7268.0), "UNKNOWN")

    def test_frequency_to_band_conversion(self) -> None:
        self.assertEqual(frequency_khz_to_band(14074.0), "20m")
        self.assertEqual(frequency_khz_to_band(7025.5), "40m")
        self.assertEqual(frequency_khz_to_band(50000.0), "6m")

    def test_lowercase_callsign_normalization(self) -> None:
        line = "DX de w3lpl:     14074.0  vb7f        FT8 CQ                     2026Z"
        spot = parse_spot_line(line)

        assert spot is not None
        self.assertEqual(spot.spotter, "W3LPL")
        self.assertEqual(spot.callsign, "VB7F")
        self.assertEqual(normalize_callsign("k1abc"), "K1ABC")

    def test_malformed_input_rejected(self) -> None:
        self.assertIsNone(parse_spot_line("not a spot"))
        self.assertIsNone(parse_spot_line("DX de BAD: incomplete"))

    def test_non_spot_lines_ignored(self) -> None:
        self.assertIsNone(parse_spot_line("Welcome to the cluster"))
        self.assertIsNone(parse_spot_line("W3LPL de KD4KZW: hello"))
        self.assertIsNone(parse_spot_line("Please enter your callsign:"))

    def test_login_prompt_detection(self) -> None:
        self.assertTrue(is_login_prompt("Please enter your callsign:"))
        self.assertTrue(is_login_prompt("login: "))
        self.assertFalse(is_login_prompt("DX de W3LPL: 14074.0 VB7F FT8 2026Z"))

    def test_partial_login_prompt_detection(self) -> None:
        self.assertTrue(is_partial_login_prompt("login:"))
        self.assertTrue(is_partial_login_prompt("Please enter your callsign:"))
        self.assertFalse(is_partial_login_prompt("Welcome to the cluster"))
        self.assertFalse(is_partial_login_prompt("user: configure your profile now"))


if __name__ == "__main__":
    unittest.main()
