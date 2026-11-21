"""SQLite storage: users, their rights per site, sessions, login attempts, audit log, submissions for review."""
import json, os, sqlite3, threading, time
from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY,
  login TEXT UNIQUE NOT NULL COLLATE NOCASE,
  name TEXT NOT NULL,
  email TEXT NOT NULL DEFAULT '',
  pw_hash TEXT NOT NULL,
  must_change_pw INTEGER NOT NULL DEFAULT 1,
  totp_secret TEXT NOT NULL DEFAULT '',
  totp_enabled INTEGER NOT NULL DEFAULT 0,
  totp_last INTEGER NOT NULL DEFAULT 0,
  is_owner INTEGER NOT NULL DEFAULT 0,
  active INTEGER NOT NULL DEFAULT 1,
  created REAL NOT NULL,
  last_login REAL
);
CREATE TABLE IF NOT EXISTS grants (
  id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  site TEXT NOT NULL,            -- site name or '*' (all sites, also future ones)
  role TEXT NOT NULL,            -- admin | editor | author | viewer
  add_perms TEXT NOT NULL DEFAULT '[]',
  remove_perms TEXT NOT NULL DEFAULT '[]',
  UNIQUE(user_id, site)
);
CREATE TABLE IF NOT EXISTS sessions (
  id TEXT PRIMARY KEY,           -- sha256 of the cookie value
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  stage TEXT NOT NULL,           -- 'password' (needs the code) | 'ok'
  csrf TEXT NOT NULL,
  created REAL NOT NULL,
  last_seen REAL NOT NULL,
  ip TEXT, ua TEXT
);
CREATE TABLE IF NOT EXISTS attempts (key TEXT NOT NULL, ts REAL NOT NULL);
CREATE INDEX IF NOT EXISTS attempts_key ON attempts(key, ts);
CREATE TABLE IF NOT EXISTS audit (
  id INTEGER PRIMARY KEY,
  ts REAL NOT NULL,
  user_id INTEGER,
  site TEXT, action TEXT NOT NULL, path TEXT, detail TEXT, commit_sha TEXT, ip TEXT
);
CREATE TABLE IF NOT EXISTS submissions (
  id INTEGER PRIMARY KEY,
  site TEXT NOT NULL, lang TEXT NOT NULL, path TEXT NOT NULL,
  kind TEXT NOT NULL,            -- edit | create
  content TEXT NOT NULL,         -- the whole proposed file
  base_hash TEXT NOT NULL DEFAULT '',
  message TEXT NOT NULL DEFAULT '',
  user_id INTEGER NOT NULL,
  created REAL NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',    -- pending | published | rejected | withdrawn
  reviewer_id INTEGER, reviewed REAL, comment TEXT NOT NULL DEFAULT '', commit_sha TEXT
);
"""

_local = threading.local()


def conn():
    c = getattr(_local, 'c', None)
    if c is None:
        os.makedirs(config.DATA, mode=0o700, exist_ok=True)
        c = sqlite3.connect(config.DB, timeout=10, isolation_level=None)
        c.row_factory = sqlite3.Row
        c.execute('PRAGMA journal_mode=WAL')
        c.execute('PRAGMA foreign_keys=ON')
        _local.c = c
    return c


def init():
    c = conn()
    c.executescript(SCHEMA)
    try:
        os.chmod(config.DB, 0o600)
    except OSError:
        pass


def q(sql, *args):
    return conn().execute(sql, args).fetchall()


def one(sql, *args):
    return conn().execute(sql, args).fetchone()


def run(sql, *args):
    cur = conn().execute(sql, args)
    return cur.lastrowid


def audit(user_id, action, site=None, path=None, detail=None, commit=None, ip=None):
    if isinstance(detail, (dict, list)):
        detail = json.dumps(detail, ensure_ascii=False)
    run('INSERT INTO audit(ts,user_id,site,action,path,detail,commit_sha,ip) VALUES (?,?,?,?,?,?,?,?)',
        time.time(), user_id, site, action, path, detail, commit, ip)


# ---------------------------------------------------------------- rights
PERMS = ['view', 'edit', 'create', 'publish', 'hide', 'delete', 'photos', 'order', 'review', 'users']
PERM_NAMES = {
    'view': 'смотреть', 'edit': 'править', 'create': 'создавать', 'publish': 'публиковать сразу',
    'hide': 'скрывать', 'delete': 'удалять', 'photos': 'загружать фото', 'order': 'порядок новостей',
    'review': 'проверять чужие правки', 'users': 'пользователи сайта',
}
ROLES = {
    'admin':  ['view', 'edit', 'create', 'publish', 'hide', 'delete', 'photos', 'order', 'review', 'users'],
    'editor': ['view', 'edit', 'create', 'publish', 'hide', 'photos', 'order', 'review'],
    'author': ['view', 'edit', 'create'],          # without "publish": everything goes to review
    'viewer': ['view'],
}
ROLE_NAMES = {'admin': 'администратор сайта', 'editor': 'редактор', 'author': 'автор', 'viewer': 'только просмотр'}


def perms_for(user, site):
    """Set of permissions of a user (row) on one site."""
    if not user or not user['active']:
        return set()
    if user['is_owner']:
        return set(PERMS)
    out = set()
    for g in q("SELECT * FROM grants WHERE user_id=? AND (site=? OR site='*')", user['id'], site):
        p = set(ROLES.get(g['role'], [])) | set(json.loads(g['add_perms']))
        p -= set(json.loads(g['remove_perms']))
        out |= p
    if out and 'view' not in out:
        out.add('view')
    return out


def sites_for(user, all_sites):
    if user['is_owner']:
        return list(all_sites)
    return [s for s in all_sites if 'view' in perms_for(user, s)]
