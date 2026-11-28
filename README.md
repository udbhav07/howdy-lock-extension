# howdy-lock-extension

`presence-guard` adds two things to KDE Plasma with [Howdy](https://github.com/boltgolt/howdy):

1. **No auto-lock while you're at the screen.** Just before KDE's idle lock fires, it checks the IR camera. If it sees you, the lock timer restarts. If it sees someone else or nobody, KDE locks as usual. In Settings you can turn this off, or keep the screen unlocked for anyone in front of the camera.
2. **Photos of wrong passwords.** A wrong password on the lock or login screen takes 5 photos. When you unlock, a notification shows them.

## Install

You need Howdy working with your face added (`sudo howdy add`), on KDE Plasma 6 Wayland (tested on Fedora 44).

```bash
git clone https://github.com/udbhav07/howdy-lock-extension.git
cd howdy-lock-extension
./install.sh              # installs missing packages, the app and both services (asks for sudo)
./install.sh --user-only  # skip the login-screen watcher
```

Then open **Presence Guard → Settings** and pick your camera. Photos stay off until you do.

Run `./install.sh` again after `git pull`.

## The app

Open **Presence Guard** from the app menu, or run `presence-guard ui`.

- **Wrong passwords:** every attempt with its time and photos. Delete removes one. An attempt made within 20 s of your own unlock is tagged "Probably you".
- **Status:** shows which services are running and lists the cameras, with a "Check camera now" button.
- **Settings:** no auto-lock on/off, and whether it holds for you only or anyone present; camera, photos on/off, how many days to keep attempts (default 30, 0 = forever).

Photos are stored in `~/.local/share/presence-guard/` and only your account can read them.

## Commands

```bash
presence-guard check   # one look: owner / stranger / nobody / busy
presence-guard photo   # test the chosen camera
presence-guard ui      # open the app
```

## Face or password, whichever is first

By default the password field waits for Howdy to give up. To run both at once, move Howdy to `kde-fingerprint`:

```bash
sudo sed -i '/pam_howdy.so/d' /etc/pam.d/kde
sudo sed -i '1i auth        sufficient    pam_howdy.so' /etc/pam.d/kde-fingerprint
```

## Limits

- Only USB (UVC) cameras work. Intel IPU6/IPU7 built-in cameras may not.
- An empty password counts as a wrong one.
- If `pam_faillock` locks the account, later attempts aren't photographed.
- While any app holds a camera open, auto-lock is skipped. Meta+L still locks.

## Uninstall

```bash
systemctl --user disable --now presence-guard
sudo systemctl disable --now "presence-guard-sddm@$USER"
sudo rm -r /usr/local/lib/presence-guard /etc/systemd/system/presence-guard-sddm@.service
rm ~/.local/bin/presence-guard ~/.local/share/applications/presence-guard.desktop
rm -r ~/.local/share/presence-guard ~/.config/presence-guard ~/.local/state/presence-guard  # photos and settings
```

Your Howdy face model stays in `/etc/howdy/models/` and is never copied into this repo.
