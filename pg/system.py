"""Questions presence-guard asks the system: KDE, systemd, Howdy and the cameras."""
import configparser
import fcntl
import glob
import os
import struct
import subprocess

HOWDY_CONFIG = "/etc/howdy/config.ini"
VIDIOC_ENUM_FMT = 0xC0405602            # _IOWR('V', 2, struct v4l2_fmtdesc), 64-byte struct
V4L2_BUF_TYPE_VIDEO_CAPTURE = 1
GREY_FORMATS = {"GREY", "Y10 ", "Y12 ", "Y16 ", "Y8I ", "Y12I"}  # IR cameras deliver greyscale


def kde_lock_seconds():
    """KDE's auto-lock timeout in seconds, or 0 if auto-lock is off."""
    def read(key, default):
        return subprocess.run(["kreadconfig6", "--file", "kscreenlockerrc", "--group", "Daemon",
                               "--key", key, "--default", default], capture_output=True, text=True).stdout.strip()
    if read("Autolock", "true") != "true":
        return 0
    return int(read("Timeout", "5")) * 60  # KDE stores minutes, default 5


def service_active(unit="presence-guard", user=True):
    cmd = ["systemctl", "--user"] if user else ["systemctl"]
    return subprocess.run(cmd + ["is-active", unit], capture_output=True, text=True).stdout.strip() or "unknown"


def howdy_device():
    """Howdy's IR camera (`device_path`), or None if Howdy isn't configured."""
    howdy = configparser.ConfigParser()
    howdy.read(HOWDY_CONFIG)
    return howdy.get("video", "device_path", fallback=None)


def first_format(device):
    """The camera's first pixel format as a fourcc string (e.g. "MJPG", "GREY"), or None if it can't be read."""
    try:
        fd = os.open(device, os.O_RDWR | os.O_NONBLOCK)  # opening doesn't start streaming, the camera light stays off
    except OSError:
        return None
    try:
        buf = bytearray(struct.pack("II", 0, V4L2_BUF_TYPE_VIDEO_CAPTURE) + bytes(56))
        fcntl.ioctl(fd, VIDIOC_ENUM_FMT, buf)
        return struct.unpack_from("4s", buf, 44)[0].decode("ascii", "replace")  # pixelformat after index/type/flags/description[32]
    except OSError:
        return None  # busy, a metadata node, or not a V4L2 device
    finally:
        os.close(fd)


def camera_label(device):
    node = os.path.realpath(device)
    try:
        with open(f"/sys/class/video4linux/{os.path.basename(node)}/name") as f:
            name = f.read().strip()
    except OSError:
        name = "Camera"
    fmt = first_format(device)
    kind = "unknown format" if fmt is None else f"{'grey' if fmt in GREY_FORMATS else 'color'} ({fmt.strip()})"
    return f"{name} · {kind} · {node}"


def list_cameras():
    """[(stable path, label)] for cameras the user can pick; Howdy's IR camera is left out."""
    howdy = howdy_device()
    skip = {os.path.realpath(howdy)} if howdy else set()
    found = []
    for path in sorted(glob.glob("/dev/v4l/by-path/*-video-index0")) or sorted(glob.glob("/dev/video*")):
        node = os.path.realpath(path)
        if node in skip:
            continue
        skip.add(node)  # the usb and usbv2 links point at the same node
        found.append((path, camera_label(path)))
    return found
