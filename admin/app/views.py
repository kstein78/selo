"""Pages of the admin: sites, pages, editor, news order, photos, review queue, users, settings, log."""
import base64, datetime, difflib, json, mimetypes, os, re, time
from . import config, content, db, frontmatter as fmx, security, sites
from .html import e, url, frame, csrf_field, js_data, select, ago
from .sites import SiteError, Conflict
from .web import route, Redirect, HttpError

EDIT_FIELDS = ['title', 'linkTitle', 'kicker', 'lead', 'summary', 'photo', 'cover', 'date', 'top', 'weight']


def all_sites():
    return list(sites.site_list().keys())


def need(req, site, perm):
    if site not in sites.site_list():
        raise HttpError(404)
    if perm not in db.perms_for(req.user, site):
        raise HttpError(403, 'Нет прав: %s.' % db.PERM_NAMES.get(perm, perm))
    return db.perms_for(req.user, site)


def page(req, title, body, **kw):
    return frame(title, body, req.user, req.sess, **kw)


def site_info(site):
    sites.sync_quiet(site)
    return sites.info(site)


def live_url(info, lang, rel, data):
    if data.get('url'):
        return info['url'] + '/' + str(data['url']).strip('/') + '/'
    parts = rel[:-3].split('/')
    if parts[-1] == '_index':
        parts = parts[:-1]
    elif data.get('slug'):
        parts[-1] = str(data['slug'])
    p = '/'.join([lang] + [x for x in parts if x])
    return '%s/%s/' % (info['url'], p)


def pending_count(user):
    rows = db.q("SELECT site FROM submissions WHERE status='pending'")
    return sum(1 for r in rows if 'review' in db.perms_for(user, r['site']))


# ---------------------------------------------------------------- dashboard
@route('GET', '/')
def dashboard(req):
    my = db.sites_for(req.user, all_sites())
    cards = []
    for s in my:
        try:
            i = site_info(s)
            langs = ', '.join(l['code'].upper() for l in i['langs'])
            cards.append('<a class="site-card" href="%s"><b>%s</b><span>%s</span><span class="muted">%s</span></a>'
                         % (url('s/%s/' % s), e(i['domain'] or s), e(i['title']), e(langs)))
        except SiteError as ex:
            cards.append('<div class="site-card"><b>%s</b><span class="error">%s</span></div>' % (e(s), e(str(ex))))
    warn = ''
    if req.user['is_owner'] and not sites.can_push():
        warn = '<p class="flash error">Публикация не настроена: введите ключ GitHub в <a href="%s">Настройках</a>.</p>' % url('settings')
    n = pending_count(req.user)
    rev = '<p class="flash info"><a href="%s">На проверке: %d</a></p>' % (url('review'), n) if n else ''
    if not my:
        cards.append('<p>У вас пока нет доступа ни к одному сайту. Попросите владельца выдать права.</p>')
    return page(req, 'Сайты', '%s%s<h1>Сайты</h1><div class="site-grid">%s</div>' % (warn, rev, ''.join(cards)))


# ---------------------------------------------------------------- site: pages
def lang_tabs(site, info, lang, base, extra=''):
    out = []
    for l in info['langs']:
        if l['generated']:
            out.append('<span class="tab off" title="Создаётся автоматически из сербской латиницы">%s</span>' % e(l['code'].upper()))
        else:
            out.append('<a class="tab%s" href="%s?%slang=%s">%s</a>' % (' on' if l['code'] == lang else '', e(base), e(extra), e(l['code']), e(l['code'].upper())))
    return '<div class="tabs">%s</div>' % ''.join(out)


def site_nav(site, info, active):
    items = [('', 'Страницы'), ('news', 'Новости'), ('photos', 'Фото')]
    return '<div class="subnav"><a href="%s" class="back">← все сайты</a><b>%s</b>%s<a href="%s" target="_blank" rel="noopener">открыть сайт ↗</a></div>' % (
        url(), e(info['domain']), ''.join('<a class="%s" href="%s">%s</a>' % ('on' if k == active else '', url('s/%s/%s' % (site, k)), t) for k, t in items),
        e(info['url'] + '/'))


def pick_lang(req, info):
    lang = req.query.get('lang') or ('ru' if 'ru' in info['editable'] else info['default'])
    if lang not in info['editable']:
        lang = info['editable'][0]
    return lang


@route('GET', r'/s/([a-z0-9-]+)/')
def site_pages(req, site):
    perms = need(req, site, 'view')
    info = site_info(site)
    lang = pick_lang(req, info)
    pages = [p for p in content.list_pages(site, lang) if not p['rel'].startswith('news/') or p['index']]
    by_sec = {}
    for p in pages:
        sec = p['rel'].rsplit('/', 1)[0] if '/' in p['rel'] else ''
        if p['index']:
            sec = p['rel'][:-len('_index.md')].rstrip('/')
        by_sec.setdefault(sec, []).append(p)
    rows = []
    for sec in sorted(by_sec):
        items = sorted(by_sec[sec], key=lambda p: (not p['index'], p['weight'], p['title'].lower()))
        rows.append('<tr class="sec"><td colspan="3">%s</td></tr>' % e('/' + sec if sec else 'Главная и разделы верхнего уровня'))
        for p in items:
            rows.append(page_row(req, site, lang, p, perms))
    new_btn = '<a class="btn" href="%s?lang=%s">+ Новая страница</a>' % (url('s/%s/new' % site), e(lang)) if 'create' in perms else ''
    body = '%s<h1>Страницы</h1>%s<p>%s</p><table class="list">%s</table>' % (
        site_nav(site, info, ''), lang_tabs(site, info, lang, url('s/%s/' % site)), new_btn, ''.join(rows))
    return page(req, 'Страницы · ' + info['domain'], body)


