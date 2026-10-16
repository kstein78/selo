# News admin and social posting: architecture

Status: design + foundations in place (October 2026). Nothing here runs yet; this is the plan the engine is built for.

## Principle: Git stays the source of truth

Every site is a Git repository. Any admin (a Telegram bot, a web form, a person with an editor) only **creates
commits** in that repository. The site then builds as usual (GitHub Actions + the Hetzner server pulling `main`).
This keeps one way of publishing, full history, and a one-click undo (`git revert`) for every news item.

```
editor ──▶ Telegram bot / web admin ──▶ scripts/new_news.py ──▶ commit to <site>.rs ──▶ build ──▶ site + RSS
                                                                                     └──▶ social poster (reads RSS / "social:")
```

## What is already in the engine

- `scripts/new_news.py`: one entry point that turns a JSON/YAML item into news files in every language given
  (`content/<lang>/news/<date>-<slug>.md`), with `feed`, `author`, `cover` and an optional `social:` list
  (channels for autoposting). The bot and any future web form call this; nothing else writes news.
- `data/authors.yaml` + `author:` in front matter: visible byline and schema.org author (Google E-E-A-T, Discover).
- RSS for the home page and for every section (`[outputs] section = ["HTML", "RSS"]` in the site config), linked
  from every page head: feed readers, Google "Follow" and autoposting tools (Make, Zapier, IFTTT, Buffer) read it.
- `translate.py`: missing languages are filled from English by the Translate workflow (needs the repository secret
  `ANTHROPIC_API_KEY`); `sr_cyrl.py` makes the Serbian Cyrillic copy.

## Telegram bot (phase 1)

One bot for the whole network; each editor is allowed only on their own sites.

- **Who may post:** a server-side allow-list `ADMINS={telegram_user_id: [sites]}` (environment / config file on
  the server, never in the repo). The bot checks `message.from.id` on every update. Telegram fills this field on its
  servers; a user cannot forge it. Usernames and display names are never trusted (they can change).
- **No self-promotion:** there is no command that adds admins. The list changes only on the server, by the owner.
  Being an admin of a Telegram *group* where the bot sits gives no rights in the bot.
- **Webhook protection:** the webhook is set with `secret_token`; requests without the matching
  `X-Telegram-Bot-Api-Secret-Token` header are dropped, so nobody can post fake updates to the bot's URL.
- **GitHub access:** a fine-grained token limited to the site repositories, permission *Contents: read and write*
  only, with an expiry date. Stored on the server, not in the bot code.
- **Flow:** editor sends text and photos → bot shows a preview (title, lead, language, site) → editor presses
  "Publish" → bot calls `new_news.py` and commits as "News: <title> (via bot, <editor name>)". "Undo" reverts that
  commit. Every action is logged with the Telegram id.
- **Photos:** resized on the server (max 1600 px, EXIF/GPS stripped), saved to `static/img/news/`, registered in
  `data/photos.yaml` with the author and licence the editor confirms.
- **Real risks** and their answers: theft of the bot token (rotate with @BotFather, keep it only on the server);
  takeover of an editor's Telegram account (two-step verification required for editors); a wrong post (preview +
  undo; the site build only publishes what is in Git).

## Web admin (phase 2, optional)

A Git-based CMS (Decap CMS or its successor Sveltia CMS) at `/admin/` on each site, signing in with GitHub: only
collaborators of the repository can edit, and every save is a commit. Good for longer articles and photo galleries;
the bot stays the fastest way for short news from a phone.

## Social posting (phase 3)

- Instagram/Facebook: Meta Graph API with a Page/Instagram professional account token kept on the server; a small
  job reads new items that have `social:` and posts the cover photo + lead + link. Tokens are entered by the owner
  only, never in chat or in the repo.
- Telegram channel / Viber community: the same job, via their bot APIs.
- Zero-code alternative: point Make/Zapier/Buffer at the section RSS feed.
