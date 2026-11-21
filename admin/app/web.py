"""HTTP server: request parsing, sessions, login with password + one-time code, routing."""
import http.cookies, json, mimetypes, os, re, time, traceback, urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from . import config, db, security, sites
from .html import e, url, frame, csrf_field

COOKIE = 'selo_admin'
STATIC = os.path.join(config.ADMIN_DIR, 'static')
ROUTES = []          # (method, regex, function, needs) ; needs: None | 'login' | 'ok'


def route(method, pattern, needs='ok'):
    def deco(fn):
        ROUTES.append((method, re.compile('^' + pattern + '$'), fn, needs))
        return fn
    return deco


class Redirect(Exception):
    def __init__(self, to):
        self.to = to


class HttpError(Exception):
    def __init__(self, code, msg=''):
        self.code, self.msg = code, msg


class Req:
    """One request: parsed query/form/json, the session and user, and the response being built."""

    def __init__(self, h):
        self.h = h
        self.method = h.command
        u = urllib.parse.urlsplit(h.path)
        self.path = u.path
        self.query = {k: v[-1] for k, v in urllib.parse.parse_qs(u.query, keep_blank_values=True).items()}
        self.ip = h.client_address[0]
        if self.ip in ('127.0.0.1', '::1') and h.headers.get('X-Forwarded-For'):
            self.ip = h.headers['X-Forwarded-For'].split(',')[-1].strip()
        self.ua = (h.headers.get('User-Agent') or '')[:200]
        self.form, self.json, self.raw = {}, None, b''
        self.sess = self.user = None
        self.out_headers = []
        self.flash = None

    def read_body(self):
        n = int(self.h.headers.get('Content-Length') or 0)
        if n > config.MAX_BODY:
            raise HttpError(413, 'Слишком большой запрос.')
        self.raw = self.h.rfile.read(n) if n else b''
        ctype = (self.h.headers.get('Content-Type') or '').split(';')[0].strip()
        if ctype == 'application/x-www-form-urlencoded':
            self.form = {}
            for k, v in urllib.parse.parse_qsl(self.raw.decode('utf-8', 'replace'), keep_blank_values=True):
                if k.endswith('[]'):
                    self.form.setdefault(k, []).append(v)
                else:
                    self.form[k] = v
        elif ctype == 'application/json':
            try:
                self.json = json.loads(self.raw.decode('utf-8'))
            except ValueError:
                raise HttpError(400, 'bad json')

    def f(self, k, default=''):
        v = self.form.get(k, default)
        return v if isinstance(v, list) else str(v)

    def cookie_set(self, value, max_age=None):
        c = http.cookies.SimpleCookie()
        c[COOKIE] = value
        m = c[COOKIE]
        m['path'] = config.BASE + '/'
        m['httponly'] = True
        m['samesite'] = 'Strict'
        if config.SECURE_COOKIE:
            m['secure'] = True
        if max_age is not None:
            m['max-age'] = max_age
        self.out_headers.append(('Set-Cookie', m.OutputString()))


# ---------------------------------------------------------------- sessions
def load_session(req):
    raw = req.h.headers.get('Cookie') or ''
    c = http.cookies.SimpleCookie()
    try:
        c.load(raw)
    except http.cookies.CookieError:
        return
    if COOKIE not in c:
        return
    sid = security.sha256(c[COOKIE].value)
    s = db.one('SELECT * FROM sessions WHERE id=?', sid)
    if not s:
        return
    now = time.time()
    limit = config.PENDING_2FA if s['stage'] != 'ok' else config.SESSION_IDLE
    if now - s['last_seen'] > limit or now - s['created'] > config.SESSION_MAX:
        db.run('DELETE FROM sessions WHERE id=?', sid)
        return
    u = db.one('SELECT * FROM users WHERE id=? AND active=1', s['user_id'])
    if not u:
        db.run('DELETE FROM sessions WHERE id=?', sid)
        return
    if s['stage'] == 'ok' and now - s['last_seen'] > 60:
        db.run('UPDATE sessions SET last_seen=? WHERE id=?', now, sid)
    req.sess, req.user = s, u


