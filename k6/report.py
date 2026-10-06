#!/usr/bin/env python3
"""Summarize one burst-10k lookup run, backend telemetry, generator samples, and optional AWS metadata."""

import argparse
import csv
import datetime as dt
import html
import json
import math
import re
import statistics
from collections import Counter, defaultdict
from pathlib import Path

REQUEST_FIELDS = ("id", "sbd", "started_ms", "finished_ms", "status", "correct", "cache_hit", "error_code")
DB_COUNTER_FIELDS = (
    "xact_commit", "xact_rollback", "blks_read", "blks_hit", "tup_returned", "tup_fetched",
    "tup_inserted", "tup_updated", "tup_deleted", "temp_files", "temp_bytes", "deadlocks", "conflicts",
)
EXAM_SCORES_COUNTER_FIELDS = ("seq_scan", "idx_scan", "seq_tup_read", "idx_tup_fetch")
CONTAINER_ROLES = ("backend", "postgres", "redis")
SECRET_KEY = re.compile(r"secret|token|password|credential|access.?key|private.?key|authorization|cookie", re.I)


def instant(value):
    if not value:
        return None
    parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"timestamp lacks timezone: {value!r}")
    return parsed.astimezone(dt.timezone.utc)


def iso(value):
    return value.isoformat(timespec="milliseconds").replace("+00:00", "Z") if value else None

def epoch_milliseconds_to_utc(value):
    milliseconds = number(value)
    if milliseconds is None:
        return None
    try:
        return dt.datetime.fromtimestamp(milliseconds / 1000.0, tz=dt.timezone.utc)
    except (OSError, OverflowError, ValueError):
        return None




def number(value):
    if isinstance(value, bool) or value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def integer(value):
    numeric = number(value)
    return int(numeric) if numeric is not None else None


def percentile(sorted_values, fraction):
    if not sorted_values:
        return None
    rank = (len(sorted_values) - 1) * fraction
    low = int(rank)
    high = min(low + 1, len(sorted_values) - 1)
    return sorted_values[low] + (sorted_values[high] - sorted_values[low]) * (rank - low)


def parse_boolean(value):
    if value is None:
        return None
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "t", "yes", "y"}:
        return True
    if normalized in {"0", "false", "f", "no", "n"}:
        return False
    return None


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path):
    rows, errors = [], []
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as error:
                errors.append({"line": line_number, "error": str(error)})
                continue
            if not isinstance(row, dict):
                errors.append({"line": line_number, "error": "expected a JSON object"})
                continue
            rows.append(row)
    return rows, errors


def summary_metrics(summary):
    """Accept the lookup wrapper, legacy k6 summary objects, and machine-readable summaries."""
    candidates = [summary]
    for key in ("k6Summary", "results"):
        nested = summary.get(key) if isinstance(summary, dict) else None
        if isinstance(nested, dict):
            candidates.append(nested)
    for candidate in candidates:
        sources = [candidate.get("metrics")]
        results = candidate.get("results")
        if isinstance(results, dict):
            sources.append(results.get("metrics"))
        for source in sources:
            if isinstance(source, dict):
                if all(isinstance(value, dict) for value in source.values()):
                    return source
            if isinstance(source, list):
                return {item["name"]: item for item in source if isinstance(item, dict) and item.get("name")}
    return {}


def metric_value(metrics, name, field):
    metric = metrics.get(name)
    values = metric.get("values") if isinstance(metric, dict) else None
    return number(values.get(field)) if isinstance(values, dict) else None


def metric_stats(metrics, name):
    return {field: metric_value(metrics, name, field) for field in ("avg", "p(95)", "p(99)")}


def read_requests(path):
    attempts = []
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        headers = set(reader.fieldnames or ())
        missing = [field for field in REQUEST_FIELDS if field not in headers]
        if missing:
            raise ValueError(f"{path} is missing required columns: {', '.join(missing)}")
        for row in reader:
            raw = {field: row.get(field, "") or "" for field in REQUEST_FIELDS}
            status = raw["status"].strip()
            correct = parse_boolean(raw["correct"])
            cache_hit = parse_boolean(raw["cache_hit"])
            error_code = raw["error_code"].strip()
            failed = correct is False or (bool(status) and status != "200") or bool(error_code)
            attempts.append({
                **raw,
                "startedMs": number(raw["started_ms"]),
                "finishedMs": number(raw["finished_ms"]),
                "correctValue": correct,
                "cacheHitValue": cache_hit,
                "failed": failed,
            })
    return attempts


