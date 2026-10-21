"""Make footage with exact ground truth: generate synthetic matches and render them to video.

Every item is a match directory (events.jsonl + tracks.jsonl from ``regista.synth``) plus the
broadcast video ``regista.render`` draws from it. Clubs and kit colours vary per match so the
models learn "a kit colour" rather than one club. The development matches (``TEST_SPECS``) use clubs the
training matches never show; the fresh matches (``FRESH_SPECS``) also use colours far from every training kit.

Everything is written under a caller-chosen root (default ``/tmp/regista_vision``), never into
the repo: the repo holds no footage, rendered or otherwise.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from regista.schema import write_jsonl

DEFAULT_ROOT = Path("/tmp/regista_vision")


@dataclass(frozen=True)
class MatchSpec:
    seed: int
    home: str | None = None   # "Name,SHORT,#primary[,#secondary[,#gk]]" as for python -m regista.synth --home
    away: str | None = None
    minutes: float = 3.0
    periods: int = 1

    @property
    def match_id(self) -> str:
        return f"syn_{self.seed:04d}"


# Training clubs. Goalkeeper colours are set wherever the default (green / orange) would clash with an outfield kit.
TRAIN_SPECS: list[MatchSpec] = [
    MatchSpec(101, minutes=5),  # Northbridge red vs Southgate navy, default keepers
    MatchSpec(102, "Kingsport Athletic,KIN,#0EA5E9,#FFFFFF,#F43F5E", "Redmoor,RED,#7F1D1D,#FFFFFF,#FACC15", minutes=5),
    MatchSpec(103, "Ashford Town,ASH,#F97316,#FFFFFF,#22C55E", "Bayside,BAY,#14B8A6,#FFFFFF,#A855F7", minutes=5),
    MatchSpec(104, "Harlow Park,HAR,#EC4899,#FFFFFF,#0EA5E9", "Norland,NRL,#4338CA,#FFFFFF,#F59E0B", minutes=2.5, periods=2),
    MatchSpec(105, "Elmstead,ELM,#B91C1C,#FFFFFF,#06B6D4", "Greyfield,GRY,#65A30D,#FFFFFF,#E11D48", minutes=5),
    MatchSpec(106, "Oakvale,OAK,#1D4ED8,#FFFFFF,#F97316", "Thornbury,THO,#DB2777,#FFFFFF,#16A34A", minutes=2.5, periods=2),
    MatchSpec(107, "Pinehurst,PIN,#0F766E,#FFFFFF,#F472B6", "Calder,CAL,#C2410C,#FFFFFF,#38BDF8", minutes=5),
    MatchSpec(108, "Rivington,RIV,#7C3AED,#FFFFFF,#84CC16", "Dunmore,DUN,#E11D48,#FFFFFF,#2DD4BF", minutes=5),
    MatchSpec(109, "Wexley,WEX,#0369A1,#FFFFFF,#FB923C", "Fenwick,FEN,#A16207,#FFFFFF,#C084FC", minutes=5),
    MatchSpec(110, "Castleford,CAS,#BE185D,#FFFFFF,#4ADE80", "Moorgate,MOO,#1E40AF,#FFFFFF,#FDBA74", minutes=5),
]

# Development set: clubs unseen in training (the first is the demo pairing from CLAUDE.md). Not held out: these were
# checked while tuning, and three keeper/primary colours repeat training kits (docs/vision.md).
TEST_SPECS: list[MatchSpec] = [
    MatchSpec(201, "Eastbury Rovers,EAS,#00A650,#FFFFFF,#F97316", "Westfield Town,WES,#6A0DAD,#FFFFFF,#FDE047", minutes=5),
    MatchSpec(202, "Corrin,COR,#DC2626,#FFFFFF,#22D3EE", "Lakeside,LAK,#2563EB,#FFFFFF,#A3E635", minutes=2.5, periods=2),
    MatchSpec(203, "Millbrook,MIL,#9333EA,#FFFFFF,#10B981", "Stonebridge,STO,#EA580C,#000000,#0891B2", minutes=5),
    MatchSpec(204, "Hollins,HOL,#0891B2,#FFFFFF,#EF4444", "Brackley,BRA,#9F1239,#FFFFFF,#A3E635", minutes=5),
    MatchSpec(205, "Kelso,KEL,#BE123C,#FFFFFF,#F0ABFC", "Ravenmoor,RAV,#F59E0B,#000000,#3B82F6", minutes=5),
    MatchSpec(206, "Ilford Vale,ILF,#6D28D9,#FFFFFF,#FB7185", "Selby,SEL,#0284C7,#FFFFFF,#FACC15", minutes=2.5, periods=2),
]


# Extra matches for the event spotter's training only: new seeds, the training clubs and colours again (so the fresh
# set's colours stay unseen). Nutmegs are rare; vision output of more matches is what teaches how they look to a camera.
EVENT_TRAIN_SPECS: list[MatchSpec] = TRAIN_SPECS + [
    MatchSpec(111 + i, TRAIN_SPECS[i % len(TRAIN_SPECS)].home, TRAIN_SPECS[i % len(TRAIN_SPECS)].away, minutes=5) for i in range(30)
]

# Fresh matches, made after the audit and scored once with frozen models: new clubs, and primary and goalkeeper colours
# at least 20 CIE76 ΔE from every training and development kit, the grass, and the neutrals.
FRESH_SPECS: list[MatchSpec] = [
    MatchSpec(301, "Hartwell,HRT,#1717E6,#FFFFFF,#F28D61", "Penrose,PEN,#B28F59,#000000,#55E617", minutes=5),
    MatchSpec(302, "Ashgrove,ASG,#66052C,#FFFFFF,#A1B259", "Varley,VAR,#F261E4,#000000,#053666", minutes=2.5, periods=2),
    MatchSpec(303, "Calloway,CLW,#663605,#FFFFFF,#7D59B2", "Linden,LIN,#B25959,#FFFFFF,#050F66", minutes=5),
]


def _team(text: str | None) -> dict[str, Any]:
    from regista.synth.generator import parse_team_arg

    return parse_team_arg(text) if text else {}


def make_match(spec: MatchSpec, root: Path | str = DEFAULT_ROOT, *, size: tuple[int, int] = (640, 360), fps: float = 10.0,
               track_hz: float = 2.0, workers: int | None = None, end_card_s: float = 3.0, force: bool = False,
               t_end: float | None = None, captions: bool = False) -> dict[str, Any]:
    """Generate and render one match. Returns ``{"match_dir", "video", "spec"}``; skips work already on disk.

    Vision footage is rendered without the on-screen captions by default: they name the event ("REPLAY · goal by
    ...", "NUTMEG! ..."), real footage has nothing like them, and the v2 shot model turned out to lean on them for
    replays (docs/vision.md). ``captions=True`` reproduces the v2 training footage."""
    from regista.render.draw import Style
    from regista.render.scene import Scene
    from regista.render.video import render_video
    from regista.synth import generate

    root = Path(root)
    match_dir = root / "matches" / spec.match_id
    tag = f"{size[0]}x{size[1]}_{fps:g}fps" + (f"_to{t_end:g}s" if t_end else "") + ("" if captions else "_nocap")
    video = root / "video" / f"{spec.match_id}_{tag}.mp4"
    if force or not (match_dir / "events.jsonl").exists():
        teams = None
        if spec.home or spec.away:
            teams = [_team(spec.home), _team(spec.away)]
        result = generate(seed=spec.seed, minutes=spec.minutes, track_hz=track_hz, periods=spec.periods, teams=teams)
        write_jsonl(match_dir / "events.jsonl", result.stream)
        write_jsonl(match_dir / "tracks.jsonl", result.tracks)
        (match_dir / "spec.json").write_text(json.dumps(spec.__dict__), encoding="utf-8")
    if force or not video.exists():
        scene = Scene.load(match_dir)
        render_video(scene, video, fps=fps, style=Style(width=size[0], height=size[1], captions=captions), workers=workers, t1=t_end,
                     end_card_s=end_card_s if t_end is None else 0.0)
    return {"match_dir": str(match_dir), "video": str(video), "spec": spec}


def make_dataset(specs: list[MatchSpec], root: Path | str = DEFAULT_ROOT, **kw: Any) -> list[dict[str, Any]]:
    return [make_match(s, root, **kw) for s in specs]