def page_row(req, site, lang, p, perms):
    rel = p['rel']
    acts = []
    if 'edit' in perms:
        acts.append('<a href="%s?lang=%s&path=%s">править</a>' % (url('s/%s/edit' % site), e(lang), e(rel)))
    if 'hide' in perms and not p['index']:
        acts.append(post_button(req, url('s/%s/%s' % (site, 'unhide' if p['draft'] else 'hide')), {'path': rel, 'lang': lang},
                                'вернуть на сайт' if p['draft'] else 'скрыть'))
    if 'delete' in perms and not p['index']:
        acts.append(post_button(req, url('s/%s/delete' % site), {'path': rel, 'lang': lang}, 'удалить', confirm=True))
    status = '<span class="badge hidden">скрыта</span>' if p['draft'] else ''
    title = p['title'] + (' · ' + p['date'][:10] if p['date'] and p['rel'].startswith('news/') else '')
    return '<tr class="%s"><td>%s %s<div class="muted small">%s</div></td><td class="acts">%s</td></tr>' % (
        'draft' if p['draft'] else '', e(title), status, e(rel), ' · '.join(acts))


def post_button(req, action, fields, label, confirm=False):
    hidden = ''.join('<input type="hidden" name="%s" value="%s">' % (e(k), e(v)) for k, v in fields.items())
    if confirm:
        return ('<details class="confirm"><summary>%s</summary><form method="post" action="%s">%s%s'
                '<p>Удалить на всех языках? Восстановить можно только из истории (кнопка «отменить» в журнале).</p>'
                '<button class="danger">Да, удалить</button></form></details>') % (e(label), e(action), csrf_field(req.sess), hidden)
    return '<form method="post" action="%s" class="inline">%s%s<button class="link">%s</button></form>' % (e(action), csrf_field(req.sess), hidden, e(label))


def do_write(req, site, op, message, path=None, action='edit'):
    try:
        sha = sites.write(site, op, message, req.user)
    except Conflict as ex:
        raise HttpError(409, str(ex))
    except SiteError as ex:
        raise HttpError(400, str(ex))
    db.audit(req.user['id'], action, site, path, message, sha, req.ip)
    return sha


@route('POST', r'/s/([a-z0-9-]+)/(hide|unhide)')
def hide_post(req, site, what):
    need(req, site, 'hide')
    rel = sites.check_rel(req.f('path'))
    do_write(req, site, content.op_set_hidden(site, rel, what == 'hide'),
             '%s %s' % ('Hide' if what == 'hide' else 'Show', rel), rel, what)
    back = url('s/%s/%s' % (site, 'news' if rel.startswith('news/') else '')) + '?lang=' + req.f('lang')
    raise Redirect(back)


@route('POST', r'/s/([a-z0-9-]+)/delete')
def delete_post(req, site):
    need(req, site, 'delete')
    rel = sites.check_rel(req.f('path'))
    do_write(req, site, content.op_delete(site, rel), 'Delete %s' % rel, rel, 'delete')
    raise Redirect(url('s/%s/%s' % (site, 'news' if rel.startswith('news/') else '')) + '?lang=' + req.f('lang'))


# ---------------------------------------------------------------- new page / news
@route('GET', r'/s/([a-z0-9-]+)/new')
def new_page(req, site):
    perms = need(req, site, 'create')
    info = site_info(site)
    lang = pick_lang(req, info)
    news = req.query.get('kind') == 'news'
    secs = sorted({p['rel'][:-len('_index.md')].rstrip('/') for p in content.list_pages(site, lang) if p['index']})
    sec_opts = [(s, '/' + s if s else '/ (верхний уровень)') for s in secs if s != 'news']
    form = (
        '<form method="get" action="%s" class="card">'
        '<input type="hidden" name="new" value="1"><input type="hidden" name="lang" value="%s">%s'
        '<label>Заголовок <input name="title" required maxlength="200"></label>'
        '%s<label>Адрес страницы (латиницей, можно оставить пустым — сделаем из заголовка) <input name="slug" pattern="[a-z0-9-]*" maxlength="60"></label>'
        '<p class="muted">Страница создаётся на языке <b>%s</b>. %s</p><button>Дальше: текст</button></form>'
    ) % (url('s/%s/edit' % site), e(lang), '<input type="hidden" name="kind" value="news">' if news else '',
         '' if news else '<label>Раздел %s</label>' % select('section', sec_opts),
         e(lang.upper()), 'Если это английский, остальные языки переведёт автоматика сайта.' if lang == 'en' else
         'Другие языки добавьте потом сами или создайте страницу сначала на английском — тогда остальные языки переведёт автоматика.')
    return page(req, 'Новая страница', '%s<h1>%s</h1>%s%s' % (site_nav(site, info, 'news' if news else ''), 'Новая новость' if news else 'Новая страница',
                                                              lang_tabs(site, info, lang, url('s/%s/new' % site), 'kind=news&' if news else ''), form))


