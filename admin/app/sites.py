"""The sites of the network and their Git working copies.

Each site gets its own clone in <data>/repos/<name> that only the admin touches. A write is a function that
changes files in a freshly synced clone; the runner commits and pushes it, and if somebody else pushed in
between (GitHub Actions, another editor), it syncs again and re-applies the change (up to 3 times)."""
import hashlib, os, re, subprocess, sys, threading, time
from . import config

_locks = {}
_synced = {}
_info = {}


class SiteError(Exception):
    pass


class Conflict(SiteError):
    pass


def site_list():
    """{name: repo url} from admin/sites.conf (rakovac.rs) and hosting/sites.conf (engine sites)."""
    out = {}
    for f in config.SITES_FILES:
        if not os.path.exists(f):
            continue
        for line in open(f, encoding='utf-8'):
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            parts = line.split()
            if len(parts) >= 2 and re.fullmatch(r'[a-z0-9-]+', parts[0]):
                out.setdefault(parts[0], parts[1])
    return out


def remote(name):
    if config.REMOTE_OVERRIDE:
        return os.path.join(config.REMOTE_OVERRIDE, name + '.git')
    return site_list()[name]


def path(name):
    if name not in site_list():
        raise SiteError('unknown site')
    return os.path.join(config.REPOS, name)


def lock(name):
    return _locks.setdefault(name, threading.Lock())


def git(name, *args, check=True, env=None, timeout=180):
    e = dict(os.environ, GIT_TERMINAL_PROMPT='0', LC_ALL='C')
    if env:
        e.update(env)
    r = subprocess.run(['git', '-C', path(name)] + list(args), capture_output=True, text=True, env=e, timeout=timeout)
    if check and r.returncode != 0:
        raise SiteError('git %s: %s' % (args[0], (r.stderr or r.stdout).strip()[-500:]))
    return r


def ensure_clone(name):
    p = path(name)
    if os.path.isdir(os.path.join(p, '.git')):
        return
    os.makedirs(config.REPOS, exist_ok=True)
    r = subprocess.run(['git', 'clone', '-q', '--recurse-submodules', remote(name), p], capture_output=True, text=True,
                       env=dict(os.environ, GIT_TERMINAL_PROMPT='0'), timeout=600)
    if r.returncode != 0:
        raise SiteError('clone failed: ' + r.stderr.strip()[-300:])


def sync(name, force=False):
    """Make the working copy equal to origin/main (it never holds unpushed work)."""
    ensure_clone(name)
    if not force and time.time() - _synced.get(name, 0) < 20:
        return
    git(name, 'fetch', '-q', 'origin', 'main')
    git(name, 'reset', '-q', '--hard', 'FETCH_HEAD')
    git(name, 'clean', '-qffd')
    if os.path.exists(os.path.join(path(name), '.gitmodules')):
        git(name, 'submodule', 'update', '-q', '--init', '--recursive', timeout=600)
    _synced[name] = time.time()
    _info.pop(name, None)


def sync_quiet(name):
    """For read-only views: refresh at most every 20 s, never wait for a running write."""
    l = lock(name)
    if l.acquire(blocking=False):
        try:
            sync(name)
        except SiteError:
            pass
        finally:
            l.release()


def head(name):
    return git(name, 'rev-parse', 'HEAD').stdout.strip()


# ---------------------------------------------------------------- hugo.toml (tiny reader: Python < 3.11 has no tomllib)
def _toml(text):
    try:
        import tomllib
        return tomllib.loads(text)
    except ImportError:
        pass
    import json
    data = {}
    cur = data
    for raw in text.split('\n'):
        line = raw.strip()
        if not line or line.startswith('#'):
            continue
        m = re.match(r'^\[\[?([^\]]+)\]\]?$', line)
        if m:
            cur = data
            for part in m.group(1).split('.'):
                cur = cur.setdefault(part.strip().strip('"'), {})
            continue
        m = re.match(r'^([A-Za-z0-9_"-]+)\s*=\s*(.+)$', line)
        if not m:
            continue
        k, v = m.group(1).strip('"'), m.group(2).strip()
        if v.startswith('"'):
            mm = re.match(r'^"((?:[^"\\]|\\.)*)"', v)
            v = json.loads('"%s"' % mm.group(1)) if mm else v
        elif v.startswith('['):
            v = re.findall(r'"([^"]*)"', v)
        elif v in ('true', 'false'):
            v = v == 'true'
        else:
            try:
                v = int(v)
            except ValueError:
                pass
        cur[k] = v
    return data


def info(name):
    """Domain, title and languages of a site, from its hugo.toml (cached until the next sync)."""
    if name in _info:
        return _info[name]
    p = path(name)
    cfg = _toml(open(os.path.join(p, 'hugo.toml'), encoding='utf-8').read())
    disabled = set(cfg.get('disableLanguages') or [])
    langs = []
    for code, lc in (cfg.get('languages') or {}).items():
        if code in disabled or not os.path.isdir(os.path.join(p, 'content', code)):
            continue
        langs.append((lc.get('weight', 99), code, lc.get('languageName', code)))
    langs.sort()
    codes = [c for _, c, _ in langs]
    generated = {'cyr'} if 'cyr' in codes and 'sr' in codes else set()
    scripts = 'scripts' if os.path.exists(os.path.join(p, 'scripts', 'sr_cyrl.py')) else 'themes/selo/scripts'
    base = (cfg.get('baseURL') or '').rstrip('/')
    i = {
        'name': name,
        'title': cfg.get('title') or name,
        'url': base,
        'domain': re.sub(r'^https?://', '', base),
        'langs': [{'code': c, 'name': n, 'generated': c in generated} for _, c, n in langs],
        'editable': [c for c in codes if c not in generated],
        'default': cfg.get('defaultContentLanguage') or (codes[0] if codes else 'en'),
        'scripts': scripts,
        'theme_css': os.path.exists(os.path.join(p, 'themes', 'selo', 'assets', 'css', 'main.css')),
    }
    _info[name] = i
    return i


