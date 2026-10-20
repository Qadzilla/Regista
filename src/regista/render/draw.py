"""Draw one broadcast frame at time t with Pillow.

A frame is: a camera view (main pitch view, replay of the main view with a different
framing, player closeup card, crowd card, end card) plus the HUD (scoreboard and clock,
segment badge, caption strip, watermark) and an optional clip title card.
"""

from __future__ import annotations

import hashlib
import math
import random
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from regista.camera import MAIN_K, MAIN_WINDOW_M, PITCH_L, PITCH_W, camera_centre
from regista.render.scene import Scene

Record = dict[str, Any]
RGB = tuple[int, int, int]

FONT_CANDIDATES = [
    "/System/Library/Fonts/Helvetica.ttc",
    "/System/Library/Fonts/HelveticaNeue.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
]
FONT_BOLD_CANDIDATES = [
    ("/System/Library/Fonts/Helvetica.ttc", 1),
    ("/System/Library/Fonts/HelveticaNeue.ttc", 1),
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 0),
    ("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf", 0),
]

# Camera framings. ``window`` is metres of pitch length visible at the near touchline,
# ``k`` the perspective shrink toward the far touchline, ``mirror`` flips left/right,
# ``flip`` swaps near and far touchlines. "live" must match regista.camera so the renderer
# shows exactly what the generator tracked.
VIEWS: dict[str, dict[str, Any]] = {
    "live": {"window": MAIN_WINDOW_M, "k": MAIN_K, "mirror": False, "flip": False},
    "reverse": {"window": MAIN_WINDOW_M, "k": MAIN_K, "mirror": True, "flip": False},
    "behind_goal": {"window": 36.0, "k": 0.5, "mirror": False, "flip": True},
    "high_wide": {"window": 105.0, "k": 0.12, "mirror": False, "flip": False},
    "touchline_cam": {"window": 38.0, "k": 0.5, "mirror": False, "flip": False},
    "highlight": {"window": 48.0, "k": 0.3, "mirror": False, "flip": False},
}

COLOUR_REPLAY: RGB = (214, 32, 40)
COLOUR_HIGHLIGHT: RGB = (255, 205, 40)
COLOUR_ACCENT: RGB = (255, 205, 40)
COLOUR_FOCUS: RGB = (255, 255, 255)
COLOUR_TEXT: RGB = (245, 245, 245)
COLOUR_UNKNOWN_KIT: RGB = (140, 140, 140)

MIN_DISC_SCALE = 0.72  # discs are symbols, not to scale: never let them shrink below this in wide views
REPLAY_FALLBACK_WINDOW_S = 4.0  # when a replay segment has no replays_window, replay this much before the event


@dataclass(frozen=True)
class Style:
    width: int = 1280
    height: int = 720
    grass_a: RGB = (36, 122, 54)
    grass_b: RGB = (42, 134, 60)
    surround: RGB = (24, 30, 34)
    line: RGB = (236, 244, 236)
    hud: RGB = (12, 14, 20)
    hud_alpha: int = 215
    caption_alpha: int = 205

    def __post_init__(self) -> None:
        # libx264 with yuv420p needs even dimensions; round down rather than fail in the encoder.
        object.__setattr__(self, "width", max(16, self.width - self.width % 2))
        object.__setattr__(self, "height", max(16, self.height - self.height % 2))

    @property
    def s(self) -> float:
        """Scale factor relative to the 1280x720 design."""
        return self.width / 1280.0

    @property
    def pitch_top(self) -> float:
        return 96 * self.s

    @property
    def pitch_bottom(self) -> float:
        return self.height - 96 * self.s


@lru_cache(maxsize=64)
def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    size = max(8, int(size))  # Helvetica regular raises 'division by zero' in FreeType below 8 px
    cands = FONT_BOLD_CANDIDATES if bold else [(p, 0) for p in FONT_CANDIDATES]
    for path, index in cands:
        try:
            return ImageFont.truetype(path, size, index=index)
        except OSError:
            continue
    return ImageFont.load_default(size)  # Pillow >= 10.1: a scalable font that honours anchors


def hex_rgb(h: str) -> RGB:
    h = h.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def darken(c: RGB, f: float) -> RGB:
    return (int(c[0] * f), int(c[1] * f), int(c[2] * f))