# ---------------------------------------------------------------- editor
@route('GET', r'/s/([a-z0-9-]+)/edit')
def editor(req, site):
    perms = need(req, site, 'view')
    info = site_info(site)
    lang = sites.check_lang(site, req.query.get('lang', ''))
    if req.query.get('new'):
        need(req, site, 'create')
        title = req.query.get('title', '').strip()[:200]
        if not title:
            raise HttpError(400, 'Нужен заголовок.')
        if req.query.get('kind') == 'news':
            rel = content.news_rel(req.query.get('slug') or title)
            now = datetime.datetime.now().astimezone() - datetime.timedelta(minutes=2)
            text = content.new_page_text(title, extra={'date': now.replace(microsecond=0).isoformat(), 'feed': 'local'})
        else:
            sec = req.query.get('section', '')
            if sec and not re.fullmatch(r'[a-z0-9_][a-z0-9/_-]*', sec):
                raise HttpError(400, 'bad section')
            slug = content.slugify(req.query.get('slug') or title)
            rel = sites.check_rel((sec + '/' if sec else '') + slug + '.md')
        if os.path.exists(sites.content_file(site, lang, rel)):
            raise HttpError(409, 'Страница с таким адресом уже есть: %s' % rel)
        base_hash, new = '', True
    else:
        need(req, site, 'edit')
        rel = sites.check_rel(req.query.get('path', ''))
        text, base_hash = content.read(site, lang, rel)
        new = False
    fm, body = fmx.split(text)
    data = fmx.parse(fm)
    fields = {k: (v.isoformat() if isinstance(v, (datetime.date, datetime.datetime)) else v) for k, v in data.items() if k in EDIT_FIELDS}
    pages = [{'rel': p['rel'], 'title': p['title']} for p in content.list_pages(site, lang)]
    payload = {
        'site': site, 'lang': lang, 'path': rel, 'base_hash': base_hash, 'new': new,
        'kind': 'news' if rel.startswith('news/') else 'page', 'fields': fields, 'raw_fm': fm, 'body': body,
        'csrf': req.sess['csrf'], 'can_publish': 'publish' in perms, 'can_upload': 'photos' in perms,
        'draft': bool(data.get('draft')), 'langs': content.translations(site, rel), 'live': live_url(info, lang, rel, data),
        'api': {'save': url('s/%s/save' % site), 'photos': url('s/%s/photos.json' % site), 'upload': url('s/%s/photo' % site),
                'frame': url('s/%s/preview-frame' % site), 'back': url('s/%s/%s' % (site, 'news' if rel.startswith('news/') else '')) + '?lang=' + lang,
                'edit': url('s/%s/edit' % site)},
        'pages': pages, 'author': req.user['name'], 'licenses': content.LICENSES,
        'other_langs': [l for l in info['editable'] if l != lang],
    }
    body_html = ('<div class="subnav"><a class="back" href="%s">← назад</a><b>%s</b><span>%s · %s</span>'
                 '<a href="%s" target="_blank" rel="noopener">на сайте ↗</a></div>'
                 '<div id="editor"></div><script type="application/json" id="editor-data">%s</script>') % (
        e(payload['api']['back']), e(info['domain']), e(lang.upper()), e(rel), e(payload['live']), js_data(payload))
    return page(req, 'Редактор', body_html, wide=True, scripts=['vendor/markdown-it.min.js', 'preview.js', 'photo.js', 'editor.js'])


def build_text(site, lang, rel, j, new):
    if new:
        title = str((j.get('fields') or {}).get('title') or '').strip()
        extra = {}
        if rel.startswith('news/'):
            now = datetime.datetime.now().astimezone() - datetime.timedelta(minutes=2)
            extra = {'date': now.replace(microsecond=0).isoformat(), 'feed': 'local'}
        base = content.new_page_text(title or 'Без названия', extra=extra)
    else:
        base, _ = content.read(site, lang, rel)
    fm, body = fmx.split(base)
    if isinstance(j.get('raw_fm'), str) and j['raw_fm'] != fm:
        fm = j['raw_fm'].replace('\r\n', '\n')
        if not isinstance(fmx.parse(fm), dict) or (fm.strip() and not fmx.parse(fm)):
            raise HttpError(400, 'Ошибка в служебных полях (YAML).')
    changes = {}
    for k, v in (j.get('fields') or {}).items():
        if k not in EDIT_FIELDS:
            continue
        if isinstance(v, str):
            v = v.strip()
            if v == '':
                v = None
        if k == 'top':
            v = True if v else None
        if k == 'weight' and v is not None:
            try:
                v = int(v)
            except (TypeError, ValueError):
                raise HttpError(400, 'Порядок (weight) — целое число.')
        if k == 'title' and not v:
            raise HttpError(400, 'Нужен заголовок.')
        changes[k] = v
    fm = fmx.set_keys(fm, changes)
    new_body = j.get('body')
    if not isinstance(new_body, str):
        new_body = body
    return fmx.join(fm, new_body.replace('\r\n', '\n'))


@route('POST', r'/s/([a-z0-9-]+)/save')
def save(req, site):
    j = req.json or {}
    perms = need(req, site, 'view')
    lang = sites.check_lang(site, j.get('lang', ''))
    rel = sites.check_rel(j.get('path', ''))
    new = bool(j.get('new'))
    need(req, site, 'create' if new else 'edit')
    text = build_text(site, lang, rel, j, new)
    message = (str(j.get('message') or '').strip()[:200]) or ('%s %s (%s)' % ('Create' if new else 'Edit', rel, lang))
    if j.get('mode') == 'publish':
        need(req, site, 'publish')
        try:
            sha = sites.write(site, content.op_save(site, lang, rel, text, '' if new else j.get('base_hash', '')), message, req.user)
        except Conflict as ex:
            return {'ok': False, 'error': str(ex), 'conflict': True}
        except SiteError as ex:
            return {'ok': False, 'error': str(ex)}
        db.audit(req.user['id'], 'create' if new else 'edit', site, '%s:%s' % (lang, rel), message, sha, req.ip)
        _, h = content.read(site, lang, rel)
        return {'ok': True, 'commit': sha, 'base_hash': h, 'message': 'Опубликовано. На сайте — примерно через минуту.' if sha else 'Изменений нет.'}
    sid = db.run('INSERT INTO submissions(site,lang,path,kind,content,base_hash,message,user_id,created) VALUES (?,?,?,?,?,?,?,?,?)',
                 site, lang, rel, 'create' if new else 'edit', text, '' if new else j.get('base_hash', ''), message, req.user['id'], time.time())
    db.audit(req.user['id'], 'submit', site, '%s:%s' % (lang, rel), message, None, req.ip)
    return {'ok': True, 'submitted': sid, 'message': 'Отправлено на проверку редактору.'}


# ---------------------------------------------------------------- preview support
@route('GET', r'/s/([a-z0-9-]+)/preview-frame')
def preview_frame(req, site):
    need(req, site, 'view')
    return ('<!doctype html><html><head><meta charset="utf-8"><link rel="stylesheet" href="%s">'
            '<style>body{margin:0} .sc-chip{display:inline-block;padding:.2em .6em;border:1px dashed #999;border-radius:4px;font:13px sans-serif;color:#555;background:#f6f6f6}'
            '.sc-todo{border:1px dashed #c90;padding:.6em;background:#fff8e6;font-size:.9em}</style></head>'
            '<body><header class="page-head" id="pv-head"><div class="wrap"><p class="kicker" id="pv-kicker"></p><h1 id="pv-title"></h1>'
            '<p class="lead" id="pv-lead"></p></div><div class="wrap wide" id="pv-hero"></div></header>'
            '<div class="wrap page-body"><div class="prose" id="pv-body"></div></div></body></html>') % url('s/%s/preview.css' % site)