def new_session(req, user, stage):
    tok = security.token()
    now = time.time()
    db.run('DELETE FROM sessions WHERE created < ?', now - config.SESSION_MAX)
    db.run('INSERT INTO sessions(id,user_id,stage,csrf,created,last_seen,ip,ua) VALUES (?,?,?,?,?,?,?,?)',
           security.sha256(tok), user['id'], stage, security.token(16), now, now, req.ip, req.ua)
    req.cookie_set(tok)


def end_session(req):
    if req.sess:
        db.run('DELETE FROM sessions WHERE id=?', req.sess['id'])
    req.cookie_set('', max_age=0)


# ---------------------------------------------------------------- brute force protection
def blocked(*keys):
    since = time.time() - config.FAIL_WINDOW
    return any(db.one('SELECT COUNT(*) n FROM attempts WHERE key=? AND ts>?', k, since)['n'] >= config.MAX_FAILS for k in keys)


def failed(*keys):
    now = time.time()
    for k in keys:
        db.run('INSERT INTO attempts(key,ts) VALUES (?,?)', k, now)
    db.run('DELETE FROM attempts WHERE ts<?', now - 24 * 3600)


# ---------------------------------------------------------------- handler
class Handler(BaseHTTPRequestHandler):
    server_version = 'SeloAdmin'
    sys_version = ''

    def log_message(self, fmt, *args):
        pass

    def do_GET(self):
        self.dispatch()

    def do_POST(self):
        self.dispatch()

    def send(self, code, body, ctype='text/html; charset=utf-8', req=None, extra=()):
        if isinstance(body, str):
            body = body.encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'same-origin')
        self.send_header('X-Frame-Options', 'SAMEORIGIN')
        self.send_header('Content-Security-Policy',
                         "default-src 'self'; img-src 'self' data: blob: https:; style-src 'self' 'unsafe-inline'; "
                         "font-src 'self' data:; frame-src 'self'; frame-ancestors 'self'; base-uri 'self'; "
                         "form-action 'self'; object-src 'none'; connect-src 'self'")
        for k, v in list(extra) + (req.out_headers if req else []):
            self.send_header(k, v)
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(body)

    def dispatch(self):
        req = Req(self)
        try:
            if not req.path.startswith(config.BASE + '/') and req.path != config.BASE:
                raise HttpError(404)
            sub = req.path[len(config.BASE):] or '/'
            if sub.startswith('/static/') and self.command == 'GET':
                return self.static(sub[len('/static/'):])
            load_session(req)
            for method, rx, fn, needs in ROUTES:
                m = rx.match(sub)
                if not m or method != self.command:
                    continue
                if self.command == 'POST':
                    req.read_body()
                    check_post(req)
                if needs == 'login' and not req.sess:
                    raise Redirect(url('login'))
                if needs == 'ok':
                    if not req.sess or req.sess['stage'] != 'ok':
                        raise Redirect(url('login'))
                    if req.user['must_change_pw'] and fn.__name__ not in ('password_page', 'password_post', 'logout'):
                        raise Redirect(url('password'))
                out = fn(req, *m.groups())
                if isinstance(out, tuple):           # (content-type, bytes)
                    return self.send(200, out[1], out[0], req)
                if isinstance(out, (dict, list)):
                    return self.send(200, json.dumps(out, ensure_ascii=False), 'application/json; charset=utf-8', req)
                return self.send(200, out, req=req)
            raise HttpError(404)
        except Redirect as r:
            self.send(303, '', req=req, extra=[('Location', r.to)])
        except HttpError as he:
            if req.json is not None or (self.headers.get('Accept') or '').startswith('application/json'):
                self.send(he.code, json.dumps({'ok': False, 'error': he.msg or str(he.code)}, ensure_ascii=False),
                          'application/json; charset=utf-8', req)
            else:
                msg = he.msg or {404: 'Страница не найдена.', 403: 'Нет прав.'}.get(he.code, 'Ошибка.')
                self.send(he.code, frame('Ошибка', '<h1>%s</h1><p><a href="%s">На главную админки</a></p>' % (e(msg), url())), req=req)
        except Exception:
            traceback.print_exc()
            self.send(500, frame('Ошибка', '<h1>Внутренняя ошибка</h1><p>Подробности записаны в журнал сервера.</p>'), req=req)

    def static(self, rel):
        if not re.fullmatch(r'[a-z0-9_./-]+', rel) or '..' in rel:
            return self.send(404, 'not found', 'text/plain')
        p = os.path.join(STATIC, rel)
        if not os.path.isfile(p):
            return self.send(404, 'not found', 'text/plain')
        ctype = mimetypes.guess_type(p)[0] or 'application/octet-stream'
        if ctype.startswith('text/') or ctype.endswith('javascript'):
            ctype += '; charset=utf-8'
        self.send(200, open(p, 'rb').read(), ctype)


