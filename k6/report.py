#!/usr/bin/env python3
"""Render a compact comparison of fixed-load k6 and server evidence."""

import argparse
import csv
import datetime as dt
import html
import json
import math
import re
import sys
from pathlib import Path

REPORT_SCHEMA = "g-scores-rps-comparison/v1"
THRESHOLDS = {
    "p95_ms_strictly_below": 500,
    "p99_ms_strictly_below": 1000,
    "error_rate_strictly_below": 0.01,
    "dropped_iterations_equal": 0,
    "successful_rps_at_least_target_fraction": 0.99,
}


class EvidenceError(ValueError):
    """An evidence file exists but is not a valid supported record."""


def finite_number(value):
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def nested(record, *keys):
    value = record
    for key in keys:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def display(value):
    if value is None:
        return "UNAVAILABLE"
    if isinstance(value, bool):
        return "true" if value else "false"
    number = finite_number(value)
    if number is not None:
        if number.is_integer():
            return str(int(number))
        return str(number)
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return str(value)


def markdown_cell(value):
    return html.escape(display(value), quote=False).replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def utc_now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def infer_rate(root, record):
    value = finite_number(nested(record, "rate"))
    if value is not None and value > 0:
        return int(value) if value.is_integer() else value
    # Run directory names conventionally contain the offered rate (for example 500RPS).
    matches = re.findall(r"(?<!\d)(500|1000|2000)(?!\d)", root.name)
    if len(set(matches)) == 1:
        return int(matches[0])
    return None


def read_evidence(path, label):
    if not path.is_file():
        return None, "missing"
    try:
        with path.open(encoding="utf-8") as stream:
            record = json.load(stream)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise EvidenceError(f"cannot read {label} {path}: {error}") from error
    if not isinstance(record, dict):
        raise EvidenceError(f"{label} {path} must contain a JSON object")
    if record.get("schema_version") != 1:
        raise EvidenceError(f"{label} {path} must have schema_version 1")
    return record, "available"


def assess_slo(k6, rate):
    """Classify each client threshold independently; absent values stay unavailable."""
    k6 = k6 if isinstance(k6, dict) else {}
    parsed_rate = finite_number(rate)
    criteria = [
        ("p95", k6.get("p95_ms"), "p95_ms < 500", lambda value: value < THRESHOLDS["p95_ms_strictly_below"]),
        ("p99", k6.get("p99_ms"), "p99_ms < 1000", lambda value: value < THRESHOLDS["p99_ms_strictly_below"]),
        ("errors", k6.get("error_rate"), "error_rate < 1%", lambda value: value < THRESHOLDS["error_rate_strictly_below"]),
        ("dropped_iterations", k6.get("dropped_iterations"), "dropped_iterations = 0", lambda value: value == THRESHOLDS["dropped_iterations_equal"]),
    ]
    throughput = k6.get("successful_rps")
    throughput_threshold = parsed_rate * THRESHOLDS["successful_rps_at_least_target_fraction"] if parsed_rate is not None else None
    criteria.append((
        "throughput",
        throughput,
        f"successful_rps >= 99% of target ({display(throughput_threshold)} RPS)" if throughput_threshold is not None else "successful_rps >= 99% of target",
        lambda value: None if throughput_threshold is None else value >= throughput_threshold,
    ))

    checks = []
    for name, raw_value, threshold, predicate in criteria:
        value = finite_number(raw_value)
        outcome = predicate(value) if value is not None else None
        status = "UNAVAILABLE" if outcome is None else ("PASS" if outcome else "FAIL")
        checks.append({"name": name, "observed": raw_value, "threshold": threshold, "status": status})
    if any(check["status"] == "FAIL" for check in checks):
        overall = "FAIL"
    elif any(check["status"] == "UNAVAILABLE" for check in checks):
        overall = "UNAVAILABLE"
    else:
        overall = "PASS"
    return {"status": overall, "checks": checks}


def load_run(root):
    root = Path(root)
    client_path = root / "evidence.json"
    server_path = root / "server-evidence.json"
    client, client_status = read_evidence(client_path, "client evidence")
    server, server_status = read_evidence(server_path, "server evidence")
    run_id = nested(client, "run_id") or root.name
    rate = infer_rate(root, client)
    k6 = nested(client, "k6") if isinstance(nested(client, "k6"), dict) else {}
    profile = nested(client, "profile") if isinstance(nested(client, "profile"), dict) else {}
    window = nested(client, "window") if isinstance(nested(client, "window"), dict) else {}
    diagnostics = nested(client, "diagnostics") if isinstance(nested(client, "diagnostics"), dict) else {}
    return {
        "run_id": run_id,
        "rate": rate,
        "base_url": nested(client, "base_url"),
        "profile": profile,
        "window": window,
        "k6": k6,
        "diagnostics": diagnostics,
        "server": server,
        "assessment": assess_slo(k6, rate),
        "source": {
            "root": str(root),
            "client_evidence_path": str(client_path),
            "client_status": client_status,
            "server_evidence_path": str(server_path),
            "server_status": server_status,
        },
        "client_record": client,
        "server_record": server,
    }


