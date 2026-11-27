# Presence Guard app: wrong-password photos UI

## Context
`presence-guard` (one script + a systemd user service) now takes 5 RGB photos on each wrong lock-screen password and opens them in Gwenview at the next unlock (uncommitted). The user wants a local desktop app instead: a menu with pages, a toggle for the feature, a stored history of every attempt (photos + timestamp), and on unlock the app opens showing only the new attempts. Pages chosen: **Wrong passwords**, **Status**, **Settings**. Delete per attempt + auto-clean after N days. It must be easy to extend with more pages later.

Toolkit: **PySide6 6.11** (already installed, native KDE look, no new dependency).

## Step 0: commit the current work
Commit the existing uncommitted photo feature (`presence-guard`, `README.md`) on its own, so the UI change is a separate commit.

## Layout (new files)
```
presence-guard            entry script: daemon + CLI (existing), adds `ui` mode
pg/__init__.py            empty
pg/store.py               settings + attempt storage (shared by daemon and UI)
pg/system.py              kde_lock_seconds() moved here, + service_active()
pg/ui.py                  Qt app: menu + pages
presence-guard.desktop    app-menu entry (Exec=presence-guard ui)
test_store.py             unittest for pg/store.py
```
`presence-guard` finds `pg/` via `sys.path.insert(0, dirname(realpath(argv[0])))` (it's symlinked into ~/.local/bin). The Qt import happens only in `ui` mode, so the daemon stays light.

## pg/store.py (one place that knows paths and formats)
- `PHOTO_DIR = ~/Pictures/failed-unlocks`. One folder per attempt: `<YYYY-MM-DD_HH-MM-SS>/1.jpg … 5.jpg`. The folder name is the timestamp.
- Photos are written to `<ts>.partial/` and then renamed, so the UI never shows a half-written attempt.
- `settings()` / `save_settings(d)`: `~/.config/presence-guard/settings.json`, defaults `{"wrong_password_photos": true, "keep_days": 30}` (0 = keep forever). Read fresh every time, so the daemon picks up a toggle change without a restart.
- `last_seen()` / `mark_seen(ts)`: `~/.local/state/presence-guard/last_seen`. It's a separate file from settings because the daemon and the UI write different files, so neither can overwrite the other's changes.
- `attempts(newer_than=None)`: newest first, list of `(datetime, folder, [jpg paths])`. Skips `.partial` and any names that don't parse.
- `new_attempt_dir()`, `finish_attempt(partial)`, `delete_attempt(folder)` (shutil.rmtree, only inside PHOTO_DIR), `prune()` (deletes attempts older than keep_days).
- One-time migration: the existing `unseen/` folder gets renamed to its mtime timestamp. The old dated folder already fits the new layout (any jpgs inside are shown).

## presence-guard (daemon changes)
- `take_photos(folder)` writes `1.jpg…5.jpg` into `store.new_attempt_dir()`, then `finish_attempt`. The `photo` CLI keeps working.
- In `watch_failed_unlocks`, take photos only if `store.settings()["wrong_password_photos"]`.
- Replace `show_photos()` with `on_unlock()`: `since = store.last_seen(); store.mark_seen(now); store.prune()`. If `store.attempts(newer_than=since)` is not empty, launch the UI with `systemd-run --user --collect <me> ui --since <since>`. That puts the app in its own unit, so restarting the service doesn't kill the window. Gwenview is no longer used.
- `kde_lock_seconds` moves to `pg/system.py` (same code) and is imported back.
- New `ui [--since TS]` mode → `pg.ui.main(since)`.

## pg/ui.py
- `MainWindow`: left `QListWidget` menu + `QStackedWidget`. Pages come from one list, `PAGES = [("Wrong passwords", AttemptsPage), ("Status", StatusPage), ("Settings", SettingsPage)]`, so a new page is one class plus one line.
- **AttemptsPage**: scrollable cards, one per attempt. Each card has the timestamp ("Sat 28 Nov 2026, 01:39:48"), 5 thumbnails (click → full image via `QDesktopServices.openUrl`), and a Delete button with a confirmation dialog. With `--since`, the page shows only the new attempts under a header "N wrong-password attempts since your last unlock" and a **Show all** button. Otherwise it shows the full history. There's an empty-state message, and a `QFileSystemWatcher` on PHOTO_DIR refreshes the list live.
- **SettingsPage**: a "Take photos on wrong password" checkbox and a "Delete attempts older than [N] days (0 = never)" spin box. Changes save immediately through `store.save_settings`.
- **StatusPage**: the service state (`systemctl --user is-active presence-guard`), the KDE auto-lock time (`system.kde_lock_seconds`), the IR and RGB camera paths, and a **Check camera now** button that runs `presence-guard check` through `QProcess` (async, so the window stays responsive) and shows owner/stranger/nobody/busy.
- shortcut: no single-instance guard. If the app is already open at unlock, a second window opens. Upgrade to `QLocalServer` if that gets annoying.

## Install / docs
- `presence-guard.desktop` (Name=Presence Guard, Icon=camera-photo, Exec=presence-guard ui). Install with `ln -s "$PWD/presence-guard.desktop" ~/.local/share/applications/`.
- README: add an App section (pages, toggle, auto-clean, where data lives), the install line, and `presence-guard ui`. Replace the Gwenview sentence.

## Verification
1. `python3 -m unittest test_store` covers settings defaults/round trip, attempt order, skipping `.partial`/bad names, `newer_than`, and `prune` with keep_days 0 and N, all in a temp dir.
2. Run `presence-guard photo` and confirm a new `<ts>/1..5.jpg` folder exists.
3. Run `presence-guard ui`: the window opens and all three pages work. Toggle the setting off and check settings.json, then run `presence-guard ui --since <old ts>` and confirm only the new attempts show. Screenshot with `spectacle -b -n -o` to check the layout.
4. `systemctl --user restart presence-guard` and confirm the status is active with the journal watcher present.
5. Real flow (needs the user): Meta+L, wrong password, then correct password. The app should open showing only that attempt. Then toggle off, repeat, and confirm no photos are taken.

---

# Eng review record (/plan-eng-review)

Target: `docs/plan-docs/wrong-password-photos-app.md` (the plan above, kept unchanged as the original proposal).
Source of truth for the problem and the approved approach: `docs/designs/wrong-password-photos-app.md` (APPROVED by /office-hours on 2026-11-28, approach C, notification-first).

## Scope record
feature answers: none proposed (every page and behavior was requested by the owner); structure: A (Original arrangement, D4); accepted scope: the approved design doc's approach C plus the 8 minor reviewer items (R2-1..R2-8, approved with the design doc), in 9 files: presence-guard, README.md, pg/__init__.py, pg/store.py, pg/system.py, pg/ui.py, presence-guard.desktop, install.sh, test_store.py; pending remedies: S2, S3, S4.
Scope Challenge result: scope accepted as-is.

## Scope Challenge findings
1. S1 [CRITICAL] (confidence: 10/10) docs/plan-docs/wrong-password-photos-app.md:20-27: the plan still says "`PHOTO_DIR = ~/Pictures/failed-unlocks`", has no camera setting, no install.sh and has the daemon "launch the UI" at unlock. That contradicts the approved design (private storage, camera picker, install.sh, notification-first). Disposition: covered by an exact prior approval (design doc approved, "A) Approve", 2026-11-28); the working plan is the design doc. No question needed.
2. S2 [INFORMATIONAL] (confidence: 9/10) design "Camera list": "labeled with `/sys/class/video4linux/<node>/name`". Probe: all four nodes report the same name, `Integrated RGB Camera: Integrat` (video0..video3), so the picker labels would be identical.
3. S3 [INFORMATIONAL] (confidence: 8/10) design UI: "A `QFileSystemWatcher` refreshes the list live". The watcher sees attempts/ changes (new or deleted folders) but not `meta.json` edits inside an attempt (burst count, probably_you), and Qt docs say rapid changes may be coalesced.
4. S4 [INFORMATIONAL] (confidence: 7/10) design Flow: `notify-send -A open=Open`. Plasma makes the notification body clickable only with a `default` action (KDE bug 477560); without it, only the button opens the app.

## Decision ledger

### S1: rewrite the working plan to the approved design
Finding: 1, CRITICAL, 10/10, docs/plan-docs/wrong-password-photos-app.md:20-27, plan-eng-review
Plan baseline: approved design doc (docs/designs/wrong-password-photos-app.md), answer "A) Approve"
Runtime evidence: n/a (plan text)
State: approved
Actual answer: covered by the design doc approval
Accepted scope: implement the approved design, not the original plan text above
History: none

### S2: distinct camera labels in the picker
Finding: 2, INFORMATIONAL, 9/10, design "Camera list", plan-eng-review
Plan baseline: label = sysfs name + node (design doc)
Runtime evidence: `/sys/class/video4linux/video{0..3}/name` all read `Integrated RGB Camera: Integrat` (probe 2026-11-28)
Comparison grid:
| Choice | Current | A | B |
|---|---|---|---|
| S2 label | sysfs name + node | sysfs name + node + pixel format of its first format (e.g. "MJPG" vs "GREY") | unchanged |
| S3, S4 | pending | pending | pending |
Question D5:
D5 — Make camera names distinguishable in the Settings picker?
Project/branch/task: howdy-lock-extension on main, wrong-password photos app.
ELI10: Linux gives all four of your camera nodes the same name, "Integrated RGB Camera". The picker would show near-identical rows. Adding each node's image format ("color MJPG" vs "grey") lets anyone tell the color camera from the IR one at a glance, which matters on other people's laptops.
Stakes if we pick wrong: a user picks the IR camera and gets grey, ghostly intruder photos without knowing why.
Recommendation: A because one extra word per row prevents the wrong-camera mistake, at ~10 lines (human: ~30 min / CC: ~2 min).
Completeness: A=10/10, B=7/10
Pros / cons:
A) Add image format (recommended)
  ✅ Rows read e.g. "Integrated RGB Camera · color (MJPG) · /dev/video0", so the color one is obvious
  ✅ Read with v4l2's VIDIOC_ENUM_FMT through OpenCV or `v4l2-ctl`, no new dependency
  ❌ About 10 more lines, and a probe of each camera when the Settings page opens