def check_post(req):
    """CSRF token of the session + same-origin check for every POST."""
    origin = req.h.headers.get('Origin')
    if origin and origin != config.ORIGIN and not (not config.SECURE_COOKIE and origin.startswith('http://127.0.0.1')):
        raise HttpError(403, 'Запрос с чужого сайта.')
    if req.sess:
        tok = req.h.headers.get('X-CSRF') or req.f('csrf') or ((req.json or {}).get('csrf') if isinstance(req.json, dict) else '')
        if not tok or not security.hmac_eq(tok, req.sess['csrf']):
            raise HttpError(403, 'Сессия устарела, обновите страницу.')


# ---------------------------------------------------------------- login flow
def login_form(msg=None, login=''):
    return frame('Вход', (
        '<div class="card narrow"><h1>Вход в Selo Admin</h1>%s'
        '<form method="post" action="%s"><label>Логин <input name="login" value="%s" autocomplete="username" required autofocus></label>'
        '<label>Пароль <input type="password" name="password" autocomplete="current-password" required></label>'
        '<button>Дальше</button></form></div>') % ('<p class="flash error">%s</p>' % e(msg) if msg else '', url('login'), e(login)))


@route('GET', '/login', needs=None)
def login_page(req):
    if not db.one('SELECT id FROM users LIMIT 1'):
        raise Redirect(url('setup'))
    if req.sess and req.sess['stage'] == 'ok':
        raise Redirect(url())
    return login_form()


@route('POST', '/login', needs=None)
def login_post(req):
    login = req.f('login').strip()[:64]
    pw = req.f('password')
    if blocked('ip:' + req.ip, 'login:' + login.lower()):
        db.audit(None, 'login_blocked', detail=login, ip=req.ip)
        return login_form('Слишком много попыток. Подождите 15 минут.', login)
    u = db.one('SELECT * FROM users WHERE login=? AND active=1', login)
    ok = security.check_password(pw, u['pw_hash'] if u else security.DUMMY_HASH)
    if not (u and ok):
        failed('ip:' + req.ip, 'login:' + login.lower())
        db.audit(u['id'] if u else None, 'login_failed', detail=login, ip=req.ip)
        return login_form('Неверный логин или пароль.', login)
    end_session(req)
    new_session(req, u, 'password')
    raise Redirect(url('2fa') if u['totp_enabled'] else url('setup-2fa'))


@route('GET', '/2fa', needs='login')
def twofa_page(req, msg=None):
    if req.sess['stage'] == 'ok':
        raise Redirect(url())
    if not req.user['totp_enabled']:
        raise Redirect(url('setup-2fa'))
    return frame('Код', (
        '<div class="card narrow"><h1>Код из приложения</h1>%s<p>Откройте приложение-аутентификатор и введите 6 цифр для Selo Admin.</p>'
        '<form method="post" action="%s">%s<label>Код <input name="code" inputmode="numeric" autocomplete="one-time-code" '
        'pattern="[0-9 ]{6,7}" required autofocus></label><button>Войти</button></form></div>'
    ) % ('<p class="flash error">%s</p>' % e(msg) if msg else '', url('2fa'), csrf_field(req.sess)))


def finish_login(req):
    db.run('UPDATE sessions SET stage=? WHERE id=?', 'ok', req.sess['id'])
    db.run('UPDATE users SET last_login=? WHERE id=?', time.time(), req.user['id'])
    db.audit(req.user['id'], 'login', ip=req.ip)
    raise Redirect(url('password') if req.user['must_change_pw'] else url())