# ---------------------------------------------------------------------------- camera

class Camera:
    """Projects pitch metres to screen pixels. Horizontal mapping is regista.camera's; vertical is linear in depth."""

    def __init__(self, style: Style, cx: float, view: dict[str, Any], y_top: float, y_bottom: float):
        self.style = style
        self.view = view
        self.window = float(view["window"])
        self.k = float(view["k"])
        self.mirror = bool(view["mirror"])
        self.flip = bool(view["flip"])
        self.cx = camera_centre(cx, self.window)
        self.S = style.width / self.window  # px per metre at the near touchline
        self.y_top = y_top
        self.y_bottom = y_bottom

    def depth(self, y: float) -> float:
        d = y / PITCH_W
        return 1.0 - d if self.flip else d

    def scale(self, y: float) -> float:
        return self.S * (1.0 - self.k * self.depth(y))

    def project(self, x: float, y: float) -> tuple[float, float]:
        d = self.depth(y)
        s = self.S * (1.0 - self.k * d)
        dx = (x - self.cx) * s
        sx = self.style.width / 2 + (-dx if self.mirror else dx)
        sy = self.y_bottom - d * (self.y_bottom - self.y_top)
        return (sx, sy)

    def disc_scale(self, y: float) -> float:
        """Disc size factor compared with the live view at the near touchline, floored so wide views stay legible."""
        return max(MIN_DISC_SCALE, self.scale(y) / (self.style.width / MAIN_WINDOW_M))


# ---------------------------------------------------------------------------- pitch

def draw_pitch(img: Image.Image, cam: Camera, style: Style) -> None:
    draw = ImageDraw.Draw(img)
    stripe = PITCH_L / 10
    for i in range(10):
        x0, x1 = i * stripe, (i + 1) * stripe
        poly = [cam.project(x0, 0), cam.project(x1, 0), cam.project(x1, PITCH_W), cam.project(x0, PITCH_W)]
        draw.polygon(poly, fill=style.grass_a if i % 2 == 0 else style.grass_b)
    lw = max(1, int(2 * style.s))

    def line(a: tuple[float, float], b: tuple[float, float], w: int = lw) -> None:
        draw.line([cam.project(*a), cam.project(*b)], fill=style.line, width=w)

    def rect(x0: float, y0: float, x1: float, y1: float) -> None:
        line((x0, y0), (x1, y0))
        line((x1, y0), (x1, y1))
        line((x1, y1), (x0, y1))
        line((x0, y1), (x0, y0))

    def circle(cx: float, cy: float, r: float) -> None:
        pts = [cam.project(cx + r * math.cos(math.radians(a)), cy + r * math.sin(math.radians(a))) for a in range(0, 361, 6)]
        draw.line(pts, fill=style.line, width=lw)

    rect(0, 0, PITCH_L, PITCH_W)
    line((PITCH_L / 2, 0), (PITCH_L / 2, PITCH_W))
    circle(PITCH_L / 2, PITCH_W / 2, 9.15)
    for gx, sign in ((0.0, 1), (PITCH_L, -1)):
        rect(gx, PITCH_W / 2 - 20.15, gx + sign * 16.5, PITCH_W / 2 + 20.15)
        rect(gx, PITCH_W / 2 - 9.16, gx + sign * 5.5, PITCH_W / 2 + 9.16)
        spot = cam.project(gx + sign * 11.0, PITCH_W / 2)
        r = max(1.5, 2.5 * style.s)
        draw.ellipse([spot[0] - r, spot[1] - r, spot[0] + r, spot[1] + r], fill=style.line)
        gpoly = [cam.project(gx, PITCH_W / 2 - 3.66), cam.project(gx - sign * 2.0, PITCH_W / 2 - 3.66),
                 cam.project(gx - sign * 2.0, PITCH_W / 2 + 3.66), cam.project(gx, PITCH_W / 2 + 3.66)]
        draw.polygon(gpoly, fill=(150, 156, 166))
        for yy in (PITCH_W / 2 - 2.44, PITCH_W / 2 - 1.22, PITCH_W / 2, PITCH_W / 2 + 1.22, PITCH_W / 2 + 2.44):
            draw.line([cam.project(gx, yy), cam.project(gx - sign * 2.0, yy)], fill=(190, 196, 206), width=1)
        draw.line([cam.project(gx - sign * 1.0, PITCH_W / 2 - 3.66), cam.project(gx - sign * 1.0, PITCH_W / 2 + 3.66)], fill=(190, 196, 206), width=1)
        draw.line([cam.project(gx, PITCH_W / 2 - 3.66), cam.project(gx, PITCH_W / 2 + 3.66)], fill=style.line, width=lw + 2)


