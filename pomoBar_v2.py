"""Pomobar v2 - a thin, always-on-top Pomodoro progress bar (PyQt5).

What's new compared to v1:
  * Fixed: crash when no config file exists, crash on 0-minute durations,
    settings dialog silently resetting saved durations, timer resetting while
    adjusting geometry, black colour on "Cancel" in the colour picker,
    tick-counting drift, config file written to the current working directory.
  * Hover to expand: the bar grows to show time, cycle dots and buttons.
  * Right-click menu (also on the tray icon): pause, skip, reset, settings...
  * Tray icon with a live progress ring, notifications and a sound when a
    session ends.
  * Long break after every N work sessions.
  * Optional "wait for click" between sessions instead of auto-starting.
"""

import os
import sys
import json
import math
import time

from PyQt5.QtCore import Qt, QTimer, QRect, QRectF
from PyQt5.QtGui import QPainter, QFont, QColor, QIcon, QPixmap, QCursor, QPen
from PyQt5.QtWidgets import (
    QApplication, QWidget, QPushButton, QDialog, QFormLayout, QSpinBox,
    QCheckBox, QColorDialog, QDialogButtonBox, QMenu, QAction,
    QSystemTrayIcon, QGroupBox, QVBoxLayout,
)

try:
    import winsound  # Windows only
except ImportError:
    winsound = None


APP_NAME = "Pomobar"
__version__ = "2.0.0"

WORK, BREAK, LONG_BREAK = "work", "break", "long_break"
PHASE_LABELS = {WORK: "Work", BREAK: "Break", LONG_BREAK: "Long break"}

FLASH_SECONDS = 2.0       # length of the rainbow sweep when a session ends
COLLAPSE_DELAY_MS = 400   # how long the bar stays expanded after the mouse leaves

DEFAULTS = {
    "work_time": 25,
    "break_time": 5,
    "long_break_time": 15,
    "sets_before_long_break": 4,
    "work_color": [0, 134, 0, 255],
    "break_color": [98, 147, 147, 255],
    "long_break_color": [70, 110, 200, 255],
    "height": 8,
    "expanded_height": 30,
    "auto_start": True,
    "sound": True,
    "notifications": True,
    # "x", "y", "width" default to the bottom of the primary screen
}


# --------------------------------------------------------------------------
# Config
# --------------------------------------------------------------------------

def config_dir():
    base = os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, APP_NAME)


CONFIG_PATH = os.path.join(config_dir(), "config.json")
# v1 kept its config next to the script; read it once so settings carry over.
LEGACY_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  "progressbar_config.json")


def read_config():
    for path in (CONFIG_PATH, LEGACY_CONFIG_PATH):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
        except (OSError, ValueError):
            continue
    return {}


def write_config(cfg):
    try:
        os.makedirs(config_dir(), exist_ok=True)
        tmp = CONFIG_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
        os.replace(tmp, CONFIG_PATH)  # atomic: never leaves a half-written file
    except OSError as exc:
        print(f"[{APP_NAME}] could not save config: {exc}", file=sys.stderr)


def _int(value, default, lo, hi):
    try:
        return max(lo, min(hi, int(value)))
    except (TypeError, ValueError):
        return default


def _color(value, default):
    try:
        parts = [max(0, min(255, int(c))) for c in value]
        if len(parts) == 3:
            parts.append(255)
        if len(parts) == 4:
            return parts
    except (TypeError, ValueError):
        pass
    return list(default)