def build_report(roots):
    runs = [load_run(root) for root in roots]
    runs.sort(key=lambda run: (run["rate"] is None, run["rate"] if run["rate"] is not None else 0, str(run["run_id"])))
    return {
        "schema": REPORT_SCHEMA,
        "generated_at_utc": utc_now(),
        "tested_profile": {
            "ramp_up_seconds": 120,
            "start_rps": 100,
            "steady_seconds": 600,
            "ramp_down_seconds": 120,
            "scheduled_seconds": 840,
        },
        "thresholds": dict(THRESHOLDS),
        "methodology": {
            "legacy_rates": [500, 1000],
            "legacy_execution_model": "three-executor profile",
            "new_rate": 2000,
            "new_execution_model": "continuous profile",
            "nginx_quantiles": "Exact p95/p99 quantiles over matched raw request_time values; not averages of per-minute percentiles.",
            "nginx_window_selection": "For second-resolution access-log timestamps, include fully contained seconds: ceil(start_ms / 1000) <= timestamp_second < floor(end_ms / 1000).",
            "missing_value_policy": "Missing or null metrics are reported as UNAVAILABLE, never as zero.",
        },
        "source_inputs": [
            {
                **run["source"],
                "run_id": run["run_id"],
                "rate": run["rate"],
                "client_record": run["client_record"],
                "server_record": run["server_record"],
            }
            for run in runs
        ],
        "runs": runs,
    }


def observed_window(window):
    start_ms = finite_number(nested(window, "start_ms"))
    end_ms = finite_number(nested(window, "end_ms"))
    duration = (end_ms - start_ms) / 1000 if start_ms is not None and end_ms is not None and end_ms >= start_ms else None
    return duration


def run_label(run):
    rate = run.get("rate")
    if rate is not None:
        return f"{display(rate)} RPS"
    return f"UNAVAILABLE ({run.get('run_id', 'run')})"


def matrix_rows(runs, specs):
    rows = []
    for title, units, getter in specs:
        rows.append([title, units] + [getter(run) for run in runs])
    return rows


def triple(record, *path):
    values = nested(record, *path)
    if not isinstance(values, dict):
        return "UNAVAILABLE"
    return "avg {avg}; min {min}; max {max}".format(
        avg=display(values.get("avg")), min=display(values.get("min")), max=display(values.get("max"))
    )


def cloudwatch_value(run, key, fields=("avg", "max")):
    values = nested(run.get("server"), "cloudwatch", key)
    if not isinstance(values, dict):
        return "UNAVAILABLE"
    result = "; ".join(f"{field} {display(values.get(field))}" for field in fields)
    result += f"; period {display(values.get('period_seconds'))} s; samples {display(values.get('samples'))}"
    return result


