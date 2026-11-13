#!/usr/bin/env python3
"""Compare supplied CU estimates without network, authentication, or allocation.

All candidates assert the same workload and quality_target. Required output count
is exact for a fair comparison; surplus output is excluded, not rewarded. Include
all preparation, allocation, transfer, compile, execution, export, and idle time.
Segments use seconds relative to workflow start; different runtimes may overlap.
Use per-runtime rates, not an account aggregate repeated for each runtime. Rates
and quality are caller-supplied evidence, never measured or verified by this tool.
Exit codes: 0 = eligible candidates, 1 = none eligible, 2 = invalid input.
"""

import argparse
import json
import math
import sys
from pathlib import Path


def number(value, field):
    """Accept only finite, nonnegative JSON numbers, never booleans."""
    if type(value) not in (int, float):
        raise ValueError(f"{field} must be a finite nonnegative number")
    try:
        result = float(value)
    except OverflowError:
        result = math.inf
    if not math.isfinite(result) or result < 0:
        raise ValueError(f"{field} must be a finite nonnegative number")
    return result


def count(value, field, minimum=0):
    number(value, field)
    if type(value) is not int or value < minimum:
        raise ValueError(f"{field} must be an integer >= {minimum}")
    return value


def text_field(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a nonempty string")
    return value.strip()


def object_field(value, field):
    if not isinstance(value, dict):
        raise ValueError(f"{field} must be an object")
    return value


def later(a, b):
    # Avoid false overlaps from float addition (e.g. 0.1 + 0.2 versus 0.3).
    return a > b and not math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-9)


def compare(document, max_cus=None, deadline_seconds=None):
    document = object_field(document, "input")
    workload = text_field(document.get("workload"), "workload")
    target = text_field(document.get("quality_target"), "quality_target")
    required = count(document.get("required_valid_outputs"), "required_valid_outputs", 1)
    max_cus = None if max_cus is None else number(max_cus, "max_cus")
    deadline_seconds = (None if deadline_seconds is None else
                        number(deadline_seconds, "deadline_seconds"))
    candidates = document.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise ValueError("candidates must be a nonempty array")
    eligible, excluded, names = [], [], set()
    for index, raw in enumerate(candidates):
        candidate = object_field(raw, f"candidates[{index}]")
        name = text_field(candidate.get("name"), f"candidates[{index}].name")
        if name in names:
            raise ValueError(f"duplicate candidate name: {name}")
        names.add(name)
        quality = candidate.get("quality_passed")
        if type(quality) is not bool:
            raise ValueError(f"{name}.quality_passed must be a boolean")
        outputs = count(candidate.get("valid_outputs"), f"{name}.valid_outputs")
        elapsed = number(candidate.get("elapsed_seconds"), f"{name}.elapsed_seconds")
        segments = candidate.get("allocation_segments")
        if not isinstance(segments, list) or not segments:
            raise ValueError(f"{name}.allocation_segments must be a nonempty array")
        costs, intervals, sources = [], {}, set()
        for i, raw_segment in enumerate(segments):
            field = f"{name}.allocation_segments[{i}]"
            segment = object_field(raw_segment, field)
            runtime = text_field(segment.get("runtime_id"), f"{field}.runtime_id")
            start = number(segment.get("start_seconds"), f"{field}.start_seconds")
            duration = number(segment.get("allocated_seconds"), f"{field}.allocated_seconds")
            rate = number(segment.get("rate_cu_per_hour"), f"{field}.rate_cu_per_hour")
            source = segment.get("rate_source")
            if source not in ("illustrative", "observed"):
                raise ValueError(f"{field}.rate_source must be illustrative or observed")
            text_field(segment.get("rate_evidence"), f"{field}.rate_evidence")
            sources.add(source)
            end = number(start + duration, f"{field} end time")
            if later(end, elapsed):
                raise ValueError(f"{field} extends beyond elapsed_seconds")
            if duration:
                intervals.setdefault(runtime, []).append((start, end))
            costs.append(number(rate * duration / 3600, f"{field} computed CU"))
        for runtime, spans in intervals.items():
            previous_end = 0.0
            for start, end in sorted(spans):
                if later(previous_end, start):
                    raise ValueError(f"{name}: overlapping segments for runtime {runtime}")
                previous_end = end
        try:
            estimated = number(math.fsum(costs), f"{name} total CU")
        except OverflowError as exc:
            raise ValueError(f"{name} total CU is too large") from exc
        reasons = []
        if not quality:
            reasons.append("quality_failed")
        if outputs != required:
            reasons.append("valid_output_count_mismatch")
        if max_cus is not None and estimated > max_cus:
            reasons.append("cu_budget_exceeded")
        if deadline_seconds is not None and elapsed > deadline_seconds:
            reasons.append("deadline_exceeded")
        row = {"name": name, "estimated_cu": estimated,
               "cu_per_valid_output": estimated / outputs if outputs else None,
               "elapsed_seconds": elapsed, "valid_outputs": outputs,
               "quality_passed": quality, "rate_sources": sorted(sources),
               "exclusion_reasons": reasons}
        (excluded if reasons else eligible).append(row)
    eligible.sort(key=lambda row: (row["estimated_cu"], row["elapsed_seconds"], row["name"]))
    fastest = min(eligible, key=lambda row: (row["elapsed_seconds"],
                  row["estimated_cu"], row["name"]), default=None)
    return {"status": "ok" if eligible else "no_eligible_candidates",
            "workload": workload, "quality_target": target,
            "required_valid_outputs": required, "output_count_policy": "exact",
            "max_cus": max_cus, "deadline_seconds": deadline_seconds,
            "notice": "Estimates from supplied rates, durations, and quality assertions; "
                      "this tool does not measure tariffs, completeness, or quality.",
            "cheapest": eligible[0]["name"] if eligible else None,
            "fastest": fastest["name"] if fastest else None,
            "eligible": eligible, "excluded": excluded}


