#!/usr/bin/env python3
"""Add a news item to a site of the network: the single entry point for the future admin (Telegram bot, web form).

Input is one JSON (or YAML) file or stdin:
  {
    "date": "2026-10-20T09:30:00+02:00",      # optional, default now (Europe/Belgrade)
    "feed": "local",                           # "local" (news of the place) or "site" (new page on the site)
    "author": "svetlana",                      # key in data/authors.yaml
    "cover": "provala-illustration",           # optional photo key from data/photos.yaml
    "slug": "plivanje-za-casni-krst-2027",     # optional, made from the Serbian/first title
    "social": ["instagram", "facebook"],       # optional: channels for autoposting (read by the poster job)
    "text": {"sr": {"title": "...", "lead": "...", "body": "..."}, "ru": {...}}   # at least one language
  }
Writes content/<lang>/news/<date>-<slug>.md for every language given. Languages not given are filled later by
translate.py (from English) or by the editor; the Serbian Cyrillic copy is made by sr_cyrl.py.
Run from the site folder:  python3 themes/selo/scripts/new_news.py item.json   (or: ... - < item.json)
Prints the files written. Refuses to overwrite an existing item unless --force."""
import json, os, re, sys, unicodedata
from datetime import datetime
from zoneinfo import ZoneInfo
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from siteconf import ROOT  # noqa: E402
import yaml

TR = str.maketrans({'đ': 'dj', 'Đ': 'dj', 'ž': 'z', 'č': 'c', 'ć': 'c', 'š': 's'})
CYR = dict(zip('абвгдђежзијклљмнњопрстћуфхцчџшыэюяёйщъь', ['a','b','v','g','d','dj','e','z','z','i','j','k','l','lj','m','n','nj','o','p','r','s','t','c','u','f','h','c','c','dz','s','y','e','ju','ja','e','j','sc','','']))


def slugify(s):
    s = ''.join(CYR.get(c, c) for c in s.lower()).translate(TR)
    s = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode()
    return re.sub(r'[^a-z0-9]+', '-', s).strip('-')[:60] or 'vest'


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    force = '--force' in sys.argv
    raw = sys.stdin.read() if not args or args[0] == '-' else open(args[0], encoding='utf-8').read()
    item = yaml.safe_load(raw)
    text = item.get('text') or {}
    if not text:
        sys.exit('no text')
    date = item.get('date') or datetime.now(ZoneInfo('Europe/Belgrade')).replace(microsecond=0).isoformat()
    first = text.get('sr') or text.get('en') or next(iter(text.values()))
    slug = item.get('slug') or slugify(first['title'])
    name = f"{str(date)[:10]}-{slug}.md"
    out = []
    for lang, t in text.items():
        if not t.get('title'):
            continue
        fm = {'title': t['title'], 'date': str(date), 'feed': item.get('feed', 'local')}
        for k in ('author', 'cover'):
            if item.get(k):
                fm[k] = item[k]
        if t.get('lead'):
            fm['lead'] = t['lead']
        if item.get('social'):
            fm['social'] = item['social']
        p = os.path.join(ROOT, 'content', lang, 'news', name)
        if os.path.exists(p) and not force:
            sys.exit(f'exists: {p} (use --force)')
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, 'w', encoding='utf-8') as f:
            f.write('---\n' + yaml.safe_dump(fm, allow_unicode=True, sort_keys=False, width=1000) + '---\n\n' + (t.get('body') or '').strip() + '\n')
        out.append(os.path.relpath(p, ROOT))
    print('\n'.join(out))


if __name__ == '__main__':
    main()
