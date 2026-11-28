"""Presence Guard app: a sidebar menu of pages. Add a page by writing a QWidget class and listing it in PAGES."""
import getpass
import os
import sys
import time

from PySide6.QtCore import QEvent, QFileSystemWatcher, QProcess, QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QImageReader, QPixmap
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QFormLayout, QFrame, QHBoxLayout, QLabel,
                               QListWidget, QMainWindow, QMessageBox, QPushButton, QScrollArea, QSpinBox,
                               QStackedWidget, QToolButton, QVBoxLayout, QWidget)

from pg import store, system

THUMB = QSize(104, 78)  # five fit beside each other in the default window
SCRIPT = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "presence-guard")


def local_time(epoch):
    return time.strftime("%a %d %b %Y, %H:%M:%S", time.localtime(epoch))


def heading(text):
    label = QLabel(text)
    font = label.font()
    font.setPointSizeF(font.pointSizeF() * 1.4)
    font.setBold(True)
    label.setFont(font)
    return label


def thumbnail(path):
    reader = QImageReader(path)
    reader.setAutoTransform(True)
    reader.setScaledSize(reader.size().scaled(THUMB, Qt.KeepAspectRatio))  # decode small: cheap for long histories
    return QPixmap.fromImage(reader.read())


class AttemptCard(QFrame):
    def __init__(self, attempt, on_delete):
        super().__init__()
        self.setFrameShape(QFrame.StyledPanel)
        meta = attempt["meta"]
        top = QHBoxLayout()
        title = QLabel(f"<b>{local_time(attempt['time'])}</b>")
        top.addWidget(title)
        tags = []
        if meta.get("failures", 1) > 1:
            tags.append(f"{meta['failures']} tries")
        if meta.get("source") == "sddm":
            tags.append("Login screen")
        if meta.get("probably_you"):
            tags.append("Probably you")
        for tag in tags:
            label = QLabel(tag)
            label.setStyleSheet("border: 1px solid palette(mid); border-radius: 3px; padding: 0 5px;")
            top.addWidget(label)
        top.addStretch()
        delete = QPushButton("Delete")
        delete.setAccessibleName(f"Delete attempt from {local_time(attempt['time'])}")
        delete.clicked.connect(lambda: on_delete(attempt))
        top.addWidget(delete)

        photos = QHBoxLayout()
        for i, path in enumerate(attempt["photos"], 1):
            button = QToolButton()
            button.setIcon(thumbnail(path))
            button.setIconSize(THUMB)
            button.setAutoRaise(True)
            button.setToolTip("Open full size")
            button.setAccessibleName(f"Photo {i}, open full size")
            button.clicked.connect(lambda _=False, p=path: QDesktopServices.openUrl(QUrl.fromLocalFile(p)))
            photos.addWidget(button)
        if not attempt["photos"]:
            photos.addWidget(QLabel(f"No photos: {meta.get('error') or 'none were saved'}"))
        photos.addStretch()

        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addLayout(photos)