def server_specs():
    return [
        ("Host sampler CPU", "% of host aggregate CPU capacity; avg/min/max", lambda run: triple(run.get("server"), "host", "sampler_cpu_percent")),
        ("Host available RAM", "MiB; avg/min/max", lambda run: triple(run.get("server"), "host", "available_ram_mib")),
        ("Host network in", "Mbps; measured coverage s", lambda run: f"{display(nested(run.get('server'), 'host', 'network', 'in_mbps'))}; coverage {display(nested(run.get('server'), 'host', 'network', 'coverage_seconds'))} s"),
        ("Host network out", "Mbps; measured coverage s", lambda run: f"{display(nested(run.get('server'), 'host', 'network', 'out_mbps'))}; coverage {display(nested(run.get('server'), 'host', 'network', 'coverage_seconds'))} s"),
        ("Backend sampler CPU", "% of one core (100% = one core); avg/min/max", lambda run: triple(run.get("server"), "containers", "backend", "sampler_cpu_percent_one_core")),
        ("Backend sampler memory", "sampler-reported %; avg/min/max", lambda run: triple(run.get("server"), "containers", "backend", "sampler_memory_percent")),
        ("Postgres sampler CPU", "% of one core (100% = one core); avg/min/max", lambda run: triple(run.get("server"), "containers", "postgres", "sampler_cpu_percent_one_core")),
        ("Postgres sampler memory", "sampler-reported %; avg/min/max", lambda run: triple(run.get("server"), "containers", "postgres", "sampler_memory_percent")),
        ("DB connections", "connections; avg/min/max", lambda run: triple(run.get("server"), "database", "connections")),
        ("DB active connections", "connections; avg/min/max", lambda run: triple(run.get("server"), "database", "active_connections")),
        ("DB idle-in-transaction", "connections; avg/min/max", lambda run: triple(run.get("server"), "database", "idle_in_transaction")),
        ("CloudWatch EC2 CPU", "% of EC2 instance aggregate capacity; avg/max", lambda run: cloudwatch_value(run, "ec2_cpu")),
        ("CloudWatch host memory", "%; avg/max", lambda run: cloudwatch_value(run, "host_memory_percent")),
        ("CloudWatch backend CPU", "CloudWatch ECS service/task CPU %; avg/max (not one-core sampler %)", lambda run: cloudwatch_value(run, "backend_cpu")),
        ("CloudWatch backend memory", "CloudWatch ECS memory %; avg/max", lambda run: cloudwatch_value(run, "backend_memory_percent")),
        ("CloudWatch Postgres CPU", "CloudWatch ECS service/task CPU %; avg/max (not one-core sampler %)", lambda run: cloudwatch_value(run, "postgres_cpu")),
        ("Telemetry coverage", "samples; missing fields; errors; UTC span", lambda run: _telemetry(run.get("server"))),
        ("Nginx matched requests", "requests", lambda run: display(nested(run.get("server"), "nginx", "requests"))),
        ("Nginx error count / rate", "requests / fraction", lambda run: f"{display(nested(run.get('server'), 'nginx', 'error_count'))} / {display(nested(run.get('server'), 'nginx', 'error_rate'))}"),
        ("Nginx p95 / p99 request_time", "ms; exact raw request_time quantiles", lambda run: f"{display(nested(run.get('server'), 'nginx', 'p95_ms'))} / {display(nested(run.get('server'), 'nginx', 'p99_ms'))}"),
        ("Nginx coverage", "UTC; seconds; timestamp resolution", lambda run: _nginx_coverage(run.get("server"))),
        ("Nginx method", "source / endpoint filter", lambda run: _nginx_method(run.get("server"))),
        ("AWS task snapshot", "ARNs; ECS CPU units; memory MiB; health / unchanged", lambda run: _task_snapshot(run.get("server"))),
        ("AWS task snapshot limitation", "as recorded by sampler", lambda run: display(nested(run.get("server"), "task", "snapshot_limitation"))),
        ("CloudWatch CPU credits", "first / last; UTC boundaries; mode", lambda run: _credits(run.get("server"))),
    ]


def _telemetry(server):
    telemetry = nested(server, "telemetry")
    if not isinstance(telemetry, dict):
        return "UNAVAILABLE"
    return (f"samples {display(telemetry.get('samples'))}; missing {display(telemetry.get('missing_count'))}; "
            f"errors {display(telemetry.get('errors'))}; {display(telemetry.get('first_utc'))} → {display(telemetry.get('last_utc'))}")


def _nginx_coverage(server):
    nginx = nested(server, "nginx")
    if not isinstance(nginx, dict):
        return "UNAVAILABLE"
    return (f"{display(nginx.get('coverage_start_utc'))} → {display(nginx.get('coverage_end_utc'))}; "
            f"{display(nginx.get('coverage_seconds'))} s; resolution {display(nginx.get('timestamp_resolution_seconds'))} s")


def _nginx_method(server):
    method = nested(server, "nginx", "method")
    if method is None:
        return "UNAVAILABLE"
    return f"{method}; /api/students/ paths only"


def _task_snapshot(server):
    task = nested(server, "task")
    if not isinstance(task, dict):
        return "UNAVAILABLE"
    return (f"before {display(task.get('before_arn'))}; after {display(task.get('after_arn'))}; "
            f"definition {display(task.get('task_definition_arn'))}; CPU {display(task.get('cpu_units'))} units; "
            f"memory {display(task.get('memory_mib'))} MiB; healthy after {display(task.get('healthy_after'))}; "
            f"unchanged {display(task.get('unchanged'))}")


def _credits(server):
    credits = nested(server, "cloudwatch", "credits")
    if not isinstance(credits, dict):
        return "UNAVAILABLE"
    return (f"first {display(credits.get('first'))} at {display(credits.get('first_utc'))}; "
            f"last {display(credits.get('last'))} at {display(credits.get('last_utc'))}; mode {display(credits.get('mode'))}")


def _markdown_table(headers, rows):
    lines = ["| " + " | ".join(markdown_cell(value) for value in headers) + " |",
             "| " + " | ".join("---" for _ in headers) + " |"]
    lines.extend("| " + " | ".join(markdown_cell(value) for value in row) + " |" for row in rows)
    return lines


def _profile_label(profile):
    return (f"ramp {display(profile.get('ramp_up_seconds'))} s; start {display(profile.get('start_rps'))} RPS; "
            f"steady {display(profile.get('steady_seconds'))} s; down {display(profile.get('ramp_down_seconds'))} s")


