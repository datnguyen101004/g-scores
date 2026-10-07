#!/usr/bin/env python3
"""Run sequential k6 arrival-rate student lookup profiles."""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

if os.name == 'posix':
    try:
        import resource
    except ImportError:  # pragma: no cover - unusual POSIX runtime
        resource = None
else:  # resource is not available on Windows
    resource = None

SCRIPT_FILE = Path(__file__).resolve().with_name('lookup.js')
SBD_FILE = Path(__file__).resolve().with_name('sbds.json')


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')


def progress(message: str) -> None:
    print(f'{utc_now()} {message}', flush=True)


def positive_integer(value: str) -> int:
    try:
        number = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError('must be a positive integer') from error
    if number < 1:
        raise argparse.ArgumentTypeError('must be a positive integer')
    return number


def nonnegative_integer(value: str) -> int:
    try:
        number = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError('must be a non-negative integer') from error
    if number < 0:
        raise argparse.ArgumentTypeError('must be a non-negative integer')
    return number


def rates_list(value: str) -> list[int]:
    values = value.split(',')
    if not values or any(not item.strip() for item in values):
        raise argparse.ArgumentTypeError('--rates must be comma-separated positive integers')
    try:
        rates = [positive_integer(item.strip()) for item in values]
    except argparse.ArgumentTypeError as error:
        raise argparse.ArgumentTypeError('--rates must be comma-separated positive integers') from error
    return rates


def base_url(value: str) -> str:
    candidate = value.strip().rstrip('/')
    parsed = urlparse(candidate)
    if parsed.scheme not in {'http', 'https'} or not parsed.netloc:
        raise argparse.ArgumentTypeError('--base-url must be an absolute http(s) URL')
    if parsed.path not in {'', '/'}:
        raise argparse.ArgumentTypeError('--base-url must not include a path')
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise argparse.ArgumentTypeError('--base-url must not contain credentials, a query, or a fragment')
    return candidate


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Run sequential k6 arrival-rate profiles for student lookups.',
        allow_abbrev=False,
    )
    parser.add_argument('--base-url', required=True, type=base_url, help='Backend base URL, without a path or query.')
    parser.add_argument('--rates', required=True, type=rates_list, help='Comma-separated offered rates in requests per second.')
    parser.add_argument('--duration-seconds', default=300, type=positive_integer, help='Measurement duration for each plateau (default: 300).')
    parser.add_argument('--warmup-seconds', default=30, type=nonnegative_integer, help='Warmup duration before each plateau measurement (default: 30).')
    parser.add_argument('--ramp-up-seconds', default=0, type=nonnegative_integer)
    parser.add_argument('--start-rps', default=100, type=positive_integer)
    parser.add_argument('--ramp-down-seconds', default=0, type=nonnegative_integer)
    parser.add_argument('--preallocated-vus', default=100, type=positive_integer, help='VUs allocated before each arrival-rate scenario (default: 100).')
    parser.add_argument('--max-vus', default=1000, type=positive_integer, help='Maximum VUs available to each scenario (default: 1000).')
    parser.add_argument('--timeout-seconds', default=30, type=positive_integer, help='Maximum duration of one HTTP request (default: 30).')
    parser.add_argument('--output-dir', type=Path, help='New, non-existing directory for all plateau results.')
    parser.add_argument('--region', default='ap-southeast-1', help='AWS region for optional ECS snapshots (default: ap-southeast-1).')
    parser.add_argument('--cluster', help='ECS cluster name or ARN; must be supplied with --service and --instance-id.')
    parser.add_argument('--service', help='ECS service name or ARN; must be supplied with --cluster and --instance-id.')
    parser.add_argument('--instance-id', help='EC2 instance ID; must be supplied with --cluster and --service.')
    args = parser.parse_args()
    if args.preallocated_vus > args.max_vus:
        parser.error('--preallocated-vus must not exceed --max-vus')
    aws_values = (args.cluster, args.service, args.instance_id)
    aws_supplied = any(value is not None for value in aws_values)
    if aws_supplied and not all(value is not None and value.strip() for value in aws_values):
        parser.error('--cluster, --service, and --instance-id must be non-empty and supplied together')
    if aws_supplied:
        args.cluster, args.service, args.instance_id = (value.strip() for value in aws_values)
    if not args.region.strip():
        parser.error('--region must not be empty')
    args.region = args.region.strip()
    return args