def request_analysis(attempts, manifest, summary):
    status_counts = Counter((attempt["status"].strip() or "<missing>") for attempt in attempts)
    error_counts = Counter(attempt["error_code"].strip() for attempt in attempts if attempt["error_code"].strip())
    missing_error_code_count = sum(not attempt["error_code"].strip() for attempt in attempts)
    correct_counts = Counter("correct" if row["correctValue"] is True else
                             "incorrect" if row["correctValue"] is False else "unknown" for row in attempts)
    cache_counts = Counter("hit" if row["cacheHitValue"] is True else
                           "miss" if row["cacheHitValue"] is False else "unknown" for row in attempts)
    starts = sorted(row["startedMs"] for row in attempts if row["startedMs"] is not None)
    start_origin = starts[0] if starts else None
    launch_offsets = sorted(value - start_origin for value in starts) if start_origin is not None else []
    in_flight_events = []
    request_elapsed = []
    timed_starts = []
    timed_finishes = []
    valid_intervals = 0
    for attempt in attempts:
        start, finish = attempt["startedMs"], attempt["finishedMs"]
        if start is None or finish is None or finish < start:
            continue
        valid_intervals += 1
        timed_starts.append(start)
        timed_finishes.append(finish)
        request_elapsed.append(finish - start)
        if finish > start:
            in_flight_events.append((start, 1))
            in_flight_events.append((finish, -1))
    in_flight_events.sort(key=lambda event: (event[0], event[1]))  # end before start at identical timestamps
    current, peak, peak_at = 0, None, None
    for timestamp, change in in_flight_events:
        current += change
        if current > (peak if peak is not None else 0):
            peak, peak_at = current, timestamp
    if in_flight_events and peak is None:
        peak = 0
    run_start = instant(manifest["startedAtUtc"])
    run_finish = instant(manifest["finishedAtUtc"])
    duration = (run_finish - run_start).total_seconds() if run_finish and run_start else None
    metrics = summary_metrics(summary)
    http_count = metric_value(metrics, "http_reqs", "count")
    http_rate = metric_value(metrics, "http_reqs", "rate")
    request_span = ((max(starts) - min(starts)) / 1000.0) if len(starts) > 1 else (0.0 if starts else None)
    correct = correct_counts["correct"]
    incorrect = correct_counts["incorrect"]
    known_correctness = correct + incorrect
    known_cache = cache_counts["hit"] + cache_counts["miss"]
    client_window_ms = (max(timed_finishes) - min(timed_starts)) if timed_starts and timed_finishes else None
    return {
        "attemptCount": len(attempts),
        "requestTimingValidCount": valid_intervals,
        "invalidOrMissingTimingCount": len(attempts) - valid_intervals,
        "failedAttemptCount": sum(attempt["failed"] for attempt in attempts),
        "statusCounts": dict(sorted(status_counts.items())),
        "errorCodeCounts": dict(sorted(error_counts.items())),
        "missingErrorCodeCount": missing_error_code_count,
        "correctnessCounts": {key: correct_counts[key] for key in ("correct", "incorrect", "unknown")},
        "cacheCounts": {key: cache_counts[key] for key in ("hit", "miss", "unknown")},
        "cloudFrontHitCount": cache_counts["hit"],
        "cloudFrontHitRateAmongKnown": cache_counts["hit"] / known_cache if known_cache else None,
        "correctnessRateAmongKnown": correct / known_correctness if known_correctness else None,
        "launchSpreadMs": {
            "p50": percentile(launch_offsets, 0.50),
            "p95": percentile(launch_offsets, 0.95),
            "max": max(launch_offsets) if launch_offsets else None,
            "startTimestampMs": start_origin,
            "requestStartSpanMs": request_span * 1000 if request_span is not None else None,
        },
        "clientElapsedMs": {
            "p50": percentile(request_elapsed, 0.50),
            "p95": percentile(request_elapsed, 0.95),
            "p99": percentile(request_elapsed, 0.99),
            "max": max(request_elapsed) if request_elapsed else None,
        },
        "measurementWindow": {
            "source": "requests.csv valid [started_ms, finished_ms] intervals",
            "startedMs": min(timed_starts) if timed_starts else None,
            "finishedMs": max(timed_finishes) if timed_finishes else None,
            "durationMs": client_window_ms,
        },
        "peakClientInFlight": peak,
        "peakClientInFlightAtOffsetMs": (peak_at - start_origin) if peak_at is not None and start_origin is not None else None,
        "throughput": {
            "k6HttpRequestsPerSecond": http_rate,
            "k6HttpRequestCount": http_count,
            "attemptsPerManifestSecond": len(attempts) / duration if duration and duration > 0 else None,
            "timedAttemptsPerClientWindowSecond": valid_intervals / (client_window_ms / 1000)
                if client_window_ms and client_window_ms > 0 else None,
            "manifestDurationSeconds": duration,
        },
        "latencyMs": {
            "httpRequestDuration": metric_stats(metrics, "http_req_duration"),
            "iterationDuration": metric_stats(metrics, "iteration_duration"),
            "connectionCosts": {
                "blocked": metric_stats(metrics, "http_req_blocked"),
                "connecting": metric_stats(metrics, "http_req_connecting"),
                "tlsHandshaking": metric_stats(metrics, "http_req_tls_handshaking"),
            },
        },
        "k6MetricsAvailable": bool(metrics),
        "summaryHttpRequestsCountMatchesCsv": http_count == len(attempts) if http_count is not None else None,
    }


def sample_time(sample):
    return instant(sample.get("timestamp_utc") or sample.get("capturedAtUtc"))


def collect_database_records(samples):
    records = []
    for sample in samples:
        for entry in sample.get("postgres") or []:
            metrics = entry.get("metrics") if isinstance(entry, dict) else None
            if not isinstance(metrics, dict):
                continue
            started = instant(entry.get("query_started_at_utc"))
            finished = instant(entry.get("query_finished_at_utc"))
            observed = finished or sample_time(sample)
            if observed is None:
                continue
            connections = metrics.get("connections")
            if not isinstance(connections, dict):
                states = metrics.get("activity_by_state") or {}
                active = integer(states.get("active"))
                idle = integer(states.get("idle"))
                connections = {
                    "active": active,
                    "idle": idle,
                    "total": (active + idle) if active is not None and idle is not None else None,
                    "idle_in_transaction": integer(states.get("idle in transaction")),
                }
            counters = metrics.get("database_counters")
            has_exam_scores_counters = "exam_scores_table_counters" in metrics
            raw_exam_scores = metrics.get("exam_scores_table_counters")
            exam_scores = []
            if isinstance(raw_exam_scores, list):
                for table in raw_exam_scores:
                    if not isinstance(table, dict):
                        continue
                    schema_name = table.get("schema_name")
                    table_name = table.get("table_name")
                    if schema_name is None or table_name is None:
                        continue
                    exam_scores.append({
                        "schemaName": str(schema_name),
                        "tableName": str(table_name),
                        "counters": {field: integer(table.get(field)) for field in EXAM_SCORES_COUNTER_FIELDS},
                    })
            records.append({
                "observedAtUtc": iso(observed),
                "queryStartedAtUtc": iso(started),
                "queryFinishedAtUtc": iso(finished),
                "queryDurationSeconds": number(entry.get("query_duration_seconds")),
                "container": entry.get("container_name"),
                "connections": {key: integer(connections.get(key)) for key in
                                ("total", "active", "idle", "idle_in_transaction")},
                "waitEvents": metrics.get("wait_events") if isinstance(metrics.get("wait_events"), list) else [],
                "activityByState": metrics.get("activity_by_state") or {},
                "counters": counters if isinstance(counters, dict) else None,
                "hasExamScoresTableCounters": has_exam_scores_counters,
                "examScoresTableCounters": exam_scores,
            })
    records.sort(key=lambda row: row["observedAtUtc"])
    return records


def snapshot_during(record, start, finish):
    begin = instant(record.get("queryStartedAtUtc"))
    end = instant(record.get("queryFinishedAtUtc"))
    observed = instant(record.get("observedAtUtc"))
    if begin and end:
        return begin <= finish and end >= start
    return bool(observed and start <= observed <= finish)


def counter_delta(before, after, fields):
    if not isinstance(before, dict) or not isinstance(after, dict):
        return None
    result = {}
    for field in fields:
        first, last = integer(before.get(field)), integer(after.get(field))
        result[field] = (last - first) if first is not None and last is not None and last >= first else None
    return result


def record_counter_delta(before, after):
    if not before or not after or before.get("container") != after.get("container"):
        return None
    return counter_delta(before.get("counters"), after.get("counters"), DB_COUNTER_FIELDS)