# ---------------------------------------------------------------- safe paths
_SEG = re.compile(r'^[a-z0-9_][a-z0-9._-]*$')


def check_rel(rel):
    """A content path like 'news/2026-11-21-x.md' or 'history/_index.md'."""
    if not isinstance(rel, str) or not rel.endswith('.md') or len(rel) > 200:
        raise SiteError('bad path')
    parts = rel.split('/')
    if any(not _SEG.match(s) or s in ('.', '..') for s in parts):
        raise SiteError('bad path')
    return rel


def check_lang(name, lang, editable=True):
    i = info(name)
    if lang not in (i['editable'] if editable else [l['code'] for l in i['langs']]):
        raise SiteError('bad language')
    return lang


def content_file(name, lang, rel):
    return os.path.join(path(name), 'content', check_lang(name, lang, editable=False), check_rel(rel))


def text_hash(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()[:16]


# ---------------------------------------------------------------- writing
def _askpass():
    p = os.path.join(config.DATA, 'git-askpass.sh')
    if not os.path.exists(p):
        with open(p, 'w') as f:
            f.write('#!/bin/sh\ncase "$1" in Username*) echo x-access-token ;; *) echo "$SELO_GIT_TOKEN" ;; esac\n')
        os.chmod(p, 0o700)
    return p


def github_token():
    try:
        return open(config.TOKEN_FILE, encoding='utf-8').read().strip()
    except OSError:
        return ''


def can_push():
    return bool(config.REMOTE_OVERRIDE) or bool(github_token())


def _push(name):
    if not config.PUSH:
        return True
    if config.REMOTE_OVERRIDE:
        return git(name, 'push', '-q', 'origin', 'HEAD:main', check=False).returncode == 0
    tok = github_token()
    if not tok:
        raise SiteError('Не задан ключ GitHub (владелец вводит его в «Настройках»).')
    url = remote(name)
    if url.startswith('https://github.com/'):
        url = url.replace('https://github.com/', 'https://x-access-token@github.com/')
    r = git(name, '-c', 'credential.helper=', '-c', 'core.askPass=' + _askpass(), 'push', '-q', url, 'HEAD:main',
            check=False, env={'SELO_GIT_TOKEN': tok, 'GIT_ASKPASS': _askpass()})
    if r.returncode != 0:
        err = (r.stderr or '').lower()
        if 'rejected' in err or 'fetch first' in err or 'non-fast-forward' in err:
            return False
        raise SiteError('GitHub не принял изменения: ' + (r.stderr or '').strip()[-300:].replace(tok, '***'))
    return True


def regenerate(name, changed):
    """After a change in Serbian Latin: the Cyrillic copy is generated by the site's sr_cyrl.py."""
    i = info(name)
    if 'cyr' not in [l['code'] for l in i['langs']]:
        return
    if not any(c.startswith(('content/sr/', 'data/photos.yaml')) for c in changed):
        return
    script = os.path.join(path(name), i['scripts'], 'sr_cyrl.py')
    if not os.path.exists(script):
        return
    env = dict(os.environ, PYTHONPATH=config.VENDOR, SITE_ROOT=path(name))
    r = subprocess.run([sys.executable, script], cwd=path(name), capture_output=True, text=True, env=env, timeout=300)
    if r.returncode != 0:
        raise SiteError('sr_cyrl.py: ' + (r.stderr or r.stdout).strip()[-300:])


def write(name, op, message, user):
    """Run op(repo_path) -> list of changed paths (relative), commit as the user, push. Returns the commit sha
    (None if nothing changed). op may raise Conflict/SiteError; it is re-run on a fresh copy if a push races."""
    if not can_push():
        raise SiteError('Не задан ключ GitHub (владелец вводит его в «Настройках»).')
    with lock(name):
        for attempt in range(3):
            sync(name, force=True)
            try:
                changed = op(path(name))
                if not changed:
                    return None
                regenerate(name, changed)
                git(name, 'add', '-A')
                if not git(name, 'status', '--porcelain').stdout.strip():
                    return None
                author = '%s <%s>' % (user['name'].replace('<', '').replace('>', ''), (user['email'] or ('%s@users.selo-admin' % user['login'])))
                git(name, '-c', 'user.name=Selo Admin', '-c', 'user.email=admin@selo-admin', 'commit', '-q',
                    '--author', author, '-m', message[:300] + '\n\nSelo Admin, ' + user['name'])
                sha = head(name)
                if _push(name):
                    _synced[name] = time.time()
                    _info.pop(name, None)
                    return sha
            except Exception:
                git(name, 'reset', '-q', '--hard', 'origin/main', check=False)
                git(name, 'clean', '-qffd', check=False)
                raise
        raise SiteError('Не удалось отправить изменения: кто-то параллельно меняет сайт. Попробуйте ещё раз.')


def revert(name, sha, user):
    if not re.fullmatch(r'[0-9a-f]{7,40}', sha or ''):
        raise SiteError('bad commit')

    def op(p):
        r = git(name, '-c', 'user.name=Selo Admin', '-c', 'user.email=admin@selo-admin', 'revert', '--no-commit', sha, check=False)
        if r.returncode != 0:
            raise Conflict('Эту правку нельзя отменить автоматически: после неё файл уже меняли.')
        return [l[3:] for l in git(name, 'status', '--porcelain').stdout.splitlines()]
    return write(name, op, 'Undo %s' % sha[:7], user)