B) Keep name + node
  ✅ No extra code; Howdy's IR camera is already hidden, so most laptops show one row
  ✅ Nothing to probe when Settings opens
  ❌ Laptops with two non-Howdy cameras show identical names
Net: ten lines versus a confusing picker on some laptops.
Header: D5 Cam label
Options:
A) Add image format (recommended)
Rows show the camera name, "color (MJPG)" or "grey (GREY)", and the node; ~10 lines.
B) Keep name + node
No change from the design; rows may look identical on some laptops.

State: approved
Actual answer: A) Add image format (recommended), D5
Accepted scope: camera picker rows show sysfs name, "color (<fourcc>)" or "grey (GREY)", and the node; ~10 lines in pg/system.list_cameras
History: none

### S3: keep the attempts list fresh when meta.json changes
Finding: 3, INFORMATIONAL, 8/10, design UI "A `QFileSystemWatcher` refreshes the list live", plan-eng-review
Plan baseline: QFileSystemWatcher on attempts/ only (design doc)
Runtime evidence: Qt docs: directoryChanged covers the watched directory's own entries; rapid changes may be coalesced. Burst updates rewrite <attempt>/meta.json one level down.
Comparison grid:
| Choice | Current | A | B |
|---|---|---|---|
| S2 label | approved (D5 A) | approved (D5 A) | approved (D5 A) |
| S3 refresh | watcher on attempts/ only | watcher on attempts/ + rescan on window focus | unchanged |
| S4 | pending | pending | pending |
Question D6:
D6 — Also refresh the list when the window gets focus?
Project/branch/task: howdy-lock-extension on main, wrong-password photos app.
ELI10: The app watches the attempts folder, so new or deleted attempts appear instantly. But when someone keeps typing wrong passwords, the daemon only updates a small file inside an existing attempt (the failure count), and the watcher doesn't see that. Rescanning whenever you switch back to the window catches it.
Stakes if we pick wrong: a card says "1 failure" when there were 4, until you reopen the app.
Recommendation: A because it is about 3 lines and makes the list always right when you look at it (human: ~15 min / CC: ~1 min).
Completeness: A=10/10, B=7/10
Pros / cons:
A) Rescan on focus (recommended)
  ✅ Counts and "Probably you" tags are current whenever you look at the window
  ✅ About 3 lines (a changeEvent/activation hook calling the same refresh)
  ❌ A rescan of a few dozen folders each time the window is focused
