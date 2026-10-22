"""python -m regista.season: make the league, build its matches, and read profiles.

    python -m regista.season new [--seed 2026] [--out data/season/league.json]
    python -m regista.season build [--league data/season/league.json] [--root data/season/matches]
    python -m regista.season table
    python -m regista.season players [--position FW] [--sort take_ons_won] [--limit 10]
    python -m regista.season profile pl_ash_09
"""

from __future__ import annotations

import argparse
import json
import time

from regista.season.build import build_all
from regista.season.league import DEFAULT_SEED, load_league, new_league, save_league
from regista.season.profiles import HEADLINE, STATS, load_season

LEAGUE = "data/season/league.json"
ROOT = "data/season/matches"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m regista.season", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--league", default=LEAGUE)
    ap.add_argument("--root", default=ROOT, help="where match folders are written (not committed)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    n = sub.add_parser("new", help="write a new league definition")
    n.add_argument("--seed", type=int, default=DEFAULT_SEED)
    sub.add_parser("build", help="generate every fixture's match folder")
    sub.add_parser("table", help="the league table")
    pl = sub.add_parser("players", help="profile cards, filtered and sorted")
    pl.add_argument("--position", choices=["GK", "DF", "MF", "FW"])
    pl.add_argument("--club")
    pl.add_argument("--sort", default="minutes")
    pl.add_argument("--limit", type=int, default=15)
    pr = sub.add_parser("profile", help="one player's profile as JSON")
    pr.add_argument("global_id")
    args = ap.parse_args(argv)

    if args.cmd == "new":
        path = save_league(new_league(args.seed), args.league)
        print(f"wrote {path}")
        return 0
    if args.cmd == "build":
        t = time.time()
        dirs = build_all(load_league(args.league), args.root)
        print(f"{len(dirs)} matches in {args.root} ({time.time() - t:.1f} s)")
        return 0
    season = load_season(args.league, args.root)
    if args.cmd == "table":
        print(f"{'':3} {'club':20} {'P':>2} {'W':>2} {'D':>2} {'L':>2} {'GF':>3} {'GA':>3} {'Pts':>3}")
        for r in season.table:
            print(f"{r['position']:>3} {r['club']:20} {r['played']:>2} {r['won']:>2} {r['drawn']:>2} {r['lost']:>2} "
                  f"{r['goals_for']:>3} {r['goals_against']:>3} {r['points']:>3}")
        return 0
    if args.cmd == "players":
        for c in season.players(position=args.position, club=args.club, sort=args.sort, limit=args.limit):
            rates = ", ".join(f"{STATS[k][0].lower()} {c['headline'][k]['per90']}" for k in HEADLINE[:6] if c["headline"][k]["count"])
            print(f"{c['global_id']:12} {c['name']:22} {c['short_name']} {c['position']} {c['minutes']:>5} min  {rates}")
        return 0
    p = season.player(args.global_id)
    if p is None:
        ap.error(f"no player {args.global_id}")
    print(json.dumps({k: v for k, v in p.items() if k not in ("evidence", "grid")}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
