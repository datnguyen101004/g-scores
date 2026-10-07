#!/usr/bin/env python3
"""Read-only host, Docker, and PostgreSQL telemetry sampler."""

import argparse
import concurrent.futures
import datetime as dt
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time


DEFAULT_OUTPUT = "/tmp/g-scores-backend-metrics.jsonl"
COMMAND_TIMEOUT_SECONDS = 10
CPU_FIELDS = ("user", "nice", "system", "idle", "iowait", "irq", "softirq", "steal")
ECS_LABEL = "com.amazonaws.ecs.container-name"
POSTGRES_QUERY = """SELECT json_build_object(
  'connections',
  (SELECT json_build_object(
     'total', count(*),
     'active', count(*) FILTER (WHERE state = 'active'),
     'idle', count(*) FILTER (WHERE state = 'idle'),
     'idle_in_transaction', count(*) FILTER (WHERE state LIKE 'idle in transaction%'))
   FROM pg_stat_activity
   WHERE datname = current_database() AND pid <> pg_backend_pid()),
  'activity_by_state',
  (SELECT COALESCE(json_object_agg(state, connections), '{}'::json)
   FROM (
     SELECT COALESCE(state, '<null>') AS state, count(*) AS connections
     FROM pg_stat_activity
     WHERE datname = current_database() AND pid <> pg_backend_pid()
     GROUP BY state
   ) AS activity),
  'wait_events',
  (SELECT COALESCE(json_agg(json_build_object(
       'wait_event_type', wait_event_type,
       'wait_event', wait_event,
       'connections', connections)), '[]'::json)
   FROM (
     SELECT wait_event_type, wait_event, count(*) AS connections
     FROM pg_stat_activity
     WHERE datname = current_database() AND pid <> pg_backend_pid() AND wait_event IS NOT NULL
     GROUP BY wait_event_type, wait_event
   ) AS waits),
  'database_counters',
  (SELECT json_build_object(
     'numbackends', numbackends,
     'xact_commit', xact_commit,
     'xact_rollback', xact_rollback,
     'blks_read', blks_read,
     'blks_hit', blks_hit,
     'tup_returned', tup_returned,
     'tup_fetched', tup_fetched,
     'tup_inserted', tup_inserted,
     'tup_updated', tup_updated,
     'tup_deleted', tup_deleted,
     'temp_files', temp_files,
     'temp_bytes', temp_bytes,
     'deadlocks', deadlocks,
     'conflicts', conflicts)
   FROM pg_stat_database
   WHERE datname = current_database()),
  'exam_scores_table_counters',
  (SELECT COALESCE(json_agg(json_build_object(
       'schema_name', schemaname,
       'table_name', relname,
       'seq_scan', seq_scan,
       'idx_scan', idx_scan,
       'seq_tup_read', seq_tup_read,
       'idx_tup_fetch', idx_tup_fetch)
     ORDER BY schemaname), '[]'::json)
   FROM pg_stat_user_tables
   WHERE relname = 'exam_scores')
)::text;"""


class SamplingError(Exception):
    """An expected telemetry read or command failed."""


def positive_finite_float(value):
    try:
        number = float(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be a number") from error
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("must be a finite number greater than zero")
    return number


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duration", type=positive_finite_float, default=3600,
                        help="sampling duration in seconds (default: 3600)")
    parser.add_argument("--interval", type=positive_finite_float, default=1,
                        help="sampling interval in seconds (default: 1)")
    parser.add_argument("--output", default=DEFAULT_OUTPUT,
                        help=f"JSONL output path (default: {DEFAULT_OUTPUT})")
    return parser.parse_args(argv)


def read_cpu_counters():
    try:
        with open("/proc/stat", "r", encoding="ascii") as proc_stat:
            first_line = proc_stat.readline().split()
    except OSError as error:
        raise SamplingError(f"cannot read /proc/stat: {error}") from error
    if not first_line or first_line[0] != "cpu" or len(first_line) < 9:
        raise SamplingError("/proc/stat does not contain the aggregate CPU counters")
    try:
        return dict(zip(CPU_FIELDS, (int(value) for value in first_line[1:9])))
    except ValueError as error:
        raise SamplingError("/proc/stat contains a non-integer CPU counter") from error