B) Watcher only
  ✅ No extra code beyond the design
  ✅ New and deleted attempts still appear instantly
  ❌ Failure counts on an open window can be stale
Net: three lines versus occasionally stale counts.
Header: D6 Refresh
Options:
A) Rescan on focus (recommended)
Keep the folder watcher and also rescan when the window is activated; ~3 lines.
B) Watcher only
Keep the design as is; counts inside an open card can be stale.

State: approved
Actual answer: A) Rescan on focus (recommended), D6
Accepted scope: keep the QFileSystemWatcher on attempts/ and also rescan when the main window is activated; ~3 lines in pg/ui.py
History: none

### S4: make the whole notification clickable
Finding: 4, INFORMATIONAL, 7/10, design Flow `notify-send -A open=Open`, plan-eng-review
Plan baseline: `notify-send -A open=Open` (design doc)
Runtime evidence: notify-send 0.8.8 `--help`: "-A, --action=[NAME=]Text... The name of the action is output to stdout". KDE bug 477560: a notification body is clickable only when it has a `default` action. Not yet tried live on this Plasma.
Comparison grid:
| Choice | Current | A | B |
|---|---|---|---|
| S2, S3 | approved (D5 A, D6 A) | approved | approved |
| S4 action | `-A open=Open` (button only) | `-A default=Open` (body click and button both open) | unchanged |
Question D7:
D7 — Let a click anywhere on the notification open the app?
Project/branch/task: howdy-lock-extension on main, wrong-password photos app.
ELI10: Right now only the small "Open" button opens the app. Most people click the notification itself, the photo or the text. Naming the action "default" tells Plasma that clicking the body does the same as the button.
Stakes if we pick wrong: you click the notification, it just closes, and the photos never open.
Recommendation: A because it is a one-word change and matches how people use notifications (human: ~5 min / CC: ~1 min).
Completeness: A=10/10, B=7/10
Pros / cons:
A) Use the default action (recommended)
  ✅ Clicking the photo, the text or the Open button all open the app
  ✅ One-word change: `-A default=Open`, and the daemon checks for "default" on stdout
  ❌ Plasma may also show the default action as a button in notification history
B) Button only
  ✅ Exactly the design as written, nothing to change
  ✅ A stray click on the notification only dismisses it
  ❌ Clicking the notification body closes it without opening the photos
Net: one word versus a notification that ignores the most natural click.
Header: D7 Notify click
Options:
A) Use the default action (recommended)
`notify-send -A default=Open`; body click or button opens the app.
B) Button only
Keep `-A open=Open`; only the button opens the app.

State: approved
Actual answer: A) Use the default action (recommended), D7
Accepted scope: notify-send uses `-A default=Open`; the daemon opens the UI when stdout reads "default"
History: none

## Review sections

### 1. Architecture
Boundaries: two processes share data only through files under XDG dirs. The daemon (`presence-guard` + `pg.store` + `pg.system`) writes attempts; the UI process (`pg.ui`) reads them, writes settings, and deletes attempts. Qt is never imported by the daemon.

