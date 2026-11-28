#!/usr/bin/env bash
# Install or update presence-guard for the current user. Safe to run again after `git pull`.
#   ./install.sh               everything, including the SDDM login-screen watcher (asks for sudo)
#   ./install.sh --user-only   skip the login-screen watcher (sudo only if packages are missing)
# Missing packages are installed with dnf (Fedora). Howdy itself must already be installed.
set -euo pipefail
cd "$(dirname "$(realpath "$0")")"
repo=$PWD
user_only=false
[ "${1:-}" = "--user-only" ] && user_only=true

if [ ! -r /etc/howdy/config.ini ]; then
  echo "Howdy is not installed. Install it and add your face first (sudo howdy add):" >&2
  echo "  https://github.com/boltgolt/howdy#installation" >&2
  exit 1
fi

# Commands and Python modules we need, each with the Fedora package that provides it.
declare -A cmd_pkg=([python3]=python3 [swayidle]=swayidle [gdbus]=glib2 [journalctl]=systemd
  [notify-send]=libnotify [kreadconfig6]=kf6-kconfig [systemd-run]=systemd)
declare -A mod_pkg=([cv2]=python3-opencv [dlib]=python3-dlib [numpy]=python3-numpy [PySide6]=python3-pyside6)
missing() {
  local c m
  for c in "${!cmd_pkg[@]}"; do command -v "$c" >/dev/null || echo "${cmd_pkg[$c]}"; done
  for m in "${!mod_pkg[@]}"; do python3 -c "import $m" 2>/dev/null || echo "${mod_pkg[$m]}"; done
}
pkgs=$(missing | sort -u | tr '\n' ' ')
if [ -n "$pkgs" ]; then
  if ! command -v dnf >/dev/null; then
    echo "Missing packages: $pkgs(install them with your package manager, then run this again)" >&2
    exit 1
  fi
  echo "Installing missing packages: $pkgs"
  # shellcheck disable=SC2086
  sudo dnf install -y $pkgs
  pkgs=$(missing | sort -u | tr '\n' ' ')
  if [ -n "$pkgs" ]; then
    echo "Still missing after install: $pkgs" >&2
    exit 1
  fi
fi

mkdir -p ~/.local/bin ~/.local/share/applications
ln -sfn "$repo/presence-guard" ~/.local/bin/presence-guard
# Absolute Exec: the app menu may not have ~/.local/bin on its PATH.
sed "s|^Exec=presence-guard|Exec=$HOME/.local/bin/presence-guard|" presence-guard.desktop \
  > ~/.local/share/applications/presence-guard.desktop
systemctl --user link "$repo/presence-guard.service" >/dev/null
systemctl --user enable presence-guard >/dev/null 2>&1
systemctl --user restart presence-guard
echo "presence-guard service: $(systemctl --user is-active presence-guard)"

if ! $user_only; then
  # The root unit runs a root-owned copy, so nothing your account can edit ever runs as root.
  dest=/usr/local/lib/presence-guard
  sudo install -d -o root -g root -m 755 "$dest" "$dest/pg"
  sudo install -o root -g root -m 755 presence-guard "$dest/presence-guard"
  sudo install -o root -g root -m 644 pg/*.py "$dest/pg/"
  sudo install -o root -g root -m 644 presence-guard-sddm@.service /etc/systemd/system/
  sudo systemctl daemon-reload
  sudo systemctl enable "presence-guard-sddm@$USER" >/dev/null 2>&1
  sudo systemctl restart "presence-guard-sddm@$USER"
  echo "login-screen watcher: $(systemctl is-active "presence-guard-sddm@$USER")"
fi

cameras=$(python3 -c 'from pg import system; print(len(system.list_cameras()))')
if [ "$cameras" = 0 ]; then
  echo "Warning: no usable camera found besides Howdy's. Only USB (UVC) cameras work; built-in Intel IPU6/IPU7" >&2
  echo "cameras may not. Wrong-password photos can't be taken until a camera shows up in Settings." >&2
elif [ "$(python3 -c 'from pg import store; print(store.settings()["camera"] or "")')" = "" ]; then
  echo "Next: open Presence Guard → Settings and pick your camera. Wrong-password photos stay off until you do."
fi
if [ -d ~/Pictures/failed-unlocks ]; then
  echo "Old photos from an earlier version are in ~/Pictures/failed-unlocks; delete them when you no longer need them."
fi
