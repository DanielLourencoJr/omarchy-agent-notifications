# Agent attention notifications for Omarchy

This installs Omarchy desktop notifications for OpenCode and Codex. It sends
alerts when either harness needs approval/input or when a turn finishes. It
does not alert on command or tool completion. Alerts are suppressed when the
matching agent process belongs to a window on a workspace currently visible on
that monitor.

## Requirements

- Omarchy on Hyprland, including `omarchy-notification-send`
- `hyprctl`, Python 3, and Bash
- OpenCode and Codex installed and available on `PATH`

## Install

Clone this repository and run:

```bash
git clone <repository-url> agent-attention-notifications
cd agent-attention-notifications
./install.sh
```

Run the command from a regular user terminal with write access to
`~/.codex/hooks.json`. Do not run it from inside a restricted agent sandbox:
the installer checks access before copying any files and exits with a clear
message if the Codex config is read-only. It never uses `sudo` or changes file
permissions to get around that restriction.

The installer copies the shared notifier, icons, and both harness adapters into
the standard user configuration directories. It merges the Codex hooks into
`~/.codex/hooks.json`, preserving existing hooks and creating a timestamped
backup before changing that file. It does not use `sudo`.

Notification clicks switch to the agent window's monitor and workspace, then
focus that exact window. Notifications are suppressed when that window's
workspace is already visible on its monitor.

Codex hooks can run in its shared app-server rather than under the terminal
process. The Codex adapter passes the session ID so the helper can resolve the
matching `codex resume <session-id>` window in that case.

Restart OpenCode after installation. In Codex, open `/hooks` and review/trust
the `PermissionRequest` and `Stop` hooks if Codex asks. Codex requires this
review before local hooks run.

## Update

`install.sh` is also the standard update command. After pulling a newer repo
revision, rerun it; it updates the installed adapters and icons, merges hooks
idempotently, and backs up any managed file it replaces:

```bash
cd ~/Projects/agent-attention-notifications
git pull
./install.sh
```

If OpenCode or Codex is already open, the installer warns and continues without
closing either app. Restart the running harnesses afterward so they load updated
plugins and hook configuration.

## Uninstall

Remove the installed files:

```bash
rm ~/.local/bin/agent-attention-notify
rm -r "${XDG_DATA_HOME:-$HOME/.local/share}/agent-attention"
rm ~/.config/opencode/plugins/attention-notifications.ts
```

Then remove the two `PermissionRequest` and `Stop` hook handler entries for
`agent-attention-notify` from `~/.codex/hooks.json`. Existing hook config
backups are kept alongside the file with a `.bak.<timestamp>` suffix.