def exam_scores_counter_delta(before, after):
    if not before or not after or before.get("container") != after.get("container"):
        return None
    def by_table(record):
        return {
            f"{row['schemaName']}.{row['tableName']}": row["counters"]
            for row in record.get("examScoresTableCounters") or []
            if isinstance(row, dict) and row.get("schemaName") and row.get("tableName")
        }
    before_tables, after_tables = by_table(before), by_table(after)
    common_tables = sorted(before_tables.keys() & after_tables.keys())
    if not common_tables:
        return None
    return {
        table: counter_delta(before_tables[table], after_tables[table], EXAM_SCORES_COUNTER_FIELDS)
        for table in common_tables
    }


def database_analysis(samples, run_start, run_finish):
    records = collect_database_records(samples)
    before = [row for row in records if (instant(row["queryFinishedAtUtc"]) or instant(row["observedAtUtc"])) <= run_start]
    during = [row for row in records if snapshot_during(row, run_start, run_finish)]
    after = [row for row in records if (instant(row["queryStartedAtUtc"]) or instant(row["observedAtUtc"])) >= run_finish]
    baseline = before[-1] if before else None
    recovery = after[0] if after else None
    last_during = during[-1] if during else None
    first_during = during[0] if during else None
    def peak(field):
        present = [row for row in during if row["connections"].get(field) is not None]
        selected = max(present, key=lambda row: row["connections"][field]) if present else None
        return {"value": selected["connections"][field], "observedAtUtc": selected["observedAtUtc"]} if selected else None
    wait_peaks = {}
    for record in during:
        for event in record["waitEvents"]:
            if not isinstance(event, dict):
                continue
            event_type = str(event.get("wait_event_type") or "<unknown>")
            event_name = str(event.get("wait_event") or "<unknown>")
            key = f"{event_type}:{event_name}"
            count = integer(event.get("connections"))
            if count is not None and (key not in wait_peaks or count > wait_peaks[key]["connections"]):
                wait_peaks[key] = {"connections": count, "observedAtUtc": record["observedAtUtc"]}
    return {
        "snapshotCount": len(records),
        "baselineBeforeBurst": baseline,
        "duringBurstSampleCount": len(during),
        "peakActiveConnectionsDuringBurst": peak("active"),
        "peakIdleConnectionsDuringBurst": peak("idle"),
        "peakTotalConnectionsDuringBurst": peak("total"),
        "peakIdleInTransactionDuringBurst": peak("idle_in_transaction"),
        "waitEventPeaksDuringBurst": dict(sorted(wait_peaks.items())),
        "lastSnapshotDuringBurst": last_during,
        "recoveryAfterBurst": recovery,
        "cumulativeDatabaseCounterDeltas": {
            "baselineToLastDuringBurst": record_counter_delta(baseline, last_during),
            "firstToLastDuringBurst": record_counter_delta(first_during, last_during),
            "baselineToRecovery": record_counter_delta(baseline, recovery),
        },
        "examScoresTableCountersAvailable": any(
            record["hasExamScoresTableCounters"] for record in records
        ),
        "examScoresTableCounterRecordCount": sum(
            bool(record["examScoresTableCounters"]) for record in records
        ),
        "examScoresTableCounterDeltas": {
            "baselineToLastDuringBurst": exam_scores_counter_delta(baseline, last_during),
            "firstToLastDuringBurst": exam_scores_counter_delta(first_during, last_during),
            "baselineToRecovery": exam_scores_counter_delta(baseline, recovery),
        },
    }


def docker_bytes(value):
    if not value:
        return None
    first = str(value).split("/", 1)[0].strip()
    match = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)\s*([A-Za-z]+)?", first)
    if not match:
        return None
    amount = float(match.group(1))
    unit = (match.group(2) or "B").lower()
    multipliers = {
        "b": 1, "kb": 1000, "mb": 1000 ** 2, "gb": 1000 ** 3, "tb": 1000 ** 4,
        "kib": 1024, "mib": 1024 ** 2, "gib": 1024 ** 3, "tib": 1024 ** 4,
    }
    return amount * multipliers[unit] if unit in multipliers else None


def docker_percent(value):
    parsed = number(str(value).strip().rstrip("%")) if value is not None else None
    return parsed


