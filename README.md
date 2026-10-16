# selo: shared engine for the village sites of Vojvodina

Hugo theme + scripts behind a small network of local sites: [rakovac.rs](https://rakovac.rs) (the original),
[vajska.rs](https://vajska.rs) and [provala.rs](https://provala.rs). One engine, one look, each site with its own
colours, emblem, languages and content. *Selo* means "village" in Serbian.

Licences: code MIT; Rakovac Common font SIL OFL 1.1; Rakovac Capital font © rakovac.rs (see `static/fonts/`).

## How a site uses it

A site repository contains only its own content, data, colours and images, and pulls the engine as a Git submodule:

```
<site>.rs/
  hugo.toml              # theme = "selo", languages, [params] (map centre, emblem, capital palette, share card)
  themes/selo/           # this repository (git submodule)
  content/<lang>/        # pages; content/cyr is generated from content/sr
  data/                  # nav.yaml, photos.yaml, authors.yaml, sister.yaml, cyrillic.yaml, sitenews.yaml
  i18n/<lang>.yaml       # only the strings that differ from the engine (brand name, region, ...)
  assets/css/site.css    # the site's colours (CSS variables on :root, light and dark)
  static/                # emblem, icons, recoloured capital font, images
```

Site files override engine files with the same path (Hugo theme lookup), so a site can replace any template too.

## Start a new site

1. Create the empty repository, then `git submodule add https://github.com/kstein78/selo themes/selo`.
2. Copy `hugo.toml`, `data/` and `.github/workflows/deploy.yml` from a sister site; set `baseURL`, languages,
   `mapCenter`, `[params.emblem]`, `[params.capital]`, `[params.share]`, `[params.place]`.
3. `python3 themes/selo/scripts/emblem.py` (shield emblem + favicons), `python3 themes/selo/scripts/capital_palette.py`
   (shield initials in the site colours).
4. Write `assets/css/site.css` (colour tokens) and the content; `python3 themes/selo/scripts/sr_cyrl.py`,
   `python3 themes/selo/scripts/share_images.py`.
5. `hugo --gc --minify && python3 themes/selo/scripts/seo_check.py public`.

## Scripts (run from the site folder)

| Script | What it does |
|---|---|
| `sr_cyrl.py` | Serbian Cyrillic copy of the Latin text (+ `data/cyrillic.yaml` for site words to keep in Latin) |
| `translate.py` | fills missing languages from English with Claude (needs `ANTHROPIC_API_KEY`) |
| `seo_check.py` | checks descriptions, canonical, hreflang, Open Graph, JSON-LD in `public/` |
| `share_images.py` | link-preview cards 1200x630 and Google Discover crops 16:9 / 4:3 / 1:1 |
| `emblem.py`, `capital_palette.py` | site emblem, favicons and recoloured capital font |
| `new_news.py` | adds a news item from JSON: the entry point for the Telegram bot / admin (see `docs/ADMIN.md`) |
| `indexnow.py` | tells Bing/Yandex which pages changed |

## Google Discover

Pages carry what Discover looks for: `max-image-preview:large`, large images (Article image in 16:9, 4:3 and 1:1,
at least 1200 px wide), Article/NewsArticle with author (Person with a profile page), publisher (Organization with
logo) and full ISO dates, a visible byline, RSS feeds linked in the head. There is no submission: Discover picks
pages that Google has indexed. See the Search Console steps in the site READMEs.
