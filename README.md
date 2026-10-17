# 8BitDo Ultimate 2C Battery Tray (Linux / KDE)

Plasma-/StatusNotifier-Tray für den **8BitDo Ultimate 2C Wireless** (u. a. WUKONG):

- **Live-Akku-%** über **Bluetooth GATT** (`org.bluez.Battery1`)
- **USB-Kabel:** Erkennung „lädt“, Zeitschätzung (~2 h), kein Hardware-Voll-Signal
- **2,4‑GHz-Dongle:** Link idle vs. aktiv; **kein** Live-% über die Funkstrecke

> ## 100 % KI-generiert
>
> **Entwicklung, Implementierung, USB/HID-Protokollversuche und diese Dokumentation
> wurden vollständig von einer KI (Cursor Agent) erstellt.** Es gab keinen manuellen
> Anwendungscode von Menschenhand — nur Anforderungen, Tests und Feedback durch
> den Nutzer (Niels). Bitte entsprechend einordnen (Review, Security, Support).

## Features

- Eigenes Tray-Icon (gleiche Battery-Theme-Optik wie das MMX-Schwesterprojekt)
- BT-Live-% mit Spike-Filter (USB→BT-Umschalt-Artefakte ≥+8 pp verwerfen)
- USB-Lade-Schätzung mit ETA; Kalibrierung durch BT-Ist-Wert + Timestamp
- CLI: `8bitdo-2c-battery-status`
- systemd-user-Service + Autostart

## Voraussetzungen

- Python 3.11+, PyQt6, dbus-python
- BlueZ (für Live-%)
- Optional: USB-Kabel / 2,4‑GHz-Receiver (`2dc8:310a`, `2dc8:301c`, …)
- udev `uaccess` für hidraw

## Installation

```bash
git clone <dieses-repo>
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

Konfiguration: `~/.config/8bitdo-2c-battery/`  
(`estimate`, `last_bt`, `charge_samples.json`, `charge_hours`, `state.json`).

## Nutzung

| Situation | Anzeige |
|---|---|
| Nur Bluetooth (kein USB-Kabel) | Live-% (GATT) — empfohlen zum Kalibrieren |
| USB-Kabel steckt | „lädt“ + Schätzung / ETA (kein Voll-Signal vom Host) |
| 2,4‑GHz-Receiver idle | getrennt / idle |
| BT kurz anbinden während/nach Laden | setzt `last_bt` + Schätzung neu |

**Tipp:** Zum Messen **USB-Kabel ziehen**, dann BT verbinden — sonst kann GATT
beim Umschalten kurz auf hohe Artefakt-Werte springen (werden gefiltert).

## Protokoll-Journal (Entwicklung)

1. **Ziel:** Akku im Tray unter Linux (2,4 GHz und/oder USB), vergleichbar Windows.
2. **USB `2dc8:310a`:** xpad auf Interface 0 (XInput), zusätzlich HID ifaces; kein
   `power_supply` für den Pad.
3. **hidraw:** Keine spontanen Battery-Input-Reports; `GET_FEATURE` leer.
4. **pyusb / Endpoint 0x84:** Im Idle/Laden oft **keine** Interrupt-IN-Pakete.
5. **Vendor Report `0x81`** (nach XInput-LED `01 03 xx`, Interface 2):
   - Antworten auf Identify / `66 aa 63` (RF-Adresse, Version) — **kein** Akku-Feld.
   - Class-`05`-ACKs spiegeln Kommandos, liefern keine Capacity.
6. **Firmware-Analyse (öffentlich, ascendedent/8bitdo-Linux-Software):** Report `0x81`
   auf dem 2,4‑GHz-Pfad erreicht die Pad-Settings/Akku-Logik nicht zuverlässig;
   Host spricht oft nur Receiver-Firmware.
7. **Bluetooth:** Zuverlässiger Live-% über `Battery1`. Filter gegen USB+BT-Spikes;
   Bugfix: UPower „irgendein bluez“ hatte kurz MMX-Werte dem Pad zugeordnet.
8. **Schätzung:** Entladen ~18 h, Laden ~2 h; Tray synct BT-Kalibrierungen von Disk.
9. **Abspaltung:** Aus kombiniertem device-battery-Tray als eigenes Repo.

**Fazit:** Live-Ist-% über USB/Dongle auf diesem Modell **nicht** verfügbar;
Bluetooth bleibt der Messweg, USB nur Lade-/Schätzkontext.

## Architektur

```
src/backend.py   # BlueZ/UPower, USB-Erkennung, Spike-Filter, EstimateStore
src/tray.py      # PyQt6 StatusNotifierItem
src/status.py    # JSON-CLI
packaging/       # udev, systemd --user, .desktop
install.sh
```

## Schwesterprojekt

Für das Beyerdynamic MMX 200: separates Repo `mmx200-battery-tray` (gleicher
Tray-Stil, eigene systemd-Unit).

## Lizenz

MIT — siehe `LICENSE`.

## Haftungsausschluss

Keine offizielle 8BitDo-Software. Protokoll/Firmware können sich ändern.
Nutzung auf eigene Gefahr.