def host_and_container_analysis(samples, run_start, run_finish):
    ordered = []
    for sample in samples:
        host = sample.get("host") or {}
        captured = instant(host.get("captured_at_utc")) or sample_time(sample)
        if captured:
            ordered.append((captured, sample))
    ordered.sort(key=lambda pair: pair[0])
    in_window = [(timestamp, sample) for timestamp, sample in ordered if run_start <= timestamp <= run_finish]
    busy, user_system, steal, iowait, available, used_percent = [], [], [], [], [], []
    disk_read_rates, disk_write_rates, network_rx_rates, network_tx_rates = [], [], [], []
    per_role = {role: {"samples": 0, "cpu": [], "memory": [], "instances": defaultdict(lambda: {"cpu": [], "memory": []})}
                for role in CONTAINER_ROLES}
    prior_by_timestamp = {id(sample): ordered[index - 1] if index else None for index, (_, sample) in enumerate(ordered)}
    for captured, sample in in_window:
        host = sample.get("host") or {}
        cpu = host.get("cpu") or {}
        percent = cpu.get("percent") or {}
        if number(percent.get("idle")) is not None:
            busy.append(100.0 - number(percent["idle"]))
        if number(percent.get("user")) is not None and number(percent.get("system")) is not None:
            user_system.append(number(percent["user"]) + number(percent["system"]))
        if number(percent.get("steal")) is not None:
            steal.append(number(percent["steal"]))
        if number(percent.get("iowait")) is not None:
            iowait.append(number(percent["iowait"]))
        memory = host.get("memory") or {}
        total_kb, available_kb = number(memory.get("total_kb")), number(memory.get("available_kb"))
        if available_kb is not None:
            available.append(available_kb)
        if total_kb and available_kb is not None:
            used_percent.append((total_kb - available_kb) * 100.0 / total_kb)
        previous = prior_by_timestamp.get(id(sample))
        if previous and previous[0] >= run_start:
            previous_time, _ = previous
            seconds = (captured - previous_time).total_seconds()
            if seconds > 0:
                disk = host.get("root_disk") or {}
                read_bytes, write_bytes = number(disk.get("read_bytes")), number(disk.get("write_bytes"))
                if read_bytes is not None:
                    disk_read_rates.append(read_bytes / seconds)
                if write_bytes is not None:
                    disk_write_rates.append(write_bytes / seconds)
                network = host.get("network") or {}
                rx, tx = number(network.get("rx_bytes")), number(network.get("tx_bytes"))
                if rx is not None:
                    network_rx_rates.append(rx / seconds)
                if tx is not None:
                    network_tx_rates.append(tx / seconds)
    docker_stats_sample_count = 0
    for _, sample in ordered:
        ecs = sample.get("ecs") or {}
        timing = ecs.get("docker_stats_timing") or {}
        captured = instant(timing.get("finished_at_utc")) or sample_time(sample)
        if captured is None or not run_start <= captured <= run_finish:
            continue
        containers = ecs.get("containers") or []
        names = {str(row.get("container_name", "")).lstrip("/"): row.get("ecs_container_name")
                 for row in containers if isinstance(row, dict)}
        ids = {str(row.get("container_id", "")): row.get("ecs_container_name")
               for row in containers if isinstance(row, dict)}
        docker_rows = ecs.get("docker_stats") or []
        if docker_rows:
            docker_stats_sample_count += 1
        for row in docker_rows:
            if not isinstance(row, dict):
                continue
            name = str(row.get("Name", "")).lstrip("/")
            role = names.get(name) or ids.get(str(row.get("ID", "")))
            if role not in per_role:
                continue
            cpu_value = docker_percent(row.get("CPUPerc"))
            memory_value = docker_bytes(row.get("MemUsage"))
            entry = per_role[role]
            entry["samples"] += 1
            if cpu_value is not None:
                entry["cpu"].append(cpu_value)
                entry["instances"][name]["cpu"].append(cpu_value)
            if memory_value is not None:
                entry["memory"].append(memory_value)
                entry["instances"][name]["memory"].append(memory_value)
    containers_result = {}
    for role, values in per_role.items():
        containers_result[role] = {
            "sampleCount": values["samples"],
            "cpuPeakPercentOfOneCore": max(values["cpu"]) if values["cpu"] else None,
            "memoryPeakBytes": max(values["memory"]) if values["memory"] else None,
            "instances": {
                name: {
                    "cpuPeakPercentOfOneCore": max(metrics["cpu"]) if metrics["cpu"] else None,
                    "memoryPeakBytes": max(metrics["memory"]) if metrics["memory"] else None,
                }
                for name, metrics in sorted(values["instances"].items())
            },
        }
    return {
        "sampleCountDuringBurst": len(in_window),
        "dockerStatsSampleCountDuringBurst": docker_stats_sample_count,
        "hostCpuBusyPeakPercent": max(busy) if busy else None,
        "hostCpuUserSystemPeakPercent": max(user_system) if user_system else None,
        "hostCpuStealPeakPercent": max(steal) if steal else None,
        "hostCpuIoWaitPeakPercent": max(iowait) if iowait else None,
        "hostAvailableMemoryMinimumKiB": min(available) if available else None,
        "hostMemoryUsedPeakPercent": max(used_percent) if used_percent else None,
        "rootDiskReadBytesPerSecondPeak": max(disk_read_rates) if disk_read_rates else None,
        "rootDiskWriteBytesPerSecondPeak": max(disk_write_rates) if disk_write_rates else None,
        "hostNetworkRxBytesPerSecondPeak": max(network_rx_rates) if network_rx_rates else None,
        "hostNetworkTxBytesPerSecondPeak": max(network_tx_rates) if network_tx_rates else None,
        "containers": containers_result,
    }


def generator_analysis(samples, run_start, run_finish):
    parsed = []
    for sample in samples:
        captured = instant(sample.get("capturedAtUtc"))
        if captured:
            parsed.append((captured, sample))
    parsed.sort(key=lambda pair: pair[0])
    in_window = [(captured, row) for captured, row in parsed if run_start <= captured <= run_finish]
    cpu_values = []
    for (previous_at, previous), (current_at, current) in zip(parsed, parsed[1:]):
        if previous_at < run_start or current_at > run_finish:
            continue
        total_before = integer(previous.get("cpuTotalTicks"))
        total_after = integer(current.get("cpuTotalTicks"))
        idle_before = integer(previous.get("cpuIdleTicks"))
        idle_after = integer(current.get("cpuIdleTicks"))
        if None in (total_before, total_after, idle_before, idle_after):
            continue
        total_delta, idle_delta = total_after - total_before, idle_after - idle_before
        if total_delta > 0 and 0 <= idle_delta <= total_delta:
            cpu_values.append((total_delta - idle_delta) * 100.0 / total_delta)
    available = [number(row.get("memoryAvailableKiB")) for _, row in in_window]
    rss = [number(row.get("k6RssKiB")) for _, row in in_window]
    high_water = [number(row.get("k6VmHwmKiB")) for _, row in in_window]
    return {
        "sampleCountDuringBurst": len(in_window),
        "systemCpuPeakPercent": max(cpu_values) if cpu_values else None,
        "systemCpuMeanPercent": statistics.fmean(cpu_values) if cpu_values else None,
        "memoryAvailableMinimumKiB": min(value for value in available if value is not None) if any(value is not None for value in available) else None,
        "k6RssPeakKiB": max(value for value in rss if value is not None) if any(value is not None for value in rss) else None,
        "k6VmHwmPeakKiB": max(value for value in high_water if value is not None) if any(value is not None for value in high_water) else None,
    }


