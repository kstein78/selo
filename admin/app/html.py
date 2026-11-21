"""Small HTML helpers: escaping, the page frame, forms. Every value that comes from users or files goes through e()."""
import html, json
from . import config


def e(s):
    return html.escape('' if s is None else str(s), quote=True)


def url(path=''):
    return config.BASE + '/' + path.lstrip('/')


def js_data(obj):
    """JSON for <script type="application/json">: safe against </script> inside strings."""
    return json.dumps(obj, ensure_ascii=False).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')


def csrf_field(sess):
    return '<input type="hidden" name="csrf" value="%s">' % e(sess['csrf']) if sess else ''


def frame(title, body, user=None, sess=None, wide=False, flash=None, extra_head='', scripts=()):
    nav = ''
    if user and sess and sess['stage'] == 'ok':
        nav = (
            '<nav class="top"><a class="brand" href="%s">Selo Admin</a>'
            '<a href="%s">Сайты</a><a href="%s">Проверка</a><a href="%s">Пользователи</a><a href="%s">Журнал</a>%s'
            '<span class="who">%s · <a href="%s">пароль</a></span>'
            '<form method="post" action="%s" class="inline">%s<button class="link">Выйти</button></form></nav>'
        ) % (url(), url(), url('review'), url('users'), url('log'),
             ('<a href="%s">Настройки</a>' % url('settings')) if user['is_owner'] else '',
             e(user['name']), url('password'), url('logout'), csrf_field(sess))
    fl = ''
    if flash:
        kind, msg = flash
        fl = '<p class="flash %s">%s</p>' % (e(kind), e(msg))
    sc = ''.join('<script src="%s"></script>' % url('static/' + s) for s in scripts)
    return (
        '<!doctype html><html lang="ru"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<meta name="robots" content="noindex, nofollow">'
        '<title>%s · Selo Admin</title><link rel="stylesheet" href="%s">%s</head>'
        '<body class="%s">%s<main>%s%s</main>%s</body></html>'
    ) % (e(title), url('static/admin.css'), extra_head, 'wide' if wide else '', nav, fl, body, sc)


def select(name, options, value=None, attrs=''):
    """options: list of (value, label)."""
    o = ''.join('<option value="%s"%s>%s</option>' % (e(v), ' selected' if str(v) == str(value) else '', e(l)) for v, l in options)
    return '<select name="%s" %s>%s</select>' % (e(name), attrs, o)


def ago(ts):
    import time
    if not ts:
        return '—'
    return time.strftime('%d.%m.%Y %H:%M', time.localtime(ts))
