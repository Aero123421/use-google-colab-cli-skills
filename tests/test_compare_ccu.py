"""Behavioral checks; set COLAB_CCU_SCRIPT to validate the installed skill copy."""

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(os.environ.get("COLAB_CCU_SCRIPT", str(
    Path(__file__).resolve().parents[1] / "skills/colab-cli-reliable/scripts/compare_ccu.py")))
SPEC = importlib.util.spec_from_file_location("compare_ccu", SCRIPT)
CCU = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CCU)


def segment(runtime="a", start=0, seconds=1800, rate=2):
    return {"runtime_id": runtime, "start_seconds": start,
            "allocated_seconds": seconds, "rate_cu_per_hour": rate,
            "rate_source": "illustrative", "rate_evidence": "Fictional test arithmetic."}


def candidate(name="base", elapsed=1800, outputs=10, quality=True, segments=None):
    return {"name": name, "quality_passed": quality, "valid_outputs": outputs,
            "elapsed_seconds": elapsed,
            "allocation_segments": [segment()] if segments is None else segments}


def document(*candidates):
    return {"workload": "Same test input and output task", "quality_target": "Same validator",
            "required_valid_outputs": 10, "candidates": list(candidates or [candidate()])}


class ComparisonTests(unittest.TestCase):
    def test_arithmetic_and_per_output(self):
        row = CCU.compare(document())["eligible"][0]
        self.assertEqual(row["estimated_cu"], 1)
        self.assertEqual(row["cu_per_valid_output"], 0.1)

    def test_simultaneous_distinct_runtimes_are_summed(self):
        runtimes = [segment("cpu", seconds=1800, rate=2),
                    segment("gpu", seconds=900, rate=4)]
        row = CCU.compare(document(candidate(segments=runtimes)))["eligible"][0]
        self.assertEqual(row["estimated_cu"], 2)
        self.assertEqual(row["elapsed_seconds"], 1800)

    def test_staged_preparation_is_included(self):
        stages = [segment("cpu", seconds=900, rate=2),
                  segment("gpu", start=900, seconds=900, rate=6)]
        row = CCU.compare(document(candidate(segments=stages)))["eligible"][0]
        self.assertEqual(row["estimated_cu"], 2)

    def test_same_runtime_overlap_rejected_and_adjacent_rates_allowed(self):
        overlapping = [segment(seconds=900), segment(start=800, seconds=900)]
        with self.assertRaisesRegex(ValueError, "overlapping"):
            CCU.compare(document(candidate(segments=overlapping)))
        adjacent = [segment(seconds=900, rate=2), segment(start=900, seconds=900, rate=4)]
        self.assertEqual(CCU.compare(document(candidate(segments=adjacent)))[
            "eligible"][0]["estimated_cu"], 1.5)

    def test_higher_hourly_rate_can_be_cheaper_and_fastest_can_differ(self):
        slow = candidate("low rate", 3600, segments=[segment(seconds=3600, rate=2)])
        fast = candidate("high rate", 600, segments=[segment(seconds=600, rate=6)])
        cheapest = candidate("staged", 1200, segments=[
            segment("cpu", seconds=900, rate=0.5),
            segment("gpu", start=900, seconds=300, rate=6)])
        result = CCU.compare(document(slow, fast, cheapest))
        self.assertEqual([r["name"] for r in result["eligible"]],
                         ["staged", "high rate", "low rate"])
        self.assertEqual(result["cheapest"], "staged")
        self.assertEqual(result["fastest"], "high rate")

    def test_quality_and_exact_output_count_gate(self):
        result = CCU.compare(document(candidate("pass"), candidate("bad quality", quality=False),
            candidate("too few", outputs=9), candidate("surplus", outputs=11),
            candidate("empty", outputs=0, quality=False)))
        self.assertEqual([r["name"] for r in result["eligible"]], ["pass"])
        reasons = {r["name"]: r["exclusion_reasons"] for r in result["excluded"]}
        self.assertEqual(reasons["bad quality"], ["quality_failed"])
        self.assertEqual(reasons["surplus"], ["valid_output_count_mismatch"])
        self.assertIsNone(result["excluded"][-1]["cu_per_valid_output"])

    def test_inclusive_budget_and_deadline(self):
        self.assertEqual(CCU.compare(document(), max_cus=1, deadline_seconds=1800)["status"], "ok")
        result = CCU.compare(document(), max_cus=0.99, deadline_seconds=1799)
        self.assertEqual(result["excluded"][0]["exclusion_reasons"],
                         ["cu_budget_exceeded", "deadline_exceeded"])

    def test_no_eligible_result_is_explicit(self):
        result = CCU.compare(document(candidate(quality=False)))
        self.assertEqual(result["status"], "no_eligible_candidates")
        self.assertEqual(result["eligible"], [])
        self.assertIsNone(result["cheapest"])
        self.assertIsNone(result["fastest"])

    def test_nonfinite_negative_and_boolean_numeric_fields_rejected(self):
        for field in ("start_seconds", "allocated_seconds", "rate_cu_per_hour"):
            for invalid in (float("nan"), float("inf"), -1, True, "1"):
                with self.subTest(field=field, invalid=invalid):
                    data = document()
                    data["candidates"][0]["allocation_segments"][0][field] = invalid
                    with self.assertRaises(ValueError):
                        CCU.compare(data)
        for field in ("valid_outputs", "elapsed_seconds"):
            for invalid in (float("nan"), -1, False):
                with self.subTest(field=field, invalid=invalid):
                    data = document()
                    data["candidates"][0][field] = invalid
                    with self.assertRaises(ValueError):
                        CCU.compare(data)

    def test_required_count_and_workload_target_are_explicit(self):
        for field, invalids in (("required_valid_outputs", (0, -1, True, 1.5)),
                               ("workload", ("", "  ", None)),
                               ("quality_target", ("", None))):
            for invalid in invalids:
                with self.subTest(field=field, invalid=invalid):
                    data = document()
                    data[field] = invalid
                    with self.assertRaises(ValueError):
                        CCU.compare(data)

    def test_evidence_and_intervals_are_required(self):
        invalid_documents = [document(candidate(segments=[])),
                             document(candidate(elapsed=100))]
        for field, value in (("rate_source", "guessed"), ("rate_evidence", "")):
            data = document()
            data["candidates"][0]["allocation_segments"][0][field] = value
            invalid_documents.append(data)
        for data in invalid_documents:
            with self.subTest(data=data), self.assertRaises(ValueError):
                CCU.compare(data)

    def test_zero_rate_with_explicit_evidence_is_allowed(self):
        row = CCU.compare(document(candidate(segments=[segment(rate=0)])))["eligible"][0]
        self.assertEqual(row["estimated_cu"], 0)

    def test_duplicate_names_and_non_boolean_quality_rejected(self):
        with self.assertRaisesRegex(ValueError, "duplicate"):
            CCU.compare(document(candidate(), candidate()))
        with self.assertRaisesRegex(ValueError, "boolean"):
            CCU.compare(document(candidate(quality=1)))

    def test_computed_overflow_rejected(self):
        with self.assertRaises(ValueError):
            CCU.compare(document(candidate(elapsed=1e308,
                segments=[segment(seconds=1e308, rate=1e308)])))


