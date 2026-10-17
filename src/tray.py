#!/usr/bin/env python3
"""KDE/Linux system-tray battery indicator for 8BitDo Ultimate 2C."""

from __future__ import annotations

import json
import os
import sys
from typing import Optional

from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QInputDialog,
    QMenu,
    QMessageBox,
    QSystemTrayIcon,
    QWidget,
)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from backend import DeviceSnapshot, EightBitDo2CBackend, EstimateStore  # noqa: E402

CONFIG_DIR = os.path.expanduser("~/.config/8bitdo-2c-battery")
STATE_PATH = os.path.join(CONFIG_DIR, "state.json")
PAD_FULL_HOURS = 18.0
PAD_CHARGE_HOURS = 2.0


def _load_charge_hours() -> float:
    path = os.path.join(CONFIG_DIR, "charge_hours")
    try:
        h = float(open(path, encoding="utf-8").read().split()[0])
        if 0.5 <= h <= 6.0:
            return h
    except (OSError, ValueError, IndexError):
        pass
    return PAD_CHARGE_HOURS


def _ensure_config() -> None:
    os.makedirs(CONFIG_DIR, exist_ok=True)


def _load_state() -> dict:
    _ensure_config()
    if not os.path.exists(STATE_PATH):
        return {"notify_level": 20}
    try:
        with open(STATE_PATH, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {"notify_level": 20}


def _theme_battery_name(pct: Optional[int], connected: bool) -> str:
    if not connected or pct is None:
        return "battery-missing"
    if pct <= 10:
        return "battery-level-10"
    if pct <= 20:
        return "battery-level-20"
    if pct <= 30:
        return "battery-level-30"
    if pct <= 40:
        return "battery-level-40"
    if pct <= 50:
        return "battery-level-50"
    if pct <= 60:
        return "battery-level-60"
    if pct <= 70:
        return "battery-level-70"
    if pct <= 80:
        return "battery-level-80"
    if pct <= 90:
        return "battery-level-90"
    return "battery-level-100"


def _battery_icon(pct: Optional[int], connected: bool) -> QIcon:
    for name in (
        _theme_battery_name(pct, connected),
        "battery",
        "battery-good",
        "preferences-system-power-management",
    ):
        icon = QIcon.fromTheme(name)
        if not icon.isNull():
            return icon

    pm = QPixmap(64, 64)
    pm.fill(QColor("#1a1a1a"))
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    color = QColor("#5db87a") if connected and pct and pct > 20 else QColor("#e3b35d")
    if not connected:
        color = QColor("#888888")
    p.setBrush(color)
    p.setPen(QColor("#ffffff"))
    p.drawRoundedRect(10, 18, 36, 28, 4, 4)
    p.drawRoundedRect(46, 26, 6, 12, 2, 2)
    font = p.font()
    font.setBold(True)
    font.setPixelSize(16)
    p.setFont(font)
    p.drawText(pm.rect(), int(Qt.AlignmentFlag.AlignCenter), "—" if pct is None else str(pct))
    p.end()
    return QIcon(pm)


class TrayApp(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.state = _load_state()
        self.pad = EightBitDo2CBackend()
        self.est = EstimateStore(
            os.path.join(CONFIG_DIR, "estimate"),
            PAD_FULL_HOURS,
            charge_hours=_load_charge_hours(),
        )
        self._warned = False
        self._full_warned = False

        if not QSystemTrayIcon.isSystemTrayAvailable():
            QMessageBox.critical(self, "8bitdo-2c-battery", "Kein System-Tray verfügbar.")
            sys.exit(1)

        self.tray = QSystemTrayIcon(self)
        self.tray.setObjectName("8bitdo-2c-battery-tray")
        self.menu = QMenu()
        self.menu.setTitle("8BitDo 2C Battery")
        self.status = QAction("8BitDo 2C: …")
        self.status.setEnabled(False)
        self.menu.addAction(self.status)
        self.menu.addSeparator()

        act_full = QAction("Als voll (100 %) markieren")
        act_full.triggered.connect(lambda: self._calibrate(100))
        act_set = QAction("Prozent setzen…")
        act_set.triggered.connect(self._ask_pct)
        tip = QAction("Tipp: Live-% per Bluetooth (ohne USB-Kabel)")
        tip.setEnabled(False)
        self.menu.addAction(act_full)
        self.menu.addAction(act_set)
        self.menu.addAction(tip)
        self.menu.addSeparator()
        act_refresh = QAction("Jetzt aktualisieren")
        act_refresh.triggered.connect(self.refresh)
        self.menu.addAction(act_refresh)
        self.menu.addSeparator()
        act_quit = QAction("Beenden")
        act_quit.triggered.connect(QApplication.instance().quit)
        self.menu.addAction(act_quit)

        self.tray.setContextMenu(self.menu)
        self.tray.setToolTip("8BitDo 2C Battery")
        self.tray.setIcon(_battery_icon(None, False))
        self.tray.show()

        self.timer = QTimer(self)
        self.timer.setInterval(5000)
        self.timer.timeout.connect(self.refresh)
        self.timer.start()
        self.refresh()

    def _ask_pct(self) -> None:
        val, ok = QInputDialog.getInt(
            self,
            "Akkustand setzen",
            "Prozent (0–100):",
            int(round(self.est.percentage)),
            0,
            100,
            1,
        )
        if ok:
            self._calibrate(val)

    def _calibrate(self, pct: int) -> None:
        self.est.set_percentage(pct)
        self._warned = False
        self.refresh()

    def refresh(self) -> None:
        hw = self.pad.read()
        self.est.sync_from_disk()
        self.est.charge_hours = _load_charge_hours()

        if hw.percentage is not None and hw.source == "hid":
            self.est.set_percentage(hw.percentage)
            pct, src = hw.percentage, "hid"
            self._full_warned = False
        elif hw.charging and hw.percentage is None:
            pct = self.est.tick(charging=True)
            src = "estimate"
            ch = self.est.charge_hours or PAD_CHARGE_HOURS
            rem = max(0.0, 100.0 - pct)
            eta_min = (rem / 100.0) * ch * 60.0
            if pct < 100:
                hw = DeviceSnapshot(
                    name=hw.name,
                    dongle=hw.dongle,
                    connected=hw.connected,
                    percentage=hw.percentage,
                    charging=hw.charging,
                    source=hw.source,
                    detail=f"{hw.detail} · ETA ~{eta_min:.0f} min",
                )
        else:
            draining = bool(hw.connected and not hw.charging)
            pct = self.est.tick(draining=draining)
            src = "estimate"
            self._full_warned = False

        if not hw.dongle and not hw.connected:
            text = f"8BitDo 2C: offline · {hw.detail}"
        else:
            link = "verbunden" if hw.connected else "getrennt"
            tag = "~" if src == "estimate" else ""
            charge = " ⚡" if hw.charging else ""
            if pct is None:
                text = f"8BitDo 2C: {link} · {hw.detail}"
            else:
                text = f"8BitDo 2C: {tag}{pct}%{charge} · {link} · {hw.detail}"

        self.status.setText(text)
        show = pct if hw.connected else None
        self.tray.setIcon(_battery_icon(show, bool(hw.connected and pct is not None)))
        self.tray.setToolTip(
            text
            + "\n\n~ = Schätzung\nLive-% nur per Bluetooth (ohne USB-Kabel)\n"
            "USB-Kabel: Laden + Zeitschätzung (kein Hardware-Voll-Signal)"
        )

        level = int(self.state.get("notify_level", 20))
        if hw.connected and pct is not None and pct <= level and not hw.charging:
            if not self._warned:
                self._warned = True
                self.tray.showMessage(
                    "8BitDo 2C Akku niedrig",
                    f"{pct}%",
                    QSystemTrayIcon.MessageIcon.Warning,
                    8000,
                )
        elif pct is not None and pct > level + 5:
            self._warned = False

        if hw.charging and pct is not None and pct >= 100 and not self._full_warned:
            self._full_warned = True
            self.tray.showMessage(
                "8BitDo vermutlich voll",
                "Lade-Schätzung ~100 % (kein USB-Voll-Signal — LED am Pad prüfen)",
                QSystemTrayIcon.MessageIcon.Information,
                8000,
            )


def main() -> None:
    lock = os.path.join(CONFIG_DIR, "tray.lock")
    _ensure_config()
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
    except FileExistsError:
        try:
            old = int(open(lock, encoding="utf-8").read().strip())
            os.kill(old, 0)
            print("8bitdo-2c-battery-tray läuft bereits", file=sys.stderr)
            sys.exit(0)
        except (OSError, ValueError):
            os.remove(lock)
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)

    QApplication.setDesktopFileName("8bitdo-2c-battery-tray")
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName("8BitDo 2C Battery")
    app.setApplicationDisplayName("8BitDo 2C Battery")

    def _cleanup() -> None:
        try:
            os.remove(lock)
        except OSError:
            pass

    app.aboutToQuit.connect(_cleanup)
    _ = TrayApp()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
