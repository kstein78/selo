#!/bin/bash
# Not needed any more: rakovac.rs's deploy/build.sh starts hosting/selo-update by itself after every
# rakovac.rs release, and selo-update then installs its own every-minute cron entry (as the deploy user).
# This script only does the same by hand, e.g. to rebuild right now:
#   sudo bash install.sh        (or, as the deploy user: bash /srv/rakovac/selo/engine/hosting/selo-update)
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "run as root (sudo)" >&2; exit 1; }
runuser -u deploy -- env HOME=/srv/rakovac bash -c '
  mkdir -p ~/selo
  [ -d ~/selo/engine/.git ] || git clone -q https://github.com/kstein78/selo.git ~/selo/engine
  bash ~/selo/engine/hosting/selo-update
  tail -n 20 ~/selo/update.log'