@route('GET', r'/s/([a-z0-9-]+)/preview\.css')
def preview_css(req, site):
    need(req, site, 'view')
    root = sites.path(site)
    parts = []
    for rel in ('themes/selo/assets/css/main.css', 'assets/css/main.css', 'assets/css/site.css'):
        p = os.path.join(root, rel)
        if os.path.exists(p):
            parts.append(open(p, encoding='utf-8').read())
    css = '\n'.join(parts)
    css = re.sub(r'url\((["\']?)\.\./', lambda m: 'url(%s%s' % (m.group(1), url('s/%s/file/' % site)), css)
    return ('text/css; charset=utf-8', css.encode('utf-8'))


FILE_TYPES = {'.jpg', '.jpeg', '.png', '.webp', '.svg', '.gif', '.woff2', '.woff', '.ttf', '.css'}


@route('GET', r'/s/([a-z0-9-]+)/file/([A-Za-z0-9_./-]+)')
def site_file(req, site, rel):
    need(req, site, 'view')
    if '..' in rel or os.path.splitext(rel)[1].lower() not in FILE_TYPES:
        raise HttpError(404)
    root = sites.path(site)
    for base in ('static', 'themes/selo/static'):
        p = os.path.realpath(os.path.join(root, base, rel))
        if p.startswith(os.path.realpath(os.path.join(root, base)) + os.sep) and os.path.isfile(p):
            ctype = mimetypes.guess_type(p)[0] or 'application/octet-stream'
            if ctype == 'image/svg+xml':
                ctype = 'image/svg+xml'
            return (ctype, open(p, 'rb').read())
    raise HttpError(404)


@route('GET', r'/s/([a-z0-9-]+)/photos\.json')
def photos_json(req, site):
    need(req, site, 'view')
    out = {}
    root = sites.path(site)
    for k, v in content.photos(site).items():
        src = str(v.get('src'))
        if src.startswith('http'):
            full = thumb = src
        else:
            full = url('s/%s/file/%s' % (site, src.lstrip('/')))
            t = os.path.join(root, 'static', 'img', 'thumb', os.path.basename(src))
            thumb = url('s/%s/file/img/thumb/%s' % (site, os.path.basename(src))) if os.path.exists(t) else full
        out[k] = {'src': full, 'thumb': thumb, 'alt': v.get('alt', ''), 'author': v.get('author', ''), 'license': v.get('license', ''),
                  'alts': {kk[4:]: vv for kk, vv in v.items() if kk.startswith('alt_')}, 'authors': {kk[7:]: vv for kk, vv in v.items() if kk.startswith('author_')}}
    return out


@route('POST', r'/s/([a-z0-9-]+)/photo')
def photo_upload(req, site):
    need(req, site, 'photos')
    j = req.json or {}
    lang = sites.check_lang(site, j.get('lang', ''))
    try:
        jpeg = base64.b64decode(str(j.get('jpeg', '')).split(',')[-1], validate=True)
    except ValueError:
        return {'ok': False, 'error': 'Файл повреждён.'}
    key = str(j.get('key', '')).strip()
    try:
        sha = sites.write(site, content.op_add_photo(site, key, jpeg, j, lang), 'Photo %s' % key, req.user)
    except (SiteError, Conflict) as ex:
        return {'ok': False, 'error': str(ex)}
    db.audit(req.user['id'], 'photo', site, key, None, sha, req.ip)
    return {'ok': True, 'key': key, 'commit': sha}


@route('GET', r'/s/([a-z0-9-]+)/photos')
def photos_page(req, site):
    perms = need(req, site, 'view')
    info = site_info(site)
    items = sorted(photos_json(req, site).items())
    grid = ''.join('<figure class="ph"><img loading="lazy" src="%s" alt=""><figcaption><b>%s</b><br>%s<br><span class="muted">%s, %s</span></figcaption></figure>'
                   % (e(v['thumb']), e(k), e(v['alt'])[:140], e(v['author']), e(v['license'])) for k, v in items)
    up = ('<p><button id="upload-btn" class="btn" data-api="%s" data-csrf="%s" data-lang="%s" data-author="%s" data-licenses="%s">+ Загрузить фото</button></p>'
          % (e(url('s/%s/photo' % site)), e(req.sess['csrf']), e(pick_lang(req, info)), e(req.user['name']), e(json.dumps(content.LICENSES, ensure_ascii=False)))) if 'photos' in perms else ''
    return page(req, 'Фото', '%s<h1>Фото (%d)</h1>%s<input id="ph-filter" placeholder="Поиск по имени или описанию"><div class="ph-grid">%s</div>'
                % (site_nav(site, info, 'photos'), len(items), up, grid), scripts=['photo.js', 'photos-page.js'])


# ---------------------------------------------------------------- news and the home page order
def home_order(news):
    """Same rule as the site template (partials/news-items.html): pinned by number, then top, then newest."""
    live = [n for n in news if not n['draft']]
    pinned = sorted([n for n in live if n['pin']], key=lambda n: n['pin'])
    rest = sorted([n for n in live if not n['pin']], key=lambda n: n['date'], reverse=True)
    if not pinned:
        tops = [n for n in rest if n['top']]
        if tops:
            rest = [tops[0]] + [n for n in rest if n is not tops[0]]
    return pinned + rest