def _client_rows(runs):
    rows = []
    for run in runs:
        k6 = run["k6"]
        window = run["window"]
        profile = run["profile"]
        rows.append([
            run_label(run), run["run_id"], run["base_url"], profile.get("execution_model"), _profile_label(profile),
            f"{display(window.get('start_utc'))} → {display(window.get('end_utc'))}; {display(observed_window(window))} s",
            f"{display(k6.get('started'))} / {display(k6.get('responses'))}",
            f"{display(k6.get('successful_completions'))} / {display(k6.get('successful_rps'))} RPS",
            f"{display(k6.get('p95_ms'))} / {display(k6.get('p99_ms'))} ms",
            f"{display(k6.get('error_count'))} / {display(k6.get('error_rate'))}",
            display(k6.get("dropped_iterations")),
            f"{display(k6.get('success_all'))} / {display(k6.get('complete_responses'))} / {display(k6.get('exit_code'))}",
            run["assessment"]["status"],
        ])
    return rows


def _slo_rows(runs):
    rows = []
    for run in runs:
        checks = {check["name"]: check["status"] for check in run["assessment"]["checks"]}
        rows.append([run_label(run), run["assessment"]["status"], checks["p95"], checks["p99"], checks["errors"],
                     checks["dropped_iterations"], checks["throughput"]])
    return rows


def _minute_rows(runs):
    rows = []
    for run in runs:
        minutes = run["k6"].get("minutes")
        valid_minutes = [minute for minute in minutes if isinstance(minute, dict)] if isinstance(minutes, list) else []
        if not valid_minutes:
            rows.append([run_label(run), "UNAVAILABLE", None, None, None, None])
            continue
        for minute in valid_minutes:
            rows.append([run_label(run), minute.get("minute"), minute.get("successful_rps"), minute.get("p95_ms"),
                         minute.get("p99_ms"), minute.get("dropped_iterations")])
    return rows


def _drop_rows(runs):
    rows = []
    for run in runs:
        drops = nested(run, "diagnostics", "dropped_by_scenario")
        valid_drops = [item for item in drops if isinstance(item, dict)] if isinstance(drops, list) else []
        if not valid_drops:
            rows.append([run_label(run), "UNAVAILABLE", None, None, None])
            continue
        for item in valid_drops:
            rows.append([run_label(run), item.get("scenario"), item.get("count"), item.get("first_utc"), item.get("last_utc")])
    return rows


def render_markdown(report):
    runs = report["runs"]
    profile = report["tested_profile"]
    lines = [
        "# Fixed-load RPS evidence comparison", "",
        "This report describes only the measured fixed-load windows. It makes no maximum-capacity conclusion.",
        ("Requested profile: {ramp_up_seconds}s ramp-up from {start_rps} RPS to target, "
         "{steady_seconds}s steady, then {ramp_down_seconds}s ramp-down to 0 ({scheduled_seconds}s scheduled total). "
         "Per-run observed windows and profiles below come from the compact evidence records.").format(**profile),
        "The 500 and 1000 RPS runs use the legacy three-executor profile; the 2000 RPS run uses a continuous profile. "
        "That execution-model change is a methodology difference, so the rows are descriptive rather than a strictly like-for-like comparison.", "",
        "## Client results", "",
        "Client p95/p99 are computed from exact k6 request-duration samples, not averages of per-minute percentiles. "
        "The error count/rate and dropped-iteration count are separate signals; drops are not added to the error rate.", "",
    ]
    lines.extend(_markdown_table(
        ["Target", "Run", "Base URL", "Execution model", "Recorded profile", "Observed steady window (UTC; duration)", "Started / responses",
         "Successful completions / successful RPS", "p95 / p99 (ms)", "Errors count / rate (fraction)", "Dropped iterations",
         "success_all / complete responses / exit code", "SLO"], _client_rows(runs)))
    lines.extend(["", "SLO thresholds (strict where shown): p95 < 500 ms; p99 < 1000 ms; error rate < 1%; dropped iterations = 0; successful RPS ≥ 99% of target. "
                  "Overall is UNAVAILABLE if any criterion is unavailable and none fails; an observed failed criterion remains FAIL even if another is unavailable.", ""])
    lines.extend(_markdown_table(["Target", "Overall", "p95", "p99", "Errors", "Drops", "Throughput"], _slo_rows(runs)))
    lines.extend(["", "## Per-minute client evidence", "",
                  "Minute numbers are 1-based full 60-second bucket indices as emitted by the collector; all available rows are included. "
                  "This full table exposes the initial transient in the 1000 RPS run and shows drop timing rather than combining phase totals.", ""])
    lines.extend(_markdown_table(["Target", "Minute", "Successful RPS", "p95 ms", "p99 ms", "Dropped iterations"], _minute_rows(runs)))
    lines.extend(["", "## Dropped iterations by scenario", "",
                  "Scenario timestamps and counts are shown separately; the k6 steady-window total is not inflated by ramp-down drops.", ""])
    drop_rows = _drop_rows(runs)
    lines.extend(_markdown_table(["Target", "Scenario", "Count", "First UTC", "Last UTC"], drop_rows))
    if not drop_rows:
        lines.append("No per-scenario drop diagnostics were available.")
    lines.extend(["", "## Backend, database, Nginx, and AWS evidence", "",
                  "Host sampler CPU is normalized to aggregate host CPU capacity. Container sampler CPU is one-core normalized (100% = one core and can exceed 100%). "
                  "CloudWatch ECS percentages retain their CloudWatch service/task denominator and must not be compared as if they were one-core sampler percentages; EC2 CPU is instance-aggregate percent.",
                  "Nginx p95/p99 are exact quantiles over raw matched request_time values for /api/students/ requests only. "
                  "Access-log timestamps have one-second precision: only fully contained seconds are selected using "
                  "ceil(start_ms/1000) ≤ timestamp_second < floor(end_ms/1000), so a nominal 600-second window commonly yields 599 seconds of coverage. "
                  "Coverage and timestamp resolution are reported per run; no unobserved boundary seconds are inferred.", ""])
    headers = ["Signal", "Units / denominator"] + [run_label(run) for run in runs]
    lines.extend(_markdown_table(headers, matrix_rows(runs, server_specs())))
    lines.extend(["", "CloudWatch values are native reported buckets/samples with their period and sample count; bucket windows can overlap the requested load window. "
                  "CPU-credit values are first/last observations with timestamps and mode, not a full-resolution trace. "
                  "Task ARNs, configured task CPU/memory, health, unchanged state, and any snapshot limitation are reported as observed; missing task evidence remains unavailable.", "",
                  "## Evidence quality", ""])
    for run in runs:
        client_status = run["source"]["client_status"]
        server_status = run["source"]["server_status"]
        lines.append(f"- **{markdown_cell(run_label(run))}** — client evidence: {client_status}; server evidence: {server_status}.")
        issues = nested(run, "diagnostics", "issues")
        if isinstance(issues, list) and issues:
            lines.append("  - k6 evidence issues: " + "; ".join(markdown_cell(issue) for issue in issues))
        telemetry_errors = nested(run.get("server"), "telemetry", "errors")
        if telemetry_errors not in (None, [], 0):
            lines.append("  - server telemetry errors: " + markdown_cell(telemetry_errors))
    if not runs:
        lines.append("No result roots were provided.")
    lines.extend(["", "## Source files", ""])
    lines.extend(_markdown_table(
        ["Run", "Client evidence", "Client status", "Server evidence", "Server status"],
        [[run["run_id"], run["source"]["client_evidence_path"], run["source"]["client_status"],
          run["source"]["server_evidence_path"], run["source"]["server_status"]] for run in runs]))
    return "\n".join(lines) + "\n"


