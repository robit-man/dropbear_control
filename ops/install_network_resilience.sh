#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
WIFI_DISPATCHER_TARGET="/etc/NetworkManager/dispatcher.d/90-dropbear-wifi-policy-routing"
ETHERNET_DISPATCHER_TARGET="/etc/NetworkManager/dispatcher.d/91-dropbear-ethernet-hardening"
WATCHDOG_TARGET="/usr/local/sbin/dropbear-ethernet-watchdog"
WATCHDOG_SERVICE_TARGET="/etc/systemd/system/dropbear-ethernet-watchdog.service"
WATCHDOG_TIMER_TARGET="/etc/systemd/system/dropbear-ethernet-watchdog.timer"
SYSCTL_TARGET="/etc/sysctl.d/90-dropbear-multihoming.conf"

if [[ ${EUID} -ne 0 ]]; then
    echo "Run with sudo: sudo $0" >&2
    exit 1
fi

install -o root -g root -m 0755 \
    "$SCRIPT_DIR/dropbear-wifi-policy-routing" \
    "$WIFI_DISPATCHER_TARGET"
install -o root -g root -m 0755 \
    "$SCRIPT_DIR/dropbear-ethernet-hardening" \
    "$ETHERNET_DISPATCHER_TARGET"
install -o root -g root -m 0755 \
    "$SCRIPT_DIR/dropbear-ethernet-watchdog" \
    "$WATCHDOG_TARGET"
install -o root -g root -m 0644 \
    "$SCRIPT_DIR/dropbear-ethernet-watchdog.service" \
    "$WATCHDOG_SERVICE_TARGET"
install -o root -g root -m 0644 \
    "$SCRIPT_DIR/dropbear-ethernet-watchdog.timer" \
    "$WATCHDOG_TIMER_TARGET"
install -o root -g root -m 0644 \
    "$SCRIPT_DIR/dropbear-multihoming.conf" \
    "$SYSCTL_TARGET"

"$WIFI_DISPATCHER_TARGET" wlan0 up
"$ETHERNET_DISPATCHER_TARGET" eth1 up
sysctl --system >/dev/null
systemctl daemon-reload
systemctl enable --now dropbear-ethernet-watchdog.timer

echo "Installed Wi-Fi source routing dispatcher: $WIFI_DISPATCHER_TARGET"
echo "Installed Ethernet hardening dispatcher: $ETHERNET_DISPATCHER_TARGET"
echo "Installed Ethernet watchdog: $WATCHDOG_TIMER_TARGET"
ip -4 rule show priority 1138
ip -4 route show table 138
ethtool --show-eee eth1
systemctl --no-pager status dropbear-ethernet-watchdog.timer