@route('GET', r'/s/([a-z0-9-]+)/news')
def news_page(req, site):
    perms = need(req, site, 'view')
    info = site_info(site)
    lang = pick_lang(req, info)
    news = [p for p in content.list_pages(site, lang) if p['rel'].startswith('news/') and not p['index']]
    order = home_order(news)[:4]
    home = ''.join('<li>%s <span class="muted">%s</span></li>' % (e(n['title']), e(n['date'][:10])) for n in order)
    can_order = 'order' in perms
    rows = []
    for n in sorted(news, key=lambda n: n['date'], reverse=True):
        # the row's own buttons are separate forms, so the order inputs join the order form by its id
        pin = ('<input class="pin" form="order" type="number" min="1" max="8" name="pin:%s" value="%s">' % (e(n['rel']), n['pin'] or '')) if can_order else e(n['pin'] or '')
        row = page_row(req, site, lang, n, perms)
        if n['top']:
            row = row.replace('<td>', '<td><span class="badge">главная</span> ', 1)
        rows.append(row[:-len('</tr>')] + '<td>%s</td></tr>' % pin)
    new_btn = '<a class="btn" href="%s?lang=%s&kind=news">+ Новая новость</a>' % (url('s/%s/new' % site), e(lang)) if 'create' in perms else ''
    form = ('<form id="order" method="post" action="%s">%s<input type="hidden" name="lang" value="%s"></form>' % (url('s/%s/order' % site), csrf_field(req.sess), e(lang))) if can_order else ''
    save_btn = ('<p><button form="order">Сохранить порядок на главной</button> <span class="muted">Число — место на главной (1 — большая новость). '
                'Пусто — по дате. Порядок общий для всех языков.</span></p>') if can_order else ''
    body = ('%s<h1>Новости</h1>%s<p>%s</p><div class="card"><h2>Сейчас на главной</h2><ol>%s</ol>'
            '<p class="muted small">Анонсы новых страниц и альбомов (data/sitenews.yaml) встают между новостями по дате.</p></div>'
            '%s<table class="list"><tr><th>Новость</th><th></th><th>Место</th></tr>%s</table>%s') % (
        site_nav(site, info, 'news'), lang_tabs(site, info, lang, url('s/%s/news' % site)), new_btn, home, form, ''.join(rows), save_btn)
    return page(req, 'Новости · ' + info['domain'], body)


@route('POST', r'/s/([a-z0-9-]+)/order')
def order_post(req, site):
    need(req, site, 'order')
    pins = []
    for k, v in req.form.items():
        if k.startswith('pin:') and str(v).strip():
            try:
                pins.append((int(v), sites.check_rel(k[4:])))
            except ValueError:
                raise HttpError(400, 'Место — число от 1 до 8.')
    rels = [r for _, r in sorted(pins)]
    do_write(req, site, content.op_order_news(site, rels), 'Home page news order', None, 'order')
    raise Redirect(url('s/%s/news' % site) + '?lang=' + req.f('lang'))


# ---------------------------------------------------------------- review queue
@route('GET', '/review')
def review_list(req):
    rows = []
    for s in db.q("SELECT s.*, u.name uname FROM submissions s JOIN users u ON u.id=s.user_id ORDER BY s.status='pending' DESC, s.created DESC LIMIT 200"):
        mine = s['user_id'] == req.user['id']
        can = 'review' in db.perms_for(req.user, s['site'])
        if not (mine or can):
            continue
        rows.append('<tr><td><a href="%s">%s</a><div class="muted small">%s · %s · %s</div></td><td>%s</td><td>%s</td></tr>' % (
            url('review/%d' % s['id']), e(s['message']), e(s['site']), e(s['lang'].upper()), e(s['path']), e(s['uname']),
            {'pending': '<span class="badge">ждёт</span>', 'published': 'опубликовано', 'rejected': 'отклонено', 'withdrawn': 'отозвано'}.get(s['status'], s['status'])))
    return page(req, 'Проверка', '<h1>Правки на проверке</h1><table class="list">%s</table>' % (''.join(rows) or '<tr><td>Пока ничего нет.</td></tr>'))


@route('GET', r'/review/(\d+)')
def review_item(req, sid):
    s = db.one('SELECT s.*, u.name uname FROM submissions s JOIN users u ON u.id=s.user_id WHERE s.id=?', int(sid))
    if not s:
        raise HttpError(404)
    can = 'review' in db.perms_for(req.user, s['site'])
    if not (can or s['user_id'] == req.user['id']):
        raise HttpError(403)
    try:
        cur, h = content.read(s['site'], s['lang'], s['path'])
    except SiteError:
        cur, h = '', ''
    diff = ''.join(difflib.unified_diff(cur.splitlines(True), s['content'].splitlines(True), 'сейчас на сайте', 'предложено', n=2))
    stale = s['base_hash'] and h and h != s['base_hash']
    acts = ''
    if s['status'] == 'pending' and can:
        acts = ('<form method="post" action="%s" class="card">%s<label>Комментарий автору <input name="comment" maxlength="500"></label>%s'
                '<button name="do" value="publish">Опубликовать</button> <button name="do" value="reject" class="danger">Отклонить</button></form>') % (
            url('review/%d' % s['id']), csrf_field(req.sess),
            '<label class="check"><input type="checkbox" name="force" value="1"> Страницу уже изменили после отправки — всё равно заменить её этой версией</label>' if stale else '')
    elif s['status'] == 'pending' and s['user_id'] == req.user['id']:
        acts = '<form method="post" action="%s">%s<button name="do" value="withdraw">Отозвать</button></form>' % (url('review/%d' % s['id']), csrf_field(req.sess))
    return page(req, 'Правка', '<p><a href="%s">← все правки</a></p><h1>%s</h1><p>%s · %s · %s · автор: %s · %s</p>%s%s<pre class="diff">%s</pre>' % (
        url('review'), e(s['message']), e(s['site']), e(s['lang'].upper()), e(s['path']), e(s['uname']), ago(s['created']),
        '<p class="flash error">После отправки страница на сайте изменилась.</p>' if stale else '',
        ('<p class="flash info">Комментарий: %s</p>' % e(s['comment'])) if s['comment'] else '', diff_html(diff)) + acts)


def diff_html(diff):
    out = []
    for line in diff.splitlines():
        cls = 'add' if line.startswith('+') else 'del' if line.startswith('-') else 'hunk' if line.startswith('@@') else ''
        out.append('<span class="%s">%s</span>' % (cls, e(line)))
    return '\n'.join(out) or 'Без изменений.'