def redact(value):
    if isinstance(value, dict):
        return {key: ("[REDACTED]" if SECRET_KEY.search(str(key)) else redact(item))
                for key, item in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


def object_or_empty(value):
    return value if isinstance(value, dict) else {}


def first_json_object_line(value):
    if not isinstance(value, str):
        return None
    for line in value.splitlines():
        if not line.strip():
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None
    return None


def metadata_evidence(metadata):
    if not isinstance(metadata, dict):
        return None
    nginx = object_or_empty(metadata.get("nginxDiagnostics"))
    recovery = object_or_empty(metadata.get("recovery"))
    origin = object_or_empty(recovery.get("origin"))
    public = object_or_empty(recovery.get("public"))
    public_attempt = object_or_empty(metadata.get("publicRecoveryAttempt"))
    final_recovery = object_or_empty(metadata.get("finalRecovery"))
    generator_during = [
        row for row in metadata.get("generatorDuring", [])
        if isinstance(row, dict)
    ] if isinstance(metadata.get("generatorDuring"), list) else []
    generator_after = [
        row for row in metadata.get("generatorAfter", [])
        if isinstance(row, dict)
    ] if isinstance(metadata.get("generatorAfter"), list) else []
    examples = nginx.get("errorExamples")
    return {
        "generatorDuring": generator_during,
        "databasePreflight": first_json_object_line(metadata.get("dbPreflight")),
        "nginxDiagnostics": {
            "errorWindowUtc": nginx.get("errorWindowUtc"),
            "errorRows": integer(nginx.get("errorRows")),
            "workerConnectionLimitErrors": integer(nginx.get("workerConnectionLimitErrors")),
            "burstAccessRows": integer(nginx.get("burstAccessRows")),
            "burstAccessStatuses": object_or_empty(nginx.get("burstAccessStatuses")),
            "errorExamples": [str(value) for value in examples] if isinstance(examples, list) else [],
        },
        "recovery": {
            "timestampUtc": recovery.get("timestampUtc"),
            "originStatus": integer(origin.get("status")),
            "originCorrect": parse_boolean(origin.get("correct")),
            "publicStatus": integer(public.get("status")),
            "publicCorrect": parse_boolean(public.get("correct")),
            "databaseRows": integer(recovery.get("databaseRows")),
        },
        "publicRecoveryAttempt": {
            "timestampUtc": public_attempt.get("timestampUtc"),
            "status": integer(public_attempt.get("status")),
            "correct": parse_boolean(public_attempt.get("correct")),
            "note": public_attempt.get("note"),
        },
        "finalRecovery": {
            "timestampUtc": final_recovery.get("timestampUtc"),
            "publicStatus": integer(final_recovery.get("publicStatus")),
            "publicCorrect": parse_boolean(final_recovery.get("publicCorrect")),
        },
        "generatorAfter": generator_after,
        "cpuCreditBefore": object_or_empty(metadata.get("cpuCreditBefore")),
        "cpuCreditAfter": object_or_empty(metadata.get("cpuCreditAfter")),
        "measurementNotes": object_or_empty(metadata.get("measurementNotes")),
    }


def telemetry_diagnostics(samples, telemetry_errors, generator_errors):
    errors = Counter()
    missing = Counter()
    durations = []
    for sample in samples:
        durations_value = number(sample.get("collection_duration_seconds"))
        if durations_value is not None:
            durations.append(durations_value)
        for error in sample.get("errors") or []:
            if isinstance(error, dict):
                errors[str(error.get("component") or "<unknown>")] += 1
        for component in sample.get("missing") or []:
            missing[str(component)] += 1
    return {
        "backendSamplesRead": len(samples),
        "backendJsonlParseErrors": len(telemetry_errors),
        "generatorJsonlParseErrors": len(generator_errors),
        "backendSampleErrorsByComponent": dict(sorted(errors.items())),
        "backendMissingByComponent": dict(sorted(missing.items())),
        "backendCollectionDurationSecondsPeak": max(durations) if durations else None,
    }


def build_report(results_dir, telemetry_path, metadata_path):
    required = {name: results_dir / name for name in
                ("manifest.json", "summary.json", "requests.csv", "generator-metrics.jsonl")}
    missing_files = [str(path) for path in required.values() if not path.is_file()]
    if missing_files:
        raise ValueError("missing required burst result file(s): " + ", ".join(missing_files))
    manifest = read_json(required["manifest.json"])
    summary = read_json(required["summary.json"])
    if not isinstance(manifest, dict) or not isinstance(summary, dict):
        raise ValueError("manifest.json and summary.json must contain JSON objects")
    for field in ("startedAtUtc", "finishedAtUtc", "baseUrl", "vus", "exitCode"):
        if field not in manifest:
            raise ValueError(f"manifest.json is missing {field}")
    run_start, run_finish = instant(manifest["startedAtUtc"]), instant(manifest["finishedAtUtc"])
    if run_start is None or run_finish is None:
        raise ValueError("manifest has an invalid startedAtUtc or finishedAtUtc")
    if run_finish < run_start:
        raise ValueError("manifest finishedAtUtc precedes startedAtUtc")
    attempts = read_requests(required["requests.csv"])
    samples, telemetry_errors = read_jsonl(telemetry_path)
    generator_samples, generator_errors = read_jsonl(required["generator-metrics.jsonl"])
    metadata = read_json(metadata_path) if metadata_path else None
    if metadata is not None and not isinstance(metadata, dict):
        raise ValueError("--metadata must point to a JSON object")
    request_stats = request_analysis(attempts, manifest, summary)
    request_window = request_stats["measurementWindow"]
    measurement_start = epoch_milliseconds_to_utc(request_window["startedMs"])
    measurement_finish = epoch_milliseconds_to_utc(request_window["finishedMs"])
    if measurement_start is None or measurement_finish is None:
        raise ValueError("requests.csv contains no valid [started_ms, finished_ms] interval for telemetry alignment")
    measurement_window_utc = {
        "source": request_window["source"],
        "startedAtUtc": iso(measurement_start),
        "finishedAtUtc": iso(measurement_finish),
        "durationMilliseconds": request_window["durationMs"],
        "validRequestAttempts": request_stats["requestTimingValidCount"],
        "manifestStartedAtUtc": iso(run_start),
        "manifestFinishedAtUtc": iso(run_finish),
    }
    db_stats = database_analysis(samples, measurement_start, measurement_finish)
    host_stats = host_and_container_analysis(samples, measurement_start, measurement_finish)
    generator_stats = generator_analysis(generator_samples, run_start, run_finish)
    generator_stats["measurementWindowUTC"] = {
        "source": "manifest.json whole run, including initialization, barrier, and request load",
        "startedAtUtc": iso(run_start),
        "finishedAtUtc": iso(run_finish),
    }
    redacted_metadata = redact(metadata) if metadata is not None else None
    report = {
        "schemaVersion": "g-scores-burst-report/v2",
        "manifest": manifest,
        "measurementWindowUTC": measurement_window_utc,
        "requestAnalysis": request_stats,
        "database": db_stats,
        "hostAndContainers": host_stats,
        "generator": generator_stats,
        "telemetryDiagnostics": telemetry_diagnostics(samples, telemetry_errors, generator_errors),
        "metadata": redacted_metadata,
        "metadataEvidence": metadata_evidence(redacted_metadata),
        "requests": attempts,
    }
    return report, attempts


def fmt(value, digits=2):
    if value is None:
        return "Không có dữ liệu"
    if isinstance(value, int):
        return f"{value:,}"
    return f"{value:,.{digits}f}"


def json_text(value):
    return json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)


