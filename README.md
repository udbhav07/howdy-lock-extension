# howdy-lock-extension

`presence-guard` keeps a Linux laptop unlocked while **you** are sitting in front of it, and locks the screen when you're gone.

When the laptop has been idle for a while, it checks the IR camera with your [Howdy](https://github.com/boltgolt/howdy) face model:

| Who is in front of the camera | What happens |
|---|---|
| you | stays unlocked and awake, checks again every 5 min |
| someone else, or nobody | locks the screen |

Any keyboard or mouse activity stops the check until you're idle again.

## Requirements

- Howdy installed and working, with your face added (`sudo howdy add`)
- A Wayland compositor with `ext-idle-notify` (tested on KDE Plasma 6, Fedora 44)
- `swayidle` (`sudo dnf install swayidle`)
- `kde-inhibit` (ships with Plasma) to stop KDE's own idle sleep while you're there

It reuses Howdy's settings: the camera (`device_path`), match strictness (`certainty`), and dlib models.

## Install

```bash
ln -s "$PWD/presence-guard" ~/.local/bin/presence-guard
systemctl --user link "$PWD/presence-guard.service"
systemctl --user enable --now presence-guard
```

## Usage

```bash
presence-guard check   # one look: prints owner / stranger / nobody
```

- Idle time before the check: the `900` (seconds) in `presence-guard.service`
- Recheck interval and look duration: constants at the top of `presence-guard`

Stop it with `systemctl --user disable --now presence-guard`.

## Notes

- If the camera is busy (e.g. Howdy at the lock screen), the check counts as "nobody" and the screen locks.
- Your face model stays in `/etc/howdy/models/` and is never copied into this repo.
