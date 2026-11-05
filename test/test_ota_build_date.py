import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from run_ota_regression import build_dates_match


class BuildDateMatchTests(unittest.TestCase):
    def test_iso_date_matches_itself(self):
        self.assertTrue(build_dates_match("2026-11-05", "2026-11-05"))

    def test_sarah_compiler_datetime_matches_iso_day(self):
        self.assertTrue(build_dates_match("2026-03-13", "Mar 13 2026 02:37:23"))

    def test_truncated_compiler_date_matches_iso_day(self):
        self.assertTrue(build_dates_match("2026-03-13", "Mar 13 202"))

    def test_different_day_does_not_match(self):
        self.assertFalse(build_dates_match("2026-03-13", "Mar 14 2026"))

    def test_different_year_does_not_match(self):
        self.assertFalse(build_dates_match("2026-03-13", "Mar 13 2025"))

    def test_short_year_prefix_does_not_match(self):
        self.assertFalse(build_dates_match("2026-03-13", "Mar 13 2"))

    def test_missing_observed_date_does_not_match(self):
        self.assertFalse(build_dates_match("2026-03-13", None))


if __name__ == "__main__":
    unittest.main()