def connection_table(database):
    rows = []
    for label, snapshot in (("Trước cửa sổ request (baseline)", database.get("baselineBeforeBurst")),
                            ("Trong cửa sổ request — mẫu cuối", database.get("lastSnapshotDuringBurst")),
                            ("Sau cửa sổ request (recovery)", database.get("recoveryAfterBurst"))):
        connections = snapshot.get("connections") if snapshot else None
        if not snapshot:
            observed = "Không có mẫu"
        elif snapshot.get("queryStartedAtUtc") and snapshot.get("queryFinishedAtUtc"):
            observed = f"{snapshot['queryStartedAtUtc']} → {snapshot['queryFinishedAtUtc']}"
        else:
            observed = snapshot.get("observedAtUtc") or "Không có timestamp"
        rows.append((label,
                     observed,
                     connections.get("active") if connections else None,
                     connections.get("idle") if connections else None,
                     connections.get("total") if connections else None))
    return rows

def measurement_period_label(period):
    return {
        "baselineToLastDuringBurst": "Baseline → mẫu cuối cửa sổ request",
        "firstToLastDuringBurst": "Mẫu đầu → cuối cửa sổ request",
        "baselineToRecovery": "Baseline → recovery sau cửa sổ request",
    }.get(period, period)


def exam_scores_delta_rows(database):
    rows = []
    for period, tables in database.get("examScoresTableCounterDeltas", {}).items():
        for table, counters in (tables or {}).items():
            if not isinstance(counters, dict):
                continue
            for field in EXAM_SCORES_COUNTER_FIELDS:
                rows.append((period, table, field, counters.get(field)))
    return rows


def exam_scores_counter_unavailable_message(database):
    if not database.get("examScoresTableCountersAvailable"):
        return "Telemetry không có trường exam_scores_table_counters; chỉ số này không được thu trong lượt burst, không phải giá trị 0."
    return "Không có hai snapshot cùng container có thể so delta exam_scores; không suy diễn giá trị 0."


def markdown_table(headers, rows):
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    lines.extend("| " + " | ".join(str(value).replace("|", "\\|").replace("\n", " ") for value in row) + " |"
                 for row in rows)
    return "\n".join(lines)


def observed_text(value):
    if value is None:
        return "Không có dữ liệu"
    if value is True:
        return "Đúng"
    if value is False:
        return "Sai"
    return str(value)


def metadata_diagnostics_view(report):
    evidence = report.get("metadataEvidence")
    if not isinstance(evidence, dict):
        return None
    request = report["requestAnalysis"]
    nginx = object_or_empty(evidence.get("nginxDiagnostics"))
    recovery = object_or_empty(evidence.get("recovery"))
    public_attempt = object_or_empty(evidence.get("publicRecoveryAttempt"))
    final_recovery = object_or_empty(evidence.get("finalRecovery"))
    access_statuses = object_or_empty(nginx.get("burstAccessStatuses"))
    preflight = object_or_empty(evidence.get("databasePreflight"))
    worker_errors = integer(nginx.get("workerConnectionLimitErrors"))
    public_status = integer(recovery.get("publicStatus"))
    public_correct = recovery.get("publicCorrect")
    final_public_status = integer(final_recovery.get("publicStatus"))
    final_public_correct = final_recovery.get("publicCorrect")
    credit_after = object_or_empty(evidence.get("cpuCreditAfter"))
    credit_points = [
        row for row in credit_after.get("Datapoints", [])
        if isinstance(row, dict)
    ] if isinstance(credit_after.get("Datapoints"), list) else []
    credit_points.sort(key=lambda row: str(row.get("Timestamp") or ""))
    if worker_errors is None:
        gateway_note = "Metadata không có số lỗi worker_connections; không kết luận giới hạn gateway từ metadata."
    elif worker_errors > 0:
        gateway_note = (
            "Log Nginx ghi nhận worker_connections không đủ trong cửa sổ trên. Đây là ràng buộc gateway được quan sát "
            "trong burst, không phải bằng chứng về giới hạn tối đa của backend hay PostgreSQL; không gán mọi lỗi client cho một nguyên nhân."
        )
    else:
        gateway_note = "Metadata ghi nhận 0 lỗi worker_connections; không kết luận giới hạn gateway từ metadata."
    if final_public_status == 200 and final_public_correct is True:
        recovery_note = (
            "Một kiểm tra public muộn hơn thành công. Nó không xóa quan sát 429 trước đó và không thay thế kiểm tra sustained capacity."
        )
    elif public_status is None:
        recovery_note = "Không có quan sát recovery public trong metadata."
    elif public_status == 200 and public_correct is True:
        recovery_note = "Quan sát public này thành công, nhưng không thay thế kiểm tra sustained capacity."
    else:
        recovery_note = "Quan sát public này không thành công; không coi public recovery đã xác nhận."
    return {
        "nginxRows": [
            ("Cửa sổ log Nginx UTC", observed_text(nginx.get("errorWindowUtc"))),
            ("Nginx error rows", fmt(integer(nginx.get("errorRows")), 0)),
            ("Lỗi `worker_connections are not enough`", fmt(worker_errors, 0)),
            ("Nginx access rows trong cửa sổ", fmt(integer(nginx.get("burstAccessRows")), 0)),
            ("Client HTTP 502 trong requests.csv", fmt(request["statusCounts"].get("502", 0), 0)),
        ],
        "accessStatusRows": [(str(status), fmt(integer(count), 0))
                             for status, count in sorted(access_statuses.items())],
        "errorExamples": nginx.get("errorExamples") if isinstance(nginx.get("errorExamples"), list) else [],
        "gatewayNote": gateway_note,
        "recoveryRows": [
            ("Recovery timestamp UTC", observed_text(recovery.get("timestampUtc"))),
            ("Origin status / correct", f"{fmt(integer(recovery.get('originStatus')), 0)} / {observed_text(recovery.get('originCorrect'))}"),
            ("Public status / correct", f"{fmt(public_status, 0)} / {observed_text(public_correct)}"),
            ("Public recovery attempt trước đó (UTC / status)", f"{observed_text(public_attempt.get('timestampUtc'))} / {fmt(integer(public_attempt.get('status')), 0)}"),
            ("Ghi chú recovery trước đó", observed_text(public_attempt.get("note"))),
            ("Final public recovery (UTC / status / correct)", f"{observed_text(final_recovery.get('timestampUtc'))} / {fmt(final_public_status, 0)} / {observed_text(final_public_correct)}"),
            ("Database rows được metadata ghi lúc recovery", fmt(integer(recovery.get("databaseRows")), 0)),
        ],
        "recoveryNote": recovery_note,
        "generatorRows": [
            (observed_text(row.get("id")), observed_text(row.get("type")), observed_text(row.get("state")))
            for row in evidence.get("generatorDuring", []) if isinstance(row, dict)
        ],
        "generatorAfterRows": [
            (observed_text(row.get("id")), observed_text(row.get("type")), observed_text(row.get("state")))
            for row in evidence.get("generatorAfter", []) if isinstance(row, dict)
        ],
        "databasePreflightRows": [
            ("PostgreSQL version", observed_text(preflight.get("version"))),
            ("max_connections", observed_text(preflight.get("max_connections"))),
            ("shared_buffers", observed_text(preflight.get("shared_buffers"))),
            ("work_mem", observed_text(preflight.get("work_mem"))),
            ("Rows preflight", fmt(integer(preflight.get("rows")), 0)),
            ("Database bytes preflight", fmt(integer(preflight.get("db_bytes")), 0)),
        ],
        "cpuCreditRows": [
            (observed_text(row.get("Timestamp")), fmt(number(row.get("Average"))), observed_text(row.get("Unit")))
            for row in credit_points
        ],
        "cpuCreditNote": observed_text(object_or_empty(evidence.get("measurementNotes")).get("cpuCredits")),
    }