```
journalctl -f ──► journal thread ──┐
                                   ├─► queue ─► worker thread ─► attempts/<ts>/ (photos, meta.json), last_seen
gdbus monitor ──► main thread ─────┘     (2 s grace on unlock)    └─► notify-send -A default=Open ─► systemd-run … ui --since
swayidle ─► `presence-guard idle` (separate process, unchanged; never touches the camera while locked)
UI process: settings.json (writes) · attempts/ (reads, deletes, prune) · QFileSystemWatcher + rescan on focus
```

Design-twice (new module `pg/`). Shape 1 (chosen): one folder per attempt + `meta.json`. Shape 2: one SQLite file (`attempts(id, first_failure, last_failure, failures, photos, error, probably_you)`) with photos as files. Every query here is "list by time, newer than X, older than N days": all by name/time, and each attempt is read and written whole, so folders hide the same behavior behind a smaller surface (os.listdir + json). SQLite would add locking between two processes for no query benefit. Pick: shape 1.
Red flags: no shallow module (`store` hides paths, atomic writes and partial renames behind attempt functions); no information leakage (paths live only in `store`); split ownership is explicit (worker writes attempts and last_seen, UI writes settings, both may delete via `store.delete_attempt`/`prune`); one list of pages (`PAGES`); one capture function used by attempts and by `photo` (target dir is a parameter).
Production failure per new path: journalctl dies → service restarts (os._exit). Camera busy or unplugged → attempt with photos 0 and an error, shown on the card and Status page. notify-send missing or fails → logged; the attempt is still in the app's history. systemd-run fails → logged; the app opens from the app menu.
Findings: No issues found.

### 2. Code quality
Organization follows the design. Error handling and edge cases are covered by the approved design and R2-1..R2-8 (atomic writes, defaults on unreadable files, partial renames, burst ends, delete via rename, UTC names, 1..k numbering). Existing `look()`/`idle`/`check` code is moved only for imports (`kde_lock_seconds` → `pg.system`).
Findings: No issues found.

### 3. Tests
Framework: none present; plan uses stdlib `unittest` (no new dependency), `python3 -m unittest test_store`.

```
CODE PATHS                                              USER FLOWS
[+] pg/store.py                                         [+] Wrong password while locked
  ├── settings() defaults / unreadable → defaults         ├── [GAP→LIVE] journal line → worker → 5 photos (owner run)
  │   [★★★ PLANNED test_store]                            └── [GAP→LIVE] 3 failures < 10 s → 1 attempt, failures 3
  ├── atomic write (temp + os.replace) [★★ PLANNED]     [+] Unlock
  ├── new_attempt / finish (.partial rename) [★★★]        ├── [GAP→LIVE] notification with thumbnail, click → app --since
  ├── burst decision (10 s / 2 min / unlock) [★★★]        └── [GAP→LIVE] wrong pw then right one < 1 s → announced
  ├── new_since(last_seen), empty last_seen [★★★]       [+] App
  ├── probably_you (≥ u − 20 s) [★★★]                     ├── [GAP→LIVE] Settings: pick camera, toggle, keep-days persist
  ├── prune (keep_days 0/N, skips .partial, open burst,   ├── [GAP→LIVE] Delete one attempt
  │   folder-name fallback) [★★★]                         └── [GAP→LIVE] empty state, 0-photo card
  └── delete_attempt (rename then rmtree, outside dir   [+] Regression (approved contract: check/idle unchanged)
      rejected) [★★★]                                     └── [LIVE] `presence-guard check` prints owner/stranger/nobody/busy
[+] pg/system.py list_cameras (dedupe, Howdy excluded by realpath, format label) [GAP→LIVE probe on this laptop]
[+] presence-guard worker: glue only; decisions live in store (tested)
[+] pg/ui.py: no unit tests (Qt glue); verified by launching and screenshots
COVERAGE: store decision paths 9/9 planned unit tests | daemon/UI flows: live checks (E2E through the real lock screen needs the owner)
```
Regression rule: the approved design's success criterion "existing `check` / `idle` behavior is unchanged" is the contract; proof = run `presence-guard check` live after the refactor, and `idle` code is untouched apart from the import.
Findings: No issues found (all gaps are either planned unit tests or live checks already in the design's Success Criteria).

### 4. Performance
P1 [INFORMATIONAL] (confidence: 6/10) design UI "5 thumbnails" per card: decoding full 640×480 JPEGs for every card costs ~5 decodes per attempt; with keep_days 30 and a busy laptop that is a few hundred decodes on open. Disposition: implementation detail, no behavior change: decode thumbnails with `QImageReader.setScaledSize` (Qt decodes JPEGs at reduced size). Recorded, no question needed.
Capture blocks the worker 3-6 s by design (events queue behind it; nothing user-facing waits). `list_cameras` reads formats via a VIDIOC_ENUM_FMT ioctl (no streaming, LED stays off), only when Settings/Status opens.

## Outside voice (native fallback)
Codex not installed (CODEX_MODE: not_installed); native Plan subagent completed within the 5-minute timer. VERDICT: FINDINGS, 10 findings (O1..O10, same numbering as its report).
- O2 factual correction: journal line verified (this boot's journal has `pam_unix(kde:auth): authentication failure` from `_COMM=kscreenlocker_g`); live capture already ran (dated folder in ~/Pictures/failed-unlocks); IR + RGB opened together gave 10/10 frames each (probe 2026-11-28). No change.
- O10 factual: no pam_faillock in /etc/pam.d/password-auth or system-auth. No change.
- O6, O7, O8, O9: necessary implementation of approved behavior (burst/announce rules use `t < u`; collision suffix on attempt names; ENOENT on a delete rename = success; store resolves XDG/HOME at call time so tests use a temp dir). Carried as common work, no question.

### O1: announce pending attempts when the service starts
Finding: O1, High (outside voice), confidence 8/10, design Flow "ScreenSaver ActiveChanged(false) (unlock)", plan-eng-review outside voice
Plan baseline: announce only on ActiveChanged(false)
Runtime evidence: a login through SDDM after a reboot does not emit ActiveChanged(false) (no lock session to end); unverified live
Comparison grid:
| Choice | Current | A | B | C | D |
|---|---|---|---|---|---|
| O1 startup announce | none | at service start, if the screen is not locked, queue ("unlock", now) | unchanged | probe: reboot test first | defer |
| O3, O4, O5 | pending | pending | pending | pending | pending |
Question D8:
D8 — Show missed attempts when you log back in after a reboot?
Project/branch/task: howdy-lock-extension on main, wrong-password photos app.
ELI10: The app only announces attempts when the screen unlocks. If someone fails your password and then holds the power button, you log in fresh after the reboot, and there is no "unlock" signal, so you never get the notification. Running the same announce step once when the service starts fixes that.
Stakes if we pick wrong: an intruder who reboots the laptop stays hidden until some later lock/unlock.
Recommendation: A because it is one line that reuses the existing announce logic, and reboot-after-failing is a common move (human: ~15 min / CC: ~1 min).
Note: options differ in kind, not coverage — no completeness score.
Pros / cons:
A) Apply this change (recommended)
  ✅ Attempts made before a reboot or logout are announced at your next login
  ✅ One line in watch(); last_seen already prevents announcing anything twice
  ❌ A service restart while unlocked also triggers it (harmless: nothing new, nothing shown)
B) Keep the current value
  ✅ No change; announcements stay tied to the unlock moment only
  ✅ Nothing runs at login
  ❌ Attempts followed by a reboot stay silent until a later unlock