def _label_text(scene: Scene, pid: str) -> str:
    """Surname, or initial + surname when the roster has two players with that surname."""
    parts = scene.player_name(pid).split() or [pid]
    surname = parts[-1]
    duplicates = sum(1 for p in scene.roster.values() if (p["name"].split() or [""])[-1] == surname)
    if duplicates > 1 and len(parts) > 1:
        return f"{parts[0][0]}. {surname}"
    return surname


def draw_players(img: Image.Image, cam: Camera, style: Style, scene: Scene, positions: dict[str, tuple[float, float]],
                 ball: tuple[float, float] | None, holder: str | None, focus: str | None = None) -> None:
    draw = ImageDraw.Draw(img)
    base_r = 14.0 * style.s
    # Far players first so near players overlap them; the focus player and the holder go last so they are never hidden.
    on_top = [pid for pid in dict.fromkeys((focus, holder)) if pid and pid in positions]
    ordinary = sorted(((pid, p) for pid, p in positions.items() if pid not in on_top), key=lambda kv: -cam.depth(kv[1][1]))
    order = ordinary + [(pid, positions[pid]) for pid in on_top]
    discs: dict[str, tuple[float, float, float]] = {}
    for pid, (x, y) in order:
        sx, sy = cam.project(x, y)
        r = base_r * cam.disc_scale(y)
        if sx < -2 * r or sx > style.width + 2 * r:
            continue
        fill_hex, text_hex = scene.kit(pid)
        fill, text = hex_rgb(fill_hex), hex_rgb(text_hex)
        draw.ellipse([sx - r * 0.9, sy - r * 0.25, sx + r * 0.9, sy + r * 0.45], fill=darken(style.grass_a, 0.6))
        ring_w = max(2, int(3 * style.s))
        if pid == holder or pid == focus:
            ring = r + max(2.0, 3.0 * style.s)
            colour = COLOUR_ACCENT if pid == holder else COLOUR_FOCUS
            draw.ellipse([sx - ring, sy - r - ring, sx + ring, sy - r + ring], outline=colour, width=ring_w)
        draw.ellipse([sx - r, sy - 2 * r, sx + r, sy], fill=fill, outline=(20, 20, 20), width=max(1, int(1.5 * style.s)))
        num = scene.kit_number(pid)
        if num:
            draw.text((sx, sy - r), num, font=font(int(r * 1.15), bold=True), fill=text, anchor="mm")
        discs[pid] = (sx, sy, r)
    if ball is not None:
        bx, by = cam.project(*ball)
        br = max(3.0, 5.5 * style.s * cam.disc_scale(ball[1]))
        draw.ellipse([bx - br * 1.2, by - br * 0.4, bx + br * 1.2, by + br * 0.6], fill=darken(style.grass_a, 0.6))
        draw.ellipse([bx - br, by - 2 * br, bx + br, by], fill=(250, 250, 250), outline=(30, 30, 30), width=max(1, int(1.5 * style.s)))
    # Name labels last, above the disc, moved below it when another disc sits where the label would go.
    for pid in on_top:
        if pid not in discs:
            continue
        sx, sy, r = discs[pid]
        name = _label_text(scene, pid)
        tf = font(int(12 * style.s), bold=True)
        tw = draw.textlength(name, font=tf)
        pad = 5 * style.s
        h = 16 * style.s
        above = [sx - tw / 2 - pad, sy - 2 * r - h - 5 * style.s, sx + tw / 2 + pad, sy - 2 * r - 5 * style.s]
        below = [sx - tw / 2 - pad, sy + 6 * style.s, sx + tw / 2 + pad, sy + 6 * style.s + h]
        box = above
        for other, (ox, oy, orr) in discs.items():
            if other != pid and above[0] - orr < ox < above[2] + orr and above[1] - orr < oy - orr < above[3] + orr:
                box = below
                break
        colour = COLOUR_ACCENT if pid == holder else COLOUR_FOCUS
        draw.rounded_rectangle(box, radius=3 * style.s, fill=(12, 14, 20), outline=colour, width=1)
        draw.text(((box[0] + box[2]) / 2, (box[1] + box[3]) / 2), name, font=tf, fill=COLOUR_TEXT, anchor="mm")