def _telemetry_errors_json(server):
    value = nested(server, "telemetry", "errors")
    return value if value is not None else None


CSV_COLUMNS = [
    "run_id", "rate_rps", "base_url", "execution_model", "ramp_up_seconds", "start_rps", "steady_seconds", "ramp_down_seconds",
    "window_start_utc", "window_end_utc", "window_duration_seconds", "started", "responses", "success_all", "successful_completions",
    "successful_rps", "error_count", "error_rate", "dropped_iterations", "p95_ms", "p99_ms", "complete_responses", "exit_code",
    "slo_status", "slo_p95_status", "slo_p99_status", "slo_errors_status", "slo_drops_status", "slo_throughput_status",
    "threshold_p95_ms_strictly_below", "threshold_p99_ms_strictly_below", "threshold_error_rate_strictly_below",
    "threshold_dropped_iterations_equal", "threshold_successful_rps_at_least_target_fraction",
    "dropped_by_scenario_json", "minutes_json", "k6_issues_json",
    "host_sampler_cpu_avg_percent", "host_sampler_cpu_min_percent", "host_sampler_cpu_max_percent",
    "host_available_ram_avg_mib", "host_available_ram_min_mib", "host_available_ram_max_mib",
    "host_network_in_mbps", "host_network_out_mbps", "host_network_coverage_seconds",
    "backend_sampler_cpu_one_core_avg_percent", "backend_sampler_cpu_one_core_min_percent", "backend_sampler_cpu_one_core_max_percent",
    "backend_sampler_memory_avg_percent", "backend_sampler_memory_min_percent", "backend_sampler_memory_max_percent",
    "postgres_sampler_cpu_one_core_avg_percent", "postgres_sampler_cpu_one_core_min_percent", "postgres_sampler_cpu_one_core_max_percent",
    "postgres_sampler_memory_avg_percent", "postgres_sampler_memory_min_percent", "postgres_sampler_memory_max_percent",
    "db_connections_avg", "db_connections_min", "db_connections_max", "db_active_connections_avg", "db_active_connections_min", "db_active_connections_max",
    "db_idle_in_transaction_avg", "db_idle_in_transaction_min", "db_idle_in_transaction_max",
    "telemetry_samples", "telemetry_first_utc", "telemetry_last_utc", "telemetry_missing_count", "telemetry_errors_json",
    "cloudwatch_ec2_cpu_avg_percent", "cloudwatch_ec2_cpu_max_percent", "cloudwatch_ec2_cpu_period_seconds", "cloudwatch_ec2_cpu_samples",
    "cloudwatch_host_memory_avg_percent", "cloudwatch_host_memory_max_percent", "cloudwatch_host_memory_period_seconds", "cloudwatch_host_memory_samples",
    "cloudwatch_backend_cpu_avg_percent", "cloudwatch_backend_cpu_max_percent", "cloudwatch_backend_cpu_period_seconds", "cloudwatch_backend_cpu_samples",
    "cloudwatch_backend_memory_avg_percent", "cloudwatch_backend_memory_max_percent", "cloudwatch_backend_memory_period_seconds", "cloudwatch_backend_memory_samples",
    "cloudwatch_postgres_cpu_avg_percent", "cloudwatch_postgres_cpu_max_percent", "cloudwatch_postgres_cpu_period_seconds", "cloudwatch_postgres_cpu_samples",
    "cloudwatch_credits_first", "cloudwatch_credits_last", "cloudwatch_credits_first_utc", "cloudwatch_credits_last_utc", "cloudwatch_credits_mode",
    "nginx_requests", "nginx_error_count", "nginx_error_rate", "nginx_p95_ms", "nginx_p99_ms", "nginx_coverage_start_utc", "nginx_coverage_end_utc",
    "nginx_coverage_seconds", "nginx_timestamp_resolution_seconds", "nginx_method",
    "task_before_arn", "task_after_arn", "task_definition_arn", "task_cpu_units", "task_memory_mib", "task_healthy_after", "task_unchanged", "task_snapshot_limitation",
    "client_evidence_path", "client_evidence_status", "server_evidence_path", "server_evidence_status",
]