def root_disk_name():
    try:
        root_device = os.stat("/").st_dev
        device_path = Path("/sys/dev/block") / f"{os.major(root_device)}:{os.minor(root_device)}"
        resolved = device_path.resolve(strict=True)
    except (OSError, RuntimeError) as error:
        raise SamplingError(f"cannot identify the root block device: {error}") from error
    if (resolved / "partition").is_file():
        resolved = resolved.parent
    return resolved.name


def read_root_disk_counters():
    device = root_disk_name()
    try:
        with open("/proc/diskstats", "r", encoding="ascii") as diskstats:
            for line in diskstats:
                fields = line.split()
                if len(fields) >= 10 and fields[2] == device:
                    return {
                        "device": device,
                        "read_sectors": int(fields[5]),
                        "write_sectors": int(fields[9]),
                    }
    except OSError as error:
        raise SamplingError(f"cannot read /proc/diskstats: {error}") from error
    except ValueError as error:
        raise SamplingError("/proc/diskstats contains an invalid root-disk counter") from error
    raise SamplingError(f"root disk {device!r} is absent from /proc/diskstats")


def read_memory():
    wanted = {"MemTotal", "MemAvailable"}
    values = {}
    try:
        with open("/proc/meminfo", "r", encoding="ascii") as meminfo:
            for line in meminfo:
                key, separator, value = line.partition(":")
                if separator and key in wanted:
                    values[key] = int(value.split()[0])
    except (OSError, ValueError, IndexError) as error:
        raise SamplingError(f"cannot read memory totals from /proc/meminfo: {error}") from error
    if wanted - values.keys():
        raise SamplingError("/proc/meminfo is missing MemTotal or MemAvailable")
    return {"total_kb": values["MemTotal"], "available_kb": values["MemAvailable"]}


def read_loadavg():
    try:
        with open("/proc/loadavg", "r", encoding="ascii") as loadavg:
            values = loadavg.readline().split()
        if len(values) < 3:
            raise SamplingError("/proc/loadavg has fewer than three load averages")
        return {"1m": float(values[0]), "5m": float(values[1]), "15m": float(values[2])}
    except (OSError, ValueError) as error:
        raise SamplingError(f"cannot read /proc/loadavg: {error}") from error


def cpu_delta(previous, current):
    deltas = {field: current[field] - previous[field] for field in CPU_FIELDS}
    if any(value < 0 for value in deltas.values()):
        raise SamplingError("CPU counters decreased since the previous sample")
    total_ticks = sum(deltas.values())
    if total_ticks <= 0:
        raise SamplingError("CPU counters did not advance since the previous sample")
    percentages = {
        "user": round((deltas["user"] + deltas["nice"]) * 100 / total_ticks, 3),
        "system": round((deltas["system"] + deltas["irq"] + deltas["softirq"]) * 100 / total_ticks, 3),
        "idle": round(deltas["idle"] * 100 / total_ticks, 3),
        "iowait": round(deltas["iowait"] * 100 / total_ticks, 3),
        "steal": round(deltas["steal"] * 100 / total_ticks, 3),
    }
    return {
        "delta_ticks": deltas,
        "total_delta_ticks": total_ticks,
        "percent": percentages,
    }


def disk_delta(previous, current):
    if previous["device"] != current["device"]:
        raise SamplingError("root block device changed since the previous sample")
    read_sectors = current["read_sectors"] - previous["read_sectors"]
    write_sectors = current["write_sectors"] - previous["write_sectors"]
    if read_sectors < 0 or write_sectors < 0:
        raise SamplingError("root-disk counters decreased since the previous sample")
    return {
        "device": current["device"],
        "read_sectors": read_sectors,
        "write_sectors": write_sectors,
        "read_bytes": read_sectors * 512,
        "write_bytes": write_sectors * 512,
    }