def write_manifest(path: Path, manifest: dict[str, object]) -> None:
    temporary_path = path.with_name(path.name + '.tmp')
    with temporary_path.open('w', encoding='utf-8', newline='\n') as stream:
        json.dump(manifest, stream, indent=2, sort_keys=True)
        stream.write('\n')
    os.replace(temporary_path, path)


def limit_value(value: int) -> int | str:
    if resource is not None and value == resource.RLIM_INFINITY:
        return 'unlimited'
    return value


def file_descriptor_plan(max_vus: int) -> dict[str, object]:
    if resource is None:
        return {'available': False, 'platform': sys.platform, 'adjusted': False}
    soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    required = max_vus + 1024
    if hard != resource.RLIM_INFINITY and hard < required:
        raise RuntimeError(f'RLIMIT_NOFILE hard limit {hard} is below required {required} for {max_vus} max VUs')
    target_soft = soft if soft == resource.RLIM_INFINITY or soft >= required else required
    return {
        'available': True,
        'platform': sys.platform,
        'required': required,
        'soft_before': limit_value(soft),
        'hard': limit_value(hard),
        'soft_for_k6': limit_value(target_soft),
        'adjusted': target_soft != soft,
    }


def set_child_file_descriptor_limit(required: int) -> None:
    if resource is None:
        return
    soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    if hard != resource.RLIM_INFINITY and hard < required:
        raise RuntimeError(f'RLIMIT_NOFILE hard limit {hard} is below required {required}')
    if soft != resource.RLIM_INFINITY and soft < required:
        resource.setrlimit(resource.RLIMIT_NOFILE, (required, hard))


def json_timestamp(value: object) -> object:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')
    return value


def capture_ecs_snapshot(client, cluster: str, service_name: str) -> dict[str, object]:
    response = client.describe_services(cluster=cluster, services=[service_name])
    services = response.get('services', [])
    if response.get('failures') or len(services) != 1:
        raise RuntimeError(f'ECS describe_services did not return exactly one service: {response.get("failures", [])}')
    service = services[0]

    task_arns: list[str] = []
    paginator = client.get_paginator('list_tasks')
    for page in paginator.paginate(cluster=cluster, serviceName=service_name, desiredStatus='RUNNING'):
        task_arns.extend(page.get('taskArns', []))

    tasks: list[dict[str, object]] = []
    for start in range(0, len(task_arns), 100):
        described = client.describe_tasks(cluster=cluster, tasks=task_arns[start:start + 100])
        if described.get('failures'):
            raise RuntimeError(f'ECS describe_tasks failed: {described["failures"]}')
        for task in described.get('tasks', []):
            tasks.append({
                key: json_timestamp(task.get(key))
                for key in (
                    'taskArn', 'startedAt', 'lastStatus', 'healthStatus',
                    'taskDefinitionArn', 'containerInstanceArn',
                )
            })

    container_arns = sorted({task['containerInstanceArn'] for task in tasks if task.get('containerInstanceArn')})
    instance_ids = {}
    for start in range(0, len(container_arns), 100):
        instances = client.describe_container_instances(cluster=cluster, containerInstances=container_arns[start:start + 100])
        if instances.get('failures'):
            raise RuntimeError(f'ECS describe_container_instances failed: {instances["failures"]}')
        instance_ids.update({item['containerInstanceArn']: item.get('ec2InstanceId') for item in instances.get('containerInstances', [])})
    for task in tasks:
        task['ec2InstanceId'] = instance_ids.get(task.get('containerInstanceArn'))

    deployments = []
    for deployment in service.get('deployments', []):
        deployments.append({
            'id': deployment.get('id'),
            'status': deployment.get('status'),
            'rolloutState': deployment.get('rolloutState'),
            'desiredCount': deployment.get('desiredCount'),
            'runningCount': deployment.get('runningCount'),
            'pendingCount': deployment.get('pendingCount'),
            'taskDefinitionArn': deployment.get('taskDefinition'),
            'createdAt': json_timestamp(deployment.get('createdAt')),
            'updatedAt': json_timestamp(deployment.get('updatedAt')),
        })
    deployments.sort(key=lambda item: str(item.get('id') or ''))
    events = []
    for event in service.get('events', []):
        events.append({
            key: json_timestamp(event.get(key))
            for key in ('id', 'createdAt', 'message')
        })

    return {
        'observed_at': utc_now(),
        'desiredCount': service.get('desiredCount'),
        'runningCount': service.get('runningCount'),
        'pendingCount': service.get('pendingCount'),
        'taskDefinitionArn': service.get('taskDefinition'),
        'tasks': sorted(tasks, key=lambda task: str(task.get('taskArn') or '')),
        'deployments': deployments,
        'events': events,
    }


