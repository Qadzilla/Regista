"""Regista's share image and README banner, in the app's dark theme: pitch lines in Regista yellow, the app's wordmark
(REGI white, STA yellow) and an icon.

    python3 docs/brand/make_images.py --font PATH/TO/Inter.ttf [--icon viewfinder|clapper|magnifier] [--out docs/brand]
    python3 docs/brand/make_images.py --font PATH/TO/Inter.ttf --sheet     # the three icon ideas side by side

Writes regista-1200x630.png (the app's share preview and the submission's project image) and regista-banner.png
(1600x400, the README header). The font is Inter (SIL Open Font License), from
https://github.com/google/fonts/tree/main/ofl/inter, standing in for the app's system font, which may not be used in
published images; it is not committed. Everything is drawn here: no photograph, no generated imagery.
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

BG = (12, 14, 20)              # --bg
PANEL = (22, 26, 36)           # --panel
EDGE = (38, 44, 58)            # --line
TEXT = (243, 244, 246)         # --text
MUTED = (154, 163, 181)        # --muted
YELLOW = (255, 205, 40)        # --accent
SS = 2                         # draw at twice the size, then scale down for smooth edges


# ----------------------------------------------------------------------------------------------- the ball
PHI = (1 + 5 ** 0.5) / 2


def _ball_faces() -> list:
    """The classic ball's 32 panels (12 pentagons, 20 hexagons): a truncated icosahedron's faces, vertices in order."""
    import numpy as np
    from scipy.spatial import ConvexHull

    pts = set()
    for a, b, c in ((0, 1, 3 * PHI), (1, 2 + PHI, 2 * PHI), (PHI, 2, 2 * PHI + 1)):
        for sa in (1, -1):
            for sb in (1, -1):
                for sc in (1, -1):
                    p = (sa * a, sb * b, sc * c)
                    for q in (p, (p[1], p[2], p[0]), (p[2], p[0], p[1])):     # the even permutations
                        pts.add(tuple(round(x, 9) for x in q))
    V = np.array(sorted(pts))
    hull = ConvexHull(V)
    groups: dict = {}
    for simplex, eq in zip(hull.simplices, hull.equations):
        groups.setdefault(tuple(np.round(eq[:3], 5)), set()).update(simplex.tolist())
    faces = []
    for normal, idx in groups.items():
        P = V[sorted(idx)]
        c, n = P.mean(axis=0), np.array(normal)
        u = (P[0] - c) / np.linalg.norm(P[0] - c)
        w = np.cross(n, u)
        faces.append(P[np.argsort([math.atan2((q - c) @ w, (q - c) @ u) for q in P])])
    return faces


def _rot(axis: str, deg: float):
    import numpy as np

    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return {"x": np.array([[1, 0, 0], [0, c, -s], [0, s, c]]), "y": np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]]),
            "z": np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])}[axis]


def _to_z(n):
    """The rotation taking direction ``n`` to the viewer (+z)."""
    import numpy as np

    n = n / np.linalg.norm(n)
    v, c = np.cross(n, [0.0, 0.0, 1.0]), n[2]
    s = np.linalg.norm(v)
    if s < 1e-9:
        return np.eye(3)
    vx = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    return np.eye(3) + vx + vx @ vx * ((1 - c) / s ** 2)


def ball(size: int, tilt: tuple[float, float, float] = (-10, 14, 8)) -> Image.Image:
    """A football, ``size`` pixels across: the truncated icosahedron's panels curved onto a sphere, turned by ``tilt``
    degrees (x, y, z) from a pentagon facing the viewer, lit from the upper left, drawn at 4x and scaled down."""
    import numpy as np

    S = 4
    D = size * S
    R = D / 2 - S
    faces = _ball_faces()
    pent = next(f for f in faces if len(f) == 5)
    M = _rot("z", tilt[2]) @ _rot("y", tilt[1]) @ _rot("x", tilt[0]) @ _to_z(pent.mean(axis=0))
    light = np.array([-0.45, 0.55, 0.70])
    light /= np.linalg.norm(light)
    white, black, seam = (244, 245, 247), (22, 25, 33), (150, 156, 170)
    img = Image.new("RGBA", (D, D), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    panels = []
    for f in faces:
        ring = []
        for i in range(len(f)):
            a, b = f[i], f[(i + 1) % len(f)]
            for t in np.linspace(0, 1, 14, endpoint=False):     # each edge as a curve on the sphere
                q = a + (b - a) * t
                ring.append(q / np.linalg.norm(q))
        ring = (M @ np.array(ring).T).T
        centre = M @ (f.mean(axis=0) / np.linalg.norm(f.mean(axis=0)))
        if centre[2] < -0.30:                                  # facing away
            continue
        xy = []
        for x, y, z in ring:
            if z < 0:                                          # round the back: on the silhouette
                k = math.hypot(x, y) or 1.0
                x, y = x / k, y / k
            xy.append((D / 2 + R * x, D / 2 - R * y))
        lit = max(0.0, float(centre @ light))
        col = (tuple(int(c + 18 * lit) for c in black) if len(f) == 5
               else tuple(int(c * (0.86 + 0.14 * lit)) for c in white))
        panels.append((centre[2], xy, col))
    for _, xy, col in sorted(panels, key=lambda p: p[0]):    # back to front
        d.polygon(xy, fill=col)
        d.line(xy + [xy[0]], fill=seam, width=max(1, int(R * 0.018)), joint="curve")
    yy, xx = np.mgrid[0:D, 0:D]                                # the sphere's shading, darker to the lower right
    nx, ny = (xx - D / 2) / R, (D / 2 - yy) / R
    nz = np.sqrt(1 - np.clip(nx ** 2 + ny ** 2, 0, 1))
    shade = np.clip(0.55 + 0.45 * (nx * light[0] + ny * light[1] + nz * light[2]), 0, 1)
    shadow = Image.new("RGBA", (D, D), (8, 10, 16, 0))
    shadow.putalpha(Image.fromarray(((1 - shade) * 120).astype(np.uint8)))
    img.alpha_composite(shadow)
    mask = Image.new("L", (D, D), 0)
    ImageDraw.Draw(mask).ellipse([D / 2 - R, D / 2 - R, D / 2 + R, D / 2 + R], fill=255)
    out = Image.new("RGBA", (D, D), (0, 0, 0, 0))
    out.paste(img, (0, 0), mask)
    ImageDraw.Draw(out).ellipse([D / 2 - R, D / 2 - R, D / 2 + R, D / 2 + R], outline=(30, 34, 44),
                                width=max(1, int(R * 0.02)))
    return out.resize((size, size), Image.LANCZOS)


# ----------------------------------------------------------------------------------------------- the icons
def _tile(size: int) -> Image.Image:
    t = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ImageDraw.Draw(t).rounded_rectangle([0, 0, size - 1, size - 1], radius=size * 0.23, fill=PANEL,
                                        outline=EDGE, width=max(2, size // 90))
    return t


def icon_viewfinder(size: int) -> Image.Image:
    """The director's frame: four yellow corner brackets around the ball."""
    t = _tile(size)
    d = ImageDraw.Draw(t)
    m, L, w = size * 0.2, size * 0.17, max(3, int(size * 0.045))
    for sx, sy in ((0, 0), (1, 0), (0, 1), (1, 1)):
        x = m if sx == 0 else size - m
        y = m if sy == 0 else size - m
        dx = L if sx == 0 else -L
        dy = L if sy == 0 else -L
        d.line([(x, y), (x + dx, y)], fill=YELLOW, width=w)
        d.line([(x, y), (x, y + dy)], fill=YELLOW, width=w)
        d.ellipse([x - w / 2, y - w / 2, x + w / 2, y + w / 2], fill=YELLOW)
    b = ball(int(size * 0.40))
    t.alpha_composite(b, ((size - b.width) // 2, (size - b.height) // 2))
    return t


def icon_clapper(size: int) -> Image.Image:
    """The director's clapperboard, its clapper striped in Regista yellow, with the ball in front."""
    t = _tile(size)
    d = ImageDraw.Draw(t)
    x0, x1, y0, y1 = size * 0.20, size * 0.80, size * 0.42, size * 0.78
    d.rounded_rectangle([x0, y0, x1, y1], radius=size * 0.04, fill=(48, 55, 72))
    # the clapper, open: a bar hinged at its left end, tilted up
    bar_h, ang = size * 0.11, math.radians(-14)
    hx, hy = x0, y0 - size * 0.015

    def rot(px: float, py: float) -> tuple[float, float]:
        return (hx + px * math.cos(ang) - py * math.sin(ang), hy + px * math.sin(ang) + py * math.cos(ang))

    width = x1 - x0
    d.polygon([rot(0, 0), rot(width, 0), rot(width, -bar_h), rot(0, -bar_h)], fill=BG)
    n = 5
    for i in range(n):
        a0, a1 = width * i / n, width * (i + 0.55) / n
        d.polygon([rot(a0, 0), rot(a1, 0), rot(a1 + bar_h * 0.6, -bar_h), rot(a0 + bar_h * 0.6, -bar_h)], fill=YELLOW)
    # the fixed stripe on the board, under the clapper
    d.rectangle([x0, y0, x1, y0 + bar_h * 0.75], fill=BG)
    for i in range(n):
        a0 = x0 + width * i / n
        d.polygon([(a0, y0), (a0 + width * 0.55 / n, y0), (a0 + width * 0.55 / n + bar_h * 0.45, y0 + bar_h * 0.75),
                   (a0 + bar_h * 0.45, y0 + bar_h * 0.75)], fill=YELLOW)
    b = ball(int(size * 0.34))
    t.alpha_composite(b, (int(size * 0.53), int(size * 0.50)))
    return t


def icon_magnifier(size: int) -> Image.Image:
    """The detective: a magnifying glass in Regista yellow with the ball in its lens."""
    t = _tile(size)
    d = ImageDraw.Draw(t)
    cx, cy, r, w = size * 0.43, size * 0.43, size * 0.24, max(3, int(size * 0.055))
    a = math.radians(45)
    sx, sy = cx + (r + w / 2) * math.cos(a), cy + (r + w / 2) * math.sin(a)
    ex, ey = size * 0.80, size * 0.80
    hw = int(size * 0.085)
    d.line([(sx, sy), (ex, ey)], fill=YELLOW, width=hw)
    d.ellipse([ex - hw / 2, ey - hw / 2, ex + hw / 2, ey + hw / 2], fill=YELLOW)
    b = ball(int(r * 2 - w * 1.2))
    t.alpha_composite(b, (int(cx - b.width / 2), int(cy - b.height / 2)))
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=YELLOW, width=w)
    return t


ICONS = {"viewfinder": icon_viewfinder, "clapper": icon_clapper, "magnifier": icon_magnifier}


# ----------------------------------------------------------------------------------------------- the frame
def pitch(draw: ImageDraw.ImageDraw, cx: float, cy: float, length: float, width: int, fill) -> None:
    """A full pitch (105 x 68) centred on (cx, cy), ``length`` pixels from goal line to goal line."""
    s = length / 105.0
    x0, x1, y0, y1 = cx - 52.5 * s, cx + 52.5 * s, cy - 34 * s, cy + 34 * s
    draw.rectangle([x0, y0, x1, y1], outline=fill, width=width)
    draw.line([cx, y0, cx, y1], fill=fill, width=width)
    r = 9.15 * s
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=fill, width=width)
    for side in (-1, 1):
        gx = cx + side * 52.5 * s
        for depth, half in ((16.5, 20.15), (5.5, 9.16)):
            ix = gx - side * depth * s
            draw.rectangle([min(gx, ix), cy - half * s, max(gx, ix), cy + half * s], outline=fill, width=width)
        spot = gx - side * 11 * s
        draw.ellipse([spot - width, cy - width, spot + width, cy + width], fill=fill)
        draw.arc([spot - r, cy - r, spot + r, cy + r], start=-53 if side < 0 else 127, end=53 if side < 0 else 233,
                 fill=fill, width=width)


