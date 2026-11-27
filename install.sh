#!/usr/bin/env bash
# Install or update presence-guard for the current user. Safe to run again after `git pull`.
#   ./install.sh               everything, including the SDDM login-screen watcher (asks for sudo)
#   ./install.sh --user-only   skip the login-screen watcher (no sudo)
set -euo pipefail
cd "$(dirname "$(realpath "$0")")"
repo=$PWD
user_only=false
[ "${1:-}" = "--user-only" ] && user_only=true

missing=()
for cmd in python3 swayidle gdbus journalctl notify-send kreadconfig6 systemd-run; do
  command -v "$cmd" >/dev/null || missing+=("$cmd")
done
for mod in cv2 dlib numpy PySide6; do
  python3 -c "import $mod" 2>/dev/null || missing+=("python3 module $mod")
done
[ -r /etc/howdy/config.ini ] || missing+=("Howdy (/etc/howdy/config.ini)")
if [ ${#missing[@]} -gt 0 ]; then
  echo "Missing: ${missing[*]}" >&2
  echo "On Fedora: sudo dnf install swayidle python3-opencv python3-pyside6 libnotify (dlib comes with Howdy)" >&2
  exit 1
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