def simple_sections(report):
    request, host, db = report["requestAnalysis"], report["hostAndContainers"], report["database"]
    latency = request["latencyMs"]["httpRequestDuration"]
    correct, count = request["correctnessCounts"]["correct"], request["attemptCount"]
    rows = [
        ("Thành công, đúng dữ liệu", f"{fmt(correct, 0)} / {fmt(count, 0)} ({fmt(correct * 100 / count if count else None)}%)"),
        ("HTTP 500 / HTTP 502", f"{fmt(request['statusCounts'].get('500', 0), 0)} / {fmt(request['statusCounts'].get('502', 0), 0)}"),
        ("Request đồng thời phía client, peak", fmt(request["peakClientInFlight"], 0)),
        ("Độ lệch thời điểm bắt đầu gửi", f"{fmt(request['launchSpreadMs']['max'], 0)} ms"),
        ("Thời gian hoàn thành burst", f"{fmt(request['measurementWindow']['durationMs'] / 1000 if request['measurementWindow']['durationMs'] is not None else None, 3)} giây"),
        ("HTTP latency p95 / p99, gồm response lỗi", f"{fmt(latency['p(95)'])} / {fmt(latency['p(99)'])} ms"),
        ("CloudFront cache hits", fmt(request["cloudFrontHitCount"], 0)),
    ]
    resources = [
        ("EC2 backend CPU peak, toàn máy", f"{fmt(host['hostCpuBusyPeakPercent'])}%"),
        ("EC2 backend RAM còn khả dụng, thấp nhất", f"{fmt(host['hostAvailableMemoryMinimumKiB'] / 1024 if host['hostAvailableMemoryMinimumKiB'] is not None else None)} MiB"),
    ]
    for role, label in (("backend", "Backend"), ("postgres", "PostgreSQL")):
        values = host["containers"].get(role, {})
        memory = values.get("memoryPeakBytes")
        resources.append((f"{label} CPU peak / RAM peak", f"{fmt(values.get('cpuPeakPercentOfOneCore'))}% một core / {fmt(memory / 1024 ** 2 if memory is not None else None)} MiB"))
    resources.append(("PostgreSQL kết nối tổng / active tại snapshot, peak", f"{fmt((db['peakTotalConnectionsDuringBurst'] or {}).get('value'), 0)} / {fmt((db['peakActiveConnectionsDuringBurst'] or {}).get('value'), 0)}"))
    notes = [("Hệ thống không phục vụ thành công toàn bộ burst." if correct < count else "Toàn bộ request trả đúng dữ liệu.") if count else "Không có dữ liệu để kết luận."]
    diagnostics = metadata_diagnostics_view(report)
    if diagnostics:
        notes.append(diagnostics["gatewayNote"])
    metadata = report.get("metadata") or {}
    recovery = metadata.get("finalRecovery") or {}
    if recovery:
        notes.append(f"Public phục hồi lúc {recovery.get('timestampUtc')}: HTTP {recovery.get('publicStatus')}, dữ liệu {'đúng' if recovery.get('publicCorrect') else 'không đúng'}.")
    after = metadata.get("generatorAfter") or []
    if after:
        notes.append("Máy phát tải sau kiểm tra: " + ", ".join(f"{row.get('type')} / {row.get('state')}" for row in after) + ".")
    notes.append("Một burst không chứng minh tải kéo dài. Client đồng thời không phải SQL đồng thời; snapshot DB có thể bỏ lỡ truy vấn ngắn. CPU Docker tính theo một core, CPU EC2 theo toàn máy.")
    return rows, resources, notes


def make_markdown(report, metadata):
    rows, resources, notes = simple_sections(report)
    window = report["measurementWindowUTC"]
    return "\n".join([
        "# G-Scores — report 10.000 request tra cứu", "",
        f"API: `{report['manifest']['baseUrl']}/api/students/{{sbd}}` — mỗi request một SBD khác nhau, không retry.",
        f"Cửa sổ request/đo DB và EC2 (UTC): `{window['startedAtUtc']}` → `{window['finishedAtUtc']}`.", "",
        "## 1. Kết quả request", "", markdown_table(["Chỉ số", "Kết quả"], rows), "",
        "## 2. DB và EC2", "", markdown_table(["Chỉ số", "Kết quả quan sát"], resources), "",
        "## 3. Kết luận", "", *("- " + note for note in notes), "",
        "Bằng chứng chi tiết giữ riêng: [JSON](burst-report.json), [request CSV](requests.csv).", "",
    ])


def make_html(report, metadata):
    rows, resources, notes = simple_sections(report)
    def table(values):
        body = "".join("<tr>" + "".join(f"<td>{html.escape(str(value))}</td>" for value in row) + "</tr>" for row in values)
        return "<table><thead><tr><th>Chỉ số</th><th>Kết quả</th></tr></thead><tbody>" + body + "</tbody></table>"
    window = report["measurementWindowUTC"]
    return "".join([
        '<!doctype html><html lang="vi"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">',
        "<title>G-Scores — report 10.000 request</title>",
        "<style>body{font:14px system-ui,sans-serif;color:#17283c;margin:20px auto;padding:0 18px;max-width:960px}h1{font-size:24px}h2{font-size:18px;margin:18px 0 8px}table{border-collapse:collapse;width:100%}th,td{padding:7px;text-align:left;border-bottom:1px solid #ddd}th{background:#eef3f8}p,li{line-height:1.4}li{margin:6px 0}a{color:#1555a2}@media print{body{margin:0;font-size:11px}h1{font-size:20px}td,th{padding:4px}h2{margin:12px 0 6px}}</style><main>",
        "<h1>G-Scores — report 10.000 request tra cứu</h1>",
        f"<p>API: {html.escape(report['manifest']['baseUrl'])}/api/students/{{sbd}} — mỗi request một SBD khác nhau, không retry.<br>",
        f"Cửa sổ request/đo DB và EC2 (UTC): {html.escape(str(window['startedAtUtc']))} → {html.escape(str(window['finishedAtUtc']))}.</p>",
        "<h2>1. Kết quả request</h2>", table(rows), "<h2>2. DB và EC2</h2>", table(resources),
        "<h2>3. Kết luận</h2><ul>", *("<li>" + html.escape(note) + "</li>" for note in notes),
        '</ul><p>Bằng chứng riêng: <a href="burst-report.md">Markdown</a> · <a href="burst-report.json">JSON</a> · <a href="requests.csv">Request CSV</a>.</p>',
        "</main></html>",
    ])