@route('POST', r'/review/(\d+)')
def review_post(req, sid):
    s = db.one('SELECT * FROM submissions WHERE id=?', int(sid))
    if not s or s['status'] != 'pending':
        raise HttpError(404)
    do = req.f('do')
    if do == 'withdraw' and s['user_id'] == req.user['id']:
        db.run("UPDATE submissions SET status='withdrawn' WHERE id=?", s['id'])
        raise Redirect(url('review'))
    need(req, s['site'], 'review')
    if do == 'reject':
        db.run("UPDATE submissions SET status='rejected', reviewer_id=?, reviewed=?, comment=? WHERE id=?",
               req.user['id'], time.time(), req.f('comment')[:500], s['id'])
        db.audit(req.user['id'], 'reject', s['site'], '%s:%s' % (s['lang'], s['path']), s['message'], None, req.ip)
        raise Redirect(url('review'))
    if do != 'publish':
        raise HttpError(400)
    need(req, s['site'], 'publish')
    base = s['base_hash']
    if s['kind'] == 'edit' and req.f('force') == '1':
        _, base = content.read(s['site'], s['lang'], s['path'])
    author = db.one('SELECT * FROM users WHERE id=?', s['user_id'])
    msg = '%s (проверил(а) %s)' % (s['message'], req.user['name'])
    try:
        sha = sites.write(s['site'], content.op_save(s['site'], s['lang'], s['path'], s['content'], base if s['kind'] == 'edit' else ''), msg, author)
    except Conflict as ex:
        raise HttpError(409, str(ex) + ' Отметьте «всё равно заменить», если уверены.')
    except SiteError as ex:
        raise HttpError(400, str(ex))
    db.run("UPDATE submissions SET status='published', reviewer_id=?, reviewed=?, comment=?, commit_sha=? WHERE id=?",
           req.user['id'], time.time(), req.f('comment')[:500], sha, s['id'])
    db.audit(req.user['id'], 'approve', s['site'], '%s:%s' % (s['lang'], s['path']), msg, sha, req.ip)
    raise Redirect(url('review'))


# ---------------------------------------------------------------- users
def manageable_sites(user):
    """Sites where the user may hand out rights ('*' only for owners)."""
    if user['is_owner']:
        return ['*'] + all_sites()
    return [s for s in all_sites() if 'users' in db.perms_for(user, s)]


def can_manage(req, target):
    if req.user['is_owner']:
        return True
    if target['is_owner']:
        return False
    mine = set(manageable_sites(req.user))
    theirs = {g['site'] for g in db.q('SELECT site FROM grants WHERE user_id=?', target['id'])}
    return bool(mine) and (not theirs or theirs <= mine)


@route('GET', '/users')
def users_page(req):
    if not manageable_sites(req.user):
        raise HttpError(403)
    rows = []
    for u in db.q('SELECT * FROM users ORDER BY active DESC, name'):
        if not can_manage(req, u):
            continue
        grants = db.q('SELECT * FROM grants WHERE user_id=?', u['id'])
        g = 'владелец (всё)' if u['is_owner'] else ', '.join('%s: %s' % ('все сайты' if x['site'] == '*' else x['site'], db.ROLE_NAMES.get(x['role'], x['role'])) for x in grants) or '—'
        rows.append('<tr class="%s"><td><a href="%s">%s</a><div class="muted small">%s</div></td><td>%s</td><td>%s</td></tr>' % (
            '' if u['active'] else 'draft', url('users/%d' % u['id']), e(u['name']), e(u['login']), e(g),
            ('2FA ✓' if u['totp_enabled'] else '<span class="badge">нет 2FA</span>') + ('' if u['active'] else ' · отключён')))
    return page(req, 'Пользователи', '<h1>Пользователи</h1><p><a class="btn" href="%s">+ Новый пользователь</a></p><table class="list">%s</table>%s' % (
        url('users/new'), ''.join(rows), roles_help()))


def roles_help():
    rows = ''.join('<tr><td>%s</td><td>%s</td></tr>' % (e(db.ROLE_NAMES[r]), e(', '.join(db.PERM_NAMES[p] for p in ps))) for r, ps in db.ROLES.items())
    return '<details class="card"><summary>Что умеют роли</summary><table class="list">%s</table><p class="muted">Владелец может всё, включая всех пользователей и настройки. Автор без права «публиковать сразу» отправляет правки на проверку.</p></details>' % rows


def grants_editor(req, target=None):
    sitesl = manageable_sites(req.user)
    cur = {g['site']: g for g in db.q('SELECT * FROM grants WHERE user_id=?', target['id'])} if target else {}
    roles = [('', '—')] + [(r, db.ROLE_NAMES[r]) for r in db.ROLES if req.user['is_owner'] or r != 'admin']
    rows = []
    for s in sitesl:
        g = cur.get(s)
        role = g['role'] if g else ''
        eff = set(db.ROLES.get(role, [])) | set(json.loads(g['add_perms']) if g else []) - set(json.loads(g['remove_perms']) if g else [])
        boxes = ''.join('<label class="perm"><input type="checkbox" name="perm:%s:%s" value="1"%s>%s</label>' % (e(s), p, ' checked' if p in eff else '', e(db.PERM_NAMES[p]))
                        for p in db.PERMS if req.user['is_owner'] or p != 'users')
        rows.append('<tr><td><b>%s</b></td><td>%s</td><td class="perms">%s<input type="hidden" name="site:%s" value="1"></td></tr>' % (
            'Все сайты (и будущие)' if s == '*' else e(s), select('role:' + s, roles, role), boxes, e(s)))
    return ('<h2>Права</h2><p class="muted">Роль задаёт набор прав; галочками можно добавить или убрать отдельные права. '
            'При смене роли галочки ставятся по новой роли.</p><table class="list grants" data-roles="%s">%s</table>') % (e(json.dumps(db.ROLES)), ''.join(rows))


