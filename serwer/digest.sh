#!/bin/bash
# Orion — digest huntera 24/7 na VPS. Wywoływany z /etc/cron.d/wow_digest
export WOW_SCOUT_OUT=/root/wow_digest/dane
cd /root/wow_digest || exit 1
mkdir -p dane
if command -v flock >/dev/null 2>&1; then
  exec 9>/root/wow_digest/.lock
  flock -n 9 || { echo "$(date '+%F %T') — inny przebieg trwa, pomijam"; exit 0; }
fi
echo "=== $(date '+%F %T') START ==="
python3 scout.py
echo "=== hermes one-shot ==="
timeout 900 hermes chat -q "$(cat prompt.txt)" -Q
echo "=== $(date '+%F %T') KONIEC ==="
