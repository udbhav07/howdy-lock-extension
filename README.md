# howdy-lock-extension

`presence-guard` stops KDE from auto-locking your screen while **you** are sitting in front of it.

It only steps in at one moment: just before KDE's idle auto-lock fires. It checks the IR camera against your [Howdy](https://github.com/boltgolt/howdy) face model:

| Who is in front of the camera | What happens |
|---|---|
| you | KDE's lock timer restarts, as if you'd touched the mouse |
| someone else, or nobody | nothing: KDE locks on schedule |
| any camera in use by another app (e.g. a meeting) | KDE's lock timer restarts, no face check: no lock while a camera is in use |

presence-guard never locks the screen itself, so turning it off leaves KDE exactly as it was.

- **Timing comes from KDE:** the check runs 15 s before your auto-lock time (System Settings → Screen Locking). Change that setting, then restart the service: `systemctl --user restart presence-guard`.
- **Meetings and videos:** apps that block idle (meeting apps, video players) stop KDE's countdown, so presence-guard never runs.

## Requirements

- Howdy installed and working, with your face added (`sudo howdy add`)
- KDE Plasma 6 on Wayland (tested on Fedora 44)
- `swayidle` (`sudo dnf install swayidle`)

It reuses Howdy's settings: the camera (`device_path`), match strictness (`certainty`), and dlib models.

## Install

```bash
ln -s "$PWD/presence-guard" ~/.local/bin/presence-guard
systemctl --user link "$PWD/presence-guard.service"
systemctl --user enable --now presence-guard
```

## Usage

```bash
presence-guard check   # one look: prints owner / stranger / nobody / busy
```

Stop it with `systemctl --user disable --now presence-guard`.

## Notes

- If an app leaves a camera open by mistake (camera light stays on), the screen won't auto-lock until it's closed. Meta+L always locks.
- Your face model stays in `/etc/howdy/models/` and is never copied into this repo.