def reject_constant(value):
    raise ValueError(f"non-finite JSON constant is not allowed: {value}")


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="JSON comparison input")
    parser.add_argument("--max-cus", help="Inclusive total estimated CU budget per candidate")
    parser.add_argument("--deadline-seconds", help="Inclusive end-to-end elapsed-time limit")
    parser.add_argument("--json", action="store_true", help="Write machine-readable JSON")
    args = parser.parse_args(argv)
    try:
        with args.input.open(encoding="utf-8") as stream:
            document = json.load(stream, parse_constant=reject_constant,
                                 object_pairs_hook=unique_object)
        result = compare(document,
                         None if args.max_cus is None else float(args.max_cus),
                         None if args.deadline_seconds is None else float(args.deadline_seconds))
    except (OSError, ValueError) as exc:
        result = {"status": "invalid_input", "error": str(exc)}
        if args.json:
            print(json.dumps(result, ensure_ascii=False, allow_nan=False))
        else:
            print(f"Error: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(result, ensure_ascii=False, allow_nan=False, indent=2))
    else:
        print(f"Workload: {result['workload']}; target: {result['quality_target']}")
        print(f"Required valid outputs: exactly {result['required_valid_outputs']}")
        print(result["notice"])
        for row in result["eligible"] + result["excluded"]:
            state = ", ".join(row["exclusion_reasons"]) or "eligible"
            per_output = row["cu_per_valid_output"]
            unit = "n/a" if per_output is None else f"{per_output:.8g}"
            print(f"{row['name']}: {row['estimated_cu']:.8g} CU; {unit} CU/output; "
                  f"{row['elapsed_seconds']:.8g} s; {state}; "
                  f"rates={','.join(row['rate_sources'])}")
        print(f"Cheapest eligible: {result['cheapest'] or '(none)'}")
        print(f"Fastest eligible: {result['fastest'] or '(none)'}")
    return 0 if result["eligible"] else 1


if __name__ == "__main__":
    sys.exit(main())