def single_running_task(snapshot: dict[str, object], instance_id: str) -> bool:
    tasks = snapshot.get('tasks')
    return (
        snapshot.get('desiredCount') == 1
        and snapshot.get('runningCount') == 1
        and snapshot.get('pendingCount') == 0
        and isinstance(tasks, list)
        and len(tasks) == 1
        and tasks[0].get('lastStatus') == 'RUNNING'
        and tasks[0].get('ec2InstanceId') == instance_id
    )


def snapshot_identity(snapshot: dict[str, object]) -> tuple[object, ...]:
    tasks = snapshot.get('tasks')
    task_identity = tuple(
        tuple(task.get(key) for key in (
            'taskArn', 'startedAt', 'lastStatus', 'healthStatus',
            'taskDefinitionArn', 'containerInstanceArn', 'ec2InstanceId',
        ))
        for task in (tasks if isinstance(tasks, list) else [])
    )
    deployments = snapshot.get('deployments')
    deployment_identity = tuple(
        tuple(deployment.get(key) for key in (
            'id', 'status', 'rolloutState', 'desiredCount', 'runningCount',
            'pendingCount', 'taskDefinitionArn', 'createdAt', 'updatedAt',
        ))
        for deployment in (deployments if isinstance(deployments, list) else [])
    )
    events = snapshot.get('events')
    event_identity = tuple(
        tuple(event.get(key) for key in ('id', 'createdAt', 'message'))
        for event in (events if isinstance(events, list) else [])
    )
    return (
        snapshot.get('desiredCount'), snapshot.get('runningCount'), snapshot.get('pendingCount'),
        snapshot.get('taskDefinitionArn'), task_identity, deployment_identity, event_identity,
    )


def aws_client(region: str):
    try:
        import boto3
    except ImportError as error:
        raise RuntimeError('boto3 is required when ECS/EC2 evidence flags are used') from error
    return boto3.client('ecs', region_name=region)


def command_for_plateau(args: argparse.Namespace, rate: int, directory: Path) -> list[str]:
    return [
        'k6',
        'run',
        '--no-usage-report',
        '--log-format=raw',
        '--out', f'json={directory / "metrics.jsonl"}',
        '--env', f'BASE_URL={args.base_url}',
        '--env', f'SBD_FILE={SBD_FILE}',
        '--env', f'SUMMARY_FILE={directory / "summary.json"}',
        '--env', f'TARGET_RPS={rate}',
        '--env', f'DURATION_SECONDS={args.duration_seconds}',
        '--env', f'WARMUP_SECONDS={args.warmup_seconds}',
        '--env', f'RAMP_UP_SECONDS={args.ramp_up_seconds}',
        '--env', f'START_RPS={args.start_rps}',
        '--env', f'RAMP_DOWN_SECONDS={args.ramp_down_seconds}',
        '--env', f'PREALLOCATED_VUS={args.preallocated_vus}',
        '--env', f'MAX_VUS={args.max_vus}',
        '--env', f'TIMEOUT_SECONDS={args.timeout_seconds}',
        str(SCRIPT_FILE),
    ]


def interrupt_process(process: subprocess.Popen[str]) -> None:
    try:
        if os.name == 'nt':
            process.send_signal(signal.CTRL_BREAK_EVENT)
        else:
            os.killpg(process.pid, signal.SIGINT)
    except (OSError, AttributeError):
        if process.poll() is None:
            process.send_signal(signal.SIGINT)


def terminate_process(process: subprocess.Popen[str]) -> int:
    if process.poll() is None:
        process.terminate()
        try:
            return process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
    return process.wait()


