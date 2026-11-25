"""Full scenario verification, including offline CLI and safe run isolation."""
import json
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from examples.integration_demo import ROOT, run_demo


class IntegrationDemoTests(unittest.TestCase):
    def setUp(self):
        parent = ROOT / "data" / "local"
        parent.mkdir(parents=True, exist_ok=True)
        self.temp = TemporaryDirectory(dir=parent)
        self.directory = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_full_offline_flow_and_saved_artifacts(self):
        with patch("socket.socket", side_effect=AssertionError("network forbidden")):
            report = run_demo(self.directory / "flow")
        self.assertEqual(report["status"], "passed")
        self.assertTrue(all(c["passed"] for c in report["checks"]))
        self.assertEqual([s["result"]["case"] for s in report["scenarios"]],
                         ["A", "B", "A", "C", "C", "SKIP", "C", "C", "C", "A"])
        self.assertEqual(report["final_memory"]["summary"]["record_days"], 9)
        directory = Path(report["run_directory"])
        state = json.loads((directory / "backend-state.json").read_text(encoding="utf-8"))
        self.assertEqual(state["cards"][2]["minutes"], 5)
        self.assertEqual(state["pending"]["demo:parent_change_request"]["status"], "approved_in_simulation")
        self.assertEqual(state["cards"][5]["content_id"], "integration-audio-l1")
        next_plan = json.loads((directory / "next-plan.json").read_text(encoding="utf-8"))
        self.assertEqual(next_plan["status"], "draft")
        self.assertEqual(next_plan["memory_context"]["summary"]["record_days"], 9)
        self.assertEqual(json.loads((directory / "report.json").read_text(encoding="utf-8")), report)

    def test_existing_directory_is_never_overwritten(self):
        sentinel = self.directory / "existing.txt"
        sentinel.write_text("keep", encoding="utf-8")
        with self.assertRaises(FileExistsError):
            run_demo(self.directory)
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep")
        self.assertFalse((self.directory / "memory.sqlite3").exists())

    def test_cli_success_and_failure_exit_status(self):
        destination = self.directory / "cli"
        command = [sys.executable, "-m", "examples.integration_demo", "--run-dir", str(destination)]
        first = subprocess.run(command, cwd=ROOT, capture_output=True, encoding="utf-8", check=True)
        summary = json.loads(first.stdout)
        self.assertEqual(summary["status"], "passed")
        report_before = (destination / "report.json").read_bytes()
        second = subprocess.run(command, cwd=ROOT, capture_output=True, encoding="utf-8")
        self.assertNotEqual(second.returncode, 0)
        self.assertEqual((destination / "report.json").read_bytes(), report_before)


if __name__ == "__main__":
    unittest.main()
