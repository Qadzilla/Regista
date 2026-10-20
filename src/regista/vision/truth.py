"""Exact ground truth for Regista's own rendered broadcast, straight from the generator.

The renderer (``regista.render``) draws every frame from a match directory, so for any
frame we can recompute what is in it:

- **Shot kind.** The ``camera_segment`` covering ``t`` (``frame_info``); frames after the last
  segment are the renderer's full-time end card, labelled ``graphic``.
- **Player and ball positions.** The same interpolated pitch positions the renderer used
  (``Scene.positions_at`` / ``Scene.ball_at`` at the frame's scene time, which for replays is
  the replayed main-view time), projected through the renderer's own ``Camera`` for that view.
  Disc centre, radius, and draw order replicate ``draw_players`` exactly.
- **Identity.** ``player_id``, team, and kit number from the match roster.
- **Possession.** The generator's ``possession`` records.

This module exists only for training and evaluation on synthetic footage. Nothing in the
inference path imports it. On real footage its role is taken by human labels (shot kinds
marked in a review tool, player boxes and numbers annotated on sampled frames), stored as
``annotation`` records with ``source: human``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from regista.render.draw import VIEWS, Camera, Style, frame_info
from regista.render.scene import Scene
from regista.schema import iter_jsonl

Record = dict[str, Any]
END_CARD_KIND = "graphic"  # the renderer's closing card is a graphic in camera_segment terms


@dataclass
class TruthDisc:
    player_id: str
    team_id: str
    kit_number: int
    is_gk: bool
    cx: float          # disc centre, pixels
    cy: float
    r: float           # disc radius, pixels
    foot_x: float      # ground contact point (bottom of the disc), pixels
    foot_y: float
    pitch: tuple[float, float] | None  # metres; None on cards
    occluded: float = 0.0  # 0 = fully visible; ~1 = centre covered by a disc drawn later
    holder: bool = False


@dataclass
class TruthBall:
    cx: float
    cy: float
    r: float
    foot_x: float
    foot_y: float
    pitch: tuple[float, float]


@dataclass
class FrameTruth:
    t: float
    kind: str
    segment_id: str | None
    view: str | None = None
    scene_t: float | None = None
    cam_cx: float | None = None
    players: list[TruthDisc] = field(default_factory=list)
    ball: TruthBall | None = None


class Truth:
    """Ground truth for one rendered match at one render size."""

    def __init__(self, match_dir: Path | str, width: int, height: int):
        self.match_dir = Path(match_dir)
        self.scene = Scene.load(self.match_dir)
        self.style = Style(width=width, height=height)
        self.width, self.height = self.style.width, self.style.height
        self.match: Record = self.scene.match
        self.roster = self.scene.roster
        self.teams = self.scene.teams

    # ------------------------------------------------------------------ shots
    def kind_at(self, t: float) -> str:
        if t >= self.scene.duration:
            return END_CARD_KIND
        return self.scene.segment_at(t)["kind"]

    def segments(self, video_duration: float | None = None) -> list[Record]:
        """``{t, t_end, kind, id}`` covering the whole video, the end card appended as a graphic segment."""
        out = [{"id": s["id"], "t": float(s["t"]), "t_end": float(s["t_end"]), "kind": s["kind"]} for s in self.scene.segments]
        if video_duration is not None and video_duration > self.scene.duration + 1e-6:
            out.append({"id": "cs_end_card", "t": float(self.scene.duration), "t_end": float(video_duration), "kind": END_CARD_KIND})
        return out

    def possessions(self) -> list[Record]:
        return list(self.scene.possessions)

    def appearances(self) -> list[Record]:
        return [r for r in self.scene.stream if r["type"] == "appearance"]

    # ------------------------------------------------------------------ objects
    def objects_at(self, t: float) -> FrameTruth:
        if t >= self.scene.duration:
            return FrameTruth(t=t, kind=END_CARD_KIND, segment_id=None)
        info = frame_info(self.scene, t)
        kind = info["kind"]
        ft = FrameTruth(t=t, kind=kind, segment_id=info["segment_id"], view=info.get("view"), scene_t=info.get("scene_t"))
        if kind in ("main", "replay", "highlight"):
            self._pitch_view(ft)
        elif kind == "closeup":
            self._closeup(ft, info.get("players", []))
        return ft

    def _pitch_view(self, ft: FrameTruth) -> None:
        scene, style = self.scene, self.style
        st = float(ft.scene_t if ft.scene_t is not None else ft.t)
        view = VIEWS.get(ft.view or "live", VIEWS["live"])
        ball = scene.ball_at(st)
        cam = Camera(style, ball[0], view, style.pitch_top, style.pitch_bottom)
        ft.cam_cx = cam.cx
        positions = scene.positions_at(st)
        holder = scene.holder_at(st)
        base_r = 14.0 * style.s
        on_top = [pid for pid in dict.fromkeys((holder,)) if pid and pid in positions]
        ordinary = sorted(((pid, p) for pid, p in positions.items() if pid not in on_top), key=lambda kv: -cam.depth(kv[1][1]))
        order = ordinary + [(pid, positions[pid]) for pid in on_top]
        discs: list[TruthDisc] = []
        for pid, (x, y) in order:
            sx, sy = cam.project(x, y)
            r = base_r * cam.disc_scale(y)
            if sx < -2 * r or sx > style.width + 2 * r:
                continue
            p = self.roster.get(pid)
            if p is None:
                continue
            discs.append(TruthDisc(player_id=pid, team_id=p["team_id"], kit_number=int(p["kit_number"]), is_gk=p["position"] == "GK",
                                   cx=sx, cy=sy - r, r=r, foot_x=sx, foot_y=sy, pitch=(x, y), holder=pid == holder))
        # Occlusion: how much of each disc's centre area is covered by discs drawn after it.
        for i, d in enumerate(discs):
            cover = 0.0
            for e in discs[i + 1:]:
                dist = ((d.cx - e.cx) ** 2 + (d.cy - e.cy) ** 2) ** 0.5
                cover = max(cover, max(0.0, 1.0 - dist / (d.r + e.r)))
            d.occluded = round(cover, 3)
        ft.players = discs
        bx, by = cam.project(*ball)
        br = max(3.0, 5.5 * style.s * cam.disc_scale(ball[1]))
        ft.ball = TruthBall(cx=bx, cy=by - br, r=br, foot_x=bx, foot_y=by, pitch=(float(ball[0]), float(ball[1])))

    def _closeup(self, ft: FrameTruth, player_ids: list[str]) -> None:
        scene, style = self.scene, self.style
        ids = [pid for pid in player_ids if pid in self.roster]
        if not ids:
            last = scene.last_player_before(ft.t)
            ids = [last or next(iter(self.roster))]
        n = len(ids)
        for i, pid in enumerate(ids):
            p = self.roster[pid]
            x0 = int(i * style.width / n)
            x1 = int((i + 1) * style.width / n)
            cx = (x0 + x1) / 2
            r = min(160 * style.s, (x1 - x0) * 0.26)
            cy = style.height * 0.47
            ft.players.append(TruthDisc(player_id=pid, team_id=p["team_id"], kit_number=int(p["kit_number"]), is_gk=p["position"] == "GK",
                                        cx=cx, cy=cy, r=r, foot_x=cx, foot_y=cy + r, pitch=None))


def load_match_header(path: Path | str) -> Record:
    """The ``match`` record from a match directory or an events.jsonl/JSON file: the roster input of the vision layer."""
    path = Path(path)
    if path.is_dir():
        path = path / "events.jsonl"
    if path.suffix == ".json":
        rec = json.loads(path.read_text(encoding="utf-8"))
        if rec.get("type") == "match":
            return rec
        raise ValueError(f"{path} is not a match record")
    for rec in iter_jsonl(path):
        if rec.get("type") == "match":
            return rec
    raise ValueError(f"no match record in {path}")