def draw_main_view(scene: Scene, t: float, style: Style, view_name: str = "live", focus: str | None = None) -> tuple[Image.Image, Camera]:
    img = Image.new("RGB", (style.width, style.height), style.surround)
    view = VIEWS.get(view_name, VIEWS["live"])
    ball = scene.ball_at(t)
    cam = Camera(style, ball[0], view, style.pitch_top, style.pitch_bottom)
    draw_pitch(img, cam, style)
    positions = scene.positions_at(t)
    holder = scene.holder_at(t)
    draw_players(img, cam, style, scene, positions, ball, holder, focus)
    return img, cam


# ---------------------------------------------------------------------------- cards

def draw_closeup(scene: Scene, player_ids: list[str], style: Style, t: float) -> Image.Image:
    img = Image.new("RGB", (style.width, style.height), style.surround)
    draw = ImageDraw.Draw(img)
    player_ids = [pid for pid in player_ids if pid in scene.roster]
    if not player_ids:
        # No tracked player in the cutaway: show whoever was last involved in play.
        last = scene.last_player_before(t)
        player_ids = [last or next(iter(scene.roster))]
    n = len(player_ids)
    for i, pid in enumerate(player_ids):
        p = scene.roster[pid]
        team = scene.teams.get(p["team_id"], {"name": p["team_id"]})
        fill_hex, text_hex = scene.kit(pid)
        fill, text = hex_rgb(fill_hex), hex_rgb(text_hex)
        x0 = int(i * style.width / n)
        x1 = int((i + 1) * style.width / n)
        for yy in range(0, style.height, 4):
            f = 0.35 + 0.45 * (1 - yy / style.height)
            draw.rectangle([x0, yy, x1, yy + 4], fill=darken(fill, f))
        cx = (x0 + x1) / 2
        r = min(160 * style.s, (x1 - x0) * 0.26)
        cy = style.height * 0.47
        draw.ellipse([cx - r - 6, cy - r + 10, cx + r + 6, cy + r + 22], fill=darken(fill, 0.25))
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=fill, outline=(20, 20, 20), width=max(2, int(4 * style.s)))
        draw.text((cx, cy), str(p["kit_number"]), font=font(int(r * 1.1), bold=True), fill=text, anchor="mm")
        name_size = int((52 if n == 1 else 38) * style.s)
        draw.text((cx, cy + r + 42 * style.s), p["name"], font=font(name_size, bold=True), fill=COLOUR_TEXT, anchor="mm")
        sub = f"{team['name']}  ·  {p['position']}  ·  #{p['kit_number']}"
        draw.text((cx, cy + r + 42 * style.s + name_size * 0.95), sub, font=font(int(24 * style.s)), fill=(225, 225, 225), anchor="mm")
    return img


def draw_crowd(scene: Scene, seg_id: str, style: Style, t: float) -> Image.Image:
    img = Image.new("RGB", (style.width, style.height), (18, 20, 26))
    draw = ImageDraw.Draw(img)
    seed = int(hashlib.md5(seg_id.encode()).hexdigest()[:8], 16)
    rng = random.Random(seed)
    palette = []
    for team in scene.teams.values():
        palette += [hex_rgb(team["kit"]["primary"])] * 4 + [hex_rgb(team["kit"].get("secondary", "#DDDDDD"))]
    palette += [(60, 60, 66), (90, 86, 80), (120, 120, 128), (200, 190, 170)]
    top = 90 * style.s
    cols, rows = 64, 20
    dw, dh = style.width / cols, (style.height - 120 * style.s - top) / rows
    wave = (t * 1.5) % cols
    for r in range(rows):
        for c in range(cols):
            colour = rng.choice(palette)
            lift = 4 * style.s if abs(c - wave) < 3 else 0
            x, y = c * dw + rng.uniform(-2, 2), top + r * dh + rng.uniform(-2, 2) - lift
            rad = dw * 0.36
            draw.ellipse([x, y, x + rad * 2, y + rad * 2], fill=darken(colour, 0.55 + 0.45 * (r / rows)))
    draw.rectangle([0, 0, style.width, top], fill=(10, 12, 16))  # clean header band behind the scoreboard
    draw.rectangle([0, style.height - 120 * style.s, style.width, style.height], fill=(10, 12, 16))
    venue = scene.match.get("venue", "")
    draw.text((style.width / 2, style.height - 70 * style.s), venue, font=font(int(30 * style.s), bold=True), fill=COLOUR_TEXT, anchor="mm")
    return img


