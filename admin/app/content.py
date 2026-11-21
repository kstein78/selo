"""What editors do with the content: list, read, save, create, hide, delete pages; order news; photos."""
import datetime, os, re, sys
from . import config, frontmatter as fmx, sites
from .sites import SiteError, Conflict

if config.VENDOR not in sys.path:
    sys.path.insert(0, config.VENDOR)
import yaml  # noqa: E402


def _date_str(v):
    if isinstance(v, (datetime.date, datetime.datetime)):
        return v.isoformat()
    return str(v) if v is not None else ''


def list_pages(name, lang):
    """All pages of one language: dicts with rel, title, draft, date, section, index (is a section page)."""
    root = os.path.join(sites.path(name), 'content', lang)
    out = []
    for d, dirs, files in os.walk(root):
        dirs.sort()
        for f in sorted(files):
            if not f.endswith('.md'):
                continue
            full = os.path.join(d, f)
            rel = os.path.relpath(full, root).replace(os.sep, '/')
            try:
                data, _ = fmx.get(open(full, encoding='utf-8').read())
            except (OSError, UnicodeDecodeError):
                continue
            out.append({
                'rel': rel,
                'title': str(data.get('title') or rel),
                'link_title': str(data.get('linkTitle') or ''),
                'draft': bool(data.get('draft')),
                'date': _date_str(data.get('date')),
                'top': bool(data.get('top')),
                'pin': int(data.get('pin') or 0) if str(data.get('pin') or '0').isdigit() else 0,
                'weight': data.get('weight') if isinstance(data.get('weight'), int) else 999,
                'section': rel.rsplit('/', 1)[0] if '/' in rel else '',
                'index': f == '_index.md',
                'photo': str(data.get('photo') or data.get('cover') or ''),
            })
    return out


def translations(name, rel):
    """Which languages have this page."""
    i = sites.info(name)
    return [l['code'] for l in i['langs'] if os.path.exists(os.path.join(sites.path(name), 'content', l['code'], rel))]


def read(name, lang, rel):
    p = sites.content_file(name, lang, rel)
    if not os.path.exists(p):
        raise SiteError('Страница не найдена.')
    text = open(p, encoding='utf-8').read()
    return text, sites.text_hash(text)


# ---------------------------------------------------------------- writes (each returns an op for sites.write)
def op_save(name, lang, rel, new_text, base_hash):
    sites.check_lang(name, lang)
    sites.check_rel(rel)
    if '\x00' in new_text or len(new_text) > 2_000_000:
        raise SiteError('Слишком большой текст.')
    fm, _ = fmx.split(new_text)
    if not new_text.startswith('---\n') or not fmx.parse(fm).get('title'):
        raise SiteError('У страницы должен быть заголовок (title).')

    def op(root):
        p = os.path.join(root, 'content', lang, rel)
        if base_hash:
            if not os.path.exists(p):
                raise Conflict('Страницу за это время удалили.')
            cur = open(p, encoding='utf-8').read()
            if sites.text_hash(cur) != base_hash:
                raise Conflict('Пока вы редактировали, страницу изменил кто-то другой. Скопируйте свой текст и откройте страницу заново.')
            if cur == new_text:
                return []
        elif os.path.exists(p):
            raise Conflict('Такая страница уже есть.')
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, 'w', encoding='utf-8', newline='\n') as f:
            f.write(new_text)
        return ['content/%s/%s' % (lang, rel)]
    return op


def slugify(s):
    tr = dict(zip('абвгдђежзијклљмнњопрстћуфхцчџшыэюяёйъь', ['a', 'b', 'v', 'g', 'd', 'dj', 'e', 'z', 'z', 'i', 'j', 'k', 'l', 'lj', 'm', 'n', 'nj', 'o', 'p', 'r', 's', 't', 'c', 'u', 'f', 'h', 'c', 'c', 'dz', 's', 'y', 'e', 'ju', 'ja', 'e', 'j', '', '']))
    tr.update({'č': 'c', 'ć': 'c', 'š': 's', 'ž': 'z', 'đ': 'dj', 'ä': 'ae', 'ö': 'oe', 'ü': 'ue', 'ß': 'ss', 'á': 'a', 'é': 'e', 'í': 'i', 'ó': 'o', 'ő': 'o', 'ú': 'u', 'ű': 'u'})
    s = ''.join(tr.get(ch, ch) for ch in s.lower())
    s = re.sub(r'[^a-z0-9]+', '-', s).strip('-')
    return s[:60].strip('-') or 'page'


def new_page_text(title, lead='', extra=None, body=''):
    data = {'title': title}
    if lead:
        data['lead'] = lead
    data.update(extra or {})
    fm = ''.join(fmx.dump_value(k, v) + '\n' for k, v in data.items())
    return fmx.join(fm, '\n' + (body.strip() + '\n' if body.strip() else ''))


def news_rel(title, date=None):
    d = date or datetime.date.today().isoformat()
    return 'news/%s-%s.md' % (d[:10], slugify(title))