C) Investigate before choosing
  ✅ Confirm by a real reboot test whether login emits any signal
  ✅ Bounded: one reboot after the build; O1 stays pending meanwhile
  ❌ Costs you a reboot and delays the decision
D) Defer this proposed change only
  ✅ Keeps v1 exactly as designed
  ✅ Can be added later without touching other parts
  ❌ The reboot gap ships in v1
Net: one line versus a known way for intruders to hide.
Header: D8 Reboot
Options:
A) Apply this change (recommended)
At service start, if the screen isn't locked, run the unlock/announce step once.
B) Keep the current value
Announce only on unlock.
C) Investigate before choosing
Test a real reboot first; O1 stays pending.
D) Defer this proposed change only
Leave it out of v1; O1 stays unresolved.

State: approved
Actual answer: B) Keep the current value, D8
Accepted scope: none (announce only on unlock; attempts before a reboot are announced at a later unlock)
History: none

### O4: what happens to failures when no camera is chosen
Finding: O4, Medium (outside voice), confidence 9/10, design Flow "not wrong_password_photos or camera null → ignore", plan-eng-review outside voice
Plan baseline: camera null or toggle off → the failure is ignored entirely (premise 2)
Runtime evidence: after the upgrade, settings.camera starts as null on this laptop too, so photos stop until Settings is opened (static read of the design)
Comparison grid:
| Choice | Current | A | B | C | D |
|---|---|---|---|---|---|
| O4 no-camera failures | ignored | toggle on + camera null → record a photo-less attempt (timestamp, failures, error "no camera chosen"); toggle off → still ignored | unchanged | investigate | defer |
| install/README prompt to pick a camera | none | install.sh ends with "open Presence Guard → Settings and pick your camera" | same line (docs only) | pending | pending |
| O3, O5 | pending | pending | pending | pending | pending |
Question D9:
D9 — Keep a timestamp of wrong passwords even before a camera is chosen?
Project/branch/task: howdy-lock-extension on main, wrong-password photos app.
ELI10: Photos stay off until you pick a camera in Settings, as you decided. Right now that also means a wrong password leaves no trace at all, not even the time. Option A still records the attempt (time and number of tries) with "no camera chosen" instead of photos, as long as the feature toggle is on. Both options add a line at the end of install.sh telling you to pick your camera.
Stakes if we pick wrong: right after upgrading, someone could try your laptop and you'd have no record of it.
Recommendation: A because it keeps your rule (no photos without a chosen camera) while still keeping the history you asked for; ~5 lines (human: ~20 min / CC: ~2 min).
Note: options differ in kind, not coverage — no completeness score.
Pros / cons:
A) Apply this change (recommended)
  ✅ Every wrong password is in the history and announced at unlock, even before setup
  ✅ The card says "No photos: no camera chosen", which reminds you to finish setup
  ❌ Turning the toggle off is now the only way to stop recording failures
B) Keep the current value
  ✅ Exactly premise 2 as agreed: nothing happens until a camera is chosen
  ✅ No new code path in the worker
  ❌ Failures before camera setup leave no record at all
C) Investigate before choosing
  ✅ Look at how long the no-camera window really lasts after install
  ✅ O4 stays pending, nothing else changes
  ❌ Delays a small decision with little to learn
D) Defer this proposed change only
  ✅ v1 ships as designed; can add it later
  ✅ install.sh reminder still possible separately
  ❌ The silent window ships in v1
