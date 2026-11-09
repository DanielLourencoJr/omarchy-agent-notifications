#!/usr/bin/env python3
"""Codex hook adapter for the shared Omarchy agent attention notifier."""

import json
import os
import subprocess
import sys

try:
    event = json.load(sys.stdin).get("hook_event_name")
except (json.JSONDecodeError, AttributeError):
    raise SystemExit(0)

normalized = {"PermissionRequest": "approval", "Stop": "finished"}.get(event)
if normalized:
    notifier = os.path.expanduser("~/.local/bin/agent-attention-notify")
    subprocess.run(
        [notifier, "Codex", normalized, str(os.getppid())],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
