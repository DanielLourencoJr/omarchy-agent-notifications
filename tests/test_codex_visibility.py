"""Regression coverage for Codex hooks running outside the TUI process tree."""

import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest


ROOT = Path(__file__).resolve().parents[1]
THREAD_ID = "01234567-89ab-cdef-0123-456789abcdef"


class CodexVisibilityTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="agent-attention-test-")
        self.addCleanup(self.temp.cleanup)
        self.temp_root = Path(self.temp.name)
        self.fake_bin = self.temp_root / "bin"
        self.fake_bin.mkdir()
        self.home = self.temp_root / "home"
        self.local_bin = self.home / ".local" / "bin"
        self.local_bin.mkdir(parents=True)
        self.data_home = self.temp_root / "data"
        (self.data_home / "agent-attention" / "icons").mkdir(parents=True)
        (self.data_home / "agent-attention" / "icons" / "codex.png").write_bytes(b"test icon")
        (self.local_bin / "agent-attention-notify").symlink_to(ROOT / "src/agent-attention-notify")
        (self.local_bin / "agent-attention-window").symlink_to(ROOT / "src/agent-attention-window.py")

        self.notification_log = self.temp_root / "notifications.jsonl"
        self.clients_json = self.temp_root / "clients.json"
        self.monitors_json = self.temp_root / "monitors.json"
        self.pid_file = self.temp_root / "fake-codex.pid"
        self.dispatch_log = self.temp_root / "dispatches.jsonl"

        self.write_executable(
            self.fake_bin / "hyprctl",
            """#!/usr/bin/env python3
import os, sys
if sys.argv[1] == "dispatch":
    import json
    with open(os.environ["TEST_DISPATCH_LOG"], "a", encoding="utf-8") as out:
        out.write(json.dumps(sys.argv[1:]) + "\\n")
    raise SystemExit(0)
path = os.environ["TEST_CLIENTS_JSON"] if sys.argv[-1] == "clients" else os.environ["TEST_MONITORS_JSON"]
sys.stdout.write(open(path, encoding="utf-8").read())
""",
        )
        self.write_executable(
            self.fake_bin / "omarchy-notification-send",
            """#!/usr/bin/env python3
import json, os, sys
with open(os.environ["TEST_NOTIFICATION_LOG"], "a", encoding="utf-8") as out:
    out.write(json.dumps(sys.argv[1:]) + "\\n")
""",
        )

        self.env = os.environ.copy()
        self.env.update(
            {
                "HOME": str(self.home),
                "XDG_DATA_HOME": str(self.data_home),
                "PATH": f"{self.fake_bin}:{os.environ['PATH']}",
                "TEST_CLIENTS_JSON": str(self.clients_json),
                "TEST_MONITORS_JSON": str(self.monitors_json),
                "TEST_NOTIFICATION_LOG": str(self.notification_log),
                "TEST_DISPATCH_LOG": str(self.dispatch_log),
                "FAKE_CODEX_PID_FILE": str(self.pid_file),
            }
        )

        # Model a terminal process that owns a Codex TUI child. The simulated
        # hook process will be launched by this test runner instead, like a hook
        # launched by Codex's shared app-server rather than the terminal.
        terminal_code = """import os, subprocess, sys, time
thread_id = sys.argv[1]
child = subprocess.Popen(
    ["codex", "-c", "import time; time.sleep(120)", thread_id],
    executable=sys.executable,
    stdin=subprocess.DEVNULL,
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
)
with open(os.environ["FAKE_CODEX_PID_FILE"], "w", encoding="utf-8") as out:
    out.write(str(child.pid))
time.sleep(120)
"""
        self.terminal = subprocess.Popen(
            [sys.executable, "-c", terminal_code, THREAD_ID],
            env=self.env,
            start_new_session=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self.addCleanup(self.stop_terminal)
        deadline = time.monotonic() + 3
        while not self.pid_file.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertTrue(self.pid_file.exists(), "fake Codex TUI did not start")

        self.clients_json.write_text(
            json.dumps(
                [
                    {
                        "address": "0x1234",
                        "pid": self.terminal.pid,
                        "monitor": 4,
                        "workspace": {"id": 7, "name": "7"},
                        "mapped": True,
                        "hidden": False,
                    }
                ]
            ),
            encoding="utf-8",
        )

    def write_executable(self, path, content):
        path.write_text(content, encoding="utf-8")
        path.chmod(0o755)

    def stop_terminal(self):
        try:
            os.killpg(self.terminal.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            self.terminal.wait(timeout=2)
        except subprocess.TimeoutExpired:
            self.terminal.kill()
            self.terminal.wait()

    def notify(self, active_workspace):
        self.monitors_json.write_text(
            json.dumps(
                [
                    {
                        "id": 4,
                        "name": "TEST-MONITOR",
                        "activeWorkspace": {"id": active_workspace, "name": str(active_workspace)},
                    }
                ]
            ),
            encoding="utf-8",
        )
        event = {"hook_event_name": "Stop", "session_id": THREAD_ID}
        return subprocess.run(
            [sys.executable, str(ROOT / "src/codex-hook.py")],
            input=json.dumps(event),
            text=True,
            env=self.env,
            check=False,
            timeout=5,
        )

    def notifications(self):
        if not self.notification_log.exists():
            return []
        return [json.loads(line) for line in self.notification_log.read_text().splitlines()]

    def test_codex_in_current_workspace_does_not_notify(self):
        # Monitor IDs are numeric, and the hook's parent is unrelated to the
        # terminal. The session ID must locate the matching Codex window.
        result = self.notify(active_workspace=7)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(self.notifications(), [])

    def test_codex_on_another_workspace_notifies_and_click_targets_it(self):
        result = self.notify(active_workspace=2)
        self.assertEqual(result.returncode, 0)
        notifications = self.notifications()
        self.assertEqual(len(notifications), 1)
        args = notifications[0]
        self.assertIn("--exec", args)
        click_index = args.index("--exec") + 1
        self.assertEqual(args[click_index], str(self.local_bin / "agent-attention-window"))
        self.assertEqual(args[click_index + 1 :], ["focus", str(os.getpid()), THREAD_ID])

        click_result = subprocess.run(
            args[click_index:], env=self.env, check=False, timeout=5
        )
        self.assertEqual(click_result.returncode, 0)
        dispatches = [
            json.loads(line) for line in self.dispatch_log.read_text().splitlines()
        ]
        self.assertEqual(
            dispatches,
            [
                ['dispatch', 'hl.dsp.focus({ monitor = "TEST-MONITOR"})'],
                ['dispatch', 'hl.dsp.focus({ workspace = "7" })'],
                [
                    'dispatch',
                    'hl.dsp.focus({ window = hl.get_window("address:0x1234") })',
                ],
            ],
        )


if __name__ == "__main__":
    unittest.main()