def sanitize_config(raw):
    """Merge a loaded config with defaults and clamp every value to a safe range."""
    cfg = dict(DEFAULTS)
    cfg["work_time"] = _int(raw.get("work_time"), DEFAULTS["work_time"], 1, 1440)
    cfg["break_time"] = _int(raw.get("break_time"), DEFAULTS["break_time"], 1, 1440)
    cfg["long_break_time"] = _int(raw.get("long_break_time"), DEFAULTS["long_break_time"], 1, 1440)
    cfg["sets_before_long_break"] = _int(raw.get("sets_before_long_break"),
                                         DEFAULTS["sets_before_long_break"], 1, 20)
    for key in ("work_color", "break_color", "long_break_color"):
        cfg[key] = _color(raw.get(key), DEFAULTS[key])
    cfg["height"] = _int(raw.get("height"), DEFAULTS["height"], 2, 200)
    cfg["expanded_height"] = _int(raw.get("expanded_height"), DEFAULTS["expanded_height"], 16, 200)
    for key in ("auto_start", "sound", "notifications"):
        cfg[key] = bool(raw.get(key, DEFAULTS[key]))

    screen = QApplication.primaryScreen().availableGeometry()
    default_rect = QRect(screen.x(), screen.bottom() - cfg["height"] + 1,
                         screen.width(), cfg["height"])
    rect = QRect(_int(raw.get("x"), default_rect.x(), -20000, 20000),
                 _int(raw.get("y"), default_rect.y(), -20000, 20000),
                 _int(raw.get("width"), default_rect.width(), 50, 20000),
                 cfg["height"])
    # A monitor may have been unplugged since last run - don't open off-screen.
    if QApplication.screenAt(rect.center()) is None:
        rect = default_rect
    cfg["x"], cfg["y"], cfg["width"] = rect.x(), rect.y(), rect.width()
    return cfg


# --------------------------------------------------------------------------
# Timer logic (no Qt; time comes from a clock function so it can't drift)
# --------------------------------------------------------------------------

class PomodoroClock:
    def __init__(self, durations, sets_before_long_break, now=time.monotonic):
        self.now = now
        self.durations = dict(durations)  # phase -> seconds
        self.sets_before_long_break = sets_before_long_break
        self.reset()

    def reset(self):
        self.phase = WORK
        self.completed = 0        # finished work sessions
        self.waiting = False      # session ended, waiting for the user to start the next
        self._acc = 0.0           # elapsed seconds banked before the last pause
        self._started = self.now()

    @property
    def running(self):
        return self._started is not None

    def start(self):
        if self._started is None:
            self._started = self.now()
        self.waiting = False

    def pause(self):
        if self._started is not None:
            self._acc += self.now() - self._started
            self._started = None

    def toggle(self):
        if self.running:
            self.pause()
        else:
            self.start()

    def elapsed(self):
        running_part = self.now() - self._started if self._started is not None else 0.0
        return self._acc + running_part

    def total(self):
        return self.durations[self.phase]

    def remaining(self):
        return max(0.0, self.total() - self.elapsed())

    def progress(self):
        return min(1.0, self.elapsed() / self.total())

    def cycle_position(self):
        """How many dots to fill in the 'sets' indicator."""
        if self.phase == LONG_BREAK:
            return self.sets_before_long_break
        return self.completed % self.sets_before_long_break

    def _advance(self, count_work, auto_start):
        finished = self.phase
        if finished == WORK:
            if count_work:
                self.completed += 1
                long_due = self.completed % self.sets_before_long_break == 0
                self.phase = LONG_BREAK if long_due else BREAK
            else:
                self.phase = BREAK  # skipped work never earns a long break
        else:
            self.phase = WORK
        self._acc = 0.0
        self._started = self.now() if auto_start else None
        self.waiting = not auto_start
        return finished

    def tick(self, auto_start):
        """Advance if the current session is over. Returns the finished phase or None."""
        if self.running and self.elapsed() >= self.total():
            return self._advance(count_work=True, auto_start=auto_start)
        return None

    def skip(self, auto_start):
        return self._advance(count_work=False, auto_start=auto_start)


# --------------------------------------------------------------------------
# Settings dialog
# --------------------------------------------------------------------------