Net: five lines versus a gap in the history right after install.
Header: D9 No camera
Options:
A) Apply this change (recommended)
Toggle on + no camera → record time-only attempts; install.sh reminds you to pick a camera.
B) Keep the current value
No camera → nothing recorded; install.sh reminds you to pick a camera.
C) Investigate before choosing
O4 stays pending.
D) Defer this proposed change only
Leave it out of v1; O4 stays unresolved.

State: approved
Actual answer: B) Keep the current value, D9
Accepted scope: no camera → failures ignored (premise 2 unchanged); install.sh ends with a reminder to open Presence Guard → Settings and pick the camera
History: none

### O5 (reopens S2/D5): camera label detail
Finding: O5, Medium (outside voice), confidence 7/10, eng review S2 accepted scope "pixel format … ~10 lines", plan-eng-review outside voice
Plan baseline: D5 A) Add image format: rows show name, "color (<fourcc>)" or "grey (GREY)", node; ~10 lines
Runtime evidence: OpenCV has no ENUM_FMT API; a raw fcntl ioctl with packed v4l2_fmtdesc is ~25 lines with its own error handling (estimated). This laptop's IR node lists only GREY (v4l2-ctl probe), but other IR cameras may also list YUYV, so "grey" is not a reliable IR signal there. Howdy's camera is already hidden by realpath (R2-1).
Reason for reopening: concrete new evidence on cost and reliability.
Comparison grid:
| Choice | Current | A | B | C | D |
|---|---|---|---|---|---|
| S2/O5 label | name + format + node (D5 A) | name + by-path interface (e.g. "usb 6:1.0") + node, no format probe | keep D5 A (format via ~25-line ioctl) | investigate | defer |
| O3 | pending | pending | pending | pending | pending |
Question D10:
D10 — Simplify the camera labels after all?
Project/branch/task: howdy-lock-extension on main, wrong-password photos app.
ELI10: You approved showing each camera's image format (color vs grey) in the picker. The outside reviewer found it costs more than I said (~25 lines of low-level code, not 10), and the "grey" hint isn't reliable on every laptop. A cheaper way to tell nodes apart is the USB interface from the device path ("usb 6:1.0" vs "6:1.2"), plus the node. Howdy's IR camera is already hidden either way.
Stakes if we pick wrong: A gives slightly less descriptive labels; B adds fragile low-level code for a hint that can mislead.
Recommendation: A because it keeps rows distinct with ~3 lines and no device probing (human: ~10 min / CC: ~1 min).
Note: options differ in kind, not coverage — no completeness score.
Pros / cons:
A) Apply this change (recommended)
  ✅ Rows stay distinct ("Integrated RGB Camera · usb 6:1.0 · /dev/video0") with about 3 lines
  ✅ No ioctl, no opening cameras when Settings loads
  ❌ Labels don't say "color" or "grey", so the user relies on Howdy's camera being hidden
B) Keep the current value
  ✅ Labels say color vs grey, the clearest hint where it is accurate
  ✅ Already approved in D5
  ❌ ~25 lines of struct-packing ioctl code, and "grey" can be wrong on other IR cameras
C) Investigate before choosing
  ✅ Prototype the ioctl and check a second laptop's formats
  ✅ S2/O5 stays pending; nothing else changes
  ❌ Needs a second machine you may not have
D) Defer this proposed change only
  ✅ Keep D5 A as approved for now
  ✅ Revisit after real users report confusion
  ❌ Leaves this row unresolved
Net: three plain lines versus a nicer hint that costs fragile code.
Header: D10 Labels
Options:
A) Apply this change (recommended)
Label = name + USB interface + node; drop the format probe.
B) Keep the current value
Keep D5 A: name + color/grey format + node (~25 lines).
C) Investigate before choosing
S2/O5 stays pending.
D) Defer this proposed change only
Leave D5 A in place; this row stays unresolved.

State: approved
Actual answer: B) Keep the current value, D10
Accepted scope: unchanged from D5 A: labels show name, "color (<fourcc>)" or "grey (GREY)", and node, via a VIDIOC_ENUM_FMT ioctl (~25 lines with error handling; a node that can't be queried is labeled without a format)
History: S2 approved D5 A (name + format + node) earlier in this review; reopened by O5 with cost/reliability evidence; user kept D5 A.

### O3: document cameras OpenCV can't read (Intel IPU6/IPU7)
Finding: O3, Medium (outside voice), confidence 6/10 (general knowledge, not verified on this machine), design "Constraints"/README, plan-eng-review outside voice
Plan baseline: no known-limits note about camera types
Runtime evidence: unverified here (this laptop's RGB camera is USB UVC and works); outside reviewer cites IPU6/IPU7 MIPI cameras needing libcamera/PipeWire
Comparison grid:
| Choice | Current | A | B | C | D |
|---|---|---|---|---|---|
| O3 known-limits note | none | README "Limits" lists: USB (UVC) cameras only, IPU6/IPU7 MIPI cameras unsupported; install.sh warns when list_cameras finds no usable camera | unchanged | investigate | defer |
Question D11:
D11 — Warn about laptop cameras the app can't use?
Project/branch/task: howdy-lock-extension on main, wrong-password photos app.
ELI10: Your camera is a normal USB webcam, which works. Many newer Intel laptops use a different kind of built-in camera (IPU6/IPU7) that this app's camera library can't read. On those, every attempt would have zero photos. A short "Limits" note in the README, plus a warning from install.sh when no usable camera is found, tells other people upfront.
Stakes if we pick wrong: open-source users install it, get empty photo cards, and file confused bug reports.
Recommendation: A because it is documentation plus a few lines in install.sh, and it saves every affected user from debugging (human: ~15 min / CC: ~2 min).
Note: options differ in kind, not coverage — no completeness score.
Pros / cons:
A) Apply this change (recommended)
  ✅ Users on unsupported laptops learn it at install time, not after an intrusion
  ✅ README states plainly which cameras work (USB/UVC)
  ❌ The IPU6 claim isn't verified on hardware here; wording must say "may not work"
B) Keep the current value
  ✅ No unverified claims in the docs
  ✅ Nothing extra in install.sh
  ❌ Affected users discover the limit only through empty attempts
