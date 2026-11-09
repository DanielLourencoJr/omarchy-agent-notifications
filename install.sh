#!/usr/bin/env bash
set -euo pipefail

repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
: "${HOME:?HOME must be set}"

for dependency in python3 hyprctl omarchy-notification-send opencode codex; do
  if ! command -v "$dependency" >/dev/null 2>&1; then
    printf 'Missing required command: %s\n' "$dependency" >&2
    exit 1
  fi
done

data_home=${XDG_DATA_HOME:-"$HOME/.local/share"}
data_dir="$data_home/agent-attention"
bin_dir="$HOME/.local/bin"
plugin_dir="$HOME/.config/opencode/plugins"
hooks_file="$HOME/.codex/hooks.json"
codex_adapter="$data_dir/codex-hook.py"

# Do not install half of the setup if Codex's active config is read-only (for
# example when this script is run inside a restricted agent sandbox).
hooks_dir=$(dirname -- "$hooks_file")
if [[ ! -d $hooks_dir ]]; then
  mkdir -p "$hooks_dir" || {
    printf 'Cannot create %s. Run this installer from a user shell with access to ~/.codex.\n' "$hooks_dir" >&2
    exit 1
  }
fi
if [[ ! -w $hooks_dir || ( -e $hooks_file && ! -w $hooks_file ) ]]; then
  printf 'Cannot update %s: it is not writable. Run this installer from a user terminal outside the restricted Codex sandbox. No files were installed.\n' "$hooks_file" >&2
  exit 1
fi
# Unix mode-bit checks above do not reveal sandbox policies. Probe the actual
# write path before copying any managed files, then remove the probe.
write_probe=$(mktemp "$hooks_dir/.agent-attention-write-test.XXXXXX") || {
  printf 'Cannot write to %s in this environment. Run this installer from a regular user terminal outside Codex read-only mode. No files were installed.\n' "$hooks_dir" >&2
  exit 1
}
if ! rm -f -- "$write_probe"; then
  printf 'Cannot clean up the write probe in %s. No files were installed.\n' "$hooks_dir" >&2
  exit 1
fi
if [[ -e $hooks_file ]]; then
  python3 - "$hooks_file" <<'PY'
import json, sys
try:
    with open(sys.argv[1], encoding="utf-8") as stream:
        json.load(stream)
except (OSError, json.JSONDecodeError) as error:
    raise SystemExit(f"Cannot read valid JSON from {sys.argv[1]}: {error}")
PY
fi

running_harnesses=()
for comm_file in /proc/[0-9]*/comm; do
  [[ -r $comm_file ]] || continue
  comm=
  IFS= read -r comm < "$comm_file" || true
  case "$comm" in
    codex|opencode)
      case " ${running_harnesses[*]-} " in *" $comm "*) ;; *) running_harnesses+=("$comm") ;; esac
      ;;
  esac
done
if ((${#running_harnesses[@]})); then
  printf 'Warning: %s appears to be running. This installer will not close it. Restart it after installation for updated hooks/plugins to load.\n' "${running_harnesses[*]}" >&2
fi

install_managed_file() {
  local source=$1 destination=$2 mode=${3:-644}
  mkdir -p "$(dirname -- "$destination")"
  if [[ -e $destination ]] && ! cmp -s -- "$source" "$destination"; then
    cp -p -- "$destination" "$destination.bak.$(date +%Y%m%d%H%M%S)"
  fi
  install -m "$mode" -- "$source" "$destination"
}

install_managed_file "$repo_dir/src/agent-attention-notify" "$bin_dir/agent-attention-notify" 755
install_managed_file "$repo_dir/src/codex-hook.py" "$codex_adapter" 755
install_managed_file "$repo_dir/src/opencode/attention-notifications.ts" "$plugin_dir/attention-notifications.ts"
install_managed_file "$repo_dir/src/icons/codex.png" "$data_dir/icons/codex.png"
install_managed_file "$repo_dir/src/icons/opencode.svg" "$data_dir/icons/opencode.svg"

AGENT_ATTENTION_HOOKS_FILE="$hooks_file" \
AGENT_ATTENTION_ADAPTER="$codex_adapter" \
AGENT_ATTENTION_PYTHON="$(command -v python3)" \
python3 - <<'PY'
import datetime
import json
import os
import shlex
import stat
import tempfile

path = os.environ["AGENT_ATTENTION_HOOKS_FILE"]
adapter = os.environ["AGENT_ATTENTION_ADAPTER"]
python = os.environ["AGENT_ATTENTION_PYTHON"]
command = f"{shlex.quote(python)} {shlex.quote(adapter)}"

try:
    with open(path, encoding="utf-8") as stream:
        config = json.load(stream)
except FileNotFoundError:
    config = {}
except json.JSONDecodeError as error:
    raise SystemExit(f"Refusing to overwrite invalid JSON in {path}: {error}")

if not isinstance(config, dict):
    raise SystemExit(f"Refusing to overwrite {path}: the top-level JSON value must be an object")
hooks = config.setdefault("hooks", {})
if not isinstance(hooks, dict):
    raise SystemExit(f"Refusing to overwrite {path}: 'hooks' must be an object")

changed = False
for event in ("PermissionRequest", "Stop"):
    groups = hooks.setdefault(event, [])
    if not isinstance(groups, list):
        raise SystemExit(f"Refusing to overwrite {path}: hooks.{event} must be an array")
    # Use an unfiltered matcher group so every approval and stop event reaches
    # this adapter, while preserving all other hooks and matchers.
    already_registered = any(
        isinstance(group, dict)
        and "matcher" not in group
        and any(
            isinstance(handler, dict)
            and handler.get("type") == "command"
            and adapter in handler.get("command", "")
            for handler in group.get("hooks", [])
        )
        for group in groups
    )
    if not already_registered:
        groups.append({"hooks": [{
            "type": "command",
            "command": command,
            "timeout": 3,
            "async": True,
        }]})
        changed = True

if changed:
    if os.path.exists(path):
        stamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        backup = f"{path}.bak.{stamp}"
        with open(path, "rb") as source, open(backup, "wb") as target:
            target.write(source.read())
        os.chmod(backup, stat.S_IMODE(os.stat(path).st_mode))
        mode = stat.S_IMODE(os.stat(path).st_mode)
    else:
        mode = 0o600
    fd, temporary = tempfile.mkstemp(prefix=".hooks.json.", dir=os.path.dirname(path))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(config, stream, indent=2)
            stream.write("\n")
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
PY

printf 'Agent attention notifications installed.\n'
printf 'Restart OpenCode and Codex to load any updated plugins/hooks.\n'
printf 'In Codex, run /hooks and review/trust the two Agent attention hooks if prompted.\n'
