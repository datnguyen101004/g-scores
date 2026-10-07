#!/usr/bin/env python3
"""Create compact, read-only evidence from k6, monitor, and Nginx artifacts."""

from __future__ import annotations

import argparse
import calendar
import datetime as dt
import json
import math
import os
import re
import sys
from collections import defaultdict
from pathlib import Path


SCHEMA_VERSION = 1
NANOSECONDS_PER_SECOND = 1_000_000_000
NANOSECONDS_PER_MILLISECOND = 1_000_000
POINT_METRICS = frozenset((
    "http_req_duration",
    "lookup_errors",
    "lookup_success",
    "lookup_started",
    "measurement_window_start",
    "dropped_iterations",
))
STUDENT_PATH = re.compile(r"^/api/students/[0-9]{8}$")
RFC3339 = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2})T(?P<time>\d{2}:\d{2}:\d{2})"
    r"(?:\.(?P<fraction>\d+))?(?P<offset>Z|[+-]\d{2}:?\d{2})$"
)


class EvidenceError(ValueError):
    """The source evidence is absent, incomplete, or internally inconsistent."""


def finite_number(value):
    if isinstance(value, bool) or value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def nonnegative_integer(value, label):
    parsed = finite_number(value)
    if parsed is None or parsed < 0 or not parsed.is_integer():
        raise EvidenceError(f"{label} must be a non-negative integer")
    return int(parsed)


def positive_integer(value, label):
    parsed = nonnegative_integer(value, label)
    if parsed < 1:
        raise EvidenceError(f"{label} must be a positive integer")
    return parsed


def parse_timestamp_ns(value):
    """Parse RFC3339 seconds plus arbitrary fractional precision on Python 3.9."""
    if not isinstance(value, str):
        return None
    match = RFC3339.match(value)
    if match is None:
        return None
    offset_text = match.group("offset")
    if offset_text == "Z":
        timezone = dt.timezone.utc
    else:
        compact_offset = offset_text[1:].replace(":", "")
        try:
            offset_minutes = int(compact_offset[:2]) * 60 + int(compact_offset[2:])
        except ValueError:
            return None
        if offset_minutes > 23 * 60 + 59:
            return None
        if offset_text[0] == "-":
            offset_minutes = -offset_minutes
        timezone = dt.timezone(dt.timedelta(minutes=offset_minutes))
    try:
        local = dt.datetime.strptime(
            f"{match.group('date')}T{match.group('time')}", "%Y-%m-%dT%H:%M:%S"
        ).replace(tzinfo=timezone)
        seconds = calendar.timegm(local.astimezone(dt.timezone.utc).timetuple())
    except (OverflowError, ValueError):
        return None
    fraction = match.group("fraction") or ""
    nanoseconds = int((fraction + "000000000")[:9])
    return seconds * NANOSECONDS_PER_SECOND + nanoseconds


def utc_from_ns(value):
    if value is None:
        return None
    try:
        seconds, nanoseconds = divmod(int(value), NANOSECONDS_PER_SECOND)
        instant = dt.datetime.fromtimestamp(seconds, tz=dt.timezone.utc).replace(
            microsecond=nanoseconds // 1000
        )
    except (OSError, OverflowError, ValueError):
        return None
    return instant.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def utc_from_ms(value):
    if value is None:
        return None
    return utc_from_ns(int(value) * NANOSECONDS_PER_MILLISECOND)


def percentile(sorted_values, fraction):
    if not sorted_values:
        return None
    position = (len(sorted_values) - 1) * fraction
    low = int(position)
    high = min(low + 1, len(sorted_values) - 1)
    return sorted_values[low] + (sorted_values[high] - sorted_values[low]) * (position - low)


def json_file(path, label):
    try:
        with path.open(encoding="utf-8") as stream:
            return json.load(stream)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise EvidenceError(f"cannot read {label} {path}: {error}") from error


