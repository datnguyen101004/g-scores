"""SSM transport for the load test. Requires boto3 and configured AWS credentials."""
import argparse
import base64
import gzip
import json
import shlex
import sys
from pathlib import Path

import boto3
from botocore.exceptions import WaiterError


def execute(client, instance, commands, timeout=3600):
    sent = client.send_command(
        InstanceIds=[instance], DocumentName="AWS-RunShellScript",
        Parameters={"commands": commands, "executionTimeout": [str(timeout)]},
        TimeoutSeconds=60,
    )
    command_id = sent["Command"]["CommandId"]
    print(f"SSM command {command_id}", file=sys.stderr, flush=True)
    try:
        client.get_waiter("command_executed").wait(
            CommandId=command_id, InstanceId=instance,
            WaiterConfig={"Delay": 2, "MaxAttempts": timeout // 2 + 60},
        )
    except WaiterError as error:
        result = client.get_command_invocation(CommandId=command_id, InstanceId=instance)
        if result["Status"] in ("Pending", "InProgress", "Delayed"):
            raise RuntimeError(f"SSM command {command_id} still {result['Status']}; not complete") from error
        return result
    result = client.get_command_invocation(CommandId=command_id, InstanceId=instance)
    return result


def require_success(result):
    if result["Status"] != "Success" or result["ResponseCode"] != 0:
        raise RuntimeError(json.dumps(result, ensure_ascii=False))
    return result["StandardOutputContent"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--instance", required=True)
    parser.add_argument("--region", default="ap-southeast-1")
    sub = parser.add_subparsers(dest="action", required=True)
    upload = sub.add_parser("upload")
    upload.add_argument("files", nargs="+")
    upload.add_argument("--directory", default="/opt/g-scores-load-test")
    run = sub.add_parser("run")
    run.add_argument("--command", required=True)
    run.add_argument("--timeout", type=int, default=3600)
    run.add_argument("--result")
    run.add_argument("--allow-exit", type=int, action="append", default=[],
                     help="Expected nonzero command exit, e.g. k6 threshold failure 99; recorded, not discarded.")
    download = sub.add_parser("download")
    download.add_argument("--remote", required=True)
    download.add_argument("--local", required=True)
    args = parser.parse_args()
    client = boto3.client("ssm", region_name=args.region)
    if args.action == "upload":
        require_success(execute(client, args.instance, [f"install -d -m 755 {shlex.quote(args.directory)}"], 30))
        for file in args.files:
            source = Path(file)
            target = f"{args.directory}/{source.name}"
            encoded = base64.b64encode(gzip.compress(source.read_bytes())).decode("ascii")
            temporary = target + ".upload"
            require_success(execute(client, args.instance, [f": > {shlex.quote(temporary)}"], 30))
            for offset in range(0, len(encoded), 12000):
                chunk = encoded[offset:offset + 12000]
                require_success(execute(client, args.instance, [f"printf '%s' '{chunk}' >> {shlex.quote(temporary)}"], 30))
            code = ("import base64,gzip,pathlib; "
                    f"p=pathlib.Path({temporary!r}); "
                    f"pathlib.Path({target!r}).write_bytes(gzip.decompress(base64.b64decode(p.read_bytes()))); p.unlink()")
            require_success(execute(client, args.instance, [f"python3 -c {shlex.quote(code)}"], 30))
            print(f"Uploaded {source} -> {target}", flush=True)
    elif args.action == "run":
        result = execute(client, args.instance, [args.command], args.timeout)
        if args.result:
            Path(args.result).parent.mkdir(parents=True, exist_ok=True)
            Path(args.result).write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        print(result["StandardOutputContent"], end="", flush=True)
        print(result["StandardErrorContent"], end="", file=sys.stderr, flush=True)
        if result["Status"] not in ("Success", "Failed") or result["ResponseCode"] not in [0] + args.allow_exit:
            sys.exit(1)
    else:
        # Compression reduces SSM calls; one chunk stays below its 24,000-character stdout cap.
        remote = args.remote + ".download.gz"
        code = ("import gzip,pathlib; "
                f"p=pathlib.Path({remote!r}); "
                f"p.write_bytes(gzip.compress(pathlib.Path({args.remote!r}).read_bytes())); print(p.stat().st_size)")
        size = int(require_success(execute(client, args.instance, [f"python3 -c {shlex.quote(code)}"], 30)).strip())
        content = bytearray()
        for offset in range(0, size, 12000):
            code = ("import base64,pathlib; "
                    f"p=pathlib.Path({remote!r}); "
                    f"f=p.open('rb'); f.seek({offset}); print(base64.b64encode(f.read(12000)).decode('ascii'))")
            value = require_success(execute(client, args.instance, [f"python3 -c {shlex.quote(code)}"], 30))
            content.extend(base64.b64decode(value.strip(), validate=True))
        target = Path(args.local)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(gzip.decompress(content))
        require_success(execute(client, args.instance, [f"rm -- {shlex.quote(remote)}"], 30))
        print(f"Downloaded {args.remote} -> {target} ({target.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