def draw_card(text: str, style: Style) -> Image.Image:
    img = Image.new("RGB", (style.width, style.height), style.surround)
    ImageDraw.Draw(img).text((style.width / 2, style.height / 2), text, font=font(int(40 * style.s), bold=True), fill=COLOUR_TEXT, anchor="mm")
    return img


def draw_end_card(scene: Scene, style: Style) -> Image.Image:
    """Closing card: final score and the Regista mark."""
    s = style.s
    img = Image.new("RGB", (style.width, style.height), style.hud)
    d = ImageDraw.Draw(img)
    home, away = scene.teams[scene.match["home_team_id"]], scene.teams[scene.match["away_team_id"]]
    score = scene.score_at(scene.duration + 1)
    f_name = font(int(40 * s), bold=True)
    f_score = font(int(56 * s), bold=True)
    d.text((style.width / 2, style.height * 0.30), "FULL TIME", font=font(int(28 * s), bold=True), fill=COLOUR_ACCENT, anchor="mm")
    y = style.height * 0.47
    score_txt = f"{score.get(home['team_id'], 0)}  -  {score.get(away['team_id'], 0)}"
    gap = d.textlength(score_txt, font=f_score) / 2 + 40 * s
    d.text((style.width / 2, y), score_txt, font=f_score, fill=COLOUR_ACCENT, anchor="mm")
    d.text((style.width / 2 - gap, y), home["name"], font=f_name, fill=COLOUR_TEXT, anchor="rm")
    d.text((style.width / 2 + gap, y), away["name"], font=f_name, fill=COLOUR_TEXT, anchor="lm")
    sw = 14 * s
    hw, aw = d.textlength(home["name"], font=f_name), d.textlength(away["name"], font=f_name)
    d.rectangle([style.width / 2 - gap - hw - 30 * s, y - sw, style.width / 2 - gap - hw - 16 * s, y + sw], fill=hex_rgb(home["kit"]["primary"]))
    d.rectangle([style.width / 2 + gap + aw + 16 * s, y - sw, style.width / 2 + gap + aw + 30 * s, y + sw], fill=hex_rgb(away["kit"]["primary"]))
    d.text((style.width / 2, style.height * 0.66), scene.match.get("venue", ""), font=font(int(22 * s)), fill=(200, 200, 200), anchor="mm")
    d.text((style.width / 2, style.height * 0.82), "REGISTA", font=font(int(30 * s), bold=True), fill=COLOUR_TEXT, anchor="mm")
    d.text((style.width / 2, style.height * 0.82 + 34 * s), "every touch · every replay · every player", font=font(int(16 * s)), fill=(170, 170, 170), anchor="mm")
    return img


# ---------------------------------------------------------------------------- HUD

def _overlay(img: Image.Image) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    ov = Image.new("RGBA", img.size, (0, 0, 0, 0))
    return ov, ImageDraw.Draw(ov)


