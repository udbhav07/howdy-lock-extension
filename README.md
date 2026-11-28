# howdy-lock-extension

`presence-guard` adds three things to KDE Plasma with [Howdy](https://github.com/boltgolt/howdy):

1. **No auto-lock while you're at the screen.** Just before KDE's idle lock fires, it checks the IR camera. If you're there, the lock timer restarts. If not, KDE locks as usual.
2. **Photos of wrong passwords.** A wrong password on the lock or login screen takes 5 photos. When you unlock, a notification shows them.
3. **Face or password, whichever is first.** The lock screen no longer makes you wait for the face check before you can type.

## Install

You need Howdy working with your face added (`sudo howdy add`), on KDE Plasma 6 Wayland (tested on Fedora 44).

```bash
git clone https://github.com/udbhav07/howdy-lock-extension.git
cd howdy-lock-extension
./install.sh
```

The installer asks for sudo once. It installs any missing packages, the app and its services, and sets up face-or-password unlock. Run it again after `git pull`.

Then open **Presence Guard → Settings** and pick your camera. Photos stay off until you do.

`./install.sh --user-only` skips the parts that change system files: the login-screen watcher and the face-or-password change.

## The app

Open **Presence Guard** from the app menu, or run `presence-guard ui`.

| Page | What's there |
|---|---|
| **Wrong passwords** | Every attempt with its time and photos. Delete removes one. Attempts within 20 s of your own unlock are tagged "Probably you". |
| **Status** | Which services are running, the cameras, and a "Check camera now" button. |
| **Settings** | **No auto-lock** on/off, and who keeps the screen unlocked: only you, or anyone in front of the camera. **Wrong-password photos** on/off and which camera takes them. How many days to keep attempts (default 30, 0 = forever). |

Settings take effect immediately. Photos are stored in `~/.local/share/presence-guard/`, readable only by your account.

## Commands

```bash
presence-guard check   # one look: owner / stranger / nobody / busy
presence-guard photo   # test the chosen camera
presence-guard ui      # open the app
```

## Limits

- Only USB (UVC) cameras work. Intel IPU6/IPU7 built-in cameras may not.
- An empty password counts as a wrong one.
- If `pam_faillock` locks the account, later attempts aren't photographed.
- While any app holds a camera open, auto-lock is skipped. Meta+L still locks.

## Uninstall

```bash
./uninstall.sh           # removes everything; asks before deleting your photos and settings
./uninstall.sh --purge   # same, deletes photos and settings without asking
```

It also puts Howdy back in front of the password, undoing face-or-password.

Your Howdy face model stays in `/etc/howdy/models/` and is never copied into this repo.