def write_outputs(output_dir, report, attempts):
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "burst-report.json").write_text(json_text(report) + "\n", encoding="utf-8")
    with (output_dir / "requests.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=REQUEST_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(attempts)
    request = report["requestAnalysis"]
    db = report["database"]
    host = report["hostAndContainers"]
    generator = report["generator"]
    measurement_window = report["measurementWindowUTC"]
    generator_window = generator["measurementWindowUTC"]
    metadata_evidence = object_or_empty(report.get("metadataEvidence"))
    nginx = object_or_empty(metadata_evidence.get("nginxDiagnostics"))
    recovery = object_or_empty(metadata_evidence.get("recovery"))
    final_recovery = object_or_empty(metadata_evidence.get("finalRecovery"))
    generator_types = ",".join(
        str(row.get("type"))
        for row in metadata_evidence.get("generatorDuring", [])
        if isinstance(row, dict) and row.get("type") is not None
    ) or None
    flat = {
        "manifestStartedAtUtc": report["manifest"]["startedAtUtc"],
        "manifestFinishedAtUtc": report["manifest"]["finishedAtUtc"],
        "measurementWindowStartedAtUtc": measurement_window["startedAtUtc"],
        "measurementWindowFinishedAtUtc": measurement_window["finishedAtUtc"],
        "measurementWindowDurationMs": measurement_window["durationMilliseconds"],
        "measurementWindowValidRequestAttempts": measurement_window["validRequestAttempts"],
        "baseUrl": report["manifest"]["baseUrl"],
        "vus": report["manifest"].get("vus"),
        "exitCode": report["manifest"].get("exitCode"),
        "requestAttempts": request["attemptCount"],
        "failedAttempts": request["failedAttemptCount"],
        "k6RequestsPerSecond": request["throughput"]["k6HttpRequestsPerSecond"],
        "attemptsPerManifestSecond": request["throughput"]["attemptsPerManifestSecond"],
        "clientTimingWindowMs": request["measurementWindow"]["durationMs"],
        "timedAttemptsPerClientWindowSecond": request["throughput"]["timedAttemptsPerClientWindowSecond"],
        "peakClientInFlight": request["peakClientInFlight"],
        "launchSpreadP95Ms": request["launchSpreadMs"]["p95"],
        "httpReqDurationP95Ms": request["latencyMs"]["httpRequestDuration"]["p(95)"],
        "httpReqDurationP99Ms": request["latencyMs"]["httpRequestDuration"]["p(99)"],
        "clientElapsedP95Ms": request["clientElapsedMs"]["p95"],
        "clientElapsedP99Ms": request["clientElapsedMs"]["p99"],
        "cloudFrontHitCount": request["cloudFrontHitCount"],
        "correctCount": request["correctnessCounts"]["correct"],
        "incorrectCount": request["correctnessCounts"]["incorrect"],
        "dbActiveConnectionPeak": (db["peakActiveConnectionsDuringBurst"] or {}).get("value"),
        "dbIdleConnectionPeak": (db["peakIdleConnectionsDuringBurst"] or {}).get("value"),
        "hostCpuBusyPeakPercent": host["hostCpuBusyPeakPercent"],
        "backendContainerCpuPeakPercent": host["containers"]["backend"]["cpuPeakPercentOfOneCore"],
        "generatorManifestCpuPeakPercent": generator["systemCpuPeakPercent"],
        "backendTelemetrySamplesDuringRequestWindow": host["sampleCountDuringBurst"],
        "databaseSnapshotsDuringRequestWindow": db["duringBurstSampleCount"],
        "examScoresTableCountersAvailable": db["examScoresTableCountersAvailable"],
        "nginxErrorRows": integer(nginx.get("errorRows")),
        "nginxWorkerConnectionLimitErrors": integer(nginx.get("workerConnectionLimitErrors")),
        "nginxBurstAccessRows": integer(nginx.get("burstAccessRows")),
        "originRecoveryStatus": integer(recovery.get("originStatus")),
        "publicRecoveryStatus": integer(recovery.get("publicStatus")),
        "finalPublicRecoveryStatus": integer(final_recovery.get("publicStatus")),
        "finalPublicRecoveryCorrect": final_recovery.get("publicCorrect"),
        "generatorInstanceTypesDuringBurst": generator_types,
        "generatorMeasurementWindowSource": generator_window["source"],
    }
    with (output_dir / "burst-summary.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(flat))
        writer.writeheader()
        writer.writerow(flat)
    with (output_dir / "exam-scores-table-deltas.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=("period", "table", "counter", "delta"))
        writer.writeheader()
        for period, table, counter, delta in exam_scores_delta_rows(db):
            writer.writerow({
                "period": period,
                "table": table,
                "counter": counter,
                "delta": delta,
            })
    markdown = make_markdown(report, report["metadata"])
    (output_dir / "burst-report.md").write_text(markdown, encoding="utf-8")
    (output_dir / "burst-report.html").write_text(make_html(report, report["metadata"]), encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, required=True,
                        help="burst results directory containing manifest.json, summary.json, requests.csv, generator-metrics.jsonl")
    parser.add_argument("--telemetry", type=Path, required=True,
                        help="backend monitor JSONL path")
    parser.add_argument("--metadata", type=Path,
                        help="optional JSON with AWS configuration and CloudWatch observations")
    parser.add_argument("--output", type=Path, required=True, help="directory for Markdown, HTML, JSON, and CSV reports")
    args = parser.parse_args(argv)
    try:
        report, attempts = build_report(args.results, args.telemetry, args.metadata)
        write_outputs(args.output, report, attempts)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        parser.error(str(error))
    print(f"Wrote burst report to {args.output}; {report['requestAnalysis']['attemptCount']} attempts, "
          f"{report['telemetryDiagnostics']['backendSamplesRead']} backend samples")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
