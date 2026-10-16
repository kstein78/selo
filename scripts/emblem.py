#!/usr/bin/env python3
"""Shield emblem of a site of the network, drawn in the family shape of the rakovac.rs shield R.

Same shield outline, inner line and layout as rakovac.rs (letter in the middle, two small motifs in the top corners,
one motif under the letter), but each site has its own letter, motifs and colours. Configured in hugo.toml:

  [params.emblem]
    letter = "V"                 # first letter of the place, drawn with Rakovac Common
    corner = "wheat"             # motif in both top corners (mirrored)
    base = "swan"                # motif under the letter
    shield = "#6b1f24"           # shield colour
    line = "#d9a441"             # inner line
    ink = "#f7efe0"              # letter
    motif = "#e3b65a"            # motifs
    mono = "#f5efe3"             # one-colour version (header, footer, placeholders on dark/light grounds)

Run from the site folder: python3 themes/selo/scripts/emblem.py
Writes static/img/brand-shield.svg (colour), static/img/brand-shield-mono.svg (one colour, motifs cut out),
static/favicon.svg and the PNG icons (favicon-16/32/48, apple-touch-icon, icon-192/512, favicon.ico).
Motifs: swan, waves, fish, wheat, reed, cross, leaf, sun."""
import os, sys, io
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from siteconf import ROOT, PARAMS  # noqa: E402
from fontTools.ttLib import TTFont
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.boundsPen import BoundsPen

ENGINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHIELD = 'M20 20H180V130C180 190 140 222 100 234C60 222 20 190 20 130Z'

# Motifs in a box of about -20..20 (x) by -20..20 (y), drawn with strokes (and a few fills marked F).
MOTIFS = {
    'swan': [
        'M-15 4C-12 10 8 11 15 1C10 3 5 3 3 1C0-2 0-8 3-11C6-14 5-18 1-18C-2-18-4-16-4-13',
        'F:M-4-13L-9-12L-4-11Z',
        'M-11 3C-7-3 0-3 5 1',
        'M-18 13C-12 10-6 16 0 13S12 10 18 13',
    ],
    'waves': ['M-18-6C-12-10-6-2 0-6S12-10 18-6', 'M-18 2C-12-2-6 6 0 2S12-2 18 2', 'M-18 10C-12 6-6 14 0 10S12 6 18 10'],
    'fish': [
        'M-14 0C-8-8 6-8 11 0C6 8-8 8-14 0Z',
        'M11 0L18-6V6Z',
        'M-6-5C-4-2-4 2-6 5',
        'F:M-9-1.5A1.5 1.5 0 1 0-9 1.5A1.5 1.5 0 1 0-9-1.5Z',
        'M-18 13C-12 10-6 16 0 13S12 10 18 13',
    ],
    'wheat': [
        'M0 18V-16',
        'M0-12C-5-14-6-18-5-20C-1-19 0-16 0-12Z', 'M0-12C5-14 6-18 5-20C1-19 0-16 0-12Z',
        'M0-3C-5-5-7-9-6-12C-2-11 0-7 0-3Z', 'M0-3C5-5 7-9 6-12C2-11 0-7 0-3Z',
        'M0 6C-5 4-7 0-6-3C-2-2 0 2 0 6Z', 'M0 6C5 4 7 0 6-3C2-2 0 2 0 6Z',
        'M0-16L0-22',
    ],
    'reed': ['M-3 18C-3 6-2-4-2-14', 'F:M-4.5-20H0.5V-8H-4.5Z', 'M3 18C3 8 5 0 9-6', 'M-3 10C-8 4-12-2-13-8', 'M3 12C8 8 12 6 16 6'],
    'cross': ['M0-16V16', 'M-10-6H10'],
    'leaf': ['M0 20C-6 13-21 15-19 3C-28-1-25-14-14-11C-15-22-4-25 0-18C4-25 15-22 14-11C25-14 28-1 19 3C21 15 6 13 0 20Z',
             'M0 17V-12M0 5L-12-5M0 5L12-5M0 12L-13 5M0 12L13 5'],
    'sun': ['M0-7A7 7 0 1 0 0 7A7 7 0 1 0 0-7Z', 'M0-17V-11M0 11V17M-17 0H-11M11 0H17M-12-12L-8-8M8 8L12 12M-12 12L-8 8M8-8L12-12'],
}


def letter_path(ch):
    f = TTFont(os.path.join(ENGINE, 'static', 'fonts', 'rakovac-common-latin-400-normal.woff2'))
    gs = f.getGlyphSet()
    name = f.getBestCmap()[ord(ch)]
    bp = BoundsPen(gs); gs[name].draw(bp)
    x0, y0, x1, y1 = bp.bounds
    pen = SVGPathPen(gs); gs[name].draw(pen)
    return pen.getCommands(), (x0, y0, x1, y1)