def write_json(path, record):
    temporary = path.with_name(path.name + ".tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as stream:
            json.dump(record, stream, indent=2, sort_keys=True, allow_nan=False)
            stream.write("\n")
        os.replace(temporary, path)
    except OSError as error:
        try:
            temporary.unlink()
        except OSError:
            pass
        raise EvidenceError(f"cannot write {path}: {error}") from error


def summary_metric(summary, name):
    pending = [summary]
    while pending:
        candidate = pending.pop()
        if isinstance(candidate, dict):
            metrics = candidate.get("metrics")
            if isinstance(metrics, dict) and isinstance(metrics.get(name), dict):
                return metrics[name]
            pending.extend(value for value in candidate.values() if isinstance(value, (dict, list)))
        elif isinstance(candidate, list):
            pending.extend(value for value in candidate if isinstance(value, (dict, list)))
    return None


def summary_counter(summary, name):
    metric = summary_metric(summary, name)
    values = metric.get("values") if isinstance(metric, dict) else None
    values = values if isinstance(values, dict) else {}
    for key in ("count", "value"):
        parsed = finite_number(values.get(key))
        if parsed is not None and parsed >= 0 and parsed.is_integer():
            return int(parsed)
    return None


def metric_parts(record):
    if not isinstance(record, dict) or record.get("type") != "Point":
        return None, None, None
    data = record.get("data")
    if not isinstance(data, dict):
        return None, None, None
    metric = record.get("metric") or data.get("name")
    if metric not in POINT_METRICS:
        return None, None, None
    tags = data.get("tags")
    return metric, data, tags if isinstance(tags, dict) else {}


def counter():
    return {"count": 0, "sum": 0, "invalid": 0}


def add_issue(issues, message):
    if len(issues) < 50:
        issues.append(message)


def target_matches(tags, rate, required, metric, issues):
    tagged = tags.get("target_rps")
    if tagged is None:
        if required:
            add_issue(issues, f"{metric} point is missing target_rps")
        return not required
    parsed = finite_number(tagged)
    if parsed is None or parsed != rate:
        add_issue(issues, f"{metric} point has target_rps={tagged!r}, expected {rate}")
        return False
    return True


def drop_bucket(tags, timestamp_ns, start_ns, end_ns):
    phase = tags.get("phase")
    scenario = tags.get("scenario")
    if scenario == "profile":
        if start_ns is None or end_ns is None:
            return "profile"
        if timestamp_ns < start_ns:
            return "ramp_up"
        if timestamp_ns < end_ns:
            return "measurement"
        return "ramp_down"
    if phase == "measurement":
        return "measurement"
    if isinstance(scenario, str) and scenario:
        return scenario
    if isinstance(phase, str) and phase:
        return phase
    return "unattributed"


def record_drop_bucket(buckets, name, value, timestamp_ns):
    entry = buckets.get(name)
    if entry is None:
        entry = {"count": 0, "first_ns": timestamp_ns, "last_ns": timestamp_ns}
        buckets[name] = entry
    entry["count"] += value
    entry["first_ns"] = min(entry["first_ns"], timestamp_ns)
    entry["last_ns"] = max(entry["last_ns"], timestamp_ns)

def record_steady_minute(points, bucket, metric, timestamp_ns, value, start_ns, end_ns):
    if start_ns is None or end_ns is None or not (start_ns <= timestamp_ns < end_ns):
        return
    minute = (timestamp_ns - start_ns) // (60 * NANOSECONDS_PER_SECOND)
    full_minutes = (end_ns - start_ns) // (60 * NANOSECONDS_PER_SECOND)
    if minute < full_minutes:
        points[bucket][int(minute)] += value
    else:
        points["partial_window"][metric] += value


def find_measurement_marker(path, rate):
    markers = []
    issues = []
    malformed = 0
    try:
        stream = path.open(encoding="utf-8")
    except OSError as error:
        raise EvidenceError(f"cannot read metrics JSONL {path}: {error}") from error
    with stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as error:
                malformed += 1
                add_issue(issues, f"metrics.jsonl line {line_number} is invalid JSON: {error.msg}")
                continue
            metric, data, tags = metric_parts(record)
            if metric != "measurement_window_start":
                continue
            if tags.get("phase") != "measurement" and tags.get("scenario") not in ("measurement", "profile"):
                continue
            if not target_matches(tags, rate, False, metric, issues):
                continue
            value = finite_number(data.get("value"))
            if value is None or value <= 0 or not value.is_integer():
                add_issue(issues, "measurement_window_start is not a positive epoch-millisecond value")
                continue
            markers.append(int(value))
    if malformed:
        add_issue(issues, f"metrics.jsonl contains {malformed} malformed JSON line(s)")
    return markers, issues, malformed


def read_metric_points(path, rate, start_ms=None, end_ms=None):
    """Stream selected k6 points without retaining raw JSONL records.

    The two-argument form deliberately preserves the native-drop counter API used by
    regression tests.  Supplying the steady window additionally assigns `profile`
    executor drops by native event timestamp.
    """
    start_ns = int(start_ms) * NANOSECONDS_PER_MILLISECOND if start_ms is not None else None
    end_ns = int(end_ms) * NANOSECONDS_PER_MILLISECOND if end_ms is not None else None
    wanted = {
        "http_req_duration": [],
        "lookup_errors": counter(),
        "lookup_success": counter(),
        "lookup_started": counter(),
        "measurement_window_start": [],
        "dropped_iterations": counter(),
        "dropped_by_scenario": {},
        "raw_dropped_iterations": 0,
        "outside_window": defaultdict(int),
        "minute_successes": defaultdict(int),
        "minute_drops": defaultdict(int),
        "partial_window": defaultdict(int),
    }
    issues = []
    malformed_rows = 0
    try:
        stream = path.open(encoding="utf-8")
    except OSError as error:
        raise EvidenceError(f"cannot read metrics JSONL {path}: {error}") from error

    with stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as error:
                malformed_rows += 1
                add_issue(issues, f"metrics.jsonl line {line_number} is invalid JSON: {error.msg}")
                continue
            metric, data, tags = metric_parts(record)
            if metric is None:
                continue

            if metric == "measurement_window_start":
                if tags.get("phase") == "measurement" or tags.get("scenario") in ("measurement", "profile"):
                    if target_matches(tags, rate, False, metric, issues):
                        value = finite_number(data.get("value"))
                        if value is None or value <= 0 or not value.is_integer():
                            add_issue(issues, "measurement_window_start is not a positive epoch-millisecond value")
                        else:
                            wanted[metric].append(int(value))
                continue

            if metric == "dropped_iterations":
                value = finite_number(data.get("value"))
                if value is None or value < 0 or not value.is_integer():
                    wanted[metric]["invalid"] += 1
                    add_issue(issues, "dropped_iterations has a negative, non-finite, or fractional increment")
                    continue
                timestamp_ns = parse_timestamp_ns(data.get("time"))
                if timestamp_ns is None:
                    wanted[metric]["invalid"] += 1
                    add_issue(issues, "dropped_iterations point is missing a valid RFC3339 timestamp")
                    continue
                integer_value = int(value)
                wanted["raw_dropped_iterations"] += integer_value
                bucket = drop_bucket(tags, timestamp_ns, start_ns, end_ns)
                record_drop_bucket(wanted["dropped_by_scenario"], bucket, integer_value, timestamp_ns)
                if bucket == "measurement":
                    wanted[metric]["count"] += 1
                    wanted[metric]["sum"] += integer_value
                    record_steady_minute(
                        wanted, "minute_drops", metric, timestamp_ns, integer_value, start_ns, end_ns
                    )
                continue

            phase = tags.get("phase")
            scenario = tags.get("scenario")
            selected = phase == "measurement" or scenario == "measurement"
            if not selected:
                if scenario == "profile" and phase is None:
                    add_issue(issues, f"{metric} profile point is missing an explicit phase tag")
                continue
            if not target_matches(tags, rate, True, metric, issues):
                continue
            value = finite_number(data.get("value"))
            if value is None:
                wanted[metric]["invalid"] += 1
                add_issue(issues, f"{metric} point has a missing or non-finite value")
                continue
            timestamp_ns = parse_timestamp_ns(data.get("time"))
            if timestamp_ns is None:
                wanted[metric]["invalid"] += 1
                add_issue(issues, f"{metric} point is missing a valid RFC3339 timestamp")
                continue
            if start_ns is not None and end_ns is not None and not (start_ns <= timestamp_ns < end_ns):
                wanted["outside_window"][metric] += 1

            if metric == "http_req_duration":
                if value < 0:
                    wanted[metric].append((timestamp_ns, value))
                    add_issue(issues, "http_req_duration contains a negative sample")
                else:
                    wanted[metric].append((timestamp_ns, value))
                continue

            metric_counter = wanted[metric]
            metric_counter["count"] += 1
            metric_counter["sum"] += int(value) if value.is_integer() else value
            if metric in ("lookup_errors", "lookup_success") and value not in (0, 1):
                metric_counter["invalid"] += 1
                add_issue(issues, f"{metric} point must be 0 or 1")
            elif metric == "lookup_started" and value != 1:
                metric_counter["invalid"] += 1
                add_issue(issues, "lookup_started point must equal 1")
            elif metric == "lookup_success" and value == 1:
                record_steady_minute(
                    wanted, "minute_successes", metric, timestamp_ns, 1, start_ns, end_ns
                )

    if malformed_rows:
        add_issue(issues, f"metrics.jsonl contains {malformed_rows} malformed JSON line(s)")
    return wanted, issues, malformed_rows


def resolve_k6_layout(root):
    root = root.resolve()
    manifest_path = root / "manifest.json"
    manifest = json_file(manifest_path, "k6 manifest")
    if not isinstance(manifest, dict):
        raise EvidenceError(f"k6 manifest {manifest_path} must be a JSON object")

    direct_files = (root / "metrics.jsonl", root / "summary.json")
    if all(path.is_file() for path in direct_files):
        entry = None
        plateaus = manifest.get("plateaus")
        if isinstance(plateaus, list):
            matching = [item for item in plateaus if isinstance(item, dict) and item.get("directory") == root.name]
            if len(matching) == 1:
                entry = matching[0]
            elif len(plateaus) == 1 and isinstance(plateaus[0], dict):
                entry = plateaus[0]
        return manifest, entry, root

    plateaus = manifest.get("plateaus")
    if not isinstance(plateaus, list):
        raise EvidenceError(f"{root} has no direct k6 metrics and manifest has no plateaus array")
    candidates = []
    for entry in plateaus:
        if not isinstance(entry, dict) or not isinstance(entry.get("directory"), str):
            continue
        candidate = (root / entry["directory"]).resolve()
        if root not in candidate.parents or not (candidate / "metrics.jsonl").is_file() or not (candidate / "summary.json").is_file():
            continue
        candidates.append((entry, candidate))
    if len(candidates) != 1:
        raise EvidenceError(
            f"{root} must contain exactly one complete plateau to produce one evidence.json; found {len(candidates)}"
        )
    entry, candidate = candidates[0]
    return manifest, entry, candidate


def value_from_manifest(manifest, entry, name):
    if isinstance(entry, dict) and name in entry:
        return entry[name]
    return manifest.get(name)


def rate_from_manifest(manifest, entry):
    value = value_from_manifest(manifest, entry, "rate")
    if value is None:
        rates = manifest.get("rates")
        if isinstance(rates, list) and len(rates) == 1:
            value = rates[0]
    return positive_integer(value, "manifest rate")


def profile_from_manifest(manifest, entry):
    ramp_up = nonnegative_integer(manifest.get("ramp_up_seconds"), "manifest ramp_up_seconds")
    start_rps = positive_integer(manifest.get("start_rps"), "manifest start_rps")
    steady = positive_integer(manifest.get("duration_seconds"), "manifest duration_seconds")
    ramp_down = nonnegative_integer(manifest.get("ramp_down_seconds"), "manifest ramp_down_seconds")
    execution_model = manifest.get("execution_model")
    if not isinstance(execution_model, str) or not execution_model:
        execution_model = (
            "legacy-three-scenario-arrival-rate"
            if ramp_up > 0 or ramp_down > 0
            else "constant-arrival-rate"
        )
    return {
        "ramp_up_seconds": ramp_up,
        "start_rps": start_rps,
        "steady_seconds": steady,
        "ramp_down_seconds": ramp_down,
        "execution_model": execution_model,
    }


def exit_code_from_manifest(manifest, entry):
    value = value_from_manifest(manifest, entry, "exit_code")
    if isinstance(value, bool) or not isinstance(value, int):
        raise EvidenceError("manifest plateau exit_code is missing or invalid")
    if value not in (0, 99):
        raise EvidenceError(f"k6 exited with {value}; no complete client evidence is available")
    return value


def build_k6_evidence(root):
    manifest, entry, metrics_directory = resolve_k6_layout(root)
    rate = rate_from_manifest(manifest, entry)
    profile = profile_from_manifest(manifest, entry)
    base_url = manifest.get("base_url")
    if not isinstance(base_url, str) or not base_url:
        raise EvidenceError("manifest base_url is missing or invalid")
    exit_code = exit_code_from_manifest(manifest, entry)

    metrics_path = metrics_directory / "metrics.jsonl"
    markers, marker_issues, marker_malformed = find_measurement_marker(metrics_path, rate)
    if marker_issues or marker_malformed or len(markers) != 1:
        details = marker_issues + [f"expected exactly one measurement_window_start point; found {len(markers)}"]
        raise EvidenceError("; ".join(details))
    start_ms = markers[0]
    end_ms = start_ms + profile["steady_seconds"] * 1000
    if utc_from_ms(start_ms) is None or utc_from_ms(end_ms) is None:
        raise EvidenceError("measurement window is outside the supported UTC range")

    points, point_issues, malformed = read_metric_points(metrics_path, rate, start_ms, end_ms)
    if malformed or point_issues:
        raise EvidenceError("; ".join(point_issues or ["metrics JSONL is malformed"]))
    if points["measurement_window_start"] != [start_ms]:
        raise EvidenceError("measurement_window_start changed or is not unique while reading metrics JSONL")

    started = points["lookup_started"]
    responses = points["lookup_errors"]
    successes = points["lookup_success"]
    latency_points = points["http_req_duration"]
    required_counters = (("lookup_started", started), ("lookup_errors", responses), ("lookup_success", successes))
    for name, values in required_counters:
        if values["count"] == 0 or values["invalid"]:
            raise EvidenceError(f"{name} measurement samples are missing or invalid")
    if not latency_points or any(value < 0 for _timestamp, value in latency_points):
        raise EvidenceError("http_req_duration measurement samples are missing or invalid")

    started_count = started["sum"]
    response_count = responses["count"]
    success_all = successes["count"]
    successful_completions = successes["sum"]
    error_count = responses["sum"]
    complete_responses = len(latency_points)
    if started_count != started["count"]:
        raise EvidenceError("lookup_started increments do not conserve request starts")
    if started_count != response_count or success_all != response_count or complete_responses != response_count:
        raise EvidenceError(
            "measurement conservation failed: lookup_started, lookup_errors, lookup_success, and http_req_duration counts differ"
        )
    if successful_completions + error_count != response_count:
        raise EvidenceError("lookup_success plus lookup_errors does not equal completed responses")

    summary = json_file(metrics_directory / "summary.json", "k6 summary")
    if not isinstance(summary, dict):
        raise EvidenceError("k6 summary must be a JSON object")
    summary_drops = summary_counter(summary, "dropped_iterations")
    if summary_drops is None:
        if "dropped_iterations" in summary.get("metrics", {}) or points["raw_dropped_iterations"]:
            raise EvidenceError("k6 summary is missing a valid dropped_iterations counter")
        summary_drops = 0
    if points["dropped_iterations"]["invalid"]:
        raise EvidenceError("dropped_iterations contains invalid native counter increments")
    if points["raw_dropped_iterations"] != summary_drops:
        raise EvidenceError(
            "native dropped_iterations JSONL total does not match summary.json "
            f"({points['raw_dropped_iterations']} != {summary_drops})"
        )

    duration = profile["steady_seconds"]
    sorted_latencies = sorted(value for _timestamp, value in latency_points)
    full_minutes = duration // 60
    latency_minutes = [[] for _ in range(full_minutes)]
    success_minutes = [points["minute_successes"][minute] for minute in range(full_minutes)]
    drop_minutes = [points["minute_drops"][minute] for minute in range(full_minutes)]
    start_ns = start_ms * NANOSECONDS_PER_MILLISECOND
    end_ns = end_ms * NANOSECONDS_PER_MILLISECOND
    minute_ns = 60 * NANOSECONDS_PER_SECOND
    partial_window_points = points["partial_window"]

    for timestamp_ns, latency in latency_points:
        if start_ns <= timestamp_ns < end_ns:
            minute = (timestamp_ns - start_ns) // minute_ns
            if minute < full_minutes:
                latency_minutes[int(minute)].append(latency)
            else:
                partial_window_points["http_req_duration"] += 1

    minutes = []
    for minute in range(full_minutes):
        samples = sorted(latency_minutes[minute])
        minutes.append({
            "minute": minute + 1,
            "successful_rps": success_minutes[minute] / 60.0,
            "p95_ms": percentile(samples, 0.95),
            "p99_ms": percentile(samples, 0.99),
            "dropped_iterations": drop_minutes[minute],
        })

    diagnostics = []
    for metric, count in sorted(points["outside_window"].items()):
        diagnostics.append(
            f"{count} phase=measurement {metric} point(s) completed outside the marker-bounded steady timestamps; "
            "overall conservation uses explicit phase tags"
        )
    if duration % 60:
        diagnostics.append(
            f"the final {duration % 60} steady second(s) are not represented in full-minute evidence"
        )
    for metric, count in sorted(partial_window_points.items()):
        diagnostics.append(f"{count} {metric} point(s) fell in a non-full final minute and are excluded from minutes")

    dropped_by_scenario = []
    for scenario, bucket in sorted(points["dropped_by_scenario"].items()):
        dropped_by_scenario.append({
            "scenario": scenario,
            "count": bucket["count"],
            "first_utc": utc_from_ns(bucket["first_ns"]),
            "last_utc": utc_from_ns(bucket["last_ns"]),
        })

    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": root.resolve().name,
        "rate": rate,
        "base_url": base_url,
        "profile": profile,
        "window": {
            "start_ms": start_ms,
            "end_ms": end_ms,
            "start_utc": utc_from_ms(start_ms),
            "end_utc": utc_from_ms(end_ms),
        },
        "k6": {
            "started": started_count,
            "responses": response_count,
            "success_all": success_all,
            "successful_completions": successful_completions,
            "successful_rps": successful_completions / duration,
            "error_count": error_count,
            "error_rate": error_count / response_count,
            "dropped_iterations": points["dropped_iterations"]["sum"],
            "p95_ms": percentile(sorted_latencies, 0.95),
            "p99_ms": percentile(sorted_latencies, 0.99),
            "complete_responses": complete_responses,
            "exit_code": exit_code,
            "minutes": minutes,
        },
        "diagnostics": {
            "dropped_by_scenario": dropped_by_scenario,
            "issues": diagnostics,
            "latency_method": "exact linear interpolation over phase=measurement http_req_duration JSONL samples",
        },
    }