def read_network_counters():
    counters = {}
    try:
        with open("/proc/net/dev", "r", encoding="ascii") as net_dev:
            for line_number, line in enumerate(net_dev):
                if line_number < 2 or ":" not in line:
                    continue
                interface, raw_values = line.split(":", 1)
                interface = interface.strip()
                if interface == "lo":
                    continue
                try:
                    values = [int(value) for value in raw_values.split()]
                except ValueError as error:
                    raise SamplingError(f"/proc/net/dev contains an invalid counter for {interface}") from error
                if len(values) < 16:
                    raise SamplingError(f"/proc/net/dev has incomplete counters for {interface}")
                counters[interface] = {
                    "rx_bytes": values[0],
                    "rx_packets": values[1],
                    "tx_bytes": values[8],
                    "tx_packets": values[9],
                }
    except OSError as error:
        raise SamplingError(f"cannot read /proc/net/dev: {error}") from error
    if not counters:
        raise SamplingError("/proc/net/dev contains no non-loopback interfaces")
    return counters


def network_delta(previous, current):
    interfaces = {}
    for interface in sorted(previous.keys() & current.keys()):
        delta = {field: current[interface][field] - previous[interface][field]
                 for field in ("rx_bytes", "rx_packets", "tx_bytes", "tx_packets")}
        if any(value < 0 for value in delta.values()):
            continue
        interfaces[interface] = delta
    if not interfaces:
        raise SamplingError("no stable non-loopback network interface counters between samples")
    totals = {
        field: sum(values[field] for values in interfaces.values())
        for field in ("rx_bytes", "rx_packets", "tx_bytes", "tx_packets")
    }
    return {"interfaces": interfaces, **totals}


def utc_now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def command_output(command, component, errors, stop_event=None):
    if stop_event is not None and stop_event.is_set():
        errors.append({"component": component, "error": "sampling interrupted by signal"})
        return None
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=COMMAND_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        errors.append({"component": component, "error": f"command timed out after {COMMAND_TIMEOUT_SECONDS}s"})
        return None
    except OSError as error:
        errors.append({"component": component, "error": f"cannot run command: {error}"})
        return None
    if result.returncode != 0:
        message = (result.stderr or "").strip().replace("\n", " ")
        if len(message) > 1000:
            message = message[:1000] + "…"
        detail = f"command exited with status {result.returncode}"
        if message:
            detail += f": {message}"
        errors.append({"component": component, "error": detail})
        return None
    return result.stdout


def parse_ecs_label(labels):
    for label in labels.split(","):
        key, separator, value = label.partition("=")
        if separator and key == ECS_LABEL:
            return value
    return None


def timed_command_output(command, component, stop_event):
    started_at = utc_now()
    started_mono = time.monotonic()
    errors = []
    output = command_output(command, component, errors, stop_event)
    finished_mono = time.monotonic()
    return {
        "output": output,
        "errors": errors,
        "timing": {
            "started_at_utc": started_at,
            "finished_at_utc": utc_now(),
            "duration_seconds": round(finished_mono - started_mono, 3),
        },
    }


