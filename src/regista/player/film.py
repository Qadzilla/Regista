"""The footage a (synthetic) player uploads: a friendly between their club and another Regista League club, generated
and rendered as broadcast video in the format the vision layer was trained on (640x360, 10 fps, no captions, no name
labels). Synthetic by design: no real camera, so ground truth exists for every frame.

    python -m regista.player.film --club cl_brookfield --opponent cl_calder --seed 4101 --minutes 3 --out data/player/film

``roster_for`` gives the team sheet the worker hands the vision layer for such footage: both clubs' squads with their
global player ids, so the match it writes joins the profiles without any mapping.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from regista.schema import write_jsonl
from regista.season.league import club_by_id, generate_kwargs, load_league_cached

Record = dict[str, Any]
LEAGUE = Path("data/season/league.json")
SIZE = (640, 360)
FPS = 10.0
TRACK_HZ = 2.0


def _sides(league: Record, club_id: str, opponent_club_id: str, side: str) -> tuple[str, str]:
    clubs = club_by_id(league)
    for c in (club_id, opponent_club_id):
        if c not in clubs:
            raise ValueError(f"no club {c!r} in the league")
    if club_id == opponent_club_id:
        raise ValueError("a club cannot play itself")
    if side not in ("home", "away"):
        raise ValueError("side is home or away")
    return (club_id, opponent_club_id) if side == "home" else (opponent_club_id, club_id)


def friendly_kwargs(league: Record, club_id: str, opponent_club_id: str, side: str, seed: int, minutes: float) -> Record:
    """``generate`` arguments for a friendly: the league's squads and kits, one period, its own match id."""
    home, away = _sides(league, club_id, opponent_club_id, side)
    clubs = club_by_id(league)
    # Without ratings: the footage stays in the format (and the event vocabulary) the vision layer was trained on.
    kw = generate_kwargs(league, {"match_id": "x", "home": home, "away": away, "seed": seed, "round": 0,
                                  "date": "2026-10-24"}, ratings=False)
    kw.update(minutes=minutes, periods=1, track_hz=TRACK_HZ, profile="demo",
              match_id=f"fr_{clubs[home]['short_name'].lower()}_{clubs[away]['short_name'].lower()}_{seed}",
              meta={"competition": "Friendly (filmed by a player)", "season": league["season"], "date": "2026-10-24",
                    "venue": clubs[home]["ground"]})
    return kw


def roster_for(club_id: str, opponent_club_id: str, side: str, league_path: Path | str = LEAGUE) -> Record:
    """The team sheet for footage of these two clubs: a match header with both squads (global ids, kit numbers,
    positions) and kits. Independent of the seed, so the worker can build it from the upload record alone."""
    from regista.synth.generator import generate

    league = load_league_cached(league_path)
    kw = friendly_kwargs(league, club_id, opponent_club_id, side, seed=1, minutes=0.05)
    header = generate(**kw).match
    return {k: v for k, v in header.items() if k not in ("periods", "score", "generator", "video")}


def film(club_id: str, opponent_club_id: str, side: str = "home", *, seed: int = 4101, minutes: float = 3.0,
         out: Path | str = "data/player/film", league_path: Path | str = LEAGUE, workers: int | None = None) -> Record:
    """Generate and render the friendly. Returns ``{"video", "truth_dir", "match_id"}``; ``truth_dir`` holds the
    generator's events and tracks (ground truth for checking what the vision layer finds)."""
    from regista.render.scene import Scene
    from regista.render.video import render_video
    from regista.synth.generator import generate
    from regista.vision.dataset import vision_style

    league = load_league_cached(league_path)
    kw = friendly_kwargs(league, club_id, opponent_club_id, side, seed, minutes)
    out = Path(out)
    truth = out / kw["match_id"]
    result = generate(**kw)
    write_jsonl(truth / "events.jsonl", result.stream)
    write_jsonl(truth / "tracks.jsonl", result.tracks)
    video = out / f"{kw['match_id']}_{SIZE[0]}x{SIZE[1]}_{FPS:g}fps.mp4"
    render_video(Scene.load(truth), video, fps=FPS, style=vision_style(SIZE), workers=workers)
    (truth / "film.json").write_text(json.dumps({"club_id": club_id, "opponent_club_id": opponent_club_id, "side": side,
                                                 "seed": seed, "minutes": minutes, "video": str(video)}, indent=1))
    return {"video": str(video), "truth_dir": str(truth), "match_id": kw["match_id"]}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m regista.player.film", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--club", required=True)
    ap.add_argument("--opponent", required=True)
    ap.add_argument("--side", choices=["home", "away"], default="home")
    ap.add_argument("--seed", type=int, default=4101)
    ap.add_argument("--minutes", type=float, default=3.0)
    ap.add_argument("--out", default="data/player/film")
    args = ap.parse_args(argv)
    r = film(args.club, args.opponent, args.side, seed=args.seed, minutes=args.minutes, out=args.out)
    print(json.dumps(r, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