def summary_values(values):
    usable = [float(value) for value in values if finite_number(value) is not None]
    if not usable:
        return {"avg": None, "min": None, "max": None}
    return {
        "avg": sum(usable) / len(usable),
        "min": min(usable),
        "max": max(usable),
    }


def nested(record, *keys):
    value = record
    for key in keys:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def percent_value(value):
    if isinstance(value, str) and value.endswith("%"):
        value = value[:-1]
    parsed = finite_number(value)
    return parsed if parsed is not None and parsed >= 0 else None


def add_distinct(errors, message):
    if message not in errors and len(errors) < 100:
        errors.append(message)


def backend_evidence(input_path, start_ms, end_ms):
    if end_ms <= start_ms:
        raise EvidenceError("--end-ms must be greater than --start-ms")
    start_ns = start_ms * NANOSECONDS_PER_MILLISECOND
    end_ns = end_ms * NANOSECONDS_PER_MILLISECOND
    host_cpu = []
    available_ram = []
    container_cpu = {"backend": [], "postgres": []}
    container_memory = {"backend": [], "postgres": []}
    database = {"connections": [], "active_connections": [], "idle_in_transaction": []}
    network_in = []
    network_out = []
    network_coverage = 0.0
    samples = 0
    first_ns = None
    last_ns = None
    missing_count = 0
    errors = []
    previous_network_anchor = None
    network_interval_count = 0

    try:
        stream = input_path.open(encoding="utf-8")
    except OSError as error:
        raise EvidenceError(f"cannot read backend telemetry {input_path}: {error}") from error
    with stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                sample = json.loads(line)
            except json.JSONDecodeError as error:
                raise EvidenceError(f"backend telemetry line {line_number} is invalid JSON: {error.msg}") from error
            if not isinstance(sample, dict):
                raise EvidenceError(f"backend telemetry line {line_number} is not a JSON object")
            timestamp_ns = parse_timestamp_ns(sample.get("timestamp_utc"))
            if timestamp_ns is None:
                raise EvidenceError(f"backend telemetry line {line_number} has no valid timestamp_utc")
            network_anchor = parse_timestamp_ns(sample.get("collection_started_at_utc"))
            host = sample.get("host") if isinstance(sample.get("host"), dict) else {}
            interface = nested(host, "network", "interfaces", "ens5")
            if (
                previous_network_anchor is not None
                and network_anchor is not None
                and start_ns <= previous_network_anchor
                and network_anchor <= end_ns
            ):
                if network_anchor <= previous_network_anchor:
                    add_distinct(errors, "backend telemetry collection_started_at_utc is not strictly increasing")
                elif isinstance(interface, dict):
                    received = finite_number(interface.get("rx_bytes"))
                    sent = finite_number(interface.get("tx_bytes"))
                    if (
                        received is not None and sent is not None and received >= 0 and sent >= 0
                        and received.is_integer() and sent.is_integer()
                    ):
                        interval_seconds = (network_anchor - previous_network_anchor) / NANOSECONDS_PER_SECOND
                        if interval_seconds > 0:
                            network_in.append(int(received) * 8 / 1_000_000 / interval_seconds)
                            network_out.append(int(sent) * 8 / 1_000_000 / interval_seconds)
                            network_coverage += interval_seconds
                            network_interval_count += 1
                    else:
                        add_distinct(errors, "ens5 interval has invalid byte counters")
                else:
                    add_distinct(errors, "ens5 network interval is unavailable")
            elif (
                previous_network_anchor is not None
                and network_anchor is not None
                and start_ns <= previous_network_anchor < end_ns
                and network_anchor <= previous_network_anchor
            ):
                add_distinct(errors, "backend telemetry collection_started_at_utc is not strictly increasing")
            if network_anchor is not None:
                previous_network_anchor = network_anchor

            if not (start_ns <= timestamp_ns < end_ns):
                continue
            samples += 1
            first_ns = timestamp_ns if first_ns is None else min(first_ns, timestamp_ns)
            last_ns = timestamp_ns if last_ns is None else max(last_ns, timestamp_ns)

            missing = sample.get("missing")
            if isinstance(missing, list):
                missing_count += len(missing)
            elif missing is not None:
                add_distinct(errors, "telemetry missing field is not an array")
            sample_errors = sample.get("errors")
            if isinstance(sample_errors, list):
                for item in sample_errors:
                    if isinstance(item, dict):
                        component = item.get("component", "unknown")
                        detail = item.get("error", "unspecified error")
                        add_distinct(errors, f"{component}: {detail}")
                    else:
                        add_distinct(errors, "telemetry contains a non-object error entry")
            elif sample_errors is not None:
                add_distinct(errors, "telemetry errors field is not an array")

            idle = finite_number(nested(host, "cpu", "percent", "idle"))
            if idle is not None and 0 <= idle <= 100:
                host_cpu.append(100.0 - idle)
            available_kb = finite_number(nested(host, "memory", "available_kb"))
            if available_kb is not None and available_kb >= 0:
                available_ram.append(available_kb / 1024.0)

            role_by_name = {}
            role_by_id = {}
            containers = nested(sample, "ecs", "containers")
            if isinstance(containers, list):
                for item in containers:
                    if not isinstance(item, dict):
                        continue
                    role = item.get("ecs_container_name")
                    if role not in container_cpu:
                        continue
                    name = item.get("container_name")
                    container_id = item.get("container_id")
                    if isinstance(name, str):
                        role_by_name[name.lstrip("/")] = role
                    if isinstance(container_id, str):
                        role_by_id[container_id] = role
            stats = nested(sample, "ecs", "docker_stats")
            if isinstance(stats, list):
                for stat in stats:
                    if not isinstance(stat, dict):
                        continue
                    name = stat.get("Name")
                    container_id = stat.get("Container")
                    role = role_by_name.get(name.lstrip("/")) if isinstance(name, str) else None
                    if role is None and isinstance(container_id, str):
                        role = role_by_id.get(container_id)
                    if role not in container_cpu:
                        continue
                    cpu = percent_value(stat.get("CPUPerc"))
                    memory = percent_value(stat.get("MemPerc"))
                    if cpu is not None:
                        container_cpu[role].append(cpu)
                    if memory is not None:
                        container_memory[role].append(memory)

            postgres = sample.get("postgres")
            if isinstance(postgres, list):
                for item in postgres:
                    if not isinstance(item, dict):
                        continue
                    connections = nested(item, "metrics", "connections")
                    if not isinstance(connections, dict):
                        continue
                    for output_name, source_name in (
                        ("connections", "total"),
                        ("active_connections", "active"),
                        ("idle_in_transaction", "idle_in_transaction"),
                    ):
                        value = finite_number(connections.get(source_name))
                        if value is not None and value >= 0:
                            database[output_name].append(value)

    if samples == 0:
        raise EvidenceError("backend telemetry has no point samples inside the requested steady window")
    if not host_cpu:
        add_distinct(errors, "host sampler CPU is unavailable in the selected window")
    if not available_ram:
        add_distinct(errors, "host available RAM is unavailable in the selected window")
    for role in ("backend", "postgres"):
        if not container_cpu[role]:
            add_distinct(errors, f"{role} sampler CPU is unavailable in the selected window")
        if not container_memory[role]:
            add_distinct(errors, f"{role} sampler memory is unavailable in the selected window")
    for name, values in database.items():
        if not values:
            add_distinct(errors, f"database {name} is unavailable in the selected window")
    if not network_interval_count:
        add_distinct(errors, "no valid fully-contained ens5 network interval is available in the selected window")

    return {
        "schema_version": SCHEMA_VERSION,
        "host": {
            "sampler_cpu_percent": summary_values(host_cpu),
            "available_ram_mib": summary_values(available_ram),
            "network": {
                "in_mbps": summary_values(network_in)["avg"],
                "out_mbps": summary_values(network_out)["avg"],
                "coverage_seconds": network_coverage,
            },
        },
        "containers": {
            "backend": {
                "sampler_cpu_percent_one_core": summary_values(container_cpu["backend"]),
                "sampler_memory_percent": summary_values(container_memory["backend"]),
            },
            "postgres": {
                "sampler_cpu_percent_one_core": summary_values(container_cpu["postgres"]),
                "sampler_memory_percent": summary_values(container_memory["postgres"]),
            },
        },
        "database": {name: summary_values(values) for name, values in database.items()},
        "telemetry": {
            "samples": samples,
            "first_utc": utc_from_ns(first_ns),
            "last_utc": utc_from_ns(last_ns),
            "missing_count": missing_count,
            "errors": errors,
            "source_period_seconds": 5,
        },
    }


