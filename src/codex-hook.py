#!/usr/bin/env python3
"""Codex hook adapter for the shared Omarchy agent attention notifier."""

import json
import os
import subprocess
import sys

try:
    payload = json.load(sys.stdin)
except (json.JSONDecodeError, AttributeError):
    raise SystemExit(0)

normalized = {"PermissionRequest": "approval", "Stop": "finished"}.get(
    payload.get("hook_event_name")
)
if normalized:
    notifier = os.path.expanduser("~/.local/bin/agent-attention-notify")
    thread_id = payload.get("session_id") or payload.get("thread_id") or payload.get("thread-id")
    args = [notifier, "Codex", normalized, str(os.getppid())]
    if thread_id:
        args.append(str(thread_id))
    subprocess.run(
        args,
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