def op_set_hidden(name, rel, hidden):
    sites.check_rel(rel)

    def op(root):
        changed = []
        for lang in sites.info(name)['editable']:
            p = os.path.join(root, 'content', lang, rel)
            if not os.path.exists(p):
                continue
            text = open(p, encoding='utf-8').read()
            new = fmx.update(text, {'draft': True if hidden else None})
            if new != text:
                open(p, 'w', encoding='utf-8', newline='\n').write(new)
                changed.append('content/%s/%s' % (lang, rel))
        if not changed:
            raise SiteError('Нечего менять.')
        return changed
    return op


def op_delete(name, rel):
    sites.check_rel(rel)
    if rel.endswith('_index.md') or rel == '_index.md':
        raise SiteError('Разделы целиком из админки не удаляются — сначала скройте или удалите страницы внутри.')

    def op(root):
        changed = []
        for l in sites.info(name)['langs']:
            p = os.path.join(root, 'content', l['code'], rel)
            if os.path.exists(p):
                os.remove(p)
                changed.append('content/%s/%s' % (l['code'], rel))
        if not changed:
            raise SiteError('Страница не найдена.')
        return changed
    return op


def op_order_news(name, rels):
    """rels: news pages in the order they should open the home page (pin 1, 2, ...). Others lose their pin."""
    for r in rels:
        sites.check_rel(r)
        if not r.startswith('news/'):
            raise SiteError('bad news path')
    if len(rels) > 8:
        raise SiteError('Можно закрепить не больше 8 новостей.')

    def op(root):
        changed = []
        for lang in sites.info(name)['editable']:
            d = os.path.join(root, 'content', lang, 'news')
            if not os.path.isdir(d):
                continue
            for f in sorted(os.listdir(d)):
                if not f.endswith('.md') or f == '_index.md':
                    continue
                rel = 'news/' + f
                p = os.path.join(d, f)
                text = open(p, encoding='utf-8').read()
                want = rels.index(rel) + 1 if rel in rels else None
                new = fmx.update(text, {'pin': want})
                if new != text:
                    open(p, 'w', encoding='utf-8', newline='\n').write(new)
                    changed.append('content/%s/%s' % (lang, rel))
        return changed
    return op


# ---------------------------------------------------------------- photos
KEY_RE = re.compile(r'^[a-z0-9][a-z0-9-]{1,79}$')
LICENSES = ['© all rights reserved', 'CC BY 4.0', 'CC BY-SA 4.0', 'CC0 / public domain']


def photos(name):
    p = os.path.join(sites.path(name), 'data', 'photos.yaml')
    try:
        data = yaml.safe_load(open(p, encoding='utf-8')) or {}
    except (OSError, yaml.YAMLError):
        data = {}
    return {k: v for k, v in data.items() if isinstance(v, dict) and v.get('src')}


def _yq(s):
    return '"' + str(s).replace('\\', '\\\\').replace('"', '\\"').replace('\n', ' ') + '"'


def op_add_photo(name, key, jpeg, meta, lang):
    if not KEY_RE.match(key or ''):
        raise SiteError('Имя фото: латинские буквы, цифры и дефисы, 2–80 символов.')
    if not (jpeg[:3] == b'\xff\xd8\xff' and len(jpeg) < 15 * 1024 * 1024):
        raise SiteError('Нужен файл JPEG до 15 МБ.')
    alt = (meta.get('alt') or '').strip()
    author = (meta.get('author') or '').strip()
    lic = meta.get('license') if meta.get('license') in LICENSES else LICENSES[0]
    if not alt or not author:
        raise SiteError('Нужны описание фото и автор.')

    def op(root):
        img = os.path.join(root, 'static', 'img', key + '.jpg')
        y = os.path.join(root, 'data', 'photos.yaml')
        text = open(y, encoding='utf-8').read() if os.path.exists(y) else ''
        if os.path.exists(img) or re.search(r'(?m)^%s:' % re.escape(key), text):
            raise Conflict('Фото с таким именем уже есть — выберите другое имя.')
        os.makedirs(os.path.dirname(img), exist_ok=True)
        open(img, 'wb').write(jpeg)
        lines = ['%s:' % key, '  src: img/%s.jpg' % key, '  author: %s' % _yq(author)]
        if lang != 'en':
            lines.append('  author_%s: %s' % (lang, _yq(author)))
        lines.append('  license: %s' % _yq(lic))
        lines.append('  alt: %s' % _yq(alt))                     # the translation workflow takes "alt" as its source
        if lang != 'en':
            lines.append('  alt_%s: %s' % (lang, _yq(alt)))
        if meta.get('position') and re.fullmatch(r'[0-9]{1,3}% [0-9]{1,3}%', meta['position']):
            lines.append('  position: "%s"' % meta['position'])
        new = text.rstrip('\n') + '\n' + '\n'.join(lines) + '\n'
        open(y, 'w', encoding='utf-8', newline='\n').write(new)
        return ['static/img/%s.jpg' % key, 'data/photos.yaml']
    return op
