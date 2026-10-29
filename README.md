# 8BitDo Ultimate 2C Battery Tray (Linux / KDE)

StatusNotifier / Plasma tray for the **8BitDo Ultimate 2C Wireless** (incl. WUKONG):

- **Live battery %** via **Bluetooth GATT** (`org.bluez.Battery1`)
- **USB cable:** “charging” detection + time estimate (~2 h); no host full-charge signal
- **2.4 GHz dongle:** idle vs active link; **no** live % over the RF link

> ## 100% AI-generated
>
> **Development, implementation, USB/HID protocol work, and this documentation were
> created entirely by an AI (Cursor Agent).** There is no hand-written application
> code — only requirements, testing, and feedback by **Morida**. Please treat the
> project accordingly (review, security, support).

<details>
<summary>Deutsch (Kurzfassung)</summary>

Tray für Ultimate 2C: Live-% per Bluetooth; USB = Laden + Zeitschätzung; 2,4 GHz
ohne Live-%. Vollständig KI-generiert (Cursor Agent), Feedback durch Morida.
</details>

## Features

- Own tray icon (same battery-theme look as the MMX sister project)
- BT live % with spike filter (drop USB→BT switch artefacts ≥ +8 pp)
- Discharge estimate (~18 h default); **learns runtime** from BT sync pairs
  (connected drain time + `%` drop → `drain_hours`)
- USB charge estimate with ETA; charge hours can also be learned from BT samples
- CLI: `8bitdo-2c-battery-status`
- systemd user service + autostart
- **Combined tray:** if [`mmx200-battery-tray`](https://github.com/MoridaDE/mmx200-battery-tray) is also installed, **one** StatusNotifier icon covers both devices (MMX hosts it; this unit stays disabled)

## Requirements

- Python 3.11+, PyQt6, dbus-python
- BlueZ (for live %)
- Optional: USB cable / 2.4 GHz receiver (`2dc8:310a`, `2dc8:301c`, …)
- udev `uaccess` for hidraw

## Installation

```bash
git clone https://github.com/MoridaDE/8bitdo-2c-battery-tray.git
cd 8bitdo-2c-battery-tray
pip install --user -r requirements.txt
./install.sh
sudo cp packaging/71-8bitdo-2c-hidraw.rules /etc/udev/rules.d/
sudo udevadm control --reload && sudo udevadm trigger
```

```bash
8bitdo-2c-battery-status
systemctl --user status 8bitdo-2c-battery-tray.service
```

Config: `~/.config/8bitdo-2c-battery/`  
(`estimate`, `last_bt`, `drain_hours`, `drain_samples.json`, `charge_samples.json`, `charge_hours`, `state.json`).

## Usage

| Situation | Display |
|---|---|
| Bluetooth only (no USB cable) | live % (GATT) — best for calibration |
| USB cable plugged | “charging” + estimate / ETA (no full-signal from host) |
| 2.4 GHz receiver idle | disconnected / idle |
| Brief BT while/after charging | refreshes `last_bt` + estimate; may learn drain/charge hours |

**Tip:** For a clean reading, **unplug USB**, then connect Bluetooth — otherwise GATT
may briefly spike to high artefact values when switching (filtered out).

## Open goal / contributing

The real goal is to read the battery **live and directly from the manufacturer
dongle / USB path**, without needing Bluetooth. No working method has been found
yet, so this project uses a Bluetooth GATT workaround (plus charge/estimate
context when only the cable or 2.4 GHz receiver is in use).

If you find a way to query capacity over the Ultimate 2C receiver or USB HID
interfaces, please open an issue or pull request — contributions that replace or
improve on the Bluetooth detour are very welcome.

## Development journal (protocol)

1. **Goal:** Battery in a Linux tray (2.4 GHz and/or USB). Neither Windows nor the
   official 8BitDo tooling exposes a system-tray battery for this pad.
2. **USB `2dc8:310a`:** xpad on interface 0 (XInput) plus HID ifaces; no pad `power_supply`.
3. **hidraw:** no spontaneous battery input reports; `GET_FEATURE` empty.
4. **pyusb / EP 0x84:** often **no** interrupt IN packets while idle/charging.
5. **Vendor report `0x81`** (after XInput LED `01 03 xx`, interface 2):
   - Identify / `66 aa 63` (RF address, version) — **no** battery field.
   - Class-`05` ACKs echo commands; no capacity.
6. **Public firmware notes** (ascendedent/8bitdo-Linux-Software): report `0x81` on the
   2.4 GHz path does not reliably reach pad battery/settings; host often talks to
   receiver firmware only.
7. **Bluetooth:** reliable live % via `Battery1`. Spike filter for USB+BT; UPower
   matching fixed so other bluez devices (e.g. MMX) cannot poison pad state.
8. **Estimate:** drain ~18 h, charge ~2 h; tray syncs BT calibrations from disk.
9. **Split:** extracted from a combined device-battery tray into this repo.

**Conclusion:** Live % over USB/dongle is **not** available on this model; Bluetooth
is the measurement path, USB is charge/estimate context only.

More detail: [`docs/JOURNAL.md`](docs/JOURNAL.md).

## Layout

```
src/backend.py        # BlueZ/UPower, USB detect, spike filter, EstimateStore
src/tray.py           # PyQt6 StatusNotifierItem (solo; exits if combined)
src/combined_tray.py  # Shared with MMX sister (same module, dual install)
src/status.py         # JSON CLI
packaging/            # udev, systemd --user, .desktop
install.sh
```

## Sister project

Beyerdynamic MMX 200: [`mmx200-battery-tray`](https://github.com/MoridaDE/mmx200-battery-tray).
Install both → one combined tray icon (MMX unit hosts it; this unit is disabled).

## License

MIT — see `LICENSE`.

## Disclaimer

Not official 8BitDo software. Protocol/firmware may change. Use at your own risk.
