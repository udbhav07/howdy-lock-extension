"""Where presence-guard keeps its data, and the rules for wrong-password attempts.

The only module that knows paths and file formats. Paths are resolved on every call
(from HOME / XDG_*), so tests and the root SDDM watcher can point them elsewhere.

  ~/.config/presence-guard/settings.json      written by the UI
  ~/.local/state/presence-guard/last_seen     newest attempt already announced (worker)
  ~/.local/share/presence-guard/attempts/<UTC YYYY-MM-DD_HH-MM-SS>[-N]/
      1.jpg … k.jpg, meta.json                created/updated by the worker; UI and prune delete
"""
import calendar
import json
import os
import shutil
import time

DEFAULTS = {"wrong_password_photos": True, "camera": None, "keep_days": 30}
BURST_GAP = 10        # a failure this soon after the last one joins the same attempt
BURST_MAX = 120       # ...unless the attempt started this long ago
TYPO_WINDOW = 20      # failures this close before your unlock are labeled "probably you"
NAME_FORMAT = "%Y-%m-%d_%H-%M-%S"
SKIP_SUFFIXES = (".partial", ".deleting")

OWNER = None  # (uid, gid): set by the root SDDM watcher so everything it writes belongs to the owner


def _xdg(var, default):
    return os.environ.get(var) or os.path.join(os.path.expanduser("~"), default)


def data_dir():
    return os.path.join(_xdg("XDG_DATA_HOME", ".local/share"), "presence-guard")


def attempts_dir():
    return os.path.join(data_dir(), "attempts")


def test_dir():
    return os.path.join(data_dir(), "test")


def settings_file():
    return os.path.join(_xdg("XDG_CONFIG_HOME", ".config"), "presence-guard", "settings.json")


def last_seen_file():
    return os.path.join(_xdg("XDG_STATE_HOME", ".local/state"), "presence-guard", "last_seen")


def _own(path):
    if OWNER:
        os.chown(path, *OWNER)


def private_dir(path):
    """Create `path` as 0700 (parents keep their normal permissions)."""
    parent = os.path.dirname(path)
    if not os.path.isdir(parent):
        private_dir(parent) if parent.startswith(data_dir()) else os.makedirs(parent, exist_ok=True)
    try:
        os.mkdir(path, 0o700)
        _own(path)
    except FileExistsError:
        pass
    return path


def atomic_write(path, text):
    """Readers never see a half-written file: write a temp file next to it, then rename."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.tmp-{os.getpid()}"
    with open(tmp, "w") as f:
        f.write(text)
    _own(tmp)
    os.replace(tmp, path)


def _read_json(path):
    try:
        with open(path) as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


# --- settings -----------------------------------------------------------------------

def settings():
    """Current settings; a missing or unreadable file gives the defaults (camera None = photos off)."""
    return {**DEFAULTS, **(_read_json(settings_file()) or {})}


def save_settings(values):
    atomic_write(settings_file(), json.dumps({**settings(), **values}, indent=2))


def photos_enabled(s):
    return bool(s.get("wrong_password_photos") and s.get("camera"))


# --- attempts -----------------------------------------------------------------------

def name_time(name):
    """Epoch of an attempt folder name (UTC), or None if it isn't one."""
    rest = name[19:]  # "" or a collision suffix like "-2"
    if rest and not (rest[0] == "-" and rest[1:].isdigit()):
        return None
    try:
        return calendar.timegm(time.strptime(name[:19], NAME_FORMAT))
    except ValueError:
        return None


def new_attempt(t):
    """Make an empty `<name>.partial/` for a failure at epoch t; names never collide."""
    base = os.path.join(private_dir(attempts_dir()), time.strftime(NAME_FORMAT, time.gmtime(t)))
    path, n = base, 1
    while os.path.exists(path) or os.path.exists(path + ".partial"):
        n += 1
        path = f"{base}-{n}"
    os.mkdir(path + ".partial", 0o700)
    _own(path + ".partial")
    return path + ".partial"