def draw_hud(img: Image.Image, scene: Scene, t: float, style: Style, info: dict[str, Any]) -> Image.Image:
    s = style.s
    ov, d = _overlay(img)
    score = scene.score_at(t)
    home, away = scene.teams[scene.match["home_team_id"]], scene.teams[scene.match["away_team_id"]]
    x, y, h = 24 * s, 22 * s, 44 * s
    f_team = font(int(22 * s), bold=True)
    f_score = font(int(24 * s), bold=True)
    f_clock = font(int(22 * s), bold=True)
    w_team = max(d.textlength(home["short_name"], font=f_team), d.textlength(away["short_name"], font=f_team))
    score_txt = f"{score.get(home['team_id'], 0)}  -  {score.get(away['team_id'], 0)}"
    w_score = d.textlength(score_txt, font=f_score)
    clock = scene.clock_at(t)
    w_clock = d.textlength(clock, font=f_clock) + 24 * s
    swatch = 10 * s
    board_w = 16 * s + swatch + 10 * s + w_team + 16 * s + w_score + 16 * s + w_team + 10 * s + swatch + 16 * s
    d.rounded_rectangle([x, y, x + board_w, y + h], radius=6 * s, fill=style.hud + (style.hud_alpha,))
    cx = x + 16 * s
    d.rectangle([cx, y + 9 * s, cx + swatch, y + h - 9 * s], fill=hex_rgb(home["kit"]["primary"]))
    cx += swatch + 10 * s
    d.text((cx, y + h / 2), home["short_name"], font=f_team, fill=COLOUR_TEXT, anchor="lm")
    cx += w_team + 16 * s
    d.text((cx, y + h / 2), score_txt, font=f_score, fill=COLOUR_ACCENT, anchor="lm")
    cx += w_score + 16 * s
    d.text((cx, y + h / 2), away["short_name"], font=f_team, fill=COLOUR_TEXT, anchor="lm")
    cx += w_team + 10 * s
    d.rectangle([cx, y + 9 * s, cx + swatch, y + h - 9 * s], fill=hex_rgb(away["kit"]["primary"]))
    d.rounded_rectangle([x + board_w + 6 * s, y, x + board_w + 6 * s + w_clock, y + h], radius=6 * s, fill=COLOUR_ACCENT + (240,))
    d.text((x + board_w + 6 * s + w_clock / 2, y + h / 2), clock, font=f_clock, fill=(20, 20, 20), anchor="mm")

    badge = info.get("badge")
    if badge:
        colour = COLOUR_HIGHLIGHT if badge["kind"] == "highlight" else COLOUR_REPLAY
        fg = (20, 20, 20) if badge["kind"] == "highlight" else COLOUR_TEXT
        f_b = font(int(22 * s), bold=True)
        f_sub = font(int(16 * s))
        text = badge["text"]
        sub = badge.get("sub", "")
        w = max(d.textlength(text, font=f_b), d.textlength(sub, font=f_sub)) + 28 * s
        bx1, by0 = style.width - 24 * s, 22 * s
        bh = h if not sub else h + 18 * s
        d.rounded_rectangle([bx1 - w, by0, bx1, by0 + bh], radius=6 * s, fill=colour + (255,))
        d.text((bx1 - w / 2, by0 + h / 2 - (6 * s if sub else 0)), text, font=f_b, fill=fg, anchor="mm")
        if sub:
            d.text((bx1 - w / 2, by0 + h / 2 + 16 * s), sub, font=f_sub, fill=fg, anchor="mm")

    text = info.get("caption")
    if text:
        cy0, cy1 = style.height - 92 * s, style.height - 44 * s
        accent = COLOUR_REPLAY if info.get("kind") == "replay" else COLOUR_HIGHLIGHT
        d.rectangle([0, cy0, style.width, cy1], fill=style.hud + (style.caption_alpha,))
        d.rectangle([0, cy0, 10 * s, cy1], fill=accent + (255,))
        d.text((28 * s, (cy0 + cy1) / 2), text, font=font(int(26 * s), bold=True), fill=COLOUR_TEXT, anchor="lm")

    d.text((style.width - 24 * s, style.height - 12 * s), "REGISTA", font=font(int(16 * s), bold=True), fill=(255, 255, 255, 150), anchor="rb")
    out = img.convert("RGBA")
    out.alpha_composite(ov)
    return out.convert("RGB")


def title_card_box(style: Style) -> tuple[float, float, float, float]:
    """The clip title card lives in the band under the scoreboard, over the far edge of the pitch."""
    s = style.s
    return (24 * s, 74 * s, style.width - 24 * s, 138 * s)


