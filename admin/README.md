# Selo Admin

The editors' admin for every site of the network (rakovac.rs, vajska.rs, provala.rs and future ones), at
**https://rakovac.rs/admin/**. Plain Python 3 standard library + vendored PyYAML (pure Python), no packages to install.

## How it works

- **Git stays the source of truth.** Every save is a commit to the site's repository on GitHub, signed with the editor's
  name; the server then rebuilds the site as before (within about a minute). Every change can be undone from the log.
- The admin keeps its own clone of each site in `~/selo/admin-data/repos/<site>`; a write syncs it to `origin/main`,
  applies the change, regenerates the Serbian Cyrillic copy (`sr_cyrl.py` of the site) when Serbian changed, commits
  and pushes; if somebody pushed in between, it syncs and applies the change again (3 attempts). Edits carry the hash
  of the text the editor started from, so a page changed meanwhile is never overwritten silently.
- **Sites** come from `admin/sites.conf` (rakovac.rs, which has its own code) and the engine's `hosting/sites.conf`:
  a new site of the network appears in the admin by itself. Languages, domain and title are read from its `hugo.toml`;
  the generated Cyrillic language is not edited directly.
- **Preview** is rendered in the browser with the site's own CSS and fonts (Markdown + the shortcodes `photo`,
  `photos`, `note`, `todo`, `relref`); building with Hugo on the server would take ~50 s and ~900 MB per site.
- **Hidden** pages get `draft: true` in every language (Hugo does not publish them); **deleted** pages are removed in
  every language (undo from the log restores them).
- **Home page order:** news with `pin: 1, 2, …` open the news list in that order (`layouts/partials/news-items.html`
  of the engine and of rakovac.rs); without pins the old rule applies (`top: true`, otherwise the newest).
- **Photos** are rotated, cropped and resized (max 2000 px, JPEG 85 %) in the browser: the uploaded file has no EXIF or
  GPS data. They land in `static/img/<key>.jpg` and `data/photos.yaml` with author and licence.

## Users and rights

Login: password (scrypt) + six-digit code from an authenticator app (TOTP, RFC 6238), required for everyone.
5 failed attempts per account or per IP address block logins for 15 minutes. Sessions end after 12 h without activity
(14 days at most); a password change logs out the other devices.

| Role | Rights |
|---|---|
| Owner | everything on every site, users, settings (GitHub key) |
| Site administrator | view, edit, create, publish, hide, **delete**, photos, news order, review, users of that site |
| Editor | view, edit, create, publish, hide, photos, news order, review — **no delete** |
| Author | view, edit, create: everything goes to the **review queue**; an editor publishes it (commit in the author's name) |
| Viewer | view only |

A role is given per site or for "all sites (and future ones)"; single rights can be added or removed on top of the
role. New users get a temporary password shown once; at the first login they enable the code and set their own password.

## Security notes

- Cookie: HttpOnly, Secure, SameSite=Strict, path `/admin/`; every POST needs the session's CSRF token and a matching
  `Origin`. Content-Security-Policy without inline scripts; the preview frame is sandboxed without scripts, Markdown
  is rendered with raw HTML off.
- The GitHub key (fine-grained token, *Contents: read and write* on the site repositories only) is entered by the owner
  on the Settings page and stored in `~/selo/admin-data/github-token` (mode 600). It is never shown again, never in Git.
- The first owner is created at `/admin/setup` with a one-time code; only its SHA-256 is in the repository
  (`bootstrap.sha256`), and the page closes for good as soon as one user exists.
- Data (`admin-data/`: database, clones, token, log) is private to the deploy user (umask 077) and outside every served folder.

## Running

On the server nothing is typed: `hosting/selo-update` (every minute, user `deploy`) runs `admin/keepalive.sh`, which
starts `run.py` on 127.0.0.1:8737 if it is not answering or its code changed; rakovac.rs's Caddyfile sends `/admin*`
there. Log: `/srv/rakovac/selo/admin-data/admin.log`.

Locally (against bare test repos):

```
SELO_ADMIN_DATA=/tmp/adm SELO_ADMIN_REMOTE_DIR=/tmp/remotes SELO_ADMIN_INSECURE_COOKIE=1 \
SELO_ADMIN_ORIGIN=http://127.0.0.1:8737 python3 admin/run.py
python3 -m unittest discover -s admin/tests
```

## Next steps

- Translation button (Claude API) for pages written in one language; locking a hand-made translation.
- Visual editing directly on the page (WYSIWYG) once the Markdown round trip is proven loss-free on all pages.
- Pending photo uploads for authors; menu editing; gallery albums; Telegram bot on the same rights model.
