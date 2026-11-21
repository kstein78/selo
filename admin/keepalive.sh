#!/bin/bash
# Keeps Selo Admin running on the server as the "deploy" user (no root, no systemd unit needed).
# Started every minute by hosting/selo-update; restarts the admin when it is not answering or when its code
# changed (a new engine version). Log: ~/selo/admin-data/admin.log
set -uo pipefail
umask 077
ADMIN=$(cd "$(dirname "$0")" && pwd)
DATA=${SELO_ADMIN_DATA:-$HOME/selo/admin-data}
PORT=${SELO_ADMIN_PORT:-8737}
mkdir -p "$DATA" && chmod 700 "$DATA"
log=$DATA/admin.log
[ -f "$log" ] && [ "$(stat -c %s "$log")" -gt 2000000 ] && tail -n 5000 "$log" > "$log.tmp" && mv "$log.tmp" "$log"
ver=$(cat "$ADMIN"/run.py "$ADMIN"/app/*.py "$ADMIN"/static/*.js "$ADMIN"/static/*.css 2>/dev/null | sha256sum | cut -c1-12)
pid=$(cat "$DATA/admin.pid" 2>/dev/null || true)
alive=0
if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
  curl -fsS -o /dev/null --max-time 5 "http://127.0.0.1:$PORT/admin/login" && alive=1
fi
if [ "$alive" = 1 ] && [ "$ver" = "$(cat "$DATA/admin.version" 2>/dev/null)" ]; then exit 0; fi
if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then kill "$pid"; sleep 1; fi
echo "$(date '+%F %T') starting Selo Admin $ver" >> "$log"
cd "$ADMIN"
# 9>&- : do not inherit selo-update's lock (fd 9), or the next selo-update runs would wait for the admin forever
SELO_ADMIN_DATA=$DATA SELO_ADMIN_PORT=$PORT nohup python3 run.py < /dev/null >> "$log" 2>&1 9>&- &
echo $! > "$DATA/admin.pid"
echo "$ver" > "$DATA/admin.version"
