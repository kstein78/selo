#!/usr/bin/env python3
"""Recolour the Rakovac Capital colour font (the shield initials) for a site of the network.

The engine ships static/fonts/RakovacCapitalColor-Regular.woff2 in the rakovac.rs colours. Its palette has 8 entries:
  0 shield, 1 outline and small ornaments, 2 leaf green, 3 letter, 4 light leaf, 5 gold, 6 mid green, 7 red.
A site lists its own colours in hugo.toml:
  [params.capital]
    palette = ["#0e4657", "#e0a84a", "#2f7f86", "#f2f7f7", "#9fd0cf", "#e0a84a", "#5aa3a6", "#b4532a"]
and runs, from the site folder:  python3 themes/selo/scripts/capital_palette.py
which writes static/fonts/RakovacCapitalColor-Regular.woff2 in the site (it overrides the engine's file, same name,
so no template changes). Same letters and ornaments, the site's colours: the family resemblance stays visible."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from siteconf import ROOT, PARAMS  # noqa: E402
from fontTools.ttLib import TTFont

ENGINE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'static', 'fonts', 'RakovacCapitalColor-Regular.woff2')


def rgb(h):
    h = h.lstrip('#')
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def main():
    pal = (PARAMS.get('capital') or {}).get('palette')
    if not pal:
        sys.exit('no [params.capital] palette in hugo.toml')
    f = TTFont(ENGINE)
    cpal = f['CPAL']
    for i, c in enumerate(pal[:len(cpal.palettes[0])]):
        r, g, b = rgb(c)
        cpal.palettes[0][i] = cpal.palettes[0][i].__class__(blue=b, green=g, red=r, alpha=255)
    out = os.path.join(ROOT, 'static', 'fonts', 'RakovacCapitalColor-Regular.woff2')
    os.makedirs(os.path.dirname(out), exist_ok=True)
    f.flavor = 'woff2'
    f.save(out)
    print('wrote', os.path.relpath(out, ROOT))


if __name__ == '__main__':
    main()
