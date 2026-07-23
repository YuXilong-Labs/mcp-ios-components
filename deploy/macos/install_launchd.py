#!/usr/bin/env python3
"""Generate the per-user launchd plist for the macOS MCP service."""

from __future__ import annotations

import argparse
import os
import plistlib


def build_launchd_plist(
    *,
    label: str,
    service_root: str,
    data_root: str,
    log_root: str,
) -> dict:
    run_script = os.path.join(service_root, "deploy", "macos", "run-mcp.sh")
    return {
        "Label": label,
        "ProgramArguments": [run_script],
        "WorkingDirectory": service_root,
        "RunAtLoad": True,
        "KeepAlive": True,
        "ProcessType": "Background",
        "ThrottleInterval": 10,
        "Umask": 0o027,
        "StandardOutPath": os.path.join(log_root, "stdout.log"),
        "StandardErrorPath": os.path.join(log_root, "stderr.log"),
        "EnvironmentVariables": {
            "MCP_SERVICE_ROOT": service_root,
            "MCP_DATA_ROOT": data_root,
            "NO_PROXY": "127.0.0.1,localhost",
            "no_proxy": "127.0.0.1,localhost",
            "PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", required=True)
    parser.add_argument("--service-root", required=True)
    parser.add_argument("--data-root", required=True)
    parser.add_argument("--log-root", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    payload = build_launchd_plist(
        label=args.label,
        service_root=os.path.abspath(args.service_root),
        data_root=os.path.abspath(args.data_root),
        log_root=os.path.abspath(args.log_root),
    )
    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    with open(args.output, "wb") as f:
        plistlib.dump(payload, f, sort_keys=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