class CommandLineTests(unittest.TestCase):
    def run_cli(self, text, *args):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "comparison.json"
            path.write_text(text, encoding="utf-8")
            return subprocess.run([sys.executable, str(SCRIPT), "--input", str(path),
                "--json", *args], text=True, capture_output=True, check=False)

    def test_success_and_no_eligible_exit_codes(self):
        success = self.run_cli(json.dumps(document()))
        self.assertEqual(success.returncode, 0, success.stderr)
        self.assertEqual(json.loads(success.stdout)["cheapest"], "base")
        excluded = self.run_cli(json.dumps(document()), "--max-cus", "0")
        self.assertEqual(excluded.returncode, 1)
        self.assertEqual(json.loads(excluded.stdout)["status"], "no_eligible_candidates")

    def test_invalid_json_and_nonfinite_cli_limit_produce_json_errors(self):
        for text, args in (("{bad}", ()), ("{\"workload\":NaN}", ()),
                           ('{"workload":"a","workload":"b"}', ()),
                           (json.dumps(document()), ("--max-cus", "nan")),
                           (json.dumps(document()), ("--deadline-seconds", "-1"))):
            with self.subTest(text=text, args=args):
                result = self.run_cli(text, *args)
                self.assertEqual(result.returncode, 2)
                parsed = json.loads(result.stdout, parse_constant=CCU.reject_constant)
                self.assertEqual(parsed["status"], "invalid_input")

    def test_shipped_fictional_example(self):
        example = SCRIPT.parent.parent / "assets/cost-comparison.example.json"
        result = self.run_cli(example.read_text(encoding="utf-8"))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        rows = json.loads(result.stdout)
        self.assertEqual(rows["eligible"][0]["estimated_cu"], 0.625)
        self.assertIn("CPU preparation", rows["cheapest"])
        self.assertIn("higher hourly rate", rows["fastest"])
        self.assertTrue(all(r["rate_sources"] == ["illustrative"] for r in rows["eligible"]))


if __name__ == "__main__":
    unittest.main()