@route('POST', '/2fa', needs='login')
def twofa_post(req):
    if req.sess['stage'] == 'ok':
        raise Redirect(url())
    u = req.user
    if blocked('ip:' + req.ip, 'login:' + u['login'].lower()):
        return twofa_page(req, 'Слишком много попыток. Подождите 15 минут.')
    step = security.verify_totp(u['totp_secret'], req.f('code'), u['totp_last'])
    if step is None:
        failed('ip:' + req.ip, 'login:' + u['login'].lower())
        db.audit(u['id'], 'code_failed', ip=req.ip)
        return twofa_page(req, 'Код не подошёл. Проверьте время на телефоне и попробуйте следующий код.')
    db.run('UPDATE users SET totp_last=? WHERE id=?', step, u['id'])
    finish_login(req)


@route('GET', '/setup-2fa', needs='login')
def setup2fa_page(req, msg=None):
    u = req.user
    if u['totp_enabled']:
        raise Redirect(url('2fa') if req.sess['stage'] != 'ok' else url())
    secret = u['totp_secret']
    if not secret:
        secret = security.new_totp_secret()
        db.run('UPDATE users SET totp_secret=? WHERE id=?', secret, u['id'])
    uri = security.totp_uri(secret, u['login'])
    pretty = ' '.join(secret[i:i + 4] for i in range(0, len(secret), 4))
    return frame('Двухэтапная проверка', (
        '<div class="card narrow"><h1>Включите вход по коду</h1>%s'
        '<ol><li>Установите приложение-аутентификатор: Google Authenticator, Microsoft Authenticator, 2FAS или Aegis.</li>'
        '<li>Отсканируйте QR-код (или введите ключ вручную).</li><li>Введите 6 цифр, которые покажет приложение.</li></ol>'
        '<div id="qr" class="qr" data-uri="%s"></div><p class="mono">%s</p>'
        '<form method="post" action="%s">%s<label>Код <input name="code" inputmode="numeric" autocomplete="one-time-code" required autofocus></label>'
        '<button>Включить</button></form></div>'
    ) % ('<p class="flash error">%s</p>' % e(msg) if msg else '', e(uri), e(pretty), url('setup-2fa'), csrf_field(req.sess)),
        scripts=['vendor/qrcode.js', 'qr.js'])


@route('POST', '/setup-2fa', needs='login')
def setup2fa_post(req):
    u = req.user
    if u['totp_enabled']:
        raise Redirect(url())
    if blocked('ip:' + req.ip, 'login:' + u['login'].lower()):
        return setup2fa_page(req, 'Слишком много попыток. Подождите 15 минут.')
    step = security.verify_totp(u['totp_secret'], req.f('code'), 0)
    if step is None:
        failed('ip:' + req.ip, 'login:' + u['login'].lower())
        return setup2fa_page(req, 'Код не подошёл. Проверьте, что время на телефоне точное.')
    db.run('UPDATE users SET totp_enabled=1, totp_last=? WHERE id=?', step, u['id'])
    db.audit(u['id'], '2fa_enabled', ip=req.ip)
    finish_login(req)


@route('POST', '/logout', needs='login')
def logout(req):
    end_session(req)
    raise Redirect(url('login'))


@route('GET', '/password', needs='ok')
def password_page(req, msg=None, kind='error'):
    forced = req.user['must_change_pw']
    return frame('Пароль', (
        '<div class="card narrow"><h1>%s</h1>%s<form method="post" action="%s">%s'
        '<label>Текущий пароль <input type="password" name="old" autocomplete="current-password" required></label>'
        '<label>Новый пароль (не короче 10 символов) <input type="password" name="new" autocomplete="new-password" minlength="10" required></label>'
        '<label>Новый пароль ещё раз <input type="password" name="new2" autocomplete="new-password" minlength="10" required></label>'
        '<button>Сохранить</button></form></div>'
    ) % ('Придумайте свой пароль' if forced else 'Смена пароля',
         '<p class="flash %s">%s</p>' % (kind, e(msg)) if msg else '', url('password'), csrf_field(req.sess)), req.user, req.sess)


