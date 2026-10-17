#!/usr/bin/env python3
"""8BitDo Ultimate 2C — Bluetooth GATT battery, USB charge estimate."""

from __future__ import annotations

import glob
import os
import select
import struct
import threading
import time
from dataclasses import dataclass
from typing import Optional


def _find_hidraw(vid: int, pid: Optional[int] = None) -> Optional[str]:
    base = "/sys/class/hidraw"
    try:
        names = sorted(os.listdir(base))
    except OSError:
        return None
    for name in names:
        try:
            with open(f"{base}/{name}/device/uevent", encoding="utf-8") as fh:
                text = fh.read()
        except OSError:
            continue
        if f"HID_ID=0003:{vid:08X}:" not in text:
            continue
        if pid is not None and f":{pid:08X}" not in text:
            continue
        return f"/dev/{name}"
    return None


def _usb_ids() -> list[tuple[int, int, str]]:
    out: list[tuple[int, int, str]] = []
    for path in glob.glob("/sys/bus/usb/devices/*/idVendor"):
        root = os.path.dirname(path)
        try:
            vid = int(open(f"{root}/idVendor", encoding="utf-8").read().strip(), 16)
            pid = int(open(f"{root}/idProduct", encoding="utf-8").read().strip(), 16)
            product = ""
            prod_path = f"{root}/product"
            if os.path.exists(prod_path):
                product = open(prod_path, encoding="utf-8", errors="replace").read().strip()
            out.append((vid, pid, product))
        except (OSError, ValueError):
            continue
    return out


@dataclass
class DeviceSnapshot:
    name: str
    dongle: bool
    connected: bool
    percentage: Optional[int]
    charging: Optional[bool]
    source: str  # "hid" | "estimate" | "none"
    detail: str


