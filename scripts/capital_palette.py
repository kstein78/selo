#!/usr/bin/env python3
"""Recolour the Rakovac Capital colour font (the shield initials) for a site of the network.

The engine ships static/fonts/RakovacCapitalColor-Regular.woff2 in the rakovac.rs colours. Its palette has 8 entries:
  0 shield, 1 outline and small ornaments, 2 leaf green, 3 letter, 4 light leaf, 5 gold, 6 mid green, 7 red.
A site lists its own colours in hugo.toml:
  [params.capital]
    palette = ["#0e4657", "#e0a84a", "#2f7f86", "#f2f7f7", "#9fd0cf", "#e0a84a", "#5aa3a6", "#b4532a"]
and runs, from the site folder:  python3 themes/selo/scripts/capital_palette.py
Optional: give a letter the ornament of another letter (the motif under the letter), e.g. waves instead of grapes:
    ornament = { P = "D" }
which writes static/fonts/RakovacCapitalColor-Regular.woff2 in the site (it overrides the engine's file, same name,
so no template changes). Same letters and ornaments, the site's colours: the family resemblance stays visible."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from siteconf import ROOT, PARAMS  # noqa: E402
from fontTools.ttLib import TTFont
from fontTools.pens.recordingPen import RecordingPen
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.t2CharStringPen import T2CharStringPen

ENGINE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'static', 'fonts', 'RakovacCapitalColor-Regular.woff2')


def rgb(h):
    h = h.lstrip('#')
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


ORN_Y = -50  # font units: contours entirely below this line belong to the ornament under the letter


def contours(gs, name):
    rp = RecordingPen(); gs[name].draw(rp)
    out, cur = [], []
    for op, args in rp.value:
        cur.append((op, args))
        if op in ('closePath', 'endPath'):
            out.append(cur); cur = []
    return out


def ymax(c):
    bp = BoundsPen(None); rp = RecordingPen(); rp.value = c; rp.replay(bp)
    return bp.bounds[3] if bp.bounds else 0


def swap_ornament(f, target, source):
    """Layers 1-3 of `target` keep their own contours above ORN_Y and take the source's contours below it."""
    gs = f.getGlyphSet()
    cff = f['CFF '].cff
    top = cff.topDictIndex[0]
    colr = f['COLR']
    for i in (1, 2, 3):
        t, s = colr.ColorLayers[target][i].name, colr.ColorLayers[source][i].name
        keep = [c for c in contours(gs, t) if ymax(c) >= ORN_Y] + [c for c in contours(gs, s) if ymax(c) < ORN_Y]
        pen = T2CharStringPen(gs[t].width, gs)
        for c in keep:
            rp = RecordingPen(); rp.value = c; rp.replay(pen)
        cs = pen.getCharString(private=top.Private, globalSubrs=cff.GlobalSubrs)
        top.CharStrings[t] = cs


def main():
    pal = (PARAMS.get('capital') or {}).get('palette')
    if not pal:
        sys.exit('no [params.capital] palette in hugo.toml')
    f = TTFont(ENGINE)
    cpal = f['CPAL']
    for i, c in enumerate(pal[:len(cpal.palettes[0])]):
        r, g, b = rgb(c)
        cpal.palettes[0][i] = cpal.palettes[0][i].__class__(blue=b, green=g, red=r, alpha=255)
    for target, source in ((PARAMS.get('capital') or {}).get('ornament') or {}).items():
        swap_ornament(f, target, source)
    out = os.path.join(ROOT, 'static', 'fonts', 'RakovacCapitalColor-Regular.woff2')
    os.makedirs(os.path.dirname(out), exist_ok=True)
    f.flavor = 'woff2'
    f.save(out)
    print('wrote', os.path.relpath(out, ROOT))


if __name__ == '__main__':
    main()
