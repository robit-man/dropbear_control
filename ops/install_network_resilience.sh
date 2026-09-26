#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
DISPATCHER_TARGET="/etc/NetworkManager/dispatcher.d/90-dropbear-wifi-policy-routing"

if [[ ${EUID} -ne 0 ]]; then
    echo "Run with sudo: sudo $0" >&2
    exit 1
fi

install -o root -g root -m 0755 \
    "$SCRIPT_DIR/dropbear-wifi-policy-routing" \
    "$DISPATCHER_TARGET"

"$DISPATCHER_TARGET" wlan0 up

echo "Installed Wi-Fi source routing dispatcher: $DISPATCHER_TARGET"
ip -4 rule show priority 1138
ip -4 route show table 138