C) Investigate before choosing
  ✅ Research IPU6 + OpenCV support before writing anything
  ✅ O3 stays pending; nothing else changes
  ❌ Needs hardware or research that won't change much for v1
D) Defer this proposed change only
  ✅ Ship v1, add notes when users report it
  ✅ Keeps the README short for now
  ❌ First users hit the problem blind
Net: a short warning versus surprised users.
Header: D11 Limits
Options:
A) Apply this change (recommended)
README "Limits" note + install.sh warns when no usable camera is found.
B) Keep the current value
No note, no warning.
C) Investigate before choosing
O3 stays pending.
D) Defer this proposed change only
Leave it out of v1; O3 stays unresolved.

State: approved
Actual answer: A) Apply this change (recommended), D11
Accepted scope: README "Limits" section (USB/UVC cameras; Intel IPU6/IPU7 MIPI cameras may not work; KDE lock screen only, not SDDM) + install.sh warns when list_cameras() finds no usable camera
History: none

### TD1: single-instance guard
State: approved
Actual answer: A) Add to TODOS.md (recommended), D12
Accepted scope: TODOS.md entry (no code in this change)

### TD2: SDDM login-screen coverage
State: approved
Actual answer: C) Build it now, D13
Accepted scope (build in this change):
- `presence-guard sddm-watch <owner>` mode, run by a new system unit `presence-guard-sddm.service` (root).
- Detection: `journalctl -f -n0 -o short-unix SYSLOG_FACILITY=10`, lines containing `pam_unix(sddm:auth): authentication failure` → the same worker (failure events only; bursts end by the 10 s / 2 min rules since there are no unlocks). Facility filter verified on this boot's lock-screen failures (SYSLOG_FACILITY=10); no SDDM failure exists in the journal yet, so the SDDM text match is verified live after install.
- Writes into the owner's attempts folder: the process sets HOME to the owner's home (store resolves paths at call time, O9), reads the owner's settings, captures as root (no session means no camera ACL for the owner), then chowns the attempt to the owner (0700 dirs).
- Security: the root unit runs a root-owned copy installed by install.sh under /usr/local/lib/presence-guard/, never the user-writable checkout.
- Announcement: SDDM attempts appear in history and are announced at the next unlock (D8 kept unlock-only announcing).
- install.sh installs/enables it with sudo; README documents it and its uninstall.
Files added: presence-guard-sddm.service.

Approval readiness: PASS. Checked: S1 (design doc approval), S2/O5 (D5 A, kept by D10 B), S3 (D6 A), S4 (D7 A), O1 (D8 B, no change), O4 (D9 B + install.sh reminder), O3 (D11 A), TD1 (D12 A), TD2 (D13 C), R2-1..R2-8 (design doc approval "A) Approve"), O6..O9 (common work of approved behavior), regression contract (design Success Criteria: `check`/`idle` unchanged).

## NOT in scope
- Announcing at service start / login (D8 B): attempts before a reboot are announced at the next unlock.
- Recording failures while no camera is chosen (D9 B): premise 2 stays strict.
- Single-instance window (D12): tracked in TODOS.md.
- Distro packaging and CI: install.sh is the v1 channel (design Distribution Plan).
- Migrating old test photos from ~/Pictures/failed-unlocks: README says to delete them.

## What already exists
- `presence-guard` (reused): `look()`, `idle`/`check` modes, `screensaver()`, `stop_howdy()`, the gdbus unlock monitor, swayidle wiring. The uncommitted journal watcher and `take_photos()` are reused and moved behind the worker/store.
- `kde_lock_seconds()` moves unchanged to `pg/system.py` (shared by the daemon and the Status page).
- Platform pieces reused instead of rebuilt: journald (`journalctl -f`), `notify-send` actions, `systemd-run`, Qt `QFileSystemWatcher`, OpenCV V4L2 capture.

## Failure modes
| Path | Realistic failure | Handling / test | User sees |
|---|---|---|---|
| journal thread | journalctl exits | os._exit(1) → systemd restart | nothing (brief gap) |
| worker capture | camera busy/unplugged | attempt with photos 0 + error (unit-tested meta; live check) | card "No photos: …", Status error |
| worker | corrupt settings/meta | defaults (unit-tested) | photos off until fixed in Settings |
| unlock announce | notify-send fails | logged | attempt still in app history |
| Open click | systemd-run fails | logged | app still opens from the menu |
| UI delete vs burst update | race | rename-then-remove, ENOENT = success (unit-tested) | card disappears |
| SDDM watcher | text match wrong on another distro | live verification after install; logged | no SDDM photos (README Limits) |
| SDDM watcher | chown fails | logged; attempt stays root-owned | app can't read it (visible as missing) |
No failure mode is silent, untested and unhandled at once: 0 critical gaps.