def save_grants(req, uid):
    for s in manageable_sites(req.user):
        if req.f('site:' + s) != '1':
            continue
        role = req.f('role:' + s)
        old = db.one('SELECT * FROM grants WHERE user_id=? AND site=?', uid, s)
        if role not in db.ROLES or (role == 'admin' and not req.user['is_owner']):
            if old:
                db.run('DELETE FROM grants WHERE id=?', old['id'])
            continue
        checked = {p for p in db.PERMS if req.f('perm:%s:%s' % (s, p)) == '1'}
        if not req.user['is_owner']:
            checked.discard('users')
        base = set(db.ROLES[role])
        if not old or old['role'] != role:
            # new grant or another role: the role's own rights stay; extra boxes ticked on top are kept
            add, remove = sorted(checked - base), []
        else:
            add, remove = sorted(checked - base), sorted(base - checked)
        if old:
            db.run('UPDATE grants SET role=?, add_perms=?, remove_perms=? WHERE id=?', role, json.dumps(add), json.dumps(remove), old['id'])
        else:
            db.run('INSERT INTO grants(user_id,site,role,add_perms,remove_perms) VALUES (?,?,?,?,?)', uid, s, role, json.dumps(add), json.dumps(remove))


def temp_password():
    alphabet = 'abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789'
    import secrets
    return '-'.join(''.join(secrets.choice(alphabet) for _ in range(4)) for _ in range(4))


@route('GET', '/users/new')
def user_new(req, msg=None):
    if not manageable_sites(req.user):
        raise HttpError(403)
    return page(req, 'Новый пользователь', (
        '<p><a href="%s">← пользователи</a></p><h1>Новый пользователь</h1>%s<form method="post" action="%s" class="card">%s'
        '<label>Логин (латиница) <input name="login" required pattern="[A-Za-z0-9._-]{3,32}"></label>'
        '<label>Имя (для подписи правок) <input name="name" required maxlength="80"></label>'
        '<label>E-mail (необязательно) <input type="email" name="email" maxlength="120"></label>%s'
        '<p class="muted">После создания вы увидите временный пароль — передайте его человеку лично. При первом входе он включит код 2FA и сменит пароль.</p>'
        '<button>Создать</button></form>') % (url('users'), '<p class="flash error">%s</p>' % e(msg) if msg else '', url('users/new'), csrf_field(req.sess), grants_editor(req)), scripts=['users.js'])


@route('POST', '/users/new')
def user_new_post(req):
    if not manageable_sites(req.user):
        raise HttpError(403)
    login, name = req.f('login').strip(), req.f('name').strip()[:80]
    if not re.fullmatch(r'[A-Za-z0-9._-]{3,32}', login) or not name:
        return user_new(req, 'Логин: 3–32 латинские буквы, цифры, точки, дефисы; имя обязательно.')
    if db.one('SELECT id FROM users WHERE login=?', login):
        return user_new(req, 'Такой логин уже есть.')
    pw = temp_password()
    uid = db.run('INSERT INTO users(login,name,email,pw_hash,must_change_pw,created) VALUES (?,?,?,?,1,?)',
                 login, name, req.f('email').strip()[:120], security.hash_password(pw), time.time())
    save_grants(req, uid)
    db.audit(req.user['id'], 'user_created', detail=login, ip=req.ip)
    return show_temp_password(req, uid, pw)


def show_temp_password(req, uid, pw):
    u = db.one('SELECT * FROM users WHERE id=?', uid)
    return page(req, 'Пароль', ('<h1>Готово: %s</h1><div class="card"><p>Временный пароль (показывается один раз):</p><p class="mono big">%s</p>'
                                '<p>Адрес входа: <span class="mono">%s%s/login</span>. Логин: <b>%s</b>.</p>'
                                '<p class="muted">Передайте пароль лично или в личном сообщении. Человек сменит его при первом входе.</p></div><p><a href="%s">К пользователю</a></p>')
                % (e(u['name']), e(pw), e(config.ORIGIN), e(config.BASE), e(u['login']), url('users/%d' % uid)))


@route('GET', r'/users/(\d+)')
def user_edit(req, uid, msg=None):
    u = db.one('SELECT * FROM users WHERE id=?', int(uid))
    if not u or not can_manage(req, u):
        raise HttpError(403)
    owner_box = ('<label class="check"><input type="checkbox" name="is_owner" value="1"%s> Владелец (все права, все сайты, пользователи и настройки)</label>'
                 % (' checked' if u['is_owner'] else '')) if req.user['is_owner'] and u['id'] != req.user['id'] else ''
    return page(req, u['name'], (
        '<p><a href="%s">← пользователи</a></p><h1>%s</h1>%s<form method="post" action="%s" class="card">%s<input type="hidden" name="do" value="save">'
        '<label>Имя <input name="name" value="%s" required maxlength="80"></label><label>E-mail <input type="email" name="email" value="%s" maxlength="120"></label>'
        '<label class="check"><input type="checkbox" name="active" value="1"%s> Доступ включён</label>%s%s<button>Сохранить</button></form>'
        '<div class="card"><h2>Безопасность</h2><p>Логин: <b>%s</b> · 2FA: %s · последний вход: %s</p>'
        '<form method="post" action="%s" class="inline">%s<button name="do" value="reset_pw">Новый временный пароль</button></form> '
        '<form method="post" action="%s" class="inline">%s<button name="do" value="reset_2fa">Сбросить 2FA (новый телефон)</button></form> '
        '<form method="post" action="%s" class="inline">%s<button name="do" value="logout_all">Завершить все сеансы</button></form></div>'
    ) % (url('users'), e(u['name']), '<p class="flash info">%s</p>' % e(msg) if msg else '', url('users/%d' % u['id']), csrf_field(req.sess),
         e(u['name']), e(u['email']), ' checked' if u['active'] else '', owner_box, '' if u['is_owner'] else grants_editor(req, u),
         e(u['login']), 'включена' if u['totp_enabled'] else 'не включена', ago(u['last_login']),
         url('users/%d' % u['id']), csrf_field(req.sess), url('users/%d' % u['id']), csrf_field(req.sess), url('users/%d' % u['id']), csrf_field(req.sess)), scripts=['users.js'])


