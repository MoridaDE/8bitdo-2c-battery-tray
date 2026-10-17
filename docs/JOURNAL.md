# Entwicklungsjournal — 8BitDo Ultimate 2C Battery Tray

Ausführlicheres Log der KI-gestützten Entwicklung (Cursor Agent, 2026-10).

## Kontext

Nutzerwunsch: Akkustand des Ultimate 2C unter Linux im Tray — ideal über
2,4 GHz oder USB, nicht nur Bluetooth.

## Meilensteine

| Phase | Ergebnis |
|---|---|
| USB 310a / xpad | Gerät erkannt, kein power_supply |
| hidraw Features | Keine Battery-Reports |
| usbmon / pyusb EP84 | Idle oft still |
| Report 0x81 nach LED | Identify/RF ok, kein Akku |
| Firmware-Doku (extern) | 2,4 GHz trägt Akku-Kanal nicht |
| Bluetooth GATT | Live-% zuverlässig |
| Spike-Filter USB→BT | Hohe Umschalt-Werte verwerfen |
| UPower-Bug | Nur noch 8BitDo-Modelle matchen |
| Lade-Schätzung + ETA | ~2 h, synct von Disk |
| Repo-Split | Eigenständiges Projekt |

## Empfohlener Messweg

1. USB-Kabel trennen  
2. Pad per Bluetooth verbinden  
3. Tray zeigt Live-% und schreibt `last_bt` / `estimate`  
4. Danach wieder 2,4 GHz / USB nach Bedarf  

## KI-Hinweis

Gesamte Codebasis und Docs: **100 % KI-generiert** (siehe README).