class AttemptsPage(QWidget):
    title = "Wrong passwords"

    def __init__(self, since):
        super().__init__()
        self.since = since  # None: full history; otherwise show only attempts newer than this name ("" = all new)
        self.header = heading("")
        self.show_all = QPushButton()
        self.show_all.clicked.connect(self.clear_filter)
        self.list = QVBoxLayout()
        self.list.setAlignment(Qt.AlignTop)
        holder = QWidget()
        holder.setLayout(self.list)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setWidget(holder)

        top = QHBoxLayout()
        top.addWidget(self.header)
        top.addStretch()
        top.addWidget(self.show_all)
        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(scroll)

        # The watcher sees attempts appear or disappear; MainWindow also refreshes on focus for in-place updates.
        self.watcher = QFileSystemWatcher([store.private_dir(store.attempts_dir())])
        self.debounce = QTimer(singleShot=True, interval=300, timeout=self.refresh)
        self.watcher.directoryChanged.connect(lambda _: self.debounce.start())
        self.refresh()

    def clear_filter(self):
        self.since = None
        self.refresh()

    def refresh(self):
        everything = store.attempts()
        shown = everything if self.since is None else [a for a in everything if store.is_new(a["name"], self.since or None)]
        while self.list.count():
            old = self.list.takeAt(0).widget()
            old.setParent(None)  # off screen now; deleteLater alone leaves it painted until the event loop runs
            old.deleteLater()
        if self.since is None:
            self.header.setText("Wrong passwords")
            self.show_all.hide()
        else:
            n = len(shown)
            self.header.setText(f"{n} attempt{'' if n == 1 else 's'} since your last unlock")
            self.show_all.setText(f"Show all ({len(everything)})")
            self.show_all.show()
        for attempt in shown:
            self.list.addWidget(AttemptCard(attempt, self.delete))
        if not shown:
            empty = QLabel("No wrong-password attempts." if store.photos_enabled(store.settings()) else
                           "No wrong-password attempts.\nPhotos are off: pick a camera on the Settings page.")
            empty.setAlignment(Qt.AlignCenter)
            empty.setEnabled(False)
            self.list.addWidget(empty)

    def delete(self, attempt):
        answer = QMessageBox.question(self, "Delete attempt",
                                      f"Delete the attempt from {local_time(attempt['time'])} and its photos?")
        if answer == QMessageBox.Yes:
            store.delete_attempt(attempt["path"])
            self.refresh()


class SettingsPage(QWidget):
    title = "Settings"

    def __init__(self, since=None):
        super().__init__()
        self.enabled = QCheckBox("Take photos on wrong password")
        self.camera = QComboBox()
        self.keep = QSpinBox(minimum=0, maximum=3650, suffix=" days")
        self.keep.setSpecialValueText("keep forever")
        self.camera_note = QLabel("Howdy's IR camera is not listed.")
        self.camera_note.setEnabled(False)
        storage = QLabel(f"Photos are stored in {store.data_dir()} (only you can read them).")
        storage.setWordWrap(True)
        storage.setEnabled(False)

        self.no_autolock = QCheckBox("No auto-lock while someone is in front of the IR camera")
        self.autolock_for = QComboBox()
        self.autolock_for.addItem("Only when you (the owner) are present", "owner")
        self.autolock_for.addItem("When anyone is present", "anyone")

        form = QFormLayout()
        form.addRow(self.no_autolock)
        form.addRow("Stay unlocked", self.autolock_for)
        form.addRow(self.enabled)
        form.addRow("Camera", self.camera)
        form.addRow("", self.camera_note)
        form.addRow("Delete attempts older than", self.keep)
        layout = QVBoxLayout(self)
        layout.addWidget(heading("Settings"))
        layout.addLayout(form)
        layout.addWidget(storage)
        layout.addStretch()
        self.refresh()
        self.enabled.toggled.connect(lambda on: store.save_settings({"wrong_password_photos": on}))
        self.camera.currentIndexChanged.connect(self.camera_changed)
        self.keep.valueChanged.connect(lambda days: store.save_settings({"keep_days": days}))
        self.no_autolock.toggled.connect(self.no_autolock_changed)
        self.autolock_for.currentIndexChanged.connect(
            lambda: store.save_settings({"no_autolock_for": self.autolock_for.currentData()}))

    def no_autolock_changed(self, on):
        store.save_settings({"no_autolock": on})
        self.autolock_for.setEnabled(on)

    def refresh(self):
        s = store.settings()
        widgets = (self.enabled, self.camera, self.keep, self.no_autolock, self.autolock_for)
        for widget in widgets:
            widget.blockSignals(True)
        self.camera.clear()
        self.camera.addItem("Choose a camera…", None)
        for path, label in system.list_cameras():
            self.camera.addItem(label, path)
        if s["camera"] and self.camera.findData(s["camera"]) < 0:
            self.camera.addItem(f"{s['camera']} (not found)", s["camera"])
        self.camera.setCurrentIndex(max(0, self.camera.findData(s["camera"])))
        self.enabled.setChecked(bool(s["wrong_password_photos"]))
        self.enabled.setEnabled(bool(s["camera"]))  # photos stay off until a camera is chosen
        self.keep.setValue(int(s["keep_days"] or 0))
        self.no_autolock.setChecked(bool(s["no_autolock"]))
        self.autolock_for.setCurrentIndex(max(0, self.autolock_for.findData(s["no_autolock_for"])))
        self.autolock_for.setEnabled(bool(s["no_autolock"]))
        for widget in widgets:
            widget.blockSignals(False)

    def camera_changed(self):
        camera = self.camera.currentData()
        store.save_settings({"camera": camera})
        self.enabled.setEnabled(bool(camera))