@route('POST', r'/users/(\d+)')
def user_edit_post(req, uid):
    u = db.one('SELECT * FROM users WHERE id=?', int(uid))
    if not u or not can_manage(req, u):
        raise HttpError(403)
    do = req.f('do')
    if do == 'reset_pw':
        pw = temp_password()
        db.run('UPDATE users SET pw_hash=?, must_change_pw=1 WHERE id=?', security.hash_password(pw), u['id'])
        db.run('DELETE FROM sessions WHERE user_id=?', u['id'])
        db.audit(req.user['id'], 'password_reset', detail=u['login'], ip=req.ip)
        return show_temp_password(req, u['id'], pw)
    if do == 'reset_2fa':
        db.run("UPDATE users SET totp_enabled=0, totp_secret='', totp_last=0 WHERE id=?", u['id'])
        db.run('DELETE FROM sessions WHERE user_id=?', u['id'])
        db.audit(req.user['id'], '2fa_reset', detail=u['login'], ip=req.ip)
        return user_edit(req, uid, '2FA сброшена: при следующем входе человек привяжет новый телефон.')
    if do == 'logout_all':
        db.run('DELETE FROM sessions WHERE user_id=? AND id<>?', u['id'], req.sess['id'])
        return user_edit(req, uid, 'Все сеансы завершены.')
    name = req.f('name').strip()[:80] or u['name']
    active = 1 if req.f('active') == '1' or u['id'] == req.user['id'] else 0
    is_owner = u['is_owner']
    if req.user['is_owner'] and u['id'] != req.user['id']:
        is_owner = 1 if req.f('is_owner') == '1' else 0
    db.run('UPDATE users SET name=?, email=?, active=?, is_owner=? WHERE id=?', name, req.f('email').strip()[:120], active, is_owner, u['id'])
    if not active:
        db.run('DELETE FROM sessions WHERE user_id=?', u['id'])
    if not is_owner:
        save_grants(req, u['id'])
    db.audit(req.user['id'], 'user_saved', detail=u['login'], ip=req.ip)
    return user_edit(req, uid, 'Сохранено.')


# ---------------------------------------------------------------- settings (owner only)
@route('GET', '/settings')
def settings_page(req, msg=None):
    if not req.user['is_owner']:
        raise HttpError(403)
    has = bool(sites.github_token())
    return page(req, 'Настройки', (
        '<h1>Настройки</h1>%s<div class="card"><h2>Ключ GitHub для публикации</h2><p>Статус: %s</p>'
        '<p>Нужен fine-grained token: GitHub → Settings → Developer settings → Fine-grained tokens → Generate new token. '
        'Repository access: только репозитории сайтов (rakovac.rs, vajska.rs, provala.rs и будущие). Permissions → Repository → <b>Contents: Read and write</b>, остальное не нужно. '
        'Срок — до года. Ключ хранится только на сервере в файле с доступом 600; на странице его потом не видно.</p>'
        '<form method="post" action="%s">%s<input type="hidden" name="do" value="token"><label>Ключ <input type="password" name="token" autocomplete="off" required></label>'
        '<button>Сохранить ключ</button></form></div>'
        '<div class="card"><h2>Сайты</h2><p>Список берётся из admin/sites.conf (rakovac.rs) и hosting/sites.conf движка — новый сайт появится здесь сам.</p><ul>%s</ul></div>'
    ) % ('<p class="flash info">%s</p>' % e(msg) if msg else '', 'задан' if has else '<b>не задан</b> — публикация не работает',
         url('settings'), csrf_field(req.sess), ''.join('<li>%s — %s</li>' % (e(k), e(v)) for k, v in sites.site_list().items())))


@route('POST', '/settings')
def settings_post(req):
    if not req.user['is_owner']:
        raise HttpError(403)
    if req.f('do') == 'token':
        tok = req.f('token').strip()
        if not re.fullmatch(r'(github_pat_|ghp_)[A-Za-z0-9_]{20,250}', tok):
            return settings_page(req, 'Это не похоже на ключ GitHub (он начинается с github_pat_).')
        os.makedirs(config.DATA, mode=0o700, exist_ok=True)
        fd = os.open(config.TOKEN_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w') as f:
            f.write(tok)
        db.audit(req.user['id'], 'token_set', ip=req.ip)
        return settings_page(req, 'Ключ сохранён.')
    raise HttpError(400)


# ---------------------------------------------------------------- log + undo
@route('GET', '/log')
def log_page(req):
    rows = []
    names = {u['id']: u['name'] for u in db.q('SELECT id, name FROM users')}
    for a in db.q('SELECT * FROM audit ORDER BY id DESC LIMIT 300'):
        if not req.user['is_owner'] and not (a['site'] and 'view' in db.perms_for(req.user, a['site'])) and a['user_id'] != req.user['id']:
            continue
        undo = ''
        if a['commit_sha'] and a['site'] and 'publish' in db.perms_for(req.user, a['site']) and a['action'] != 'undo':
            undo = '<form method="post" action="%s" class="inline">%s<input type="hidden" name="sha" value="%s"><button class="link">отменить</button></form>' % (
                url('s/%s/undo' % a['site']), csrf_field(req.sess), e(a['commit_sha']))
        rows.append('<tr><td class="small">%s</td><td>%s</td><td>%s</td><td>%s<div class="muted small">%s</div></td><td>%s</td></tr>' % (
            ago(a['ts']), e(names.get(a['user_id'], '—')), e(a['action']), e(a['site'] or ''), e((a['path'] or '') + (' · ' + a['detail'] if a['detail'] else '')), undo))
    return page(req, 'Журнал', '<h1>Журнал действий</h1><table class="list">%s</table>' % ''.join(rows))


@route('POST', r'/s/([a-z0-9-]+)/undo')
def undo_post(req, site):
    need(req, site, 'publish')
    sha = req.f('sha')
    try:
        new = sites.revert(site, sha, req.user)
    except Conflict as ex:
        raise HttpError(409, str(ex))
    except SiteError as ex:
        raise HttpError(400, str(ex))
    db.audit(req.user['id'], 'undo', site, None, sha, new, req.ip)
    raise Redirect(url('log'))
