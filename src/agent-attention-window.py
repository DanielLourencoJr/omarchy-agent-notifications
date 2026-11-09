#!/usr/bin/env python3
"""Resolve an agent process to its Hyprland window for visibility and focus."""

import json
import subprocess
import sys


def hypr_json(topic):
    result = subprocess.run(
        ["hyprctl", "-j", topic], check=True, capture_output=True, text=True
    )
    return json.loads(result.stdout)


def ancestors(pid):
    found = {}
    while pid > 1 and pid not in found:
        found[pid] = len(found)
        try:
            with open(f"/proc/{pid}/stat", encoding="utf-8") as stream:
                pid = int(stream.read().rsplit(")", 1)[1].split()[1])
        except (OSError, ValueError, IndexError):
            break
    return found


def target_window(pid):
    process_ancestors = ancestors(pid)
    clients = hypr_json("clients")
    matches = [
        client
        for client in clients
        if int(client.get("pid") or -1) in process_ancestors
    ]
    if not matches:
        return None
    matches.sort(key=lambda client: process_ancestors[int(client["pid"])])
    return matches[0]


def is_visible(client):
    if not client or not client.get("mapped") or client.get("hidden"):
        return False
    monitor_id = client.get("monitor")
    workspace_id = client.get("workspace", {}).get("id")
    for monitor in hypr_json("monitors"):
        if monitor.get("id") == monitor_id:
            return monitor.get("activeWorkspace", {}).get("id") == workspace_id
    return False


def focus(client):
    if not client:
        return False
    monitor_id = client.get("monitor")
    workspace_id = client.get("workspace", {}).get("id")
    address = client.get("address")
    monitors = hypr_json("monitors")
    monitor = next((item for item in monitors if item.get("id") == monitor_id), None)
    if not monitor or workspace_id is None or not address:
        return False

    dispatch("focusmonitor", monitor.get("name", str(monitor_id)))
    dispatch("workspace", str(workspace_id))
    dispatch("focuswindow", f"address:{address}")
    return True


def dispatch(name, argument):
    subprocess.run(["hyprctl", "dispatch", name, argument], check=True)


def main():
    if len(sys.argv) != 3 or sys.argv[1] not in {"visible", "focus"}:
        return 2
    try:
        pid = int(sys.argv[2])
        client = target_window(pid)
        if sys.argv[1] == "visible":
            return 0 if is_visible(client) else 1
        return 0 if focus(client) else 1
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError, json.JSONDecodeError):
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
