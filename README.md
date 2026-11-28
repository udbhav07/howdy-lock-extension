# howdy-lock-extension

`presence-guard` does two things on KDE Plasma with [Howdy](https://github.com/boltgolt/howdy):

1. **Stops KDE from auto-locking while you are sitting in front of it.**
2. **Photographs whoever types a wrong password on your lock screen**, and shows you their photos when you come back.

## Auto-lock only when you're away

It only steps in at one moment: just before KDE's idle auto-lock fires. It checks the IR camera against your Howdy face model:

| Who is in front of the camera | What happens |
|---|---|
| you | KDE's lock timer restarts, as if you'd touched the mouse |
| someone else, or nobody | nothing: KDE locks on schedule |
| any camera in use by another app (e.g. a meeting) | KDE's lock timer restarts, no face check: no lock while a camera is in use |

It also stops Howdy's lock-screen face check the moment the screen unlocks, so the camera turns off when you unlock with your password instead.

presence-guard never locks the screen itself, so turning it off leaves KDE exactly as it was.

- **Timing comes from KDE:** the check runs 15 s before your auto-lock time (System Settings → Screen Locking). Change that setting, then restart the service: `systemctl --user restart presence-guard`.
- **Meetings and videos:** apps that block idle (meeting apps, video players) stop KDE's countdown, so presence-guard never runs.

## Wrong-password photos

When someone types a wrong password on the lock screen (or the SDDM login screen), the color camera takes 5 photos. Several wrong passwords within a few seconds count as one attempt.

When you unlock, a notification shows the newest photo and how many attempts there were. Click it to open the **Presence Guard** app on just those attempts. Open the app from the menu any time to see the full history.

The app has three pages:

- **Wrong passwords:** each attempt with its time, photos (click to open full size) and tags: "3 tries", "Login screen", or "Probably you" when you unlocked within 20 s, which is usually your own typo. Delete removes an attempt.
- **Status:** whether the services run, the KDE auto-lock time, both cameras, the last capture problem, and a "Check camera now" button.
- **Settings:** pick the camera, turn photos on or off, and choose how long to keep attempts (default 30 days).

Photos stay off until you pick a camera in Settings. They are stored in `~/.local/share/presence-guard/` and only your account can read them.

## Requirements

- Howdy installed and working, with your face added (`sudo howdy add`)
- KDE Plasma 6 on Wayland (tested on Fedora 44)
- `swayidle`, OpenCV, PySide6 and libnotify: `install.sh` installs any that are missing with `dnf`. On other distributions, install them yourself first.

It reuses Howdy's settings: the IR camera (`device_path`), match strictness (`certainty`), and dlib models.

## Install

```bash
git clone https://github.com/udbhav07/howdy-lock-extension.git
cd howdy-lock-extension
./install.sh              # asks for sudo to install the login-screen watcher
./install.sh --user-only  # or: everything except the login-screen watcher (sudo only to install missing packages)
```

Then open **Presence Guard → Settings** and pick your camera.

`install.sh` installs missing packages, links `presence-guard` into `~/.local/bin`, adds the app to the menu, and enables the `presence-guard` user service. Without `--user-only` it also installs a root-owned copy in `/usr/local/lib/presence-guard` and enables `presence-guard-sddm@$USER` for the login screen. Run it again after `git pull`, so the root copy is updated too.

## Usage

```bash
presence-guard check   # one look: prints owner / stranger / nobody / busy
presence-guard photo   # test the chosen camera (photos go to a test folder, never into the history)
presence-guard ui      # open the app
```

## Uninstall

```bash
systemctl --user disable --now presence-guard
sudo systemctl disable --now "presence-guard-sddm@$USER"
sudo rm -r /usr/local/lib/presence-guard /etc/systemd/system/presence-guard-sddm@.service
rm ~/.local/bin/presence-guard ~/.local/share/applications/presence-guard.desktop
rm -r ~/.local/share/presence-guard ~/.config/presence-guard ~/.local/state/presence-guard  # your photos and settings
```

## Face and password unlock at the same time

If Howdy is in `/etc/pam.d/kde`, the password field waits until the face check gives up. Put Howdy in `kde-fingerprint` instead. The KDE lock screen runs that stack in parallel with the password, so face or password unlocks, whichever finishes first:

```bash
sudo sed -i '/pam_howdy.so/d' /etc/pam.d/kde
sudo sed -i '1i auth        sufficient    pam_howdy.so' /etc/pam.d/kde-fingerprint
```

Undo: run the same two commands with the file names swapped.

## Limits

- Only USB (UVC) cameras work. Built-in Intel IPU6/IPU7 cameras on many newer laptops may not; `install.sh` warns when it finds no usable camera.
- Pressing Enter with an empty password also counts as a wrong password, so you may see photos of yourself (often tagged "Probably you").
- Attempts made before a reboot are shown at your next unlock, not at login.
- If `pam_faillock` is enabled and locks the account after several failures, later attempts are not logged, so no photos are taken.
- If an app leaves a camera open by mistake (camera light stays on), the screen won't auto-lock until it's closed. Meta+L always locks.

## Notes

- On the lock screen presence-guard uses only the color camera, and only after a wrong password. If the IR camera turns on there, it is Howdy (you pressed Enter or clicked unlock).
- Your face model stays in `/etc/howdy/models/` and is never copied into this repo.