class SettingsDialog(QDialog):
    def __init__(self, bar):
        super().__init__(bar)
        self.bar = bar
        self.setWindowTitle(f"{APP_NAME} {__version__} settings")
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
        cfg = bar.cfg
        self.colors = {k: list(cfg[k]) for k in ("work_color", "break_color", "long_break_color")}
        self.original_rect = bar.base_rect()

        # --- timer ---
        timer_box = QGroupBox("Timer")
        timer_form = QFormLayout(timer_box)
        self.work_spin = self._spin(1, 1440, cfg["work_time"], " min")
        self.break_spin = self._spin(1, 1440, cfg["break_time"], " min")
        self.long_break_spin = self._spin(1, 1440, cfg["long_break_time"], " min")
        self.sets_spin = self._spin(1, 20, cfg["sets_before_long_break"], " sessions")
        timer_form.addRow("Work:", self.work_spin)
        timer_form.addRow("Break:", self.break_spin)
        timer_form.addRow("Long break:", self.long_break_spin)
        timer_form.addRow("Long break every:", self.sets_spin)
        self.auto_start_check = QCheckBox("Start the next session automatically")
        self.auto_start_check.setChecked(cfg["auto_start"])
        timer_form.addRow(self.auto_start_check)

        # --- look ---
        look_box = QGroupBox("Appearance")
        look_form = QFormLayout(look_box)
        self.color_buttons = {}
        for key, label in (("work_color", "Work colour:"), ("break_color", "Break colour:"),
                           ("long_break_color", "Long break colour:")):
            btn = QPushButton()
            btn.setFixedHeight(22)
            btn.clicked.connect(lambda _=False, k=key: self.pick_color(k))
            self.color_buttons[key] = btn
            self._paint_color_button(key)
            look_form.addRow(label, btn)

        # --- position (previewed live, reverted on Cancel) ---
        pos_box = QGroupBox("Position && size")
        pos_form = QFormLayout(pos_box)
        rect = self.original_rect
        self.x_spin = self._spin(-20000, 20000, rect.x(), " px")
        self.y_spin = self._spin(-20000, 20000, rect.y(), " px")
        self.width_spin = self._spin(50, 20000, rect.width(), " px")
        self.height_spin = self._spin(2, 200, rect.height(), " px")
        self.expanded_spin = self._spin(16, 200, cfg["expanded_height"], " px")
        pos_form.addRow("X:", self.x_spin)
        pos_form.addRow("Y:", self.y_spin)
        pos_form.addRow("Width:", self.width_spin)
        pos_form.addRow("Height:", self.height_spin)
        pos_form.addRow("Height on hover:", self.expanded_spin)
        for spin in (self.x_spin, self.y_spin, self.width_spin, self.height_spin):
            spin.valueChanged.connect(self.preview_geometry)

        # --- alerts ---
        alert_box = QGroupBox("Alerts")
        alert_layout = QVBoxLayout(alert_box)
        self.sound_check = QCheckBox("Play a sound when a session ends")
        self.sound_check.setChecked(cfg["sound"])
        self.notify_check = QCheckBox("Show a notification when a session ends")
        self.notify_check.setChecked(cfg["notifications"])
        alert_layout.addWidget(self.sound_check)
        alert_layout.addWidget(self.notify_check)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        for box in (timer_box, look_box, pos_box, alert_box):
            layout.addWidget(box)
        layout.addWidget(buttons)

    @staticmethod
    def _spin(lo, hi, value, suffix=""):
        spin = QSpinBox()
        spin.setRange(lo, hi)
        spin.setValue(value)
        spin.setSuffix(suffix)
        return spin

    def _paint_color_button(self, key):
        r, g, b, a = self.colors[key]
        self.color_buttons[key].setStyleSheet(
            f"background-color: rgba({r}, {g}, {b}, {a}); border: 1px solid #888;")

    def pick_color(self, key):
        color = QColorDialog.getColor(QColor(*self.colors[key]), self, "Pick a colour",
                                      QColorDialog.ShowAlphaChannel)
        if color.isValid():  # invalid == the user pressed Cancel
            self.colors[key] = list(color.getRgb())
            self._paint_color_button(key)

    def current_rect(self):
        return QRect(self.x_spin.value(), self.y_spin.value(),
                     self.width_spin.value(), self.height_spin.value())

    def preview_geometry(self):
        self.bar.set_base_rect(self.current_rect())

    def reject(self):
        self.bar.set_base_rect(self.original_rect)
        super().reject()

    def values(self):
        rect = self.current_rect()
        values = {
            "work_time": self.work_spin.value(),
            "break_time": self.break_spin.value(),
            "long_break_time": self.long_break_spin.value(),
            "sets_before_long_break": self.sets_spin.value(),
            "auto_start": self.auto_start_check.isChecked(),
            "sound": self.sound_check.isChecked(),
            "notifications": self.notify_check.isChecked(),
            "x": rect.x(), "y": rect.y(), "width": rect.width(), "height": rect.height(),
            "expanded_height": self.expanded_spin.value(),
        }
        values.update(self.colors)
        return values


