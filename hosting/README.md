# Hosting the selo sites (one Hetzner server for the whole network)

All sites of the network live on the same server as rakovac.rs. Each site is a static Hugo build;
Caddy serves them all and gets their HTTPS certificates. The server pulls from GitHub every minute,
so publishing is just `git push`. The repos are public: no keys, tokens or passwords on the server
or in GitHub.

```
GitHub: kstein78/selo (engine + hosting/)      kstein78/vajska.rs, provala.rs, … (sites)
                 │                                       │
                 ▼  (user "deploy": after each rakovac.rs release + every minute from cron)
 server: /srv/rakovac/selo/engine     /srv/rakovac/selo/sites/<name>/{repo, releases/<sha>, current}
         hosting/selo-update ─builds─┘ /srv/rakovac/selo/caddy/<name>.caddy  ◄── made from the site's hugo.toml
         rakovac-update.timer → /srv/rakovac (rakovac.rs, as before; its build.sh starts selo-update)
         /etc/caddy/Caddyfile (from rakovac.rs/deploy) ── import /srv/rakovac/selo/caddy/*.caddy
```

| File | What it is |
|---|---|
| `sites.conf` | The list of sites: short name + repository. Add a line to add a site. |
| `selo-update` | Runs as the `deploy` user after each rakovac.rs release and every minute from cron: pulls the engine, builds every site whose `main` changed, writes its Caddy config, reloads Caddy through its local admin API and puts the old config back if Caddy refuses. |
| `build.sh` | Builds one commit (Hugo and Pagefind versions from the site's workflow), switches `current` atomically, keeps 3 releases. |
| `caddy_site.py` | Caddy config for a site from its `hugo.toml`: domain, www redirect, language redirect on `/` (Croatian browsers to `/hr/` where the site has it), `/weather.json` for the map centre, caching, 404 pages. |
| `install.sh` | Optional: run the same update by hand as root. |

## Setup: nothing to type on the server

rakovac.rs's `deploy/build.sh` starts `hosting/selo-update` (as the same `deploy` user) after every rakovac.rs
release; its first run builds the sites, writes their Caddy configs to `/srv/rakovac/selo/caddy/` (imported by
rakovac.rs's Caddyfile) and installs an every-minute cron entry for itself. No root, no keys.

For each new domain only DNS is needed:
1. **Hetzner Console → DNS → Add zone** `<domain>`: `A @`, `A www` → server IPv4; `AAAA @`, `AAAA www` → server IPv6
   (the address ending in `::1`). The same IPs as rakovac.rs.
2. **Webglobe → Moji domeni → the domain → Nameservers** → "Koristi DNS servere (upisane ispod)":
   `hydrogen.ns.hetzner.com`, `oxygen.ns.hetzner.com`, `helium.ns.hetzner.de`.
3. Caddy gets the HTTPS certificate by itself once DNS points at the server.

## A new site later

Create the site repo from the engine template, add one line to `sites.conf`, push, then steps 2–4.

## On the server (only if something is wrong)

```
tail -n 40 /srv/rakovac/selo/update.log          # builds, Caddy reloads, errors
cat /srv/rakovac/selo/sites/*/deployed /srv/rakovac/selo/sites/*/failed
ls /srv/rakovac/selo/caddy/ ; journalctl -u caddy -n 50   # web server and certificates
```

A failed build keeps the previous version live and is not retried until the next commit.
To roll back a site, revert the commit on GitHub.