def _flatten_run(run):
    row = {column: None for column in CSV_COLUMNS}
    profile = run["profile"]
    window = run["window"]
    k6 = run["k6"]
    server = run["server"]
    row.update({
        "run_id": run["run_id"], "rate_rps": run["rate"], "base_url": run["base_url"],
        "execution_model": profile.get("execution_model"), "ramp_up_seconds": profile.get("ramp_up_seconds"),
        "start_rps": profile.get("start_rps"), "steady_seconds": profile.get("steady_seconds"), "ramp_down_seconds": profile.get("ramp_down_seconds"),
        "window_start_utc": window.get("start_utc"), "window_end_utc": window.get("end_utc"), "window_duration_seconds": observed_window(window),
        "started": k6.get("started"), "responses": k6.get("responses"), "success_all": k6.get("success_all"),
        "successful_completions": k6.get("successful_completions"), "successful_rps": k6.get("successful_rps"),
        "error_count": k6.get("error_count"), "error_rate": k6.get("error_rate"), "dropped_iterations": k6.get("dropped_iterations"),
        "p95_ms": k6.get("p95_ms"), "p99_ms": k6.get("p99_ms"), "complete_responses": k6.get("complete_responses"), "exit_code": k6.get("exit_code"),
        "slo_status": run["assessment"]["status"],
        "threshold_p95_ms_strictly_below": THRESHOLDS["p95_ms_strictly_below"],
        "threshold_p99_ms_strictly_below": THRESHOLDS["p99_ms_strictly_below"],
        "threshold_error_rate_strictly_below": THRESHOLDS["error_rate_strictly_below"],
        "threshold_dropped_iterations_equal": THRESHOLDS["dropped_iterations_equal"],
        "threshold_successful_rps_at_least_target_fraction": THRESHOLDS["successful_rps_at_least_target_fraction"],
        "dropped_by_scenario_json": _json_cell(run["diagnostics"].get("dropped_by_scenario")),
        "minutes_json": _json_cell(k6.get("minutes")), "k6_issues_json": _json_cell(run["diagnostics"].get("issues")),
        "host_network_in_mbps": nested(server, "host", "network", "in_mbps"),
        "host_network_out_mbps": nested(server, "host", "network", "out_mbps"),
        "host_network_coverage_seconds": nested(server, "host", "network", "coverage_seconds"),
        "telemetry_samples": nested(server, "telemetry", "samples"), "telemetry_first_utc": nested(server, "telemetry", "first_utc"),
        "telemetry_last_utc": nested(server, "telemetry", "last_utc"), "telemetry_missing_count": nested(server, "telemetry", "missing_count"),
        "telemetry_errors_json": _json_cell(_telemetry_errors_json(server)),
        "cloudwatch_credits_first": nested(server, "cloudwatch", "credits", "first"), "cloudwatch_credits_last": nested(server, "cloudwatch", "credits", "last"),
        "cloudwatch_credits_first_utc": nested(server, "cloudwatch", "credits", "first_utc"), "cloudwatch_credits_last_utc": nested(server, "cloudwatch", "credits", "last_utc"),
        "cloudwatch_credits_mode": nested(server, "cloudwatch", "credits", "mode"),
        "nginx_requests": nested(server, "nginx", "requests"), "nginx_error_count": nested(server, "nginx", "error_count"),
        "nginx_error_rate": nested(server, "nginx", "error_rate"), "nginx_p95_ms": nested(server, "nginx", "p95_ms"),
        "nginx_p99_ms": nested(server, "nginx", "p99_ms"), "nginx_coverage_start_utc": nested(server, "nginx", "coverage_start_utc"),
        "nginx_coverage_end_utc": nested(server, "nginx", "coverage_end_utc"), "nginx_coverage_seconds": nested(server, "nginx", "coverage_seconds"),
        "nginx_timestamp_resolution_seconds": nested(server, "nginx", "timestamp_resolution_seconds"), "nginx_method": nested(server, "nginx", "method"),
        "task_before_arn": nested(server, "task", "before_arn"), "task_after_arn": nested(server, "task", "after_arn"),
        "task_definition_arn": nested(server, "task", "task_definition_arn"), "task_cpu_units": nested(server, "task", "cpu_units"),
        "task_memory_mib": nested(server, "task", "memory_mib"), "task_healthy_after": nested(server, "task", "healthy_after"),
        "task_unchanged": nested(server, "task", "unchanged"), "task_snapshot_limitation": nested(server, "task", "snapshot_limitation"),
        "client_evidence_path": run["source"]["client_evidence_path"], "client_evidence_status": run["source"]["client_status"],
        "server_evidence_path": run["source"]["server_evidence_path"], "server_evidence_status": run["source"]["server_status"],
    })
    check_names = {"p95": "slo_p95_status", "p99": "slo_p99_status", "errors": "slo_errors_status",
                   "dropped_iterations": "slo_drops_status", "throughput": "slo_throughput_status"}
    check_statuses = {check["name"]: check["status"] for check in run["assessment"]["checks"]}
    row.update({column: check_statuses[name] for name, column in check_names.items()})
    for prefix, path in [
        ("host_sampler_cpu", ("host", "sampler_cpu_percent")),
        ("host_available_ram", ("host", "available_ram_mib")),
        ("backend_sampler_cpu_one_core", ("containers", "backend", "sampler_cpu_percent_one_core")),
        ("backend_sampler_memory", ("containers", "backend", "sampler_memory_percent")),
        ("postgres_sampler_cpu_one_core", ("containers", "postgres", "sampler_cpu_percent_one_core")),
        ("postgres_sampler_memory", ("containers", "postgres", "sampler_memory_percent")),
        ("db_connections", ("database", "connections")),
        ("db_active_connections", ("database", "active_connections")),
        ("db_idle_in_transaction", ("database", "idle_in_transaction")),
    ]:
        values = nested(server, *path)
        if isinstance(values, dict):
            suffix = "_mib" if prefix == "host_available_ram" else "_percent" if "cpu" in prefix or "memory" in prefix else ""
            for field in ("avg", "min", "max"):
                row[f"{prefix}_{field}{suffix}"] = values.get(field)
    for metric_key, prefix in [("ec2_cpu", "cloudwatch_ec2_cpu"), ("host_memory_percent", "cloudwatch_host_memory"),
                               ("backend_cpu", "cloudwatch_backend_cpu"), ("backend_memory_percent", "cloudwatch_backend_memory"),
                               ("postgres_cpu", "cloudwatch_postgres_cpu")]:
        metric = nested(server, "cloudwatch", metric_key)
        if isinstance(metric, dict):
            for source, target in (("avg", "avg_percent"), ("max", "max_percent"), ("period_seconds", "period_seconds"), ("samples", "samples")):
                row[f"{prefix}_{target}"] = metric.get(source)
    return row