# --------------------------------------------------------------------------
# The bar
# --------------------------------------------------------------------------

class Pomobar(QWidget):
    def __init__(self):
        super().__init__()
        self.cfg = sanitize_config(read_config())
        self.clock = PomodoroClock(self._durations(), self.cfg["sets_before_long_break"])
        self.expanded = False
        self.flash_started = None
        self.settings_dialog = None
        self._last_tray_state = None

        self.setWindowTitle(APP_NAME)
        # Qt.Tool keeps the bar out of the taskbar and Alt+Tab.
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMouseTracking(True)

        self._build_buttons()
        self._build_menu()
        self._build_tray()

        self.collapse_timer = QTimer(self)
        self.collapse_timer.setSingleShot(True)
        self.collapse_timer.timeout.connect(self.collapse_if_mouse_left)

        self.tick_timer = QTimer(self)
        self.tick_timer.timeout.connect(self.on_tick)
        self.tick_timer.start(200)

        self._apply_geometry()
        self.refresh_controls()

    # ----- setup -------------------------------------------------------

    def _durations(self):
        return {WORK: self.cfg["work_time"] * 60,
                BREAK: self.cfg["break_time"] * 60,
                LONG_BREAK: self.cfg["long_break_time"] * 60}

    def _build_buttons(self):
        style = ("QPushButton { background: rgba(255,255,255,30); color: white; border: none;"
                 " font-weight: bold; }"
                 "QPushButton:hover { background: rgba(255,255,255,70); }")
        self.pause_button = QPushButton(self)
        self.skip_button = QPushButton("⏭︎", self)
        self.reset_button = QPushButton("↺", self)
        self.pause_button.setToolTip("Pause / resume")
        self.skip_button.setToolTip("Skip to the next session")
        self.reset_button.setToolTip("Reset")
        self.pause_button.clicked.connect(self.toggle_pause)
        self.skip_button.clicked.connect(self.skip)
        self.reset_button.clicked.connect(self.reset)
        self.buttons = [self.pause_button, self.skip_button, self.reset_button]
        for btn in self.buttons:
            btn.setStyleSheet(style)
            btn.setCursor(Qt.PointingHandCursor)
            btn.hide()

    def _build_menu(self):
        self.menu = QMenu()
        self.pause_action = QAction("Pause", self, triggered=self.toggle_pause)
        self.skip_action = QAction("Skip to next session", self, triggered=self.skip)
        self.reset_action = QAction("Reset", self, triggered=self.reset)
        self.auto_action = QAction("Start next session automatically", self, checkable=True,
                                   triggered=lambda on: self.set_option("auto_start", on))
        self.sound_action = QAction("Sound", self, checkable=True,
                                    triggered=lambda on: self.set_option("sound", on))
        self.settings_action = QAction("Settings…", self, triggered=self.open_settings)
        self.quit_action = QAction("Quit", self, triggered=self.quit)
        for item in (self.pause_action, self.skip_action, self.reset_action, None,
                     self.auto_action, self.sound_action, None,
                     self.settings_action, self.quit_action):
            if item is None:
                self.menu.addSeparator()
            else:
                self.menu.addAction(item)

    def _build_tray(self):
        self.tray = None
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self.tray = QSystemTrayIcon(self)
        self.tray.setContextMenu(self.menu)
        self.tray.activated.connect(self.on_tray_activated)
        self.update_tray(force=True)
        self.tray.show()

    # ----- geometry & hover expansion ----------------------------------

    def base_rect(self):
        return QRect(self.cfg["x"], self.cfg["y"], self.cfg["width"], self.cfg["height"])

    def set_base_rect(self, rect):
        self.cfg.update(x=rect.x(), y=rect.y(), width=rect.width(), height=rect.height())
        self._apply_geometry()

    def _expanded_rect(self):
        base = self.base_rect()
        h = max(base.height(), self.cfg["expanded_height"])
        screen = QApplication.screenAt(base.center()) or QApplication.primaryScreen()
        # Grow away from the nearest screen edge: upward if the bar sits in the lower half.
        if base.center().y() > screen.geometry().center().y():
            return QRect(base.x(), base.bottom() - h + 1, base.width(), h)
        return QRect(base.x(), base.y(), base.width(), h)

    def _apply_geometry(self):
        self.setGeometry(self._expanded_rect() if self.expanded else self.base_rect())
        self._layout_buttons()
        self.update()

    def _layout_buttons(self):
        size = self.height()
        for i, btn in enumerate(reversed(self.buttons)):
            btn.setGeometry(self.width() - (i + 1) * size, 0, size, size)
            btn.setFont(QFont("Segoe UI Symbol", max(6, int(size * 0.4))))
            btn.setVisible(self.expanded)

    def enterEvent(self, event):
        self.collapse_timer.stop()
        if not self.expanded:
            self.expanded = True
            self._apply_geometry()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.collapse_timer.start(COLLAPSE_DELAY_MS)
        super().leaveEvent(event)

    def collapse_if_mouse_left(self):
        if self.menu.isVisible() or self.geometry().contains(QCursor.pos()):
            self.collapse_timer.start(COLLAPSE_DELAY_MS)
            return
        self.expanded = False
        self._apply_geometry()

    # ----- input --------------------------------------------------------

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self.clock.waiting:
            self.toggle_pause()  # click to start the next session

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.open_settings()

    def contextMenuEvent(self, event):
        self.menu.exec_(event.globalPos())

    def on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.Trigger:
            self.toggle_pause()
        elif reason == QSystemTrayIcon.DoubleClick:
            self.open_settings()

    # ----- actions ------------------------------------------------------

    def toggle_pause(self):
        self.clock.toggle()
        self.refresh_controls()

    def skip(self):
        finished = self.clock.skip(self.cfg["auto_start"])
        self.flash_started = time.monotonic()
        self.refresh_controls()
        return finished

    def reset(self):
        self.clock.reset()
        self.flash_started = None
        self.refresh_controls()

    def set_option(self, key, value):
        self.cfg[key] = bool(value)
        write_config(self.cfg)
        self.refresh_controls()

    def open_settings(self):
        if self.settings_dialog is not None:
            self.settings_dialog.raise_()
            self.settings_dialog.activateWindow()
            return
        self.settings_dialog = SettingsDialog(self)
        try:
            if self.settings_dialog.exec_() == QDialog.Accepted:
                self.apply_settings(self.settings_dialog.values())
        finally:
            self.settings_dialog = None

    def apply_settings(self, values):
        self.cfg.update(values)
        # Durations change in place: time already spent in this session is kept.
        self.clock.durations = self._durations()
        self.clock.sets_before_long_break = self.cfg["sets_before_long_break"]
        self._apply_geometry()
        write_config(self.cfg)
        self.refresh_controls()

    def quit(self):
        write_config(self.cfg)
        if self.tray:
            self.tray.hide()
        QApplication.quit()

    # ----- ticking & alerts ---------------------------------------------

    def on_tick(self):
        finished = self.clock.tick(self.cfg["auto_start"])
        if finished:
            self.flash_started = time.monotonic()
            self.alert(finished)
            self.refresh_controls()
        if self.flash_started and time.monotonic() - self.flash_started > FLASH_SECONDS:
            self.flash_started = None
        self.update_tray()
        self.update()

    def alert(self, finished):
        if self.cfg["sound"]:
            if winsound is not None:
                winsound.MessageBeep(winsound.MB_ICONASTERISK)
            else:
                QApplication.beep()
        if self.cfg["notifications"] and self.tray:
            nxt = self.clock.phase
            minutes = self.clock.total() // 60
            if finished == WORK:
                title = "Work session done"
                text = f"Time for a {minutes}-minute {PHASE_LABELS[nxt].lower()}."
            else:
                title = "Break's over"
                text = f"Back to work - {minutes} minutes."
            if self.clock.waiting:
                text += " Click the bar to start."
            self.tray.showMessage(title, text, QSystemTrayIcon.Information, 6000)

    def refresh_controls(self):
        paused = not self.clock.running
        self.pause_button.setText("▶︎" if paused else "❚❚")
        if self.clock.waiting:
            self.pause_action.setText(f"Start {PHASE_LABELS[self.clock.phase].lower()}")
        else:
            self.pause_action.setText("Resume" if paused else "Pause")
        self.auto_action.setChecked(self.cfg["auto_start"])
        self.sound_action.setChecked(self.cfg["sound"])
        self.setCursor(Qt.PointingHandCursor if self.clock.waiting else Qt.ArrowCursor)
        self.update_tray(force=True)
        self.update()

    # ----- drawing -------------------------------------------------------

    def phase_color(self, phase=None):
        key = {WORK: "work_color", BREAK: "break_color",
               LONG_BREAK: "long_break_color"}[phase or self.clock.phase]
        return QColor(*self.cfg[key])

    def status_text(self):
        secs = int(math.ceil(self.clock.remaining()))
        label = PHASE_LABELS[self.clock.phase]
        if self.clock.waiting:
            return f"{label} - click to start"
        text = f"{label}  {secs // 60:02}:{secs % 60:02}"
        if not self.clock.running:
            text += "  (paused)"
        return text

    def update_tray(self, force=False):
        if not self.tray:
            return
        state = (self.clock.phase, self.clock.running, self.clock.waiting,
                 int(self.clock.progress() * 48), int(self.clock.remaining()))
        if not force and state == self._last_tray_state:
            return
        if force or self._last_tray_state is None or state[:4] != self._last_tray_state[:4]:
            self.tray.setIcon(self._tray_icon())
        self._last_tray_state = state
        self.tray.setToolTip(f"{APP_NAME} - {self.status_text()}  |  "
                             f"completed: {self.clock.completed}")

    def _tray_icon(self):
        size = 64
        pix = QPixmap(size, size)
        pix.fill(Qt.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.Antialiasing)
        ring = QRectF(6, 6, size - 12, size - 12)
        color = self.phase_color()
        p.setPen(QPen(QColor(80, 80, 80, 200), 10))
        p.drawEllipse(ring)
        if not self.clock.running:
            color.setAlpha(110)
        p.setPen(QPen(color, 10, Qt.SolidLine, Qt.FlatCap))
        p.drawArc(ring, 90 * 16, -int(self.clock.progress() * 360 * 16))
        p.end()
        return QIcon(pix)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()

        p.fillRect(self.rect(), QColor(0, 0, 0, 200 if self.expanded else 170))

        color = self.phase_color()
        if self.clock.waiting:
            # Gentle pulse across the whole bar until the user clicks.
            pulse = 0.5 + 0.5 * math.sin(time.monotonic() * 3)
            color.setAlpha(int(60 + 140 * pulse))
            p.fillRect(self.rect(), color)
        else:
            if not self.clock.running:
                color.setAlpha(110)
            p.fillRect(QRect(0, 0, int(w * self.clock.progress()), h), color)

        if self.flash_started is not None:
            t = (time.monotonic() - self.flash_started) / FLASH_SECONDS
            sweep_w = int(w * min(1.0, t * 1.5))
            hue = int(t * 720) % 360
            flash = QColor.fromHsv(hue, 220, 255, int(220 * (1 - t)))
            p.fillRect(QRect(0, 0, sweep_w, h), flash)

        if self.expanded:
            self._paint_details(p, w, h)
        p.end()

    def _paint_details(self, p, w, h):
        text_right = w - len(self.buttons) * h - 10
        font = QFont("Segoe UI", max(6, int(h * 0.38)), QFont.Bold)
        p.setFont(font)
        text_rect = QRect(10, 0, max(0, text_right - 10), h)
        text = self.status_text()
        # Soft shadow so the text stays readable over light bar colours.
        p.setPen(QColor(0, 0, 0, 160))
        p.drawText(text_rect.translated(1, 1), Qt.AlignLeft | Qt.AlignVCenter, text)
        p.setPen(Qt.white)
        p.drawText(text_rect, Qt.AlignLeft | Qt.AlignVCenter, text)

        # Cycle dots: one per work session before the long break.
        n = self.cfg["sets_before_long_break"]
        filled = self.clock.cycle_position()
        r = max(2, int(h * 0.13))
        gap = r * 3
        x = text_right - n * gap
        cy = h // 2
        p.setPen(Qt.NoPen)
        for i in range(n):
            p.setBrush(QColor(255, 255, 255, 230 if i < filled else 70))
            p.drawEllipse(x + i * gap, cy - r, 2 * r, 2 * r)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setQuitOnLastWindowClosed(False)  # closing the settings dialog must not quit
    bar = Pomobar()
    bar.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