def collect_docker(errors, stop_event):
    ps_format = "{{.ID}}\t{{.Names}}\t{{.Image}}\t{{.Labels}}"
    output = command_output(
        ["docker", "ps", "--no-trunc", "--filter", f"label={ECS_LABEL}", "--format", ps_format],
        "docker_ps",
        errors,
        stop_event,
    )
    by_role = {"backend": [], "postgres": [], "redis": []}
    if output is None:
        return {"containers": [], "stats": [], "postgres": [], "timing": {}}, by_role

    containers = []
    for line_number, line in enumerate(output.splitlines(), 1):
        fields = line.split("\t", 3)
        if len(fields) != 4:
            errors.append({"component": "docker_ps", "error": f"malformed container row {line_number}"})
            continue
        container_id, name, image, labels = fields
        role = parse_ecs_label(labels)
        if role not in by_role:
            continue
        container = {
            "ecs_container_name": role,
            "container_name": name,
            "container_id": container_id,
            "image": image,
            "image_id": None,
        }
        containers.append(container)
        by_role[role].append(container)

    for role in ("backend", "postgres"):
        if not by_role[role]:
            errors.append({"component": f"ecs_{role}", "error": f"no running ECS container with {ECS_LABEL}={role}"})

    if containers:
        inspect_format = "{{.Id}}\t{{.Image}}\t{{.Name}}"
        inspect_output = command_output(
            ["docker", "inspect", "--type", "container", "--format", inspect_format]
            + [container["container_id"] for container in containers],
            "docker_inspect",
            errors,
            stop_event,
        )
        if inspect_output is not None:
            inspected = {}
            for line_number, line in enumerate(inspect_output.splitlines(), 1):
                fields = line.split("\t", 2)
                if len(fields) != 3:
                    errors.append({"component": "docker_inspect", "error": f"malformed identity row {line_number}"})
                    continue
                inspected[fields[0]] = (fields[1], fields[2].lstrip("/"))
            for container in containers:
                identity = inspected.get(container["container_id"])
                if identity is None:
                    errors.append({"component": "docker_inspect", "error": f"identity missing for {container['container_name']}"})
                else:
                    container["image_id"], container["container_name"] = identity

    stats = []
    postgres = []
    timing = {}
    query_commands = {
        container["container_id"]: (
            container,
            [
                "docker", "exec", container["container_id"], "psql", "-X", "-q", "-A", "-t", "-w",
                "-v", "ON_ERROR_STOP=1", "-U", "g_scores", "-d", "g_scores", "-c", POSTGRES_QUERY,
            ],
        )
        for container in by_role["postgres"]
    }
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, len(query_commands) + bool(containers))) as executor:
        stats_future = None
        if containers:
            stats_command = (
                ["docker", "stats", "--no-stream", "--format", "{{json .}}"]
                + [container["container_id"] for container in containers]
            )
            stats_future = executor.submit(timed_command_output, stats_command, "docker_stats", stop_event)
        query_futures = {
            container_id: executor.submit(
                timed_command_output, command, f"postgres_stats:{container['container_name']}", stop_event
            )
            for container_id, (container, command) in query_commands.items()
        }
        if stats_future is not None:
            stats_result = stats_future.result()
            errors.extend(stats_result["errors"])
            timing["docker_stats"] = stats_result["timing"]
            stats_output = stats_result["output"]
            if stats_output is not None:
                for line_number, line in enumerate(stats_output.splitlines(), 1):
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        errors.append({"component": "docker_stats", "error": f"invalid JSON row {line_number}"})
                        continue
                    if isinstance(row, dict):
                        stats.append(row)
                    else:
                        errors.append({"component": "docker_stats", "error": f"non-object JSON row {line_number}"})
                seen_names = {str(row.get("Name", "")).lstrip("/") for row in stats}
                for container in containers:
                    if container["container_name"].lstrip("/") not in seen_names:
                        errors.append({"component": "docker_stats", "error": f"stats missing for {container['container_name']}"})
        for container_id, future in query_futures.items():
            container, _command = query_commands[container_id]
            result = future.result()
            errors.extend(result["errors"])
            parsed = None
            query_output = result["output"]
            if query_output is not None:
                try:
                    parsed = json.loads(query_output.strip())
                    if not isinstance(parsed, dict):
                        raise json.JSONDecodeError("expected JSON object", query_output, 0)
                except json.JSONDecodeError:
                    errors.append({
                        "component": f"postgres_stats:{container['container_name']}",
                        "error": "psql returned invalid JSON",
                    })
            postgres.append({
                "container_name": container["container_name"],
                "container_id": container["container_id"],
                "metrics": parsed,
                "query_started_at_utc": result["timing"]["started_at_utc"],
                "query_finished_at_utc": result["timing"]["finished_at_utc"],
                "query_duration_seconds": result["timing"]["duration_seconds"],
            })
            if parsed is None:
                errors.append({
                    "component": f"postgres_stats:{container['container_name']}",
                    "error": "PostgreSQL metrics unavailable",
                })

    return {
        "containers": containers,
        "stats": stats,
        "postgres": postgres,
        "timing": timing,
    }, by_role


def add_error(errors, missing, component, error):
    errors.append({"component": component, "error": str(error)})
    missing.add(component)


