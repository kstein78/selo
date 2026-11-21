"""Passwords (scrypt), one-time codes (TOTP, RFC 6238), random tokens. Standard library only."""
import base64, hashlib, hmac, os, secrets, struct, time

SCRYPT_N, SCRYPT_R, SCRYPT_P = 2 ** 14, 8, 1


def hash_password(password):
    salt = os.urandom(16)
    dk = hashlib.scrypt(password.encode('utf-8'), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, maxmem=64 * 1024 * 1024, dklen=32)
    return 'scrypt$%d$%d$%d$%s$%s' % (SCRYPT_N, SCRYPT_R, SCRYPT_P, base64.b64encode(salt).decode(), base64.b64encode(dk).decode())


def check_password(password, stored):
    try:
        kind, n, r, p, salt, dk = stored.split('$')
        if kind != 'scrypt':
            return False
        got = hashlib.scrypt(password.encode('utf-8'), salt=base64.b64decode(salt), n=int(n), r=int(r), p=int(p),
                             maxmem=64 * 1024 * 1024, dklen=32)
        return hmac.compare_digest(got, base64.b64decode(dk))
    except Exception:
        return False


# A fixed hash to spend the same time on unknown logins (no hint which logins exist).
DUMMY_HASH = hash_password(secrets.token_hex(8))


def password_problem(password, login='', name=''):
    """None if the password is acceptable, else a reason (in Russian, shown to the user)."""
    if len(password) < 10:
        return 'Пароль короче 10 символов.'
    low = password.lower()
    for bad in (login.lower(), name.lower()):
        if bad and len(bad) >= 3 and bad in low:
            return 'Пароль не должен содержать логин или имя.'
    if len(set(password)) < 5:
        return 'В пароле слишком мало разных символов.'
    if low in ('1234567890', 'qwertyuiop', 'password12', 'rakovac123', 'admin12345'):
        return 'Слишком простой пароль.'
    return None


def new_totp_secret():
    return base64.b32encode(os.urandom(20)).decode().rstrip('=')


def _hotp(secret, counter):
    key = base64.b32decode(secret + '=' * (-len(secret) % 8), casefold=True)
    digest = hmac.new(key, struct.pack('>Q', counter), hashlib.sha1).digest()
    off = digest[-1] & 0x0F
    code = (struct.unpack('>I', digest[off:off + 4])[0] & 0x7FFFFFFF) % 1000000
    return '%06d' % code


def totp_now(secret, t=None):
    return _hotp(secret, int((t if t is not None else time.time()) // 30))


def verify_totp(secret, code, last_counter=0, t=None):
    """Returns the matched time step (to remember, so a code cannot be used twice) or None."""
    code = (code or '').strip().replace(' ', '')
    if not (len(code) == 6 and code.isdigit()) or not secret:
        return None
    now = int((t if t is not None else time.time()) // 30)
    for step in (now - 1, now, now + 1):
        if step > (last_counter or 0) and hmac.compare_digest(_hotp(secret, step), code):
            return step
    return None


def totp_uri(secret, login, issuer='Selo Admin'):
    from urllib.parse import quote
    return 'otpauth://totp/%s:%s?secret=%s&issuer=%s&digits=6&period=30' % (quote(issuer), quote(login), secret, quote(issuer))


def token(n=32):
    return secrets.token_urlsafe(n)


def sha256(s):
    return hashlib.sha256(s.encode('utf-8')).hexdigest()


def hmac_eq(a, b):
    return hmac.compare_digest(str(a).encode('utf-8'), str(b).encode('utf-8'))