def _json_cell(value):
    return None if value is None else json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def render_csv(report):
    from io import StringIO
    stream = StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=CSV_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    for run in report["runs"]:
        row = _flatten_run(run)
        writer.writerow({column: "UNAVAILABLE" if value is None else value for column, value in row.items()})
    return stream.getvalue()


def html_table(title, headers, rows):
    rendered_rows = []
    for row in rows:
        rendered_rows.append("<tr>" + "".join(f"<td>{html.escape(display(value), quote=True)}</td>" for value in row) + "</tr>")
    table_headers = "".join(f"<th scope=\"col\">{html.escape(display(value), quote=True)}</th>" for value in headers)
    return (f"<section><h2>{html.escape(title, quote=True)}</h2><div class=\"table-wrap\"><table><thead><tr>{table_headers}</tr></thead>"
            f"<tbody>{''.join(rendered_rows)}</tbody></table></div></section>")


def render_html(report):
    runs = report["runs"]
    profile = report["tested_profile"]
    summary = (
        "This report describes only the measured fixed-load windows and makes no maximum-capacity conclusion. "
        f"Requested profile: {profile['ramp_up_seconds']}s ramp-up from {profile['start_rps']} RPS to target, "
        f"{profile['steady_seconds']}s steady, {profile['ramp_down_seconds']}s ramp-down to 0 "
        f"({profile['scheduled_seconds']}s scheduled total). The 500/1000 RPS runs use the legacy three-executor profile; "
        "the 2000 RPS run uses a continuous profile. This execution-model change is a methodology difference, so the comparison is descriptive."
    )
    sections = [
        html_table("Client results", ["Target", "Run", "Base URL", "Execution model", "Recorded profile", "Observed steady window (UTC; duration)", "Started / responses",
                                      "Successful completions / RPS", "p95 / p99 ms", "Errors count / rate (fraction)", "Dropped iterations",
                                      "success_all / complete responses / exit code", "SLO"], _client_rows(runs)),
        html_table("SLO classification", ["Target", "Overall", "p95", "p99", "Errors", "Drops", "Throughput"], _slo_rows(runs)),
        html_table("Per-minute client evidence", ["Target", "Minute", "Successful RPS", "p95 ms", "p99 ms", "Dropped iterations"], _minute_rows(runs)),
        html_table("Dropped iterations by scenario", ["Target", "Scenario", "Count", "First UTC", "Last UTC"], _drop_rows(runs)),
        html_table("Backend, database, Nginx, and AWS evidence", ["Signal", "Units / denominator"] + [run_label(run) for run in runs], matrix_rows(runs, server_specs())),
        html_table("Evidence sources", ["Run", "Client evidence", "Client status", "Server evidence", "Server status"],
                   [[run["run_id"], run["source"]["client_evidence_path"], run["source"]["client_status"],
                     run["source"]["server_evidence_path"], run["source"]["server_status"]] for run in runs]),
    ]
    methodology = (
        "SLO thresholds: p95 < 500 ms; p99 < 1000 ms; error rate < 1%; dropped iterations = 0; successful RPS ≥ 99% of target. "
        "Missing criteria are UNAVAILABLE, never assumed to be zero. Errors and dropped iterations remain distinct. "
        "Client latency percentiles use exact k6 samples, not per-minute averages. "
        "Nginx p95/p99 are exact quantiles over matched raw request_time values for /api/students/ only. "
        "One-second access-log timestamps are filtered to fully contained steady-window seconds: "
        "ceil(start_ms/1000) ≤ timestamp_second < floor(end_ms/1000); a nominal 600s window commonly has 599s coverage. "
        "Host sampler CPU is host-aggregate normalized, container sampler CPU is one-core normalized (100% = one core), "
        "CloudWatch ECS percentages retain their service/task denominator, and EC2 CPU is instance-aggregate percent. "
        "CloudWatch buckets may overlap window boundaries; credit fields are first/last observations, not a full-resolution trace."
    )
    style = """<style>
:root{color-scheme:light;font-family:system-ui,-apple-system,Segoe UI,sans-serif;color:#172033;background:#f5f7fb}
body{max-width:1500px;margin:0 auto;padding:2rem;line-height:1.45}h1,h2{color:#13294b}section{margin:2rem 0}p{max-width:1100px}.table-wrap{overflow-x:auto;background:white;border:1px solid #d7deea;border-radius:6px}
table{border-collapse:collapse;width:100%;font-size:.92rem}th,td{padding:.55rem .7rem;border-bottom:1px solid #e2e7ef;text-align:left;vertical-align:top}th{background:#eaf0f8;position:sticky;top:0}tbody tr:nth-child(even){background:#f8fafd}footer{margin-top:2rem;color:#44536a}
</style>"""
    return ("<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
            "<title>Fixed-load RPS evidence comparison</title>" + style + "</head><body><h1>Fixed-load RPS evidence comparison</h1>"
            f"<p>{html.escape(summary, quote=True)}</p><p>{html.escape(methodology, quote=True)}</p>"
            + "".join(sections) + f"<footer>Generated {html.escape(str(report.get('generated_at_utc', 'UNAVAILABLE')), quote=True)}.</footer></body></html>\n")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", nargs=3, required=True, metavar=("500_ROOT", "1000_ROOT", "2000_ROOT"),
                        help="the 500, 1000, and 2000 RPS evidence directories")
    parser.add_argument("--output", required=True, help="directory for comparison.md/json/csv/html")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    try:
        report = build_report(args.results)
        output = Path(args.output)
        output.mkdir(parents=True, exist_ok=True)
        files = {
            "comparison.md": render_markdown(report),
            "comparison.json": json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
            "comparison.csv": render_csv(report),
            "comparison.html": render_html(report),
        }
        for name, content in files.items():
            with (output / name).open("w", encoding="utf-8", newline="") as stream:
                stream.write(content)
    except (EvidenceError, OSError, ValueError) as error:
        print(f"report generation failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
