#!/usr/bin/env python3
"""Resolve an agent process to its Hyprland window for visibility and focus."""

import json
import os
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


def processes_for_thread(thread_id):
    if not thread_id:
        return []
    matches = []
    try:
        entries = os.scandir("/proc")
    except OSError:
        return matches
    with entries:
        for entry in entries:
            if not entry.name.isdigit():
                continue
            try:
                with open(f"{entry.path}/cmdline", "rb") as stream:
                    argv = [part.decode(errors="replace") for part in stream.read().split(b"\0") if part]
            except OSError:
                continue
            if thread_id in argv and argv and os.path.basename(argv[0]) == "codex":
                matches.append(int(entry.name))
    return matches


def target_window(pid, thread_id=None):
    process_ids = [pid] + processes_for_thread(thread_id)
    process_ancestors = {}
    for process_id in process_ids:
        for ancestor_pid, distance in ancestors(process_id).items():
            process_ancestors[ancestor_pid] = min(
                distance, process_ancestors.get(ancestor_pid, distance)
            )
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

    dispatch(f"hl.dsp.focus({{ monitor = {lua_string(monitor.get('name', str(monitor_id))) }}})")
    dispatch(f"hl.dsp.focus({{ workspace = {lua_string(str(workspace_id))} }})")
    dispatch(
        "hl.dsp.focus({ window = hl.get_window("
        f"{lua_string(f'address:{address}')}) }})"
    )
    return True


def lua_string(value):
    """Encode a string as a Lua literal for Hyprland's Lua-based dispatcher."""
    return json.dumps(str(value), ensure_ascii=True)


def dispatch(expression):
    subprocess.run(["hyprctl", "dispatch", expression], check=True)


def main():
    if len(sys.argv) not in (3, 4) or sys.argv[1] not in {"visible", "focus"}:
        return 2
    try:
        pid = int(sys.argv[2])
        thread_id = sys.argv[3] if len(sys.argv) == 4 else None
        client = target_window(pid, thread_id)
        if sys.argv[1] == "visible":
            return 0 if is_visible(client) else 1
        return 0 if focus(client) else 1
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError, json.JSONDecodeError):
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
