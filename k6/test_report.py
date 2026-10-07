import json
from pathlib import Path
import tempfile
import unittest

from evidence import read_metric_points
from report import assess_slo, render_html


class NativeDroppedIterationsTests(unittest.TestCase):
    def test_scenario_only_counters_exclude_other_load_phases(self):
        # Executor counters observed in k6 2.3.0 omit custom scenario tags.
        points = [
            {"metric": "dropped_iterations", "type": "Point", "data": {
                "time": "2026-10-07T12:57:59.373254379Z", "value": 1,
                "tags": {"scenario": "measurement"}}},
            {"metric": "dropped_iterations", "type": "Point", "data": {
                "time": "2026-10-07T12:57:59.373256003Z", "value": 1,
                "tags": {"scenario": "measurement"}}},
            {"metric": "dropped_iterations", "type": "Point", "data": {
                "time": "2026-10-07T13:08:00.444660297Z", "value": 1,
                "tags": {"scenario": "ramp_down"}}},
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "metrics.jsonl"
            path.write_text("".join(json.dumps(point) + "\n" for point in points), encoding="utf-8")
            metrics, issues, malformed = read_metric_points(path, 1000)
        self.assertEqual(metrics["dropped_iterations"]["sum"], 2)
        self.assertEqual(issues, [])
        self.assertEqual(malformed, 0)


class SloClassificationTests(unittest.TestCase):
    def test_strict_threshold_edges_and_inclusive_throughput(self):
        result = assess_slo({
            "p95_ms": 500,
            "p99_ms": 999.99,
            "error_rate": 0.01,
            "dropped_iterations": 0,
            "successful_rps": 99,
        }, 100)
        checks = {check["name"]: check["status"] for check in result["checks"]}
        self.assertEqual(checks, {
            "p95": "FAIL",
            "p99": "PASS",
            "errors": "FAIL",
            "dropped_iterations": "PASS",
            "throughput": "PASS",
        })
        self.assertEqual(result["status"], "FAIL")

    def test_missing_metrics_and_target_are_unavailable(self):
        result = assess_slo({"successful_rps": 100}, None)
        self.assertEqual(result["status"], "UNAVAILABLE")
        self.assertTrue(all(check["status"] == "UNAVAILABLE" for check in result["checks"]))


class HtmlSafetyTests(unittest.TestCase):
    def test_run_name_is_escaped_and_missing_client_data_is_unavailable(self):
        report = {
            "generated_at_utc": "2026-10-07T00:00:00Z",
            "tested_profile": {
                "ramp_up_seconds": 120, "start_rps": 100, "steady_seconds": 600,
                "ramp_down_seconds": 120, "scheduled_seconds": 840,
            },
            "runs": [{
                "run_id": "<script>alert(1)</script>", "rate": 100, "base_url": None,
                "profile": {}, "window": {}, "k6": {}, "diagnostics": {},
                "server": None, "assessment": assess_slo({}, 100),
                "source": {
                    "client_evidence_path": "missing", "client_status": "missing",
                    "server_evidence_path": "missing", "server_status": "missing",
                },
            }],
        }
        rendered = render_html(report)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", rendered)
        self.assertNotIn("<script>alert(1)</script>", rendered)
        self.assertIn("UNAVAILABLE", rendered)
        self.assertNotIn(">PASS<", rendered)


if __name__ == "__main__":
    unittest.main()