def draw_title_card(img: Image.Image, title: str, subtitle: str, watchability: float, style: Style) -> Image.Image:
    s = style.s
    ov, d = _overlay(img)
    x0, y0, x1, y1 = title_card_box(style)
    d.rounded_rectangle([x0, y0, x1, y1], radius=6 * s, fill=style.hud + (235,))
    d.rectangle([x0, y0, x0 + 10 * s, y1], fill=COLOUR_ACCENT + (255,))
    d.text((x0 + 26 * s, y0 + 20 * s), title, font=font(int(24 * s), bold=True), fill=COLOUR_TEXT, anchor="lm")
    d.text((x0 + 26 * s, y0 + 46 * s), subtitle, font=font(int(15 * s)), fill=(205, 205, 205), anchor="lm")
    bw, bh = 150 * s, 8 * s
    bx, by = x1 - 24 * s - bw, y0 + 42 * s
    d.rounded_rectangle([bx, by, bx + bw, by + bh], radius=3 * s, fill=(60, 60, 70, 255))
    d.rounded_rectangle([bx, by, bx + bw * max(0.02, min(1.0, watchability)), by + bh], radius=3 * s, fill=COLOUR_ACCENT + (255,))
    d.text((x1 - 24 * s, y0 + 20 * s), f"watchability {watchability:.2f}", font=font(int(15 * s), bold=True), fill=COLOUR_ACCENT, anchor="rm")
    out = img.convert("RGBA")
    out.alpha_composite(ov)
    return out.convert("RGB")


# ---------------------------------------------------------------------------- frame

def replay_window(scene: Scene, seg: Record) -> tuple[float, float]:
    """The main-view time range a replay/highlight reproduces, synthesised when the record lacks one."""
    win = seg.get("replays_window")
    if win:
        return float(win["t"]), float(win["t_end"])
    speed = float(seg.get("playback_speed", 1.0))
    length = (seg["t_end"] - seg["t"]) * speed
    for event_id in seg.get("replay_of", []):
        e = scene.event_by_id(event_id)
        if e is not None:
            end = e["t"] + min(1.5, length * 0.25)
            return max(0.0, end - length), end
    end = seg["t"]  # no event to anchor on: replay the main-view footage leading up to the cut
    return max(0.0, end - length), end


def frame_info(scene: Scene, t: float) -> dict[str, Any]:
    """What a frame at ``t`` shows, without drawing it. Used by the renderer and the tests."""
    seg = scene.segment_at(t)
    kind = seg["kind"]
    info: dict[str, Any] = {"t": t, "segment_id": seg["id"], "kind": kind, "view": "live", "scene_t": t, "badge": None, "caption": None}
    if kind == "main":
        cap = scene.caption_at(t)
        info["caption"] = cap.text if cap else None
    elif kind in ("replay", "highlight"):
        speed = float(seg.get("playback_speed", 1.0))
        w0, w1 = replay_window(scene, seg)
        tm = w0 + (t - seg["t"]) * speed
        info["scene_t"] = min(max(tm, w0), max(w0, w1 - 1e-3))
        angle = seg.get("angle") or "live"
        info["view"] = "highlight" if kind == "highlight" else (angle if angle in VIEWS else "live")
        desc = ", ".join(scene.describe_event(i) for i in seg.get("replay_of", [])) or ("Highlights" if kind == "highlight" else "Replay")
        if kind == "highlight":
            info["badge"] = {"kind": "highlight", "text": "HIGHLIGHTS", "sub": ""}
            info["caption"] = f"HIGHLIGHTS  ·  {desc}"
        else:
            sub = f"{speed:g}x" + (f"  ·  {angle.replace('_', ' ')}" if seg.get("angle") else "")
            info["badge"] = {"kind": "replay", "text": "REPLAY", "sub": sub}
            info["caption"] = f"REPLAY  ·  {desc}"
    elif kind == "closeup":
        info["players"] = scene.cutaway_players.get(seg["id"], [])
    return info


def render_frame(scene: Scene, t: float, style: Style | None = None, title: dict[str, Any] | None = None,
                 focus: str | None = None) -> Image.Image:
    """One frame. ``title`` draws a clip title card; ``focus`` keeps a white ring on that player in pitch views."""
    style = style or Style()
    info = frame_info(scene, t)
    kind = info["kind"]
    if kind in ("main", "replay", "highlight"):
        img, _ = draw_main_view(scene, info["scene_t"], style, info["view"], focus)
    elif kind == "closeup":
        img = draw_closeup(scene, info["players"], style, t)
    elif kind == "crowd":
        img = draw_crowd(scene, info["segment_id"], style, t)
    else:
        img = draw_card(kind.upper(), style)
    img = draw_hud(img, scene, t, style, info)
    if title:
        img = draw_title_card(img, title["title"], title.get("subtitle", ""), float(title.get("watchability", 0.0)), style)
    return img
