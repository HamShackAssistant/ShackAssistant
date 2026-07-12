"""Lightweight tests for shack startup script process detection."""

from __future__ import annotations

import re
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
START_SHACK = REPO_ROOT / "scripts" / "start-shack.sh"


class StartShackProcessDetectionTests(unittest.TestCase):
    def test_cqrlog_uses_exact_process_name_matching(self) -> None:
        content = START_SHACK.read_text(encoding="utf-8")

        self.assertIn('start_app "CQRLOG" "cqrlog" 3 -x', content)
        self.assertIn('pgrep "$pgrep_flag" "$cmd"', content)
        self.assertNotRegex(content, r'pgrep\s+-f\s+"?\$?cmd"?.*CQRLOG')
        self.assertNotIn("pgrep -f cqrlog", content)

    def test_other_applications_keep_command_line_matching(self) -> None:
        content = START_SHACK.read_text(encoding="utf-8")

        self.assertIn('start_app "FLrig" "flrig" 3', content)
        self.assertIn('start_app "WSJT-X" "wsjtx" 5', content)
        self.assertIn(
            'start_app "GridTracker" "/opt/GridTracker2/gridtracker2" 3',
            content,
        )
        self.assertRegex(
            content,
            r'pgrep_flag="\$\{4:--f\}"',
        )

    def test_broad_and_exact_pgrep_differ_for_embedded_cqrlog_text(self) -> None:
        """Document why CQRLOG must not use pgrep -f."""
        sample_cmdline = "sleep 120 # cqrlog sandbox simulation"

        self.assertIsNotNone(re.search(r"cqrlog", sample_cmdline, re.IGNORECASE))
        self.assertNotEqual(Path(sample_cmdline.split()[0]).name, "cqrlog")


if __name__ == "__main__":
    unittest.main()
