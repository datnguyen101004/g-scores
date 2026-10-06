#!/usr/bin/env python3
"""Run one synchronized k6 burst of student lookup requests."""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import resource
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

RESULTS_DIRECTORY = Path('/opt/g-scores-load-test/results/burst-10k')
SBD_FILE = Path('/opt/g-scores-load-test/sbds.json')
SCRIPT_FILE = Path(__file__).resolve().with_name('lookup.js')
REQUEST_PREFIX = 'BURST_REQUEST,'
REQUEST_FIELDS = ('id', 'sbd', 'started_ms', 'finished_ms', 'status', 'correct', 'cache_hit', 'error_code')
CPU_FIELDS = ('user', 'nice', 'system', 'idle', 'iowait', 'irq', 'softirq', 'steal')
MEMORY_FIELDS = ('MemTotal', 'MemFree', 'MemAvailable')


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')


def progress(message: str) -> None:
    print(f'{utc_now()} {message}', flush=True)


def positive_integer(value: str) -> int:
    try:
        number = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError('--vus must be a positive integer') from error
    if number < 1:
        raise argparse.ArgumentTypeError('--vus must be a positive integer')
    return number


def nonnegative_seconds(value: str) -> float:
    try:
        seconds = float(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError('--barrier-seconds must be a non-negative number') from error
    if not math.isfinite(seconds) or seconds < 0:
        raise argparse.ArgumentTypeError('--barrier-seconds must be a non-negative number')
    return seconds


def base_url(value: str) -> str:
    candidate = value.strip().rstrip('/')
    parsed = urlparse(candidate)
    if parsed.scheme not in {'http', 'https'} or not parsed.netloc:
        raise argparse.ArgumentTypeError('--base-url must be an absolute http(s) URL')
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise argparse.ArgumentTypeError('--base-url must not contain credentials, a query, or a fragment')
    return candidate


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Run one synchronized k6 student lookup burst.')
    parser.add_argument('--base-url', required=True, type=base_url)
    parser.add_argument('--vus', default=10000, type=positive_integer, help='Requested k6 VUs (default: 10000).')
    parser.add_argument('--output-dir', type=Path, default=RESULTS_DIRECTORY)
    parser.add_argument(
        '--barrier-seconds',
        default=20.0,
        type=nonnegative_seconds,
        help='Seconds after setup when VUs issue their one request (default: 20; lower for smoke runs).',
    )
    return parser.parse_args()


def limit_value(value: int) -> int | str:
    return 'unlimited' if value == resource.RLIM_INFINITY else value


def file_descriptor_plan(vus: int) -> dict[str, int | str]:
    soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    required = vus + 1024
    if hard != resource.RLIM_INFINITY and hard < required:
        raise RuntimeError(f'RLIMIT_NOFILE hard limit {hard} is below required {required} for {vus} VUs')
    if soft == resource.RLIM_INFINITY or soft >= required:
        target_soft = soft
    else:
        target_soft = required
    return {
        'required': required,
        'softBefore': limit_value(soft),
        'hard': limit_value(hard),
        'softForK6': limit_value(target_soft),
    }


def set_child_file_descriptor_limit(required: int) -> None:
    soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    if hard != resource.RLIM_INFINITY and hard < required:
        raise RuntimeError(f'RLIMIT_NOFILE hard limit {hard} is below required {required}')
    if soft != resource.RLIM_INFINITY and soft < required:
        resource.setrlimit(resource.RLIMIT_NOFILE, (required, hard))


def write_manifest(path: Path, manifest: dict[str, object]) -> None:
    temporary_path = path.with_suffix('.json.tmp')
    with temporary_path.open('w', encoding='utf-8') as stream:
        json.dump(manifest, stream, indent=2, sort_keys=True)
        stream.write('\n')
    os.replace(temporary_path, path)


def proc_cpu() -> tuple[int | None, int | None, int | None]:
    try:
        with Path('/proc/stat').open(encoding='utf-8') as stream:
            line = next(line for line in stream if line.startswith('cpu '))
        values = [int(value) for value in line.split()[1:]]
    except (OSError, StopIteration, ValueError):
        return None, None, None
    ticks = {field: values[index] if index < len(values) else 0 for index, field in enumerate(CPU_FIELDS)}
    return sum(ticks.values()), ticks['idle'], ticks['iowait']


def proc_memory() -> dict[str, int | None]:
    memory: dict[str, int | None] = {field: None for field in MEMORY_FIELDS}
    try:
        with Path('/proc/meminfo').open(encoding='utf-8') as stream:
            for line in stream:
                fields = line.split()
                name = fields[0].rstrip(':') if fields else ''
                if name in memory and len(fields) > 1:
                    memory[name] = int(fields[1])
    except (OSError, ValueError):
        pass
    return memory


def proc_k6_memory(pid: int) -> tuple[int | None, int | None]:
    values: dict[str, int] = {}
    try:
        with Path(f'/proc/{pid}/status').open(encoding='utf-8') as stream:
            for line in stream:
                fields = line.split()
                if len(fields) >= 2 and fields[0] in {'VmRSS:', 'VmHWM:'}:
                    values[fields[0]] = int(fields[1])
    except (OSError, ValueError):
        return None, None
    return values.get('VmRSS:'), values.get('VmHWM:')


def generator_sample(pid: int) -> dict[str, object]:
    total_ticks, idle_ticks, io_wait_ticks = proc_cpu()
    rss_kib, hwm_kib = proc_k6_memory(pid)
    memory = proc_memory()
    return {
        'capturedAtUtc': utc_now(),
        'cpuTotalTicks': total_ticks,
        'cpuIdleTicks': idle_ticks,
        'cpuIoWaitTicks': io_wait_ticks,
        'memoryAvailableKiB': memory['MemAvailable'],
        'memoryTotalKiB': memory['MemTotal'],
        'memoryFreeKiB': memory['MemFree'],
        'k6RssKiB': rss_kib,
        'k6VmHwmKiB': hwm_kib,
    }


def write_generator_sample(stream, pid: int) -> None:
    json.dump(generator_sample(pid), stream, separators=(',', ':'))
    stream.write('\n')
    stream.flush()


def command_for_burst(
    base: str,
    vus: int,
    barrier_seconds: float,
    run_token: str,
    summary_path: Path,
) -> list[str]:
    return [
        'k6',
        'run',
        '--no-usage-report',
        '--log-format=raw',
        '--new-machine-readable-summary=false',
        '--env', f'BASE_URL={base}',
        '--env', f'VUS={vus}',
        '--env', f'BARRIER_SECONDS={barrier_seconds:g}',
        '--env', f'RUN_ID={run_token}',
        '--env', f'SBD_FILE={SBD_FILE}',
        '--env', f'SUMMARY_FILE={summary_path}',
        str(SCRIPT_FILE),
    ]


def extract_request_rows(stdout_path: Path, requests_path: Path) -> tuple[int, int]:
    extracted = 0
    malformed = 0
    with requests_path.open('w', encoding='utf-8', newline='') as output:
        writer = csv.writer(output)
        writer.writerow(REQUEST_FIELDS)
        with stdout_path.open(encoding='utf-8', errors='replace') as stdout:
            for line in stdout:
                marker = line.find(REQUEST_PREFIX)
                if marker < 0:
                    continue
                record = line[marker + len(REQUEST_PREFIX):].rstrip(chr(10) + chr(13))
                if record.endswith(' source=console'):
                    record = record[:-len(' source=console')]
                try:
                    row = next(csv.reader([record], strict=True))
                except (csv.Error, StopIteration):
                    malformed += 1
                    continue
                if len(row) != len(REQUEST_FIELDS):
                    malformed += 1
                    continue
                writer.writerow(row)
                extracted += 1

    return extracted, malformed

def execute_burst(args: argparse.Namespace) -> int:
    if not SCRIPT_FILE.is_file():
        print(f'lookup script not found: {SCRIPT_FILE}', file=sys.stderr, flush=True)
        return 1
    if not SBD_FILE.is_file():
        print(f'SBD input not found: {SBD_FILE}', file=sys.stderr, flush=True)
        return 1

    run_directory = args.output_dir.expanduser().resolve()
    try:
        run_directory.mkdir(parents=True, exist_ok=False)
    except OSError as error:
        print(f'cannot create output directory {run_directory}: {error}', file=sys.stderr, flush=True)
        return 1

    manifest_path = run_directory / 'manifest.json'
    summary_path = run_directory / 'summary.json'
    stdout_path = run_directory / 'stdout.log'
    requests_path = run_directory / 'requests.csv'
    generator_metrics_path = run_directory / 'generator-metrics.jsonl'
    started_at = utc_now()
    manifest: dict[str, object] = {
        'schemaVersion': 'g-scores-lookup-burst/v1',
        'startedAtUtc': started_at,
        'finishedAtUtc': None,
        'baseUrl': args.base_url,
        'vus': args.vus,
        'requestedVus': args.vus,
        'concurrencyNote': 'VUs are requested; achieved concurrency is not guaranteed.',
        'barrierSeconds': args.barrier_seconds,
        'exitCode': None,
        'status': 'running',
        'resultsDirectory': str(run_directory),
        'files': {
            'stdout': str(stdout_path),
            'summary': str(summary_path),
            'requests': str(requests_path),
            'generatorMetrics': str(generator_metrics_path),
        },
    }
    try:
        fd_plan = file_descriptor_plan(args.vus)
    except (OSError, RuntimeError, ValueError) as error:
        manifest.update({
            'finishedAtUtc': utc_now(),
            'exitCode': 1,
            'status': 'insufficient_file_descriptor_limit',
            'fileDescriptorLimitError': str(error),
        })
        write_manifest(manifest_path, manifest)
        print(str(error), file=sys.stderr, flush=True)
        return 1
    manifest['fileDescriptorLimit'] = fd_plan
    write_manifest(manifest_path, manifest)
    progress(f'results={run_directory}')
    progress(f'requested vus={args.vus}; achieved concurrency is not guaranteed; barrier={args.barrier_seconds:g}s')

    run_token = started_at.replace(':', '').replace('-', '')
    command = command_for_burst(args.base_url, args.vus, args.barrier_seconds, run_token, summary_path)
    exit_code: int | None = None
    launch_error: str | None = None
    with stdout_path.open('w', encoding='utf-8') as stdout_stream, generator_metrics_path.open(
        'w', encoding='utf-8', buffering=1
    ) as metrics_stream:
        try:
            process = subprocess.Popen(
                command,
                cwd=SCRIPT_FILE.parent,
                env=os.environ.copy(),
                stdout=stdout_stream,
                stderr=subprocess.STDOUT,
                preexec_fn=lambda: set_child_file_descriptor_limit(int(fd_plan['required'])),
            )
        except (OSError, subprocess.SubprocessError, RuntimeError) as error:
            launch_error = str(error)
            stdout_stream.write(f'Unable to start k6: {error}\n')
            exit_code = 1
        else:
            write_generator_sample(metrics_stream, process.pid)
            while True:
                try:
                    exit_code = process.wait(timeout=1.0)
                    break
                except subprocess.TimeoutExpired:
                    write_generator_sample(metrics_stream, process.pid)

    extracted, malformed = extract_request_rows(stdout_path, requests_path)
    manifest.update({
        'finishedAtUtc': utc_now(),
        'exitCode': exit_code,
        'status': 'completed' if exit_code == 0 else 'k6_failed',
        'launchError': launch_error,
        'requestRowsExtracted': extracted,
        'requestRowsMalformed': malformed,
        'summaryExists': summary_path.is_file(),
        'command': command,
    })
    write_manifest(manifest_path, manifest)
    progress(
        f'burst finished exit={exit_code} request_rows={extracted} '
        f'malformed_rows={malformed} summary={summary_path}'
    )
    return exit_code if isinstance(exit_code, int) and exit_code > 0 else (0 if exit_code == 0 else 1)


def main() -> int:
    return execute_burst(parse_args())


if __name__ == '__main__':
    sys.exit(main())