def parse_windows(path):
    windows = json_file(path, "Nginx window file")
    if not isinstance(windows, list) or not windows:
        raise EvidenceError("Nginx window file must be a non-empty JSON array")
    parsed = []
    seen = set()
    for index, item in enumerate(windows, 1):
        if not isinstance(item, dict):
            raise EvidenceError(f"Nginx window {index} must be an object")
        run_id = item.get("run_id")
        if not isinstance(run_id, str) or not run_id or run_id in seen:
            raise EvidenceError(f"Nginx window {index} has a missing or duplicate run_id")
        start_ms = nonnegative_integer(item.get("start_ms"), f"Nginx window {run_id} start_ms")
        end_ms = nonnegative_integer(item.get("end_ms"), f"Nginx window {run_id} end_ms")
        if end_ms <= start_ms:
            raise EvidenceError(f"Nginx window {run_id} end_ms must be greater than start_ms")
        seen.add(run_id)
        parsed.append({
            "run_id": run_id,
            "start_second": (start_ms + 999) // 1000,
            "end_second": end_ms // 1000,
        })
    return parsed


def nginx_evidence(input_path, windows_path):
    windows = parse_windows(windows_path)
    accumulators = {
        window["run_id"]: {"request_times_ms": [], "error_count": 0}
        for window in windows
    }
    try:
        stream = input_path.open(encoding="utf-8")
    except OSError as error:
        raise EvidenceError(f"cannot read Nginx access log {input_path}: {error}") from error
    with stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError as error:
                raise EvidenceError(f"Nginx access log line {line_number} is invalid JSON: {error.msg}") from error
            if not isinstance(entry, dict):
                raise EvidenceError(f"Nginx access log line {line_number} is not a JSON object")
            if entry.get("method") != "GET" or not isinstance(entry.get("path"), str) or not STUDENT_PATH.match(entry["path"]):
                continue
            timestamp_ns = parse_timestamp_ns(entry.get("time"))
            if timestamp_ns is None or timestamp_ns % NANOSECONDS_PER_SECOND:
                raise EvidenceError(
                    f"Nginx access log line {line_number} has no whole-second RFC3339 time for a student lookup"
                )
            timestamp_second = timestamp_ns // NANOSECONDS_PER_SECOND
            matching = [
                window for window in windows
                if window["start_second"] <= timestamp_second < window["end_second"]
            ]
            if not matching:
                continue
            request_seconds = finite_number(entry.get("request_time"))
            status = finite_number(entry.get("status"))
            if request_seconds is None or request_seconds < 0:
                raise EvidenceError(f"Nginx access log line {line_number} has an invalid request_time")
            if status is None or status < 100 or not status.is_integer():
                raise EvidenceError(f"Nginx access log line {line_number} has an invalid status")
            for window in matching:
                accumulator = accumulators[window["run_id"]]
                accumulator["request_times_ms"].append(request_seconds * 1000.0)
                if status >= 400:
                    accumulator["error_count"] += 1

    output = {}
    for window in windows:
        accumulator = accumulators[window["run_id"]]
        samples = sorted(accumulator["request_times_ms"])
        requests = len(samples)
        error_count = accumulator["error_count"]
        output[window["run_id"]] = {
            "requests": requests,
            "error_count": error_count,
            "error_rate": error_count / requests if requests else None,
            "p95_ms": percentile(samples, 0.95),
            "p99_ms": percentile(samples, 0.99),
            "coverage_start_utc": utc_from_ns(window["start_second"] * NANOSECONDS_PER_SECOND),
            "coverage_end_utc": utc_from_ns(window["end_second"] * NANOSECONDS_PER_SECOND),
            "coverage_seconds": window["end_second"] - window["start_second"],
            "timestamp_resolution_seconds": 1,
            "method": "GET",
        }
    return output


