#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
SHARE="${XDG_DATA_HOME:-$HOME/.local/share}/8bitdo-2c-battery-tray"
BIN="${XDG_BIN_HOME:-$HOME/.local/bin}"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
AUTO_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/autostart"
APP_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"

mkdir -p "$SHARE" "$BIN" "$UNIT_DIR" "$AUTO_DIR" "$APP_DIR"
install -m 0644 "$ROOT/src/backend.py" "$SHARE/backend.py"
install -m 0755 "$ROOT/src/tray.py" "$SHARE/tray.py"
install -m 0755 "$ROOT/src/status.py" "$SHARE/status.py"

cat > "$BIN/8bitdo-2c-battery-tray" <<EOF
#!/bin/sh
exec /usr/bin/python3 "$SHARE/tray.py" "\$@"
EOF
cat > "$BIN/8bitdo-2c-battery-status" <<EOF
#!/bin/sh
exec /usr/bin/python3 "$SHARE/status.py" "\$@"
EOF
chmod 0755 "$BIN/8bitdo-2c-battery-tray" "$BIN/8bitdo-2c-battery-status"

install -m 0644 "$ROOT/packaging/8bitdo-2c-battery-tray.service" "$UNIT_DIR/"
install -m 0644 "$ROOT/packaging/8bitdo-2c-battery-tray.desktop" "$AUTO_DIR/"
install -m 0644 "$ROOT/packaging/8bitdo-2c-battery-tray.desktop" "$APP_DIR/"

echo "Optional udev rule (once, with sudo):"
echo "  sudo cp $ROOT/packaging/71-8bitdo-2c-hidraw.rules /etc/udev/rules.d/"
echo "  sudo udevadm control --reload && sudo udevadm trigger"

systemctl --user daemon-reload
systemctl --user enable --now 8bitdo-2c-battery-tray.service
echo "Installed. Check status with: 8bitdo-2c-battery-status"