## Worktree parallelization strategy
Sequential implementation, no parallelization opportunity (one primary module, `pg/`, that every step depends on).

## Implementation Tasks
Synthesized from this review's findings. Each task derives from a specific finding above. Run with Claude Code or Codex; checkbox as you ship.

- [ ] **T1 (P1, human: ~2h / CC: ~10min)** — pg/store — store with atomic writes, lazy XDG paths, attempts, bursts, prune, delete, last_seen + unit tests
  - Surfaced by: design Data/Flow; R2-2, R2-3, R2-5, R2-7, R2-8; O6..O9
  - Files: pg/__init__.py, pg/store.py, test_store.py
  - Verify: `python3 -m unittest test_store`
- [ ] **T2 (P1, human: ~2h / CC: ~10min)** — daemon — worker queue, capture via store, unlock announce with `notify-send -A default=Open`, `photo` test mode, `ui` mode
  - Surfaced by: design Flow; S4/D7; R2-6
  - Files: presence-guard, pg/system.py
  - Verify: `presence-guard photo`; `presence-guard check`; service restart status
- [ ] **T3 (P1, human: ~3h / CC: ~15min)** — pg/ui — sidebar + 3 pages, watcher + rescan on focus, scaled thumbnails, camera picker with format labels
  - Surfaced by: design UI; S2/D5(D10); S3/D6; Performance P1
  - Files: pg/ui.py, pg/system.py
  - Verify: launch `presence-guard ui`, screenshot each page
- [ ] **T4 (P1, human: ~2h / CC: ~10min)** — SDDM — `sddm-watch` mode + root unit using a root-owned copy
  - Surfaced by: TD2/D13
  - Files: presence-guard, presence-guard-sddm.service
  - Verify: `systemd-analyze verify`; live wrong password at SDDM after install
- [ ] **T5 (P2, human: ~1h / CC: ~5min)** — install/docs — install.sh (deps, links, .desktop, units, camera reminder, no-camera warning), README Limits, TODOS.md
  - Surfaced by: premise 4; O4/D9; O3/D11; D12
  - Files: install.sh, presence-guard.desktop, README.md, TODOS.md
  - Verify: `bash -n install.sh`; run install.sh

## Unresolved decisions
None.

## Completion summary
- Step 0: Scope Challenge — scope accepted as-is
- Reality rows: 7/7 applicable rows emitted, 0 unverified premises (SDDM text match verified after install)
- Architecture Review: 0 issues found
- Code Quality Review: 0 issues found
- Test Review: diagram produced, 0 gaps identified (unit + live checks planned)
- Performance Review: 1 issue found (thumbnail decoding, recorded as implementation detail)
- NOT in scope: written
- What already exists: written
- TODOS.md updates: 2 items proposed to user (1 added, 1 built now)
- Failure modes: 0 critical gaps flagged
- Unresolved decisions: 0 in this review
- Outside voice: codex not installed; native Plan subagent completed (in-host), 10 findings
- Parallelization: 1 lane, 0 parallel / 1 sequential
- Lake Score: 4/4 (D5, D6, D7 picked the 10/10 option; D9 was kind-only, excluded) — scored answers: D5, D6, D7 = 3/3; N/A others

REALITY: premise-table pass 4 premises with receipts, unverified=0 docs/plan-docs/wrong-password-photos-app.md:253
REALITY: already-done pass git log shows no commits touching pg/ or the app since the request bc5c541
REALITY: surface-check pass journalctl/systemd-run/notify-send flags verified via --help and live probes docs/plan-docs/wrong-password-photos-app.md:162
REALITY: binding-decisions pass decision search empty; ledger D4..D13 binds this plan docs/plan-docs/wrong-password-photos-app.md:74
REALITY: numbers pass capture 30 warm-up frames presence-guard:32, 5×12 photo frames presence-guard:31, 90 frames = 3.0 s at 30 fps [measured: presence-guard:32-31], 6.0 s at 15 fps [estimated]
REALITY: deferred-asks pass no linked issue docs/designs/wrong-password-photos-app.md:9
REALITY: pr-count pass 1 PR, no .gstack/ship-policy.json docs/plan-docs/wrong-password-photos-app.md:64

## Suppressed findings
None.

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope & strategy | 0 | — | — |
| Outside Review | native Plan subagent (codex not installed) | Independent 2nd opinion | 1 | unavailable (outside); in-host completed | 10 findings |
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 1 | issues_open | 1 issues, 0 critical gaps |
| Design Review | `/plan-design-review` | UI/UX gaps | 0 | — | — |
| DX Review | `/plan-devex-review` | Developer experience gaps | 0 | — | — |

- **OUTSIDE COVERAGE:** codex: not installed, outside coverage unavailable; native Plan subagent (in-host) completed within the timer, 10 findings, all resolved (D8–D11, factual/common-work dispositions).
- **VERDICT:** Eng Review has 1 recorded performance issue (accepted as an implementation detail); all decisions resolved, ready to implement.

NO UNRESOLVED DECISIONS