def run_k6(
    command: list[str],
    stdout_path: Path,
    args: argparse.Namespace,
    fd_plan: dict[str, object],
) -> tuple[int | None, bool, str | None]:
    launch_error = None
    interrupted = False
    with stdout_path.open('w', encoding='utf-8', newline='\n') as stdout_stream:
        launch_options: dict[str, object] = {
            'cwd': SCRIPT_FILE.parent,
            'env': os.environ.copy(),
            'stdout': stdout_stream,
            'stderr': subprocess.STDOUT,
        }
        if resource is not None and fd_plan.get('adjusted'):
            launch_options['preexec_fn'] = lambda: set_child_file_descriptor_limit(int(fd_plan['required']))
        if os.name == 'nt':
            launch_options['creationflags'] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            launch_options['start_new_session'] = True
        try:
            process = subprocess.Popen(command, **launch_options)
        except (OSError, subprocess.SubprocessError, RuntimeError) as error:
            launch_error = str(error)
            stdout_stream.write(f'Unable to start k6: {error}\n')
            return None, False, launch_error

        try:
            return process.wait(), False, None
        except KeyboardInterrupt:
            interrupted = True
            progress('interrupt received; asking k6 to stop and drain requests')
            interrupt_process(process)
            try:
                exit_code = process.wait(timeout=args.timeout_seconds + 15)
            except KeyboardInterrupt:
                exit_code = terminate_process(process)
            except subprocess.TimeoutExpired:
                exit_code = terminate_process(process)
            return exit_code, interrupted, None


