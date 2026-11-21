"""Reading and changing Hugo front matter without reformatting the rest of the file.

Only the keys that are changed are rewritten; every other line (comments, order, quoting) stays as it was,
so a commit from the admin shows exactly what the editor changed."""
import re, sys
from . import config
if config.VENDOR not in sys.path:
    sys.path.insert(0, config.VENDOR)
import yaml  # noqa: E402  (vendored PyYAML, pure Python)


def split(text):
    """(front matter text without the --- lines, body). Files without front matter: ('', text)."""
    if text.startswith('---\n') or text.startswith('---\r\n'):
        t = text.replace('\r\n', '\n')
        end = t.find('\n---\n', 3)
        if end == -1 and t.endswith('\n---'):
            end = len(t) - 4
        if end != -1:
            return t[4:end + 1], t[end + 5:]
    return '', text


def join(fm, body):
    fm = fm if fm.endswith('\n') or not fm else fm + '\n'
    return '---\n' + fm + '---\n' + body


def parse(fm):
    try:
        data = yaml.safe_load(fm) if fm.strip() else {}
        return data if isinstance(data, dict) else {}
    except yaml.YAMLError:
        return {}


_KEY = re.compile(r'^([A-Za-z_][\w-]*)\s*:')


def _blocks(fm):
    """Top-level keys with their line ranges: {key: (start, end)} (end exclusive)."""
    lines = fm.split('\n')
    if lines and lines[-1] == '':
        lines = lines[:-1]
    out, cur, start = {}, None, 0
    for i, line in enumerate(lines):
        m = _KEY.match(line)
        if m and not line.startswith((' ', '\t', '-', '#')):
            if cur is not None:
                out[cur] = (start, i)
            cur, start = m.group(1), i
    if cur is not None:
        out[cur] = (start, len(lines))
    # trailing blank/comment lines belong to nobody
    for k, (s, e) in list(out.items()):
        while e - 1 > s and (lines[e - 1].strip() == '' or lines[e - 1].lstrip().startswith('#')):
            e -= 1
        out[k] = (s, e)
    return lines, out


def dump_value(key, value):
    s = yaml.safe_dump({key: value}, allow_unicode=True, sort_keys=False, width=100000, default_flow_style=False)
    return s.rstrip('\n')


def set_keys(fm, changes):
    """changes: {key: value or None (= remove)}. Returns new front matter text."""
    lines, blocks = _blocks(fm)
    # replace or remove from the bottom up so earlier ranges stay valid
    for key, (s, e) in sorted(blocks.items(), key=lambda kv: -kv[1][0]):
        if key in changes:
            val = changes[key]
            if val is None:
                lines[s:e] = []
            else:
                if parse('\n'.join(lines[s:e])).get(key) == val:
                    continue                                   # unchanged: keep the original spelling
                lines[s:e] = dump_value(key, val).split('\n')
    for key, val in changes.items():
        if key not in blocks and val is not None:
            lines.extend(dump_value(key, val).split('\n'))
    return '\n'.join(lines) + '\n'


def get(text):
    fm, body = split(text)
    return parse(fm), body


def update(text, changes, body=None):
    fm, old_body = split(text)
    return join(set_keys(fm, changes), old_body if body is None else body)
