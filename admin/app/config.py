"""Settings of Selo Admin, all from environment variables (the server sets nothing: defaults fit the
rakovac.rs server, where the admin runs as the "deploy" user behind Caddy at https://rakovac.rs/admin/)."""
import os

ADMIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # .../selo/admin
ENGINE_DIR = os.path.dirname(ADMIN_DIR)                                    # .../selo

DATA = os.path.abspath(os.environ.get('SELO_ADMIN_DATA') or os.path.expanduser('~/selo/admin-data'))
HOST = os.environ.get('SELO_ADMIN_HOST', '127.0.0.1')
PORT = int(os.environ.get('SELO_ADMIN_PORT', '8737'))
BASE = (os.environ.get('SELO_ADMIN_BASE') or '/admin').rstrip('/')          # URL prefix behind Caddy
ORIGIN = os.environ.get('SELO_ADMIN_ORIGIN', 'https://rakovac.rs')          # for the Origin check of POSTs
SECURE_COOKIE = os.environ.get('SELO_ADMIN_INSECURE_COOKIE') != '1'        # only local tests turn this off
# Git remotes: "https://github.com/kstein78/{repo}.git" from the site lists; tests point this at local bare repos.
REMOTE_OVERRIDE = os.environ.get('SELO_ADMIN_REMOTE_DIR')                   # dir with <name>.git bare repos (tests)
PUSH = os.environ.get('SELO_ADMIN_PUSH', '1') == '1'

DB = os.path.join(DATA, 'admin.sqlite3')
REPOS = os.path.join(DATA, 'repos')
TOKEN_FILE = os.path.join(DATA, 'github-token')       # written by the owner on the Settings page, mode 600
SITES_FILES = [os.path.join(ADMIN_DIR, 'sites.conf'), os.path.join(ENGINE_DIR, 'hosting', 'sites.conf')]
BOOTSTRAP_HASH = os.path.join(ADMIN_DIR, 'bootstrap.sha256')
VENDOR = os.path.join(ADMIN_DIR, 'vendor')

SESSION_IDLE = 12 * 3600          # seconds without activity before a new login is needed
SESSION_MAX = 14 * 24 * 3600      # absolute session lifetime
PENDING_2FA = 5 * 60              # time to enter the code after the password
MAX_FAILS = 5                     # failed logins per account or per IP address ...
FAIL_WINDOW = 15 * 60             # ... within this window block further attempts
MAX_BODY = 25 * 1024 * 1024       # largest request (photo uploads)
MIN_PASSWORD = 10
