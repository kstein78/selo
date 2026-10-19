#!/bin/bash
# One-time setup of the selo sites on the server that already serves rakovac.rs (Ubuntu 24.04, Caddy).
# Run as root:   curl -fsSL https://raw.githubusercontent.com/kstein78/selo/main/hosting/install.sh | sudo bash
# Safe to run again. Changes nothing for rakovac.rs: its own updater and Caddyfile stay as they are;
# rakovac.rs's Caddyfile only imports /etc/caddy/sites/*.caddy, where this updater puts the other sites.
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "run as root (sudo)" >&2; exit 1; }
command -v caddy >/dev/null || { echo "Caddy is not installed: this script expects the rakovac.rs server" >&2; exit 1; }
DEBIAN_FRONTEND=noninteractive apt-get install -y -q git curl python3 python3-yaml >/dev/null
id deploy >/dev/null 2>&1 || useradd --system --shell /bin/bash --home-dir /srv/selo deploy
install -d -o deploy -g deploy -m 755 /srv/selo /srv/selo/sites /srv/selo/bin
install -d -m 755 /etc/caddy/sites
cd /srv/selo
[ -d engine/.git ] || runuser -u deploy -- env HOME=/srv/selo git clone -q https://github.com/kstein78/selo.git engine
install -m 755 engine/hosting/selo-update /usr/local/sbin/selo-update
cat > /etc/systemd/system/selo-update.service <<'UNIT'
[Unit]
Description=Update the selo network sites from GitHub
Wants=network-online.target
After=network-online.target caddy.service

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/selo-update
TimeoutStartSec=30min
UNIT
cat > /etc/systemd/system/selo-update.timer <<'UNIT'
[Unit]
Description=Check GitHub for new versions of the selo sites every minute

[Timer]
OnBootSec=45s
OnUnitInactiveSec=1min
AccuracySec=5s

[Install]
WantedBy=timers.target
UNIT
systemctl daemon-reload
echo "first build of every site (a few minutes)..."
/usr/local/sbin/selo-update
systemctl enable --now selo-update.timer
echo
echo "Done. Sites on this server:"
for d in /srv/selo/sites/*/; do n=$(basename "$d"); printf '  %-10s %s\n' "$n" "$(cat "$d/deployed" 2>/dev/null || echo 'not built: journalctl -u selo-update')"; done
ls /etc/caddy/sites/
grep -q 'import /etc/caddy/sites/\*.caddy' /etc/caddy/Caddyfile && echo "Caddy imports them: OK" \
  || echo "Caddy does not import /etc/caddy/sites yet: wait a minute for rakovac.rs's Caddyfile update (journalctl -u rakovac-update)"
