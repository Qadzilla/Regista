"""python -m regista.catalogue {define|build|check|competitions}

  define [--check]          write data/catalogue/ from the definition (or only check the committed files equal it)
  build [--workers N]       regenerate every catalogue match into REGISTA_CATALOGUE_ROOT (default data/catalogue/matches)
  check                     build, then compare every match's events with its pin (regista.catalogue.pins)
  competitions              the 14 competitions: country, level, teams, people, uploaded matches, cameras
"""

from __future__ import annotations

import argparse
import sys
import time
from collections import Counter
from pathlib import Path


def _define(check: bool) -> int:
    from regista.catalogue.define import dumps, new_catalogue, save_catalogue
    from regista.season.league import load_league

    league = load_league("data/season/league.json")
    index, comps = new_catalogue(league)
    if check:
        bad = []
        if Path("data/catalogue/catalogue.json").read_text() != dumps(index):
            bad.append("data/catalogue/catalogue.json")
        for e in index["competitions"]:
            if e["source"] == "catalogue" and Path(e["path"]).read_text() != dumps(comps[e["competition_id"]]):
                bad.append(e["path"])
        print("the committed catalogue is what the definition writes" if not bad else f"differs: {bad}")
        return 1 if bad else 0
    for p in save_catalogue(index, comps):
        print(f"wrote {p}")
    return 0


def _build(workers: int | None) -> int:
    from regista.catalogue.build import build_catalogue
    from regista.catalogue.store import matches_root

    t = time.perf_counter()
    paths = build_catalogue(workers=workers)
    print(f"{len(paths)} catalogue matches current in {matches_root()} ({time.perf_counter() - t:.1f} s)")
    return 0


def _check(workers: int | None) -> int:
    from regista.catalogue.pins import drift
    from regista.catalogue.store import matches_root

    _build(workers)
    moved = drift(root=matches_root())
    print("every catalogue match is its pin" if not moved else f"{len(moved)} differ: {sorted(moved)}")
    return 1 if moved else 0


def _competitions() -> int:
    from regista.catalogue import store

    print(f"{'competition':22s} {'country':8s} {'tier':9s} {'age':8s} {'gender':6s} teams people matches  cameras")
    for e in store.entries():
        comp = store.competition(e["competition_id"])
        fx = comp["fixtures"]
        cams = Counter((e.get("uploads", {}).get(f["match_id"]) or f).get("camera") for f in fx)
        people = len({p["global_id"] for c in comp["clubs"] for p in c["squad"]})
        print(f"{e['competition_id']:22s} {e['country']:8s} {e['tier']:9s} {e['age_group']:8s} {e['gender']:6s} "
              f"{len(comp['clubs']):5d} {people:6d} {len(fx):7d}  {dict(cams)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m regista.catalogue", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("define")
    d.add_argument("--check", action="store_true")
    for name in ("build", "check"):
        b = sub.add_parser(name)
        b.add_argument("--workers", type=int, default=None)
    sub.add_parser("competitions")
    args = ap.parse_args(argv)
    if args.cmd == "define":
        return _define(args.check)
    if args.cmd == "build":
        return _build(args.workers)
    if args.cmd == "check":
        return _check(args.workers)
    return _competitions()


if __name__ == "__main__":
    sys.exit(main())