def execute(args: argparse.Namespace) -> int:
    if not SCRIPT_FILE.is_file():
        print(f'lookup script not found: {SCRIPT_FILE}', file=sys.stderr, flush=True)
        return 1
    if not SBD_FILE.is_file():
        print(f'SBD input not found: {SBD_FILE}', file=sys.stderr, flush=True)
        return 1

    started_at = utc_now()
    if args.output_dir is None:
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        requested_directory = SCRIPT_FILE.parent / 'results' / f'run-{stamp}'
    else:
        requested_directory = args.output_dir.expanduser()
    run_directory = requested_directory.resolve()
    try:
        run_directory.mkdir(parents=True, exist_ok=False)
    except OSError as error:
        print(f'cannot create new output directory {run_directory}: {error}', file=sys.stderr, flush=True)
        return 1
    manifest_path = run_directory / 'manifest.json'

    occurrences: dict[int, int] = {}
    plateaus: list[dict[str, object]] = []
    for rate in args.rates:
        occurrences[rate] = occurrences.get(rate, 0) + 1
        suffix = '' if occurrences[rate] == 1 else f'-{occurrences[rate]}'
        plateaus.append({
            'rate': rate,
            'directory': f'rps-{rate}{suffix}',
            'exit_code': None,
            'status': 'not_started',
        })
    manifest: dict[str, object] = {
        'schema_version': 1,
        'base_url': args.base_url,
        'rates': args.rates,
        'duration_seconds': args.duration_seconds,
        'warmup_seconds': args.warmup_seconds,
        'ramp_up_seconds': args.ramp_up_seconds,
        'start_rps': args.start_rps,
        'ramp_down_seconds': args.ramp_down_seconds,
        'execution_model': (
            'single-ramping-arrival-rate'
            if args.ramp_up_seconds > 0 or args.ramp_down_seconds > 0
            else 'constant-arrival-rate'
        ),
        'timeout_seconds': args.timeout_seconds,
        'preallocated_vus': args.preallocated_vus,
        'max_vus': args.max_vus,
        'plateaus': plateaus,
        'started_at_utc': started_at,
        'finished_at_utc': None,
        'status': 'running',
    }
    aws_requested = bool(args.cluster)
    if aws_requested:
        manifest['aws'] = {
            'region': args.region,
            'cluster': args.cluster,
            'service': args.service,
            'instance_id': args.instance_id,
        }
    write_manifest(manifest_path, manifest)
    progress(f'results={run_directory}')

    try:
        fd_plan = file_descriptor_plan(args.max_vus)
        manifest['file_descriptor_limit'] = fd_plan
        ecs = aws_client(args.region) if aws_requested else None
    except (OSError, RuntimeError, ValueError) as error:
        manifest.update({'status': 'failed_preflight', 'error': str(error), 'finished_at_utc': utc_now()})
        write_manifest(manifest_path, manifest)
        print(str(error), file=sys.stderr, flush=True)
        return 1

    run_exit_code = 0
    try:
        for plateau in plateaus:
            rate = int(plateau['rate'])
            plateau_directory = run_directory / str(plateau['directory'])
            plateau_directory.mkdir()
            if ecs is not None:
                try:
                    before = capture_ecs_snapshot(ecs, args.cluster, args.service)
                    plateau['ecs_before'] = before
                except Exception as error:
                    plateau.update({'status': 'aws_snapshot_failed', 'error': str(error)})
                    manifest['status'] = 'aws_snapshot_failed'
                    run_exit_code = 1
                    write_manifest(manifest_path, manifest)
                    break
                if not single_running_task(before, args.instance_id):
                    plateau.update({
                        'status': 'refused_before_start',
                        'aws_evidence_valid': False,
                        'aws_evidence_issues': [
                            'ECS service must have desiredCount=1, runningCount=1, pendingCount=0 and exactly one RUNNING task on the specified EC2 instance'
                        ],
                    })
                    manifest['status'] = 'refused_before_start'
                    run_exit_code = 1
                    write_manifest(manifest_path, manifest)
                    break
                write_manifest(manifest_path, manifest)

            command = command_for_plateau(args, rate, plateau_directory)
            plateau['command'] = command
            plateau['status'] = 'running'
            write_manifest(manifest_path, manifest)
            progress(
                f'rate={rate} requests/s warmup={args.warmup_seconds}s '
                f'measurement={args.duration_seconds}s'
            )
            exit_code, interrupted, launch_error = run_k6(
                command,
                plateau_directory / 'stdout.log',
                args,
                fd_plan,
            )
            plateau['exit_code'] = exit_code
            if launch_error:
                plateau.update({'status': 'launch_failed', 'error': launch_error})
                manifest['status'] = 'failed'
                run_exit_code = 1
                write_manifest(manifest_path, manifest)
                break

            if ecs is not None:
                try:
                    after = capture_ecs_snapshot(ecs, args.cluster, args.service)
                    plateau['ecs_after'] = after
                    issues = []
                    if not single_running_task(after, args.instance_id):
                        issues.append('ECS service no longer has exactly one desired and RUNNING task with no pending tasks')
                    if snapshot_identity(before) != snapshot_identity(after):
                        issues.append('ECS service/task/deployment identity changed during the plateau')
                    plateau['aws_evidence_valid'] = not issues
                    plateau['aws_evidence_issues'] = issues
                except Exception as error:
                    plateau.update({
                        'aws_evidence_valid': False,
                        'aws_evidence_issues': [f'Unable to capture ECS after snapshot: {error}'],
                    })
                if not plateau.get('aws_evidence_valid'):
                    plateau['status'] = 'interrupted' if interrupted else 'aws_evidence_invalid'
                    manifest['status'] = 'interrupted' if interrupted else 'aws_evidence_invalid'
                    if interrupted:
                        plateau['interrupted'] = True
                        manifest['interrupted'] = True
                        run_exit_code = 130
                    else:
                        run_exit_code = 1
                    write_manifest(manifest_path, manifest)
                    break

            if interrupted:
                plateau.update({'status': 'interrupted', 'interrupted': True})
                manifest['status'] = 'interrupted'
                manifest['interrupted'] = True
                run_exit_code = 130
                write_manifest(manifest_path, manifest)
                break
            if exit_code == 99:
                plateau['status'] = 'threshold_failed'
                manifest['status'] = 'running'
                write_manifest(manifest_path, manifest)
                continue
            if exit_code != 0:
                plateau['status'] = 'k6_failed'
                manifest['status'] = 'failed'
                run_exit_code = exit_code if exit_code > 0 else 1
                write_manifest(manifest_path, manifest)
                break

            plateau['status'] = 'completed'
            manifest['status'] = 'running'
            write_manifest(manifest_path, manifest)

        if run_exit_code == 0 and all(item.get('status') in {'completed', 'threshold_failed'} for item in plateaus):
            manifest['status'] = 'completed'
        elif manifest.get('status') == 'running':
            manifest['status'] = 'incomplete'
    except KeyboardInterrupt:
        manifest['status'] = 'interrupted'
        manifest['interrupted'] = True
        run_exit_code = 130
        progress('runner interrupted; results are marked incomplete')
    finally:
        manifest['finished_at_utc'] = utc_now()
        write_manifest(manifest_path, manifest)

    progress(f"run finished status={manifest['status']} manifest={manifest_path}")
    return run_exit_code


def main() -> int:
    return execute(parse_args())


if __name__ == '__main__':
    sys.exit(main())