class StatusPage(QWidget):
    title = "Status"

    def __init__(self, since=None):
        super().__init__()
        self.rows = {}
        form = QFormLayout()
        for key in ("Service", "Login-screen watcher", "KDE auto-lock", "IR camera (Howdy)", "RGB camera",
                    "Wrong-password photos", "Last capture problem"):
            self.rows[key] = QLabel()
            self.rows[key].setTextInteractionFlags(Qt.TextSelectableByMouse)
            self.rows[key].setWordWrap(True)
            form.addRow(key, self.rows[key])
        self.check = QPushButton("Check camera now")
        self.check.clicked.connect(self.run_check)
        self.result = QLabel()
        self.process = QProcess(self)
        self.process.finished.connect(self.check_done)
        row = QHBoxLayout()
        row.addWidget(self.check)
        row.addWidget(self.result)
        row.addStretch()
        layout = QVBoxLayout(self)
        layout.addWidget(heading("Status"))
        layout.addLayout(form)
        layout.addLayout(row)
        layout.addStretch()
        self.refresh()

    def refresh(self):
        s = store.settings()
        lock = system.kde_lock_seconds()
        problems = [a for a in store.attempts() if a["meta"].get("error")]
        values = {
            "Service": system.service_active(),
            "Login-screen watcher": system.service_active(f"presence-guard-sddm@{getpass.getuser()}", user=False),
            "KDE auto-lock": f"{lock // 60} min (face check runs 15 s before)" if lock else "off",
            "IR camera (Howdy)": system.howdy_device() or "not configured",
            "RGB camera": s["camera"] or "not chosen",
            "Wrong-password photos": "on" if store.photos_enabled(s) else "off",
            "Last capture problem": (f"{problems[0]['meta']['error']} ({local_time(problems[0]['time'])})"
                                     if problems else "none"),
        }
        for key, value in values.items():
            self.rows[key].setText(value)

    def run_check(self):
        self.check.setEnabled(False)
        self.result.setText("Looking…")
        self.process.start(sys.executable, [SCRIPT, "check"])

    def check_done(self):
        output = bytes(self.process.readAllStandardOutput()).decode().strip()
        self.result.setText(output or "check failed (see journal)")
        self.check.setEnabled(True)


PAGES = [AttemptsPage, StatusPage, SettingsPage]


class MainWindow(QMainWindow):
    def __init__(self, since):
        super().__init__()
        self.setWindowTitle("Presence Guard")
        self.menu = QListWidget()
        self.menu.setFixedWidth(170)
        self.pages = QStackedWidget()
        for page in PAGES:
            self.menu.addItem(page.title)
            self.pages.addWidget(page(since) if page is AttemptsPage else page())
        self.menu.currentRowChanged.connect(self.show_page)
        self.menu.setCurrentRow(0)
        body = QWidget()
        layout = QHBoxLayout(body)
        layout.addWidget(self.menu)
        layout.addWidget(self.pages, 1)
        self.setCentralWidget(body)
        self.resize(900, 600)

    def show_page(self, row):
        self.pages.setCurrentIndex(row)
        self.pages.currentWidget().refresh()

    def changeEvent(self, event):
        # The folder watcher misses edits inside an attempt (e.g. its failure count); rescan when you come back.
        if event.type() == QEvent.ActivationChange and self.isActiveWindow():
            self.pages.currentWidget().refresh()
        super().changeEvent(event)


def main(since=None):
    app = QApplication(sys.argv[:1])
    app.setApplicationName("Presence Guard")
    app.setDesktopFileName("presence-guard")
    store.prune()
    window = MainWindow(since)
    window.show()
    return app.exec()