class EightBitDo2CBackend:
    """8BitDo Ultimate 2C — Bluetooth GATT (real %), USB cable, 2.4 GHz estimate.

    USB XInput (2dc8:310a) is recognized by xpad but does not expose battery %
    or charge bit on this model (no power_supply, silent interrupt EP). Live %
    only via Bluetooth GATT. Cable presence ⇒ treat as charging/powered.
    """

    VID = 0x2DC8
    IDLE_PID = 0x301C  # 2.4 GHz receiver, pad off / not linked
    USB_PID = 0x310A  # USB cable (XInput / charging)
    LAST_BT_PATH = os.path.expanduser("~/.config/8bitdo-2c-battery/last_bt")
    SAMPLES_PATH = os.path.expanduser("~/.config/8bitdo-2c-battery/charge_samples.json")
    CHARGE_HOURS_PATH = os.path.expanduser("~/.config/8bitdo-2c-battery/charge_hours")

    def __init__(self) -> None:
        self._last_hid_pct: Optional[int] = None
        self._last_charging: Optional[bool] = None
        self._bt_recent: list[tuple[float, int]] = []  # (ts, pct) for stability

    def _devices(self) -> list[tuple[int, int, str]]:
        return [(v, p, n) for v, p, n in _usb_ids() if v == self.VID]

    def usb_cable_present(self) -> bool:
        return any(p == self.USB_PID for _, p, _ in self._devices())

    def receiver_present(self) -> bool:
        """2.4 GHz dongle plugged (idle or active), not the USB cable."""
        return any(p != self.USB_PID for _, p, _ in self._devices())

    def dongle_present(self) -> bool:
        return self.receiver_present() or self.usb_cable_present()

    def pad_linked_dongle(self) -> bool:
        """True when pad is linked over 2.4 GHz (not USB cable, not idle RX)."""
        for _, pid, name in self._devices():
            if pid in (self.IDLE_PID, self.USB_PID):
                continue
            # Any other 2dc8 PID = active wireless receiver / pad
            return True
        if self.usb_cable_present():
            # xpad also creates "Ultimate 2C Wireless Controller" — ignore for RF
            return False
        for path in glob.glob("/sys/class/input/input*/name"):
            try:
                name = open(path, encoding="utf-8").read().strip().lower()
            except OSError:
                continue
            if "8bitdo" not in name and "ultimate 2c" not in name:
                continue
            if "idle" in name:
                continue
            return True
        return False

    def _is_usb_bt_spike(self, pct: int) -> bool:
        """Bogus GATT jump when enabling BT while USB cable still plugged.

        Without cable: trust BlueZ (e.g. 78% is real).
        With cable: only reject sudden +8pp jumps vs recent accepted baseline
        (e.g. 67→80/89), not a steady ~78% that was measured cable-free.
        """
        if not self.usb_cable_present():
            return False
        recent = [p for _, p in self._bt_recent[-6:]]
        last = self._load_last_bt()
        if recent:
            baseline = sorted(recent)[len(recent) // 2]
        elif last is not None:
            baseline = last
        else:
            return False
        return pct >= baseline + 8

    def _append_bt_sample(self, pct: int) -> Optional[int]:
        """Log GATT sample; return stabilized % only when last 3 readings agree ±2."""
        import json

        now = time.time()
        spike = self._is_usb_bt_spike(pct)

        # Persist raw history (spikes marked, excluded from rate fit)
        try:
            hist: list[dict] = []
            if os.path.exists(self.SAMPLES_PATH):
                hist = json.loads(open(self.SAMPLES_PATH, encoding="utf-8").read())
            hist.append(
                {
                    "pct": pct,
                    "ts": now,
                    "iso": time.strftime("%H:%M:%S", time.localtime(now)),
                    "spike": spike,
                    "usb": self.usb_cable_present(),
                }
            )
            os.makedirs(os.path.dirname(self.SAMPLES_PATH), exist_ok=True)
            with open(self.SAMPLES_PATH, "w", encoding="utf-8") as fh:
                json.dump(hist[-80:], fh, indent=2)
            self._maybe_update_charge_hours(hist[-80:])
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            pass

        if spike:
            return None  # ignore USB→BT switch spikes

        # Cable unplugged: drop USB-era samples so a real 100% isn't stuck at old 60%
        if not self.usb_cable_present():
            self._bt_recent = [(t, p) for t, p in self._bt_recent if t > now - 30]

        self._bt_recent.append((now, pct))
        self._bt_recent = [(t, p) for t, p in self._bt_recent if now - t < 120][-12:]

        # No USB: trust cable-free GATT quickly (2 agreeing reads)
        if not self.usb_cable_present():
            if len(self._bt_recent) < 2:
                return None
            vals = [p for _, p in self._bt_recent[-2:]]
            if max(vals) - min(vals) > 2:
                return None
            return int(round(sum(vals) / 2))

        if len(self._bt_recent) < 3:
            return None
        vals = [p for _, p in self._bt_recent[-3:]]
        if max(vals) - min(vals) > 2:
            return None
        return int(round(sum(vals) / 3))

    def _maybe_update_charge_hours(self, hist: list[dict]) -> None:
        """Fit charge rate from stable rising segment (≥3 min, +≥3%)."""
        if len(hist) < 4:
            return
        # Use points at least 30s apart; drop mode-switch spikes
        pts: list[tuple[float, int]] = []
        for row in hist:
            try:
                ts, pct = float(row["ts"]), int(row["pct"])
            except (KeyError, TypeError, ValueError):
                continue
            if row.get("spike"):
                continue
            if not 1 <= pct <= 100:
                continue
            if pts and ts - pts[-1][0] < 25:
                continue
            pts.append((ts, pct))
        if len(pts) < 3:
            return
        # Longest rising window
        best: Optional[tuple[float, float, int, int]] = None
        for i in range(len(pts)):
            for j in range(i + 1, len(pts)):
                dt_h = (pts[j][0] - pts[i][0]) / 3600.0
                dp = pts[j][1] - pts[i][1]
                if dt_h < 3 / 60 or dp < 3:
                    continue
                mid = pts[i : j + 1]
                if any(p < pts[i][1] - 3 for _, p in mid):
                    continue
                rate = dp / dt_h
                if not 5 <= rate <= 80:  # sane %/h for USB charge
                    continue
                h100 = 100.0 / rate
                if best is None or dt_h > best[0]:
                    best = (dt_h, h100, pts[i][1], pts[j][1])
        if best is None:
            return
        _dt, h100, a, b = best
        try:
            with open(self.CHARGE_HOURS_PATH, "w", encoding="utf-8") as fh:
                fh.write(f"{h100:.4f} {time.time():.3f} {100.0/h100:.4f} {a}->{b}\n")
        except OSError:
            pass

    def _commit_last_bt(self, pct: int) -> None:
        try:
            os.makedirs(os.path.dirname(self.LAST_BT_PATH), exist_ok=True)
            with open(self.LAST_BT_PATH, "w", encoding="utf-8") as fh:
                fh.write(f"{pct} {time.time():.3f}\n")
            est = os.path.expanduser("~/.config/8bitdo-2c-battery/estimate")
            with open(est, "w", encoding="utf-8") as fh:
                fh.write(f"{float(pct):.4f} {time.time():.3f}\n")
        except OSError:
            pass

    def _load_last_bt(self) -> Optional[int]:
        try:
            pct_s, _ts = open(self.LAST_BT_PATH, encoding="utf-8").read().split()
            pct = int(float(pct_s))
            return pct if 1 <= pct <= 100 else None
        except (OSError, ValueError):
            return None

    def bluetooth_battery(self) -> Optional[tuple[int, bool, str]]:
        """Real % via BlueZ Battery1 / UPower gaming_input (GATT).

        Returns (percentage, connected, detail) or None if no 8BitDo BT device.
        """
        # 1) BlueZ org.bluez.Battery1 — most accurate while BT linked
        try:
            import dbus

            bus = dbus.SystemBus()
            obj = bus.get_object("org.bluez", "/")
            mgr = dbus.Interface(obj, "org.freedesktop.DBus.ObjectManager")
            for path, ifaces in mgr.GetManagedObjects().items():
                dev = ifaces.get("org.bluez.Device1")
                batt = ifaces.get("org.bluez.Battery1")
                if not dev:
                    continue
                name = str(dev.get("Name", "") or "")
                alias = str(dev.get("Alias", "") or "")
                blob = f"{name} {alias}".lower()
                if "8bit" not in blob and "ultimate 2c" not in blob:
                    continue
                connected = bool(dev.get("Connected", False))
                if batt is not None:
                    pct = int(batt.get("Percentage", 0))
                    if 1 <= pct <= 100:
                        stable = self._append_bt_sample(pct)
                        if stable is not None:
                            self._commit_last_bt(stable)
                            return stable, connected, "Bluetooth GATT"
                        # USB+BT only: hold last; cable-free: show fresh GATT while settling
                        if connected and self.usb_cable_present():
                            last = self._load_last_bt()
                            if last is not None:
                                return last, connected, "Bluetooth GATT (geglättet)"
                        if connected:
                            return pct, connected, "Bluetooth GATT (stabilisiert…)"
                if connected:
                    return None  # device known, wait for battery iface
        except Exception:
            pass

        # 2) UPower — must be the 8BitDo device (not MMX/other bluez batteries)
        try:
            import dbus

            bus = dbus.SystemBus()
            up = bus.get_object("org.freedesktop.UPower", "/org/freedesktop/UPower")
            for dev_path in dbus.Interface(up, "org.freedesktop.UPower").EnumerateDevices():
                d = bus.get_object("org.freedesktop.UPower", dev_path)
                props = dict(
                    dbus.Interface(d, "org.freedesktop.DBus.Properties").GetAll(
                        "org.freedesktop.UPower.Device"
                    )
                )
                model = str(props.get("Model", "")).lower()
                native = str(props.get("NativePath", "")).lower()
                blob = f"{model} {native} {dev_path}".lower()
                if "8bit" not in blob and "2dc8" not in blob and "ultimate 2c" not in blob:
                    continue
                pct = int(float(props.get("Percentage", 0)))
                if 1 <= pct <= 100:
                    stable = self._append_bt_sample(pct)
                    if stable is not None:
                        self._commit_last_bt(stable)
                        return stable, True, "UPower/Bluetooth"
                    if self.usb_cable_present():
                        last = self._load_last_bt()
                        if last is not None:
                            return last, True, "UPower/Bluetooth (geglättet)"
                    return pct, True, "UPower/Bluetooth (stabilisiert…)"
        except Exception:
            pass
        return None

    def _power_supply_pct(self) -> Optional[tuple[int, Optional[bool]]]:
        """Sysfs battery — skip the known-broken 0% HID stub for BT pads."""
        for root in glob.glob("/sys/class/power_supply/*"):
            try:
                model = ""
                if os.path.exists(f"{root}/model_name"):
                    model = open(f"{root}/model_name", encoding="utf-8").read().strip()
                name = os.path.basename(root)
                device = ""
                try:
                    device = os.path.realpath(f"{root}/device")
                except OSError:
                    pass
                blob = f"{model} {name} {device}".lower()
                if "2dc8" not in blob and "8bit" not in blob:
                    continue
                # Prefer only non-zero capacities; BT HID stub is always 0%
                cap = int(open(f"{root}/capacity", encoding="utf-8").read().strip())
                if not 1 <= cap <= 100:
                    continue
                charging = None
                if os.path.exists(f"{root}/status"):
                    st = open(f"{root}/status", encoding="utf-8").read().strip().lower()
                    if st == "charging":
                        charging = True
                    elif st in ("discharging", "full", "not charging"):
                        charging = False
                return cap, charging
            except (OSError, ValueError):
                continue
        return None

    def probe_hid_battery(self) -> Optional[tuple[int, Optional[bool]]]:
        paths: list[str] = []
        for name in sorted(os.listdir("/sys/class/hidraw")):
            try:
                text = open(
                    f"/sys/class/hidraw/{name}/device/uevent", encoding="utf-8"
                ).read()
            except OSError:
                continue
            if "00002DC8" not in text:
                continue
            # Skip pure IDLE receiver nodes for battery scan
            if "301C" in text.upper() and "IDLE" in text.upper():
                continue
            paths.append(f"/dev/{name}")
        for path in paths:
            try:
                fd = os.open(path, os.O_RDWR | os.O_NONBLOCK)
            except OSError:
                continue
            try:
                while select.select([fd], [], [], 0)[0]:
                    os.read(fd, 64)
                deadline = time.monotonic() + 0.4
                samples: list[tuple[int, bool]] = []
                while time.monotonic() < deadline:
                    ready, _, _ = select.select([fd], [], [], 0.1)
                    if not ready:
                        continue
                    data = os.read(fd, 64)
                    if len(data) < 15:
                        continue
                    if data[0] == 0x01:
                        raw = data[14]
                        pct = raw & 0x7F
                        charging = bool(raw & 0x80)
                        if 1 <= pct <= 100:
                            samples.append((pct, charging))
                if samples:
                    pcts = [s[0] for s in samples]
                    best = max(set(pcts), key=pcts.count)
                    charging = next(s[1] for s in samples if s[0] == best)
                    self._last_hid_pct = best
                    self._last_charging = charging
                    return best, charging
            finally:
                os.close(fd)
        if self._last_hid_pct is not None and self._last_hid_pct > 0:
            return self._last_hid_pct, self._last_charging
        return None

    def read(self) -> DeviceSnapshot:
        usb = self.usb_cable_present()
        receiver = self.receiver_present()
        linked = self.pad_linked_dongle()
        last_bt = self._load_last_bt()

        bt = self.bluetooth_battery()
        if bt is not None:
            pct, connected, detail = bt
            if connected:
                # USB cable + BT (unusual) → surface charging
                charging = True if usb else None
                if usb:
                    detail = f"{detail} · USB-Kabel"
                return DeviceSnapshot(
                    name="8BitDo 2C",
                    dongle=receiver or usb or connected,
                    connected=True,
                    percentage=pct,
                    charging=charging,
                    source="hid",
                    detail=detail,
                )
            # BT known but offline — fall through; may be on USB / 2.4 GHz

        if not receiver and not usb and not linked:
            return DeviceSnapshot(
                name="8BitDo 2C",
                dongle=False,
                connected=False,
                percentage=None,
                charging=None,
                source="none",
                detail="Weder Bluetooth noch Receiver/USB",
            )

        # USB cable: xpad sees the pad, but Ultimate 2C exposes no battery over USB
        # (no power_supply, no HID % on 2dc8:310a). Live % only via Bluetooth GATT.
        if usb and not linked:
            detail = "USB · lädt (~2h-Schätzung, kein Voll-Signal)"
            if last_bt is not None:
                detail += f" · Start BT {last_bt}%"
            if receiver:
                detail += " · 2.4-GHz-Dongle idle"
            return DeviceSnapshot(
                name="8BitDo 2C",
                dongle=True,
                connected=True,
                percentage=None,
                charging=True,
                source="none",
                detail=detail,
            )

        ps = self._power_supply_pct()
        if ps is not None and linked:
            pct, charging = ps
            return DeviceSnapshot(
                name="8BitDo 2C",
                dongle=receiver,
                connected=True,
                percentage=pct,
                charging=charging,
                source="hid",
                detail="Kernel power_supply",
            )

        hid = self.probe_hid_battery()
        if hid is not None and linked:
            pct, charging = hid
            return DeviceSnapshot(
                name="8BitDo 2C",
                dongle=receiver,
                connected=True,
                percentage=pct,
                charging=charging,
                source="hid",
                detail="HID-Telemetrie (2.4 GHz)",
            )

        if linked:
            detail = "2.4 GHz · kein Live-% (Schätzung)"
            if last_bt is not None:
                detail += f" · kalibriert von BT {last_bt}%"
            if usb:
                detail += " · + USB"
            return DeviceSnapshot(
                name="8BitDo 2C",
                dongle=receiver or usb,
                connected=True,
                percentage=None,
                charging=True if usb else None,
                source="none",
                detail=detail,
            )

        return DeviceSnapshot(
            name="8BitDo 2C",
            dongle=receiver or usb,
            connected=False,
            percentage=None,
            charging=None,
            source="none",
            detail="Receiver idle (Pad aus / nicht verbunden)",
        )


class EstimateStore:
    """Persisted coulomb-counter estimate when hardware % is unavailable.

    drain_hours: empty→full discharge runtime
    charge_hours: empty→full charge time (USB), optional
    """

    def __init__(
        self,
        path: str,
        drain_hours: float,
        charge_hours: Optional[float] = None,
    ) -> None:
        self.path = path
        self.full_hours = drain_hours
        self.charge_hours = charge_hours if charge_hours and charge_hours > 0 else None
        self.percentage = 70.0
        self.last_ts = time.time()
        self._load()

    def _load(self) -> None:
        if not os.path.exists(self.path):
            return
        try:
            data = open(self.path, encoding="utf-8").read().strip().split()
            self.percentage = float(data[0])
            self.last_ts = float(data[1])
        except (OSError, ValueError, IndexError):
            pass

    def save(self) -> None:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as fh:
            fh.write(f"{self.percentage:.4f} {time.time():.3f}\n")

    def set_percentage(self, pct: int) -> None:
        self.percentage = max(0.0, min(100.0, float(pct)))
        self.last_ts = time.time()
        self.save()

    def sync_from_disk(self) -> None:
        """Pick up calibrations written by backends (BT GATT) without restart."""
        if not os.path.exists(self.path):
            return
        try:
            data = open(self.path, encoding="utf-8").read().strip().split()
            file_pct = float(data[0])
            file_ts = float(data[1])
        except (OSError, ValueError, IndexError):
            return
        if file_ts > self.last_ts + 0.05:
            self.percentage = max(0.0, min(100.0, file_pct))
            self.last_ts = file_ts

    def tick(self, draining: bool = False, charging: bool = False) -> int:
        now = time.time()
        dt = max(0.0, now - self.last_ts)
        self.last_ts = now
        if charging and self.charge_hours:
            self.percentage = min(
                100.0,
                self.percentage + (dt / 3600.0) * (100.0 / self.charge_hours),
            )
        elif draining and self.full_hours > 0:
            self.percentage = max(
                0.0, self.percentage - (dt / 3600.0) * (100.0 / self.full_hours)
            )
        self.save()
        return int(round(self.percentage))
