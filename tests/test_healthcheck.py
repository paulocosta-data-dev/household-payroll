from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from household_payroll.cli import _healthcheck


class HealthcheckTests(unittest.TestCase):
    def test_creates_runtime_directories(self) -> None:
        temporary_root = Path.cwd() / ".test-tmp"
        temporary_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=temporary_root) as temporary_directory:
            root = Path(temporary_directory)
            environment = {
                "APP_TIMEZONE": "Europe/Lisbon",
                "APP_DATA_DIR": str(root / "data"),
                "APP_REPORT_DIR": str(root / "reports"),
                "APP_LOG_DIR": str(root / "logs"),
            }
            with patch.dict(os.environ, environment, clear=False):
                self.assertEqual(_healthcheck(), 0)

            self.assertTrue((root / "data").is_dir())
            self.assertTrue((root / "reports").is_dir())
            self.assertTrue((root / "logs").is_dir())


if __name__ == "__main__":
    unittest.main()