def wordmark(font_path: str, cap: int) -> Image.Image:
    """REGISTA as the app writes it: heavy, letter-spaced 0.08em, STA in Regista yellow; ``cap`` is the cap height."""
    font = ImageFont.truetype(font_path, int(cap / 0.727))
    font.set_variation_by_axes([32, 800])          # optical size Display, weight ExtraBold (the app: 800)
    track = font.size * 0.08
    parts = [(ch, TEXT if i < 4 else YELLOW) for i, ch in enumerate("REGISTA")]
    widths = [font.getlength(ch) for ch, _ in parts]
    w = int(sum(widths) + track * (len(parts) - 1)) + 4
    l, t, r, b = font.getbbox("REGISTA")
    out = Image.new("RGBA", (w, b - t + 4), (0, 0, 0, 0))
    d = ImageDraw.Draw(out)
    x = 0.0
    for (ch, col), cw in zip(parts, widths):
        d.text((x, -t + 2), ch, font=font, fill=col)
        x += cw + track
    return out


def lockup(font_path: str, icon_name: str, height: int) -> Image.Image:
    ic = ICONS[icon_name](height)
    wm = wordmark(font_path, int(height * 0.42))
    gap = int(height * 0.30)
    out = Image.new("RGBA", (height + gap + wm.width, height), (0, 0, 0, 0))
    out.alpha_composite(ic, (0, 0))
    out.alpha_composite(wm, (height + gap, (height - wm.height) // 2))
    return out


def render(w: int, h: int, font_path: str, icon_name: str, pitch_length: float, icon_px: int,
           clear: tuple[float, float]) -> Image.Image:
    W, H = w * SS, h * SS
    img = Image.new("RGBA", (W, H), BG)
    lines = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    pitch(ImageDraw.Draw(lines), W / 2, H / 2, pitch_length * SS, width=2 * SS, fill=YELLOW + (70,))
    # the lines fade out behind the lockup, so the name sits on clean colour
    fade = Image.new("L", (W, H), 255)
    rx, ry = W * clear[0] / 2, H * clear[1] / 2
    ImageDraw.Draw(fade).ellipse([W / 2 - rx, H / 2 - ry, W / 2 + rx, H / 2 + ry], fill=0)
    fade = fade.filter(ImageFilter.GaussianBlur(min(W, H) / 9))
    lines.putalpha(Image.composite(lines.getchannel("A"), Image.new("L", (W, H), 0), fade))
    img.alpha_composite(lines)
    lk = lockup(font_path, icon_name, icon_px * SS)
    img.alpha_composite(lk, ((W - lk.width) // 2, (H - lk.height) // 2))
    return img.resize((w, h), Image.LANCZOS).convert("RGB")


def sheet(font_path: str) -> Image.Image:
    """The three icon ideas side by side, each labelled."""
    tile, gap = 300, 60
    W = 3 * tile + 4 * gap
    img = Image.new("RGB", (W, tile + 2 * gap + 50), BG)
    font = ImageFont.truetype(font_path, 26)
    font.set_variation_by_axes([14, 600])
    labels = {"viewfinder": "A · Director's frame", "clapper": "B · Clapperboard", "magnifier": "C · Detective"}
    for i, name in enumerate(ICONS):
        x = gap + i * (tile + gap)
        ic = ICONS[name](tile * SS).resize((tile, tile), Image.LANCZOS)
        img.paste(ic, (x, gap), ic)
        ImageDraw.Draw(img).text((x + tile / 2, gap + tile + 22), labels[name], font=font, fill=MUTED, anchor="mt")
    return img


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--font", required=True, help="Inter (variable TTF)")
    ap.add_argument("--icon", default="clapper", choices=sorted(ICONS))
    ap.add_argument("--sheet", action="store_true", help="write icon-ideas.png instead")
    ap.add_argument("--out", default=str(Path(__file__).parent))
    a = ap.parse_args()
    out = Path(a.out)
    if a.sheet:
        sheet(a.font).save(out / "icon-ideas.png", optimize=True)
        print("wrote", out / "icon-ideas.png")
        return
    render(1200, 630, a.font, a.icon, pitch_length=1040, icon_px=120, clear=(0.74, 0.55)).save(
        out / "regista-1200x630.png", optimize=True)
    render(1600, 400, a.font, a.icon, pitch_length=1300, icon_px=100, clear=(0.50, 0.8)).save(
        out / "regista-banner.png", optimize=True)
    print("wrote", out / "regista-1200x630.png", out / "regista-banner.png")


if __name__ == "__main__":
    main()
