# Development journal — 8BitDo Ultimate 2C Battery Tray

Extended log of the AI-assisted development (Cursor Agent, 2026-10).

## Context

Request from **Morida**: show Ultimate 2C battery in a Linux tray — ideally over
2.4 GHz or USB, not only Bluetooth.

## Milestones

| Phase | Result |
|---|---|
| USB 310a / xpad | Device seen, no power_supply |
| hidraw features | No battery reports |
| usbmon / pyusb EP84 | Often silent when idle |
| Report 0x81 after LED | Identify/RF OK, no battery |
| Firmware docs (external) | 2.4 GHz does not carry battery channel |
| Bluetooth GATT | Reliable live % |
| Spike filter USB→BT | Drop high switch artefacts |
| UPower bug | Match 8BitDo devices only |
| Charge estimate + ETA | ~2 h, sync from disk |
| Repo split | Standalone project |

## Recommended measurement path

1. Unplug USB cable  
2. Connect pad over Bluetooth  
3. Tray shows live % and writes `last_bt` / `estimate`  
4. Return to 2.4 GHz / USB as needed  

## AI notice

Entire codebase and docs: **100% AI-generated** (see README).
