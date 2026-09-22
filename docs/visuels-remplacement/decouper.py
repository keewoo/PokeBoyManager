#!/usr/bin/env python3
"""Découpe une planche 3x3 en 9 vignettes, en détectant les gouttières magenta.

Refuse une planche mal alignée plutôt que de produire des vignettes décalées :
on cherche les bandes magenta ; à défaut, on retombe sur une grille régulière,
mais on le DIT dans la sortie.
"""
import sys, os
from PIL import Image

def bandes(im, axe):
    """Indices des lignes (ou colonnes) majoritairement magenta."""
    w, h = im.size
    px = im.convert("RGB").load()
    n = h if axe == "y" else w
    m = w if axe == "y" else h
    out = []
    for i in range(n):
        mag = 0
        for j in range(0, m, 8):
            r, g, b = px[(j, i)] if axe == "y" else px[(i, j)]
            if r > 180 and b > 180 and g < 90:
                mag += 1
        if mag > (m // 8) * 0.8:
            out.append(i)
    return out

def groupes(idx):
    """Regroupe des indices contigus en bandes."""
    g, cur = [], []
    for i in idx:
        if cur and i != cur[-1] + 1:
            g.append(cur); cur = []
        cur.append(i)
    if cur: g.append(cur)
    return g

def coupes(im, axe):
    gs = groupes(bandes(im, axe))
    n = im.size[1] if axe == "y" else im.size[0]
    inter = [g for g in gs if g[0] > n * 0.05 and g[-1] < n * 0.95]
    if len(inter) == 2:                      # les deux gouttières intérieures
        bords = [g for g in gs if g not in inter]
        d0 = (bords[0][-1] + 1) if bords and bords[0][0] == 0 else 0
        d3 = bords[-1][0] if bords and bords[-1][-1] == n - 1 else n
        return [(d0, inter[0][0]), (inter[0][-1] + 1, inter[1][0]), (inter[1][-1] + 1, d3)], True
    p = n / 3
    return [(int(i * p), int((i + 1) * p)) for i in range(3)], False

def decouper(src, dst, code, taille=512):
    im = Image.open(src).convert("RGB")
    cy, oky = coupes(im, "y")
    cx, okx = coupes(im, "x")
    os.makedirs(dst, exist_ok=True)
    n = 0
    for iy, (y0, y1) in enumerate(cy):
        for ix, (x0, x1) in enumerate(cx):
            n += 1
            v = im.crop((x0, y0, x1, y1))
            c = min(v.size)                                   # recadrage carré au centre
            v = v.crop(((v.width - c) // 2, (v.height - c) // 2,
                        (v.width + c) // 2, (v.height + c) // 2)).resize((taille, taille), Image.LANCZOS)
            v.save(f"{dst}/{code}-{n:02d}.webp", "WEBP", quality=82, method=6)
    detecte = "gouttières détectées" if (oky and okx) else "⚠ gouttières NON détectées — grille régulière supposée, à vérifier à l'œil"
    print(f"{code} : 9 vignettes de {taille}px écrites dans {dst} ({detecte})")
    return oky and okx

if __name__ == "__main__":
    src, code = sys.argv[1], sys.argv[2]
    dst = sys.argv[3] if len(sys.argv) > 3 else "fonds"
    decouper(src, code=code, dst=dst)
