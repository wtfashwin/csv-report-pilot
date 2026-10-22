import csv
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent
SCRIPT = ROOT / "report_demo.py"


class ReportingDemoTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.performance = self.folder / "performance.csv"
        self.leads = self.folder / "leads.csv"
        for path in (self.performance, self.leads):
            path.write_bytes((ROOT / "fixtures" / path.name).read_bytes())
        self.output = self.folder / "report"

    def run_cli(self, **changes):
        values = dict(performance=self.performance, leads=self.leads,
                      previous_start="2026-10-05", previous_end="2026-10-11",
                      current_start="2026-10-12", current_end="2026-10-18",
                      output_dir=self.output)
        values.update(changes)
        args = [str(item) for pair in values.items()
                for item in ("--" + pair[0].replace("_", "-"), pair[1])]
        return subprocess.run([sys.executable, str(SCRIPT), *args],
                              capture_output=True, text=True, timeout=10)

    def rows(self, path):
        with path.open(newline="") as stream:
            return list(csv.reader(stream))

    def write_rows(self, path, rows):
        with path.open("w", newline="") as stream:
            csv.writer(stream).writerows(rows)

    def assert_rejected(self, **changes):
        result = self.run_cli(**changes)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("error:", result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertFalse(self.output.exists(), result.stderr)
        return result

    def test_valid_command_creates_expected_report(self):
        result = self.run_cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        receipt = json.loads((self.output / "receipt.json").read_text())
        previous, current = (receipt["periods"][key]["metrics"]
                             for key in ("previous", "current"))
        self.assertEqual(previous, dict(spend="280.00", impressions=3500,
                         clicks=140, reported_leads=14, ctr_percent="4.00",
                         cost_per_reported_lead="20.00"))
        self.assertEqual(current, dict(spend="315.00", impressions=4200,
                         clicks=210, reported_leads=21, ctr_percent="5.00",
                         cost_per_reported_lead="15.00"))
        for name, path in [("performance", self.performance), ("leads", self.leads)]:
            self.assertEqual(receipt["sources"][name]["rows"], 14)
            self.assertEqual(receipt["sources"][name]["sha256"],
                             hashlib.sha256(path.read_bytes()).hexdigest())
        self.assertEqual(receipt["validation"]["status"], "passed")
        self.assertEqual(len(receipt["formulas"]), 6)
        self.assertNotIn("raw_rows", receipt)
        html = (self.output / "report.html").read_text()
        for phrase in ["Synthetic demonstration", "invented formats", "clicks / impressions",
                       "spend / reported leads", "2026-10-05", "2026-10-18",
                       "performance.csv", "leads.csv", "@media print"]:
            self.assertIn(phrase, html)
        self.assertNotIn("<script", html.lower())
        self.assertNotIn('src="http', html.lower())

    def test_deterministic_outputs_and_decimal_addition(self):
        rows = self.rows(self.performance)
        for row in rows[1:]:
            row[4] = "0.10"
        self.write_rows(self.performance, rows)
        self.assertEqual(self.run_cli().returncode, 0)
        second = self.folder / "second"
        self.assertEqual(self.run_cli(output_dir=second).returncode, 0)
        for name in ("report.html", "receipt.json"):
            self.assertEqual((self.output / name).read_bytes(), (second / name).read_bytes())
        receipt = json.loads((self.output / "receipt.json").read_text())
        self.assertEqual(receipt["periods"]["current"]["metrics"]["spend"], "0.70")

    def test_zero_denominators_and_zero_baseline(self):
        for path, indexes in [(self.performance, (2, 3, 4)), (self.leads, (2,))]:
            rows = self.rows(path)
            for row in rows[1:]:
                for index in indexes:
                    row[index] = "0"
            self.write_rows(path, rows)
        self.assertEqual(self.run_cli().returncode, 0)
        receipt = json.loads((self.output / "receipt.json").read_text())
        for period in receipt["periods"].values():
            self.assertIsNone(period["metrics"]["ctr_percent"])
            self.assertIsNone(period["metrics"]["cost_per_reported_lead"])
        self.assertTrue(all(value is None for value in receipt["percent_changes"].values()))
        self.assertIn("N/A", (self.output / "report.html").read_text())

    def test_campaign_and_source_names_are_escaped(self):
        for path in (self.performance, self.leads):
            rows = self.rows(path)
            for row in rows[1:]:
                row[1] = '<script>alert("demo")</script>'
            self.write_rows(path, rows)
        renamed = self.folder / "performance<&>.csv"
        self.performance.rename(renamed)
        result = self.run_cli(performance=renamed)
        self.assertEqual(result.returncode, 0, result.stderr)
        html = (self.output / "report.html").read_text()
        self.assertIn("&lt;script&gt;", html)
        self.assertIn("performance&lt;&amp;&gt;.csv", html)
        self.assertNotIn("<script", html)

    def test_invalid_cells_headers_and_values_fail_closed(self):
        original = self.performance.read_bytes()
        mutations = [
            (0, 0, "day"), (1, 0, "2026-10-5"), (1, 0, "2026-02-30"),
            (1, 1, " "), (1, 2, "-1"), (1, 2, "1.5"), (1, 3, "NaN"),
            (1, 4, "NaN"), (1, 4, "Infinity"), (1, 4, "-1"),
            (1, 4, "0.001"), (1, 4, "1e2"), (1, 5, "EUR"),
        ]
        for row_index, column, value in mutations:
            with self.subTest(row=row_index, column=column, value=value):
                self.performance.write_bytes(original)
                rows = self.rows(self.performance)
                rows[row_index][column] = value
                self.write_rows(self.performance, rows)
                self.assert_rejected()
        for row_index in (0, 1):
            for change in ("extra", "missing"):
                with self.subTest(row=row_index, cells=change):
                    self.performance.write_bytes(original)
                    rows = self.rows(self.performance)
                    if change == "extra":
                        rows[row_index].append("unexpected")
                    else:
                        rows[row_index].pop()
                    self.write_rows(self.performance, rows)
                    self.assert_rejected()
        for invalid in (b"", original.splitlines()[0] + b"\n", b'"unclosed'):
            with self.subTest(contents=invalid[:30]):
                self.performance.write_bytes(invalid)
                self.assert_rejected()

    def test_duplicate_keys_missing_dates_mismatches_and_outside_dates(self):
        self.leads.write_bytes((ROOT / "fixtures/leads-duplicate.csv").read_bytes())
        self.assertIn("duplicate", self.assert_rejected().stderr)
        self.leads.write_bytes((ROOT / "fixtures/leads.csv").read_bytes())
        rows = self.rows(self.leads)
        self.write_rows(self.leads, rows[:-1])
        self.assertIn("keys", self.assert_rejected().stderr)
        rows = self.rows(self.performance)
        self.write_rows(self.performance, rows[:-1])
        self.assertIn("every date", self.assert_rejected().stderr)
        rows[1][0] = "2026-10-04"
        self.write_rows(self.performance, rows)
        self.assertIn("outside", self.assert_rejected().stderr)

    def test_period_boundaries(self):
        for changes in [dict(previous_end="2026-10-04"),
                        dict(current_end="2026-10-11"),
                        dict(current_start="2026-10-11"),
                        dict(previous_start="2026-1-05")]:
            with self.subTest(changes=changes):
                self.assert_rejected(**changes)

    def test_file_and_row_limits(self):
        self.performance.write_bytes(b" " * (2 * 1024 * 1024 + 1))
        self.assertIn("2 MiB", self.assert_rejected().stderr)
        header = self.rows(ROOT / "fixtures/performance.csv")[0]
        rows = [header]
        for index in range(10001):
            rows.append(["2026-10-05", str(index), "1", "1", "1.00", "USD"])
        self.write_rows(self.performance, rows)
        self.assertIn("10000", self.assert_rejected().stderr)

    def test_existing_directory_is_preserved(self):
        self.output.mkdir()
        sentinel = self.output / "report.html"
        sentinel.write_text("already here")
        result = self.run_cli()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(sentinel.read_text(), "already here")
        self.assertEqual(list(self.output.iterdir()), [sentinel])


if __name__ == "__main__":
    unittest.main()
