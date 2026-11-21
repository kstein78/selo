"""Unit tests: passwords, one-time codes, front matter editing, rights.  python3 -m unittest discover admin/tests"""
import os, sys, tempfile, time, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ['SELO_ADMIN_DATA'] = tempfile.mkdtemp()
from app import security, frontmatter as fmx, db, content, sites  # noqa: E402


class Security(unittest.TestCase):
    def test_password(self):
        h = security.hash_password('correct horse battery')
        self.assertTrue(security.check_password('correct horse battery', h))
        self.assertFalse(security.check_password('correct horse batterY', h))
        self.assertFalse(security.check_password('x', 'garbage'))
        self.assertNotEqual(h, security.hash_password('correct horse battery'))   # salted

    def test_password_rules(self):
        self.assertIsNotNone(security.password_problem('short'))
        self.assertIsNotNone(security.password_problem('kosta-kosta-123', login='kosta'))
        self.assertIsNotNone(security.password_problem('aaaaaaaaaaaa'))
        self.assertIsNone(security.password_problem('Ракавац-2026-лес!'))

    def test_totp_rfc6238(self):
        # RFC 6238 test vector (SHA1, secret "12345678901234567890"), last 6 digits
        import base64
        secret = base64.b32encode(b'12345678901234567890').decode()
        self.assertEqual(security.totp_now(secret, 59), '287082')
        self.assertEqual(security.totp_now(secret, 1111111109), '081804')

    def test_totp_no_reuse(self):
        s = security.new_totp_secret()
        now = time.time()
        code = security.totp_now(s, now)
        step = security.verify_totp(s, code, 0, now)
        self.assertIsNotNone(step)
        self.assertIsNone(security.verify_totp(s, code, step, now))          # same code twice: refused
        self.assertIsNone(security.verify_totp(s, '000000' if code != '000000' else '111111', 0, now))
        self.assertIsNone(security.verify_totp(s, security.totp_now(s, now - 120), 0, now))   # too old


class FrontMatter(unittest.TestCase):
    TEXT = '---\ntitle: "Old"\n# a comment\nlead: >-\n  long\n  lead\ntags: [a, b]\nweight: 3\n---\n\nBody **text**.\n'

    def test_keeps_other_lines(self):
        new = fmx.update(self.TEXT, {'title': 'New: title'})
        self.assertIn('# a comment\nlead: >-\n  long\n  lead\ntags: [a, b]\nweight: 3\n', new)
        self.assertEqual(fmx.get(new)[0]['title'], 'New: title')
        self.assertTrue(new.endswith('\nBody **text**.\n'))

    def test_unchanged_value_keeps_spelling(self):
        self.assertEqual(fmx.update(self.TEXT, {'title': 'Old', 'weight': 3}), self.TEXT)

    def test_replace_block_and_remove_and_add(self):
        new = fmx.update(self.TEXT, {'lead': 'short', 'weight': None, 'draft': True})
        d = fmx.get(new)[0]
        self.assertEqual(d['lead'], 'short')
        self.assertNotIn('weight', d)
        self.assertIs(d['draft'], True)
        self.assertEqual(d['tags'], ['a', 'b'])

    def test_quotes_and_unicode(self):
        new = fmx.update(self.TEXT, {'title': 'Раковац: «да» — "кавычки" # не комментарий'})
        self.assertEqual(fmx.get(new)[0]['title'], 'Раковац: «да» — "кавычки" # не комментарий')


class Rights(unittest.TestCase):
    def setUp(self):
        db.init()
        for t in ('grants', 'users'):
            db.run('DELETE FROM %s' % t)
        self.uid = db.run("INSERT INTO users(login,name,pw_hash,created) VALUES ('ed','Ed','x',0)")

    def user(self):
        return db.one('SELECT * FROM users WHERE id=?', self.uid)

    def test_roles_and_overrides(self):
        db.run("INSERT INTO grants(user_id,site,role,add_perms,remove_perms) VALUES (?, 'vajska', 'editor', '[\"delete\"]', '[\"publish\"]')", self.uid)
        p = db.perms_for(self.user(), 'vajska')
        self.assertIn('delete', p)
        self.assertNotIn('publish', p)
        self.assertEqual(db.perms_for(self.user(), 'provala'), set())

    def test_all_sites_grant(self):
        db.run("INSERT INTO grants(user_id,site,role) VALUES (?, '*', 'author')", self.uid)
        self.assertEqual(db.perms_for(self.user(), 'any-future-site'), {'view', 'edit', 'create'})

    def test_inactive_and_owner(self):
        db.run("INSERT INTO grants(user_id,site,role) VALUES (?, '*', 'admin')", self.uid)
        db.run('UPDATE users SET active=0 WHERE id=?', self.uid)
        self.assertEqual(db.perms_for(self.user(), 'vajska'), set())
        db.run('UPDATE users SET active=1, is_owner=1 WHERE id=?', self.uid)
        self.assertEqual(db.perms_for(self.user(), 'x'), set(db.PERMS))


class Paths(unittest.TestCase):
    def test_bad_paths(self):
        for bad in ('../x.md', 'a/../b.md', '/etc/passwd.md', 'a//b.md', 'A.md', 'x.txt', 'a/.git/x.md', ''):
            with self.assertRaises(sites.SiteError, msg=bad):
                sites.check_rel(bad)
        self.assertEqual(sites.check_rel('news/2026-11-21-x.md'), 'news/2026-11-21-x.md')
        self.assertEqual(sites.check_rel('history/_index.md'), 'history/_index.md')

    def test_slug(self):
        self.assertEqual(content.slugify('Šnicla de la Provala!'), 'snicla-de-la-provala')
        self.assertEqual(content.slugify('Прогулка по Раковцу'), 'progulka-po-rakovcu')


if __name__ == '__main__':
    unittest.main()