@route('POST', '/password', needs='ok')
def password_post(req):
    u = req.user
    if not security.check_password(req.f('old'), u['pw_hash']):
        failed('login:' + u['login'].lower())
        return password_page(req, 'Текущий пароль неверный.')
    new = req.f('new')
    if new != req.f('new2'):
        return password_page(req, 'Пароли не совпадают.')
    prob = security.password_problem(new, u['login'], u['name'])
    if prob:
        return password_page(req, prob)
    db.run('UPDATE users SET pw_hash=?, must_change_pw=0 WHERE id=?', security.hash_password(new), u['id'])
    db.run('DELETE FROM sessions WHERE user_id=? AND id<>?', u['id'], req.sess['id'])     # log out other devices
    db.audit(u['id'], 'password_changed', ip=req.ip)
    raise Redirect(url())


# ---------------------------------------------------------------- first owner (only while there are no users)
def bootstrap_hash():
    try:
        return open(config.BOOTSTRAP_HASH, encoding='utf-8').read().split()[0].strip().lower()
    except (OSError, IndexError):
        return ''


@route('GET', '/setup', needs=None)
def setup_page(req, msg=None):
    if db.one('SELECT id FROM users LIMIT 1'):
        raise Redirect(url('login'))
    if not bootstrap_hash():
        return frame('Настройка', '<div class="card narrow"><h1>Админка ещё не настроена</h1><p>Нет файла admin/bootstrap.sha256.</p></div>')
    return frame('Первый вход', (
        '<div class="card narrow"><h1>Создание владельца</h1>%s<p>Этот шаг работает один раз: пока в админке нет ни одного пользователя.</p>'
        '<form method="post" action="%s"><label>Одноразовый код настройки <input name="code" required autocomplete="off"></label>'
        '<label>Логин <input name="login" required pattern="[A-Za-z0-9._-]{3,32}" autocomplete="username"></label>'
        '<label>Имя (так будет подписан в истории правок) <input name="name" required></label>'
        '<label>Пароль (не короче 10 символов) <input type="password" name="password" minlength="10" required autocomplete="new-password"></label>'
        '<label>Пароль ещё раз <input type="password" name="password2" minlength="10" required autocomplete="new-password"></label>'
        '<button>Создать</button></form></div>') % ('<p class="flash error">%s</p>' % e(msg) if msg else '', url('setup')))


@route('POST', '/setup', needs=None)
def setup_post(req):
    if db.one('SELECT id FROM users LIMIT 1'):
        raise Redirect(url('login'))
    if blocked('ip:' + req.ip, 'setup'):
        return setup_page(req, 'Слишком много попыток. Подождите 15 минут.')
    want = bootstrap_hash()
    if not want or not security.hmac_eq(security.sha256(req.f('code').strip()), want):
        failed('ip:' + req.ip, 'setup')
        db.audit(None, 'setup_failed', ip=req.ip)
        return setup_page(req, 'Код настройки не подошёл.')
    login, name, pw = req.f('login').strip(), req.f('name').strip()[:80], req.f('password')
    if not re.fullmatch(r'[A-Za-z0-9._-]{3,32}', login) or not name:
        return setup_page(req, 'Логин: 3–32 латинские буквы, цифры, точки, дефисы.')
    if pw != req.f('password2'):
        return setup_page(req, 'Пароли не совпадают.')
    prob = security.password_problem(pw, login, name)
    if prob:
        return setup_page(req, prob)
    uid = db.run('INSERT INTO users(login,name,pw_hash,must_change_pw,is_owner,created) VALUES (?,?,?,?,?,?)',
                 login, name, security.hash_password(pw), 0, 1, time.time())
    db.audit(uid, 'owner_created', ip=req.ip)
    u = db.one('SELECT * FROM users WHERE id=?', uid)
    new_session(req, u, 'password')
    raise Redirect(url('setup-2fa'))


def serve():
    os.umask(0o077)          # database, its WAL files and the token stay readable only by the deploy user
    db.init()
    from . import views  # noqa: F401  (registers the routes)
    srv = ThreadingHTTPServer((config.HOST, config.PORT), Handler)
    srv.daemon_threads = True
    print('Selo Admin on http://%s:%d%s/' % (config.HOST, config.PORT, config.BASE), flush=True)
    srv.serve_forever()