def collect_sample(started_mono, previous_cpu, previous_disk, previous_network, pending_errors, stop_event):
    sample_started_mono = time.monotonic()
    sample_started_at = utc_now()
    errors = list(pending_errors)
    missing = {entry["component"] for entry in errors}
    pending_errors.clear()
    host = {"cpu": None, "memory": None, "loadavg": None, "root_disk": None, "network": None}
    current_cpu = None
    current_disk = None
    current_network = None

    try:
        current_cpu = read_cpu_counters()
        if previous_cpu is not None:
            host["cpu"] = cpu_delta(previous_cpu, current_cpu)
        else:
            add_error(errors, missing, "cpu", "baseline unavailable; waiting for next sample")
    except SamplingError as error:
        add_error(errors, missing, "cpu", error)

    try:
        current_disk = read_root_disk_counters()
        if previous_disk is not None:
            host["root_disk"] = disk_delta(previous_disk, current_disk)
        else:
            add_error(errors, missing, "root_disk", "baseline unavailable; waiting for next sample")
    except SamplingError as error:
        add_error(errors, missing, "root_disk", error)

    try:
        current_network = read_network_counters()
        if previous_network is not None:
            host["network"] = network_delta(previous_network, current_network)
        else:
            add_error(errors, missing, "network", "baseline unavailable; waiting for next sample")
    except SamplingError as error:
        add_error(errors, missing, "network", error)

    for component, reader in (("memory", read_memory), ("loadavg", read_loadavg)):
        try:
            host[component] = reader()
        except SamplingError as error:
            add_error(errors, missing, component, error)
    host["captured_at_utc"] = utc_now()

    docker, by_role = collect_docker(errors, stop_event)
    for role in ("backend", "postgres"):
        if not by_role[role]:
            missing.add(f"ecs_{role}")
    if any(entry["metrics"] is None for entry in docker["postgres"]):
        missing.add("postgres_stats")
    if any(entry["component"] == "docker_stats" for entry in errors):
        missing.add("docker_stats")
    missing.update(entry["component"] for entry in errors)

    now_mono = time.monotonic()
    sample = {
        "collection_started_at_utc": sample_started_at,
        "timestamp_utc": utc_now(),
        "elapsed_seconds": round(now_mono - started_mono, 3),
        "collection_duration_seconds": round(now_mono - sample_started_mono, 3),
        "host": host,
        "ecs": {
            "containers": docker["containers"],
            "docker_stats": docker["stats"],
            "docker_stats_timing": docker["timing"].get("docker_stats"),
        },
        "postgres": docker["postgres"],
        "missing": sorted(missing),
        "errors": errors,
    }
    return sample, current_cpu, current_disk, current_network, now_mono


def main(argv=None):
    args = parse_args(argv)
    stop_event = threading.Event()

    def request_stop(_signum, _frame):
        stop_event.set()

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)

    try:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output = output_path.open("w", encoding="utf-8", buffering=1)
    except OSError as error:
        print(f"cannot open telemetry output: {error}", file=sys.stderr)
        return 1

    started_mono = time.monotonic()
    end_mono = started_mono + args.duration
    pending_errors = []
    try:
        try:
            previous_cpu = read_cpu_counters()
        except SamplingError as error:
            previous_cpu = None
            pending_errors.append({"component": "cpu", "error": str(error)})
        try:
            previous_disk = read_root_disk_counters()
        except SamplingError as error:
            previous_disk = None
            pending_errors.append({"component": "root_disk", "error": str(error)})
        try:
            previous_network = read_network_counters()
        except SamplingError as error:
            previous_network = None
            pending_errors.append({"component": "network", "error": str(error)})

        deadline = min(started_mono + args.interval, end_mono)
        while not stop_event.is_set():
            delay = deadline - time.monotonic()
            if delay > 0 and stop_event.wait(delay):
                break
            if stop_event.is_set():
                break
            sample, current_cpu, current_disk, current_network, finished_mono = collect_sample(
                started_mono, previous_cpu, previous_disk, previous_network, pending_errors, stop_event
            )
            if current_cpu is not None:
                previous_cpu = current_cpu
            if current_disk is not None:
                previous_disk = current_disk
            if current_network is not None:
                previous_network = current_network
            output.write(json.dumps(sample, separators=(",", ":"), allow_nan=False) + "\n")
            output.flush()

            if stop_event.is_set() or finished_mono >= end_mono:
                break
            deadline += args.interval
            while deadline <= finished_mono:
                deadline += args.interval
            if deadline > end_mono:
                deadline = end_mono
    except (OSError, ValueError) as error:
        print(f"telemetry sampling failed: {error}", file=sys.stderr)
        return 1
    finally:
        output.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