def motif(name, tx, ty, scale, colour, stroke, mirror=False, rot=0):
    out = []
    sx = -scale if mirror else scale
    tr = f'translate({tx} {ty}) rotate({rot}) scale({sx} {scale})'
    for d in MOTIFS[name]:
        if d.startswith('F:'):
            out.append(f'<path d="{d[2:]}" fill="{colour}"/>')
        else:
            out.append(f'<path d="{d}" fill="none" stroke="{colour}" stroke-width="{stroke / scale:.2f}" stroke-linecap="round" stroke-linejoin="round"/>')
    return f'<g transform="{tr}">' + ''.join(out) + '</g>'


def build(e, mono=None):
    """mono=None: colour emblem. mono=<colour>: one colour with the drawing cut out (mask)."""
    d, (x0, y0, x1, y1) = letter_path(e.get('letter', 'A'))
    h = 82.0  # letter height in shield units
    s = h / (y1 - y0)
    cx = 100 - (x0 + x1) / 2 * s
    base_y = 150  # letter baseline area
    let = f'<path d="{d}" transform="translate({cx:.2f} {base_y}) scale({s:.4f} {-s:.4f}) translate(0 {-y0:.1f})"/>'
    corner, base = e.get('corner', 'leaf'), e.get('base', 'waves')
    ink = 'black' if mono else e.get('ink', '#f5f0e6')
    mot = 'black' if mono else e.get('motif', '#e07a2e')
    line = 'black' if mono else e.get('line', '#e07a2e')
    parts = []
    inner = f'<path d="{SHIELD}" transform="translate(100 127) scale(.9) translate(-100 -127)" fill="none" stroke="{line}" stroke-width="2"/>'
    parts.append(inner)
    parts.append(motif(corner, 44, 46, 0.62, mot, 2.2, rot=-25))
    parts.append(motif(corner, 156, 46, 0.62, mot, 2.2, mirror=True, rot=25))
    parts.append(f'<g fill="{ink}">{let}</g>')
    parts.append(motif(base, 100, 188, 1.25, mot, 2.6))
    body = ''.join(parts)
    head = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="14 14 172 224" width="172" height="224">'
    title = f'<title>{PARAMS.get("emblem", {}).get("title", "")}</title>'
    if mono is None:
        return head + title + f'<path d="{SHIELD}" fill="{e.get("shield", "#1f3a2e")}"/>' + body + '</svg>'
    m = (f'<mask id="kn" maskUnits="userSpaceOnUse" x="14" y="14" width="172" height="224">'
         f'<rect x="14" y="14" width="172" height="224" fill="#000"/><path d="{SHIELD}" fill="#fff"/>{body}</mask>')
    return head + title + m + f'<rect x="14" y="14" width="172" height="224" fill="{mono}" mask="url(#kn)"/></svg>'


def main():
    e = PARAMS.get('emblem')
    if not e:
        sys.exit('no [params.emblem] in hugo.toml')
    img = os.path.join(ROOT, 'static', 'img')
    os.makedirs(img, exist_ok=True)
    colour = build(e)
    open(os.path.join(img, 'brand-shield.svg'), 'w').write(colour)
    open(os.path.join(img, 'brand-shield-mono.svg'), 'w').write(build(e, e.get('mono', '#f5f0e6')))
    open(os.path.join(ROOT, 'static', 'favicon.svg'), 'w').write(colour)
    try:
        import cairosvg  # noqa: F401
        png = lambda w: __import__('cairosvg').svg2png(bytestring=colour.encode(), output_width=w, output_height=round(w * 224 / 172))
    except Exception:
        png = None
    if png is None:
        try:
            from playwright.sync_api import sync_playwright
            def png(w):
                with sync_playwright() as p:
                    b = p.chromium.launch(); pg = b.new_page(viewport={'width': w, 'height': round(w * 224 / 172)})
                    styled = colour.replace('<svg ', '<svg style="width:%dpx;height:auto;display:block" ' % w, 1)
                    pg.set_content('<html><body style="margin:0;background:transparent">' + styled + '</body></html>')
                    data = pg.screenshot(omit_background=True); b.close(); return data
        except Exception:
            print('no cairosvg or playwright: PNG icons skipped'); return
    from PIL import Image
    big = Image.open(io.BytesIO(png(512))).convert('RGBA')

    def square(n):
        c = Image.new('RGBA', (n, n), (0, 0, 0, 0))
        im = big.copy(); im.thumbnail((n, n), Image.LANCZOS)
        c.paste(im, ((n - im.width) // 2, (n - im.height) // 2), im)
        return c
    for n, name in [(16, 'favicon-16.png'), (32, 'favicon-32.png'), (48, 'favicon-48.png'), (192, 'icon-192.png'), (512, 'icon-512.png')]:
        square(n).save(os.path.join(ROOT, 'static', name))
    bg = Image.new('RGBA', (180, 180), e.get('touch_bg', '#ffffff'))
    t = square(160); bg.paste(t, (10, 10), t); bg.convert('RGB').save(os.path.join(ROOT, 'static', 'apple-touch-icon.png'))
    square(48).save(os.path.join(ROOT, 'static', 'favicon.ico'), sizes=[(16, 16), (32, 32), (48, 48)])
    print('emblem and icons written to static/')


if __name__ == '__main__':
    main()
