#!/usr/bin/env bash
# Remove presence-guard. Safe to run again: anything already gone is skipped.
#   ./uninstall.sh           asks before deleting your photos and settings
#   ./uninstall.sh --purge   deletes them without asking
set -uo pipefail
purge=false
[ "${1:-}" = "--purge" ] && purge=true

systemctl --user disable --now presence-guard 2>/dev/null
rm -f ~/.config/systemd/user/presence-guard.service  # the link install.sh made
systemctl --user daemon-reload
rm -f ~/.local/bin/presence-guard ~/.local/share/applications/presence-guard.desktop
echo "removed the app and user service"

if [ -e /etc/systemd/system/presence-guard-sddm@.service ] || [ -d /usr/local/lib/presence-guard ] ||
   grep -q pam_howdy.so /etc/pam.d/kde-fingerprint 2>/dev/null; then
  sudo systemctl disable --now "presence-guard-sddm@$USER" 2>/dev/null
  sudo rm -rf /usr/local/lib/presence-guard /etc/systemd/system/presence-guard-sddm@.service
  sudo systemctl daemon-reload
  echo "removed the login-screen watcher"

  # Undo face-or-password: put Howdy back in front of the password.
  if grep -q pam_howdy.so /etc/pam.d/kde-fingerprint 2>/dev/null; then
    grep -q pam_howdy.so /etc/pam.d/kde ||
      sudo sed -i '1i auth        sufficient    pam_howdy.so' /etc/pam.d/kde
    sudo sed -i '/pam_howdy.so/d' /etc/pam.d/kde-fingerprint
    echo "lock screen: Howdy runs before the password again"
  fi
fi

data=(~/.local/share/presence-guard ~/.config/presence-guard ~/.local/state/presence-guard)
found=false
for d in "${data[@]}"; do [ -e "$d" ] && found=true; done
if $found; then
  if ! $purge; then
    read -rp "Delete your wrong-password photos and settings too? [y/N] " answer
    [[ $answer =~ ^[Yy] ]] && purge=true
  fi
  if $purge; then
    rm -rf "${data[@]}"
    echo "deleted photos and settings"
  else
    echo "kept photos and settings in ${data[*]}"
  fi
fi
