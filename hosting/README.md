# Hosting the selo sites (one Hetzner server for the whole network)

All sites of the network live on the same server as rakovac.rs. Each site is a static Hugo build;
Caddy serves them all and gets their HTTPS certificates. The server pulls from GitHub every minute,
so publishing is just `git push`. The repos are public: no keys, tokens or passwords on the server
or in GitHub.

```
GitHub: kstein78/selo (engine + hosting/)      kstein78/vajska.rs, provala.rs, … (sites)
                 │  every minute                         │  every minute
                 ▼                                       ▼
 server: /srv/selo/engine            /srv/selo/sites/<name>/{repo, releases/<sha>, current}
         selo-update.timer ──builds──┘    /etc/caddy/sites/<name>.caddy  ◄── made from the site's hugo.toml
         rakovac-update.timer → /srv/rakovac (rakovac.rs, unchanged)
         /etc/caddy/Caddyfile (from rakovac.rs/deploy) ── import /etc/caddy/sites/*.caddy
```

| File | What it is |
|---|---|
| `sites.conf` | The list of sites: short name + repository. Add a line to add a site. |
| `selo-update` | Runs every minute: pulls the engine, builds every site whose `main` changed, writes its Caddy config, reloads Caddy only if the whole config validates. Updates itself. |
| `build.sh` | Builds one commit (Hugo and Pagefind versions from the site's workflow), switches `current` atomically, keeps 3 releases. |
| `caddy_site.py` | Caddy config for a site from its `hugo.toml`: domain, www redirect, language redirect on `/` (Croatian browsers to `/hr/` where the site has it), `/weather.json` for the map centre, caching, 404 pages. |
| `install.sh` | One-time setup on the rakovac.rs server. |

## One-time setup

Best order: DNS first (steps 2–3), then the server (step 1), so Caddy finds the domain already pointing
at the server and gets the certificate on the first try. The other order also works, it just takes longer.

1. **Server** (Hetzner Console → the rakovac.rs server → Console, or SSH as root):
   ```
   curl -fsSL https://raw.githubusercontent.com/kstein78/selo/main/hosting/install.sh | sudo bash
   ```
   It builds every site in `sites.conf` and prints what is live. rakovac.rs is not touched.
2. **DNS for each domain** (Hetzner Console → DNS → Add zone `vajska.rs`, then `provala.rs`):
   `A @` and `A www` → the server IPv4; `AAAA @` and `AAAA www` → the server IPv6 (the address ending in `::1`).
   The same IPs as rakovac.rs.
3. **Registrar** (Webglobe → Moji domeni → the domain → Nameservers → "Koristi DNS servere (upisane ispod)"):
   `hydrogen.ns.hetzner.com`, `oxygen.ns.hetzner.com`, `helium.ns.hetzner.de` → Izmeni Name servere.
4. Wait for DNS (1–2 hours, up to 24). Caddy gets the certificates by itself (it retries).

## A new site later

Create the site repo from the engine template, add one line to `sites.conf`, push, then steps 2–4.

## On the server (only if something is wrong)

```
journalctl -u selo-update -n 50                 # builds, Caddy reloads, errors
cat /srv/selo/sites/vajska/deployed /srv/selo/sites/vajska/failed
systemctl start selo-update                     # check GitHub right now
ls /etc/caddy/sites/ ; journalctl -u caddy -n 50   # web server and certificates
```

A failed build keeps the previous version live and is not retried until the next commit.
To roll back a site, revert the commit on GitHub.
