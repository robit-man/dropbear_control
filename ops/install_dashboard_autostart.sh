#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
user_unit_dir=${XDG_CONFIG_HOME:-"$HOME/.config"}/systemd/user
autostart_dir=${XDG_CONFIG_HOME:-"$HOME/.config"}/autostart
application_dir=${XDG_DATA_HOME:-"$HOME/.local/share"}/applications

mkdir -p "$user_unit_dir" "$autostart_dir" "$application_dir"
install -m 0644 "$repo_root/ops/dropbear-dashboard.service" \
  "$user_unit_dir/dropbear-dashboard.service"
install -m 0644 "$repo_root/ops/dropbear-status.desktop" \
  "$application_dir/dropbear-status.desktop"
install -m 0644 "$repo_root/ops/dropbear-status.desktop" \
  "$autostart_dir/dropbear-status.desktop"

systemctl --user disable --now dropbear-status.service 2>/dev/null || true
rm -f "$user_unit_dir/dropbear-status.service"
systemctl --user daemon-reload
systemctl --user enable --now dropbear-dashboard.service

printf 'Dashboard service enabled: http://127.0.0.1:8000\n'
printf 'Desktop status indicator registered for graphical-session autostart.\n'