def finish_attempt(partial, meta):
    write_meta(partial, meta)
    final = partial[: -len(".partial")]
    os.rename(partial, final)
    return final


def recover_partials(now=None, min_age=60):
    """Finish attempts whose capture was cut short (service killed or restarted), so they aren't lost.

    Only partials older than `min_age` seconds: a younger one may still be capturing in another process.
    """
    now = time.time() if now is None else now
    try:
        names = [n for n in os.listdir(attempts_dir()) if n.endswith(".partial")]
    except OSError:
        return
    for name in names:
        partial = os.path.join(attempts_dir(), name)
        t = name_time(name[: -len(".partial")])
        if t is None or now - t < min_age:
            continue
        count = len(photo_paths(partial))
        finish_attempt(partial, {"failures": 1, "first_failure": t, "last_failure": t, "photos": count,
                                 "error": "capture interrupted", "probably_you": False})


def read_meta(folder):
    return _read_json(os.path.join(folder, "meta.json"))


def write_meta(folder, meta):
    atomic_write(os.path.join(folder, "meta.json"), json.dumps(meta, indent=2))


def photo_paths(folder):
    """Photos 1.jpg … k.jpg in order."""
    try:
        stems = sorted(int(f[:-4]) for f in os.listdir(folder) if f.endswith(".jpg") and f[:-4].isdigit())
    except OSError:
        return []
    return [os.path.join(folder, f"{n}.jpg") for n in stems]


def attempts():
    """Finished attempts, newest first: dicts with name, path, time, meta, photos."""
    try:
        names = os.listdir(attempts_dir())
    except OSError:
        return []
    out = []
    for name in names:
        t = name_time(name)
        if t is None or name.endswith(SKIP_SUFFIXES):
            continue
        path = os.path.join(attempts_dir(), name)
        meta = read_meta(path) or {}
        out.append({"name": name, "path": path, "time": meta.get("first_failure", t),
                    "meta": meta, "photos": photo_paths(path)})
    return sorted(out, key=lambda a: a["name"], reverse=True)


def delete_attempt(path):
    """Remove one attempt. Renamed away first, so a concurrent writer can't leave half a folder behind."""
    if os.path.dirname(os.path.realpath(path)) != os.path.realpath(attempts_dir()):
        raise ValueError(f"not an attempt: {path}")
    gone = f"{path}.deleting-{os.getpid()}"
    try:
        os.rename(path, gone)
    except FileNotFoundError:
        return  # someone else deleted it first
    shutil.rmtree(gone, ignore_errors=True)


# --- rules (pure: times are passed in, so they're unit-tested) ------------------------

def burst_continues(burst, t):
    """Does a failure at t join the open attempt `burst` ({"first", "last"}, or None)?"""
    return bool(burst) and 0 <= t - burst["last"] < BURST_GAP and t - burst["first"] < BURST_MAX


def is_new(name, last_seen):
    return last_seen is None or name > last_seen


def probably_you(last_failure, unlock_t):
    return unlock_t - TYPO_WINDOW <= last_failure <= unlock_t


def prunable(attempt, now, keep_days):
    """Old enough to delete? keep_days 0 keeps everything; a still-open burst is never pruned."""
    if not keep_days:
        return False
    last = attempt["meta"].get("last_failure", attempt["time"])
    if now - last < BURST_MAX:
        return False
    return now - attempt["time"] > keep_days * 86400


def prune(now=None):
    now = time.time() if now is None else now
    keep = settings().get("keep_days") or 0
    for a in attempts():
        if prunable(a, now, keep):
            delete_attempt(a["path"])


# --- announcing -----------------------------------------------------------------------

def last_seen():
    """Name of the newest attempt already announced; None (announce everything) if unknown."""
    try:
        with open(last_seen_file()) as f:
            return f.read().strip() or None
    except OSError:
        return None


def mark_seen(name):
    atomic_write(last_seen_file(), name + "\n")