def argument_milliseconds(value):
    try:
        parsed = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be a non-negative integer number of milliseconds") from error
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be a non-negative integer number of milliseconds")
    return parsed


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    subcommands = parser.add_subparsers(dest="command", required=True)

    k6_parser = subcommands.add_parser("k6", allow_abbrev=False)
    k6_parser.add_argument("--results", type=Path, required=True)

    backend_parser = subcommands.add_parser("backend", allow_abbrev=False)
    backend_parser.add_argument("--input", type=Path, required=True)
    backend_parser.add_argument("--start-ms", type=argument_milliseconds, required=True)
    backend_parser.add_argument("--end-ms", type=argument_milliseconds, required=True)

    nginx_parser = subcommands.add_parser("nginx", allow_abbrev=False)
    nginx_parser.add_argument("--input", type=Path, required=True)
    nginx_parser.add_argument("--windows", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    try:
        if args.command == "k6":
            root = args.results.expanduser()
            evidence = build_k6_evidence(root)
            write_json(root / "evidence.json", evidence)
        elif args.command == "backend":
            input_path = args.input.expanduser()
            evidence = backend_evidence(input_path, args.start_ms, args.end_ms)
            write_json(Path(str(input_path) + ".evidence.json"), evidence)
        else:
            evidence = nginx_evidence(args.input.expanduser(), args.windows.expanduser())
            json.dump(evidence, sys.stdout, sort_keys=True, separators=(",", ":"), allow_nan=False)
            sys.stdout.write("\n")
    except EvidenceError as error:
        print(f"evidence: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
