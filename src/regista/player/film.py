"""The footage a (synthetic) player uploads: a friendly between their club and another Regista League club, or (with
``competition_id``) a match between two clubs of a catalogue competition, generated and rendered as broadcast video in
the format the vision layer was trained on (640x360, 10 fps, no captions, no name labels). Synthetic by design: no real
camera, so ground truth exists for every frame.

    python -m regista.player.film --club cl_brookfield --opponent cl_calder --seed 4101 --minutes 3 --out data/player/film
    python -m regista.player.film --competition co_nga_am_men --club cl_... --opponent cl_... --date 2026-10-17

``roster_for`` gives the team sheet the worker hands the vision layer for such footage: both clubs' squads with their
global player ids, so the match it writes names its players without any mapping. Always without ratings
(``ratings=False``): no hidden rating or level scale reaches the roster, the header or the manifest.
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
FRIENDLY = "Friendly (filmed by a player)"
FRIENDLY_DATE = "2026-10-24"
SIZE = (640, 360)
FPS = 10.0
TRACK_HZ = 2.0


def competition_for(competition_id: str | None, league_path: Path | str = LEAGUE) -> Record:
    """The league-shaped competition the footage is from: the Regista League (None, or England's id), else a catalogue
    competition (``regista.catalogue.store.competition``)."""
    from regista.catalogue.taxonomy import ENGLAND_ID

    if competition_id is None or competition_id == ENGLAND_ID:
        return load_league_cached(league_path)
    from regista.catalogue import store

    comp = store.competition(competition_id)
    if comp is None:
        raise ValueError(f"no competition {competition_id!r} in the catalogue")
    return comp


def _sides(league: Record, club_id: str, opponent_club_id: str, side: str) -> tuple[str, str]:
    clubs = club_by_id(league)
    for c in (club_id, opponent_club_id):
        if c not in clubs:
            raise ValueError(f"no club {c!r} in {league.get('league') or 'the league'}")
    if club_id == opponent_club_id:
        raise ValueError("a club cannot play itself")
    if side not in ("home", "away"):
        raise ValueError("side is home or away")
    return (club_id, opponent_club_id) if side == "home" else (opponent_club_id, club_id)


def friendly_kwargs(league: Record, club_id: str, opponent_club_id: str, side: str, seed: int, minutes: float, *,
                    date: str | None = None, competition: str | None = None) -> Record:
    """``generate`` arguments for the footage: the competition's squads and kits, one period, its own match id.
    ``competition`` names it in the header (default: a friendly); ``date`` the day it was played."""
    home, away = _sides(league, club_id, opponent_club_id, side)
    clubs = club_by_id(league)
    day = date or FRIENDLY_DATE
    # Without ratings: the footage stays in the format (and the event vocabulary) the vision layer was trained on, and
    # no hidden rating or level scale (a catalogue file's ``level``) reaches the generator's header.
    kw = generate_kwargs(league, {"match_id": "x", "home": home, "away": away, "seed": seed, "round": 0,
                                  "date": day}, ratings=False)
    kw.update(minutes=minutes, periods=1, track_hz=TRACK_HZ, profile="demo",
              match_id=f"fr_{clubs[home]['short_name'].lower()}_{clubs[away]['short_name'].lower()}_{seed}",
              meta={"competition": competition or FRIENDLY, "season": league["season"], "date": day,
                    "venue": clubs[home].get("ground")})
    return kw


def _label(league: Record, competition_id: str | None) -> str | None:
    """The header's competition name: the catalogue competition's (a match of its clubs), else None (a friendly)."""
    from regista.catalogue.taxonomy import ENGLAND_ID

    return None if competition_id is None or competition_id == ENGLAND_ID else league["league"]


def roster_for(club_id: str, opponent_club_id: str, side: str, league_path: Path | str = LEAGUE, *,
               competition_id: str | None = None, date: str | None = None) -> Record:
    """The team sheet for footage of these two clubs: a match header with both squads (global ids, kit numbers,
    positions) and kits. Independent of the seed, so the worker can build it from the upload record alone.
    ``competition_id`` reads a catalogue competition's squads (default: the Regista League's)."""
    from regista.synth.generator import generate

    league = competition_for(competition_id, league_path)
    kw = friendly_kwargs(league, club_id, opponent_club_id, side, seed=1, minutes=0.05, date=date,
                         competition=_label(league, competition_id))
    header = generate(**kw).match
    return {k: v for k, v in header.items() if k not in ("periods", "score", "generator", "video")}


def film(club_id: str, opponent_club_id: str, side: str = "home", *, seed: int = 4101, minutes: float = 3.0,
         out: Path | str = "data/player/film", league_path: Path | str = LEAGUE, workers: int | None = None,
         competition_id: str | None = None, date: str | None = None) -> Record:
    """Generate and render the friendly. Returns ``{"video", "truth_dir", "match_id"}``; ``truth_dir`` holds the
    generator's events and tracks (ground truth for checking what the vision layer finds)."""
    from regista.render.scene import Scene
    from regista.render.video import render_video
    from regista.synth.generator import generate
    from regista.vision.dataset import vision_style

    league = competition_for(competition_id, league_path)
    kw = friendly_kwargs(league, club_id, opponent_club_id, side, seed, minutes, date=date,
                         competition=_label(league, competition_id))
    out = Path(out)
    truth = out / kw["match_id"]
    result = generate(**kw)
    write_jsonl(truth / "events.jsonl", result.stream)
    write_jsonl(truth / "tracks.jsonl", result.tracks)
    video = out / f"{kw['match_id']}_{SIZE[0]}x{SIZE[1]}_{FPS:g}fps.mp4"
    render_video(Scene.load(truth), video, fps=FPS, style=vision_style(SIZE), workers=workers)
    (truth / "film.json").write_text(json.dumps({"club_id": club_id, "opponent_club_id": opponent_club_id, "side": side,
                                                 "seed": seed, "minutes": minutes, "video": str(video),
                                                 "competition_id": competition_id, "date": kw["meta"]["date"]}, indent=1))
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
    ap.add_argument("--competition", default=None, help="a catalogue competition id (default: the Regista League)")
    ap.add_argument("--date", default=None, help="the day the match was played, YYYY-MM-DD")
    args = ap.parse_args(argv)
    r = film(args.club, args.opponent, args.side, seed=args.seed, minutes=args.minutes, out=args.out,
             competition_id=args.competition, date=args.date)
    print(json.dumps(r, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
