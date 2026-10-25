"""python -m regista.catalogue {define|build|check|competitions|reliability|levels|player}

  define [--check]          write data/catalogue/ from the definition (or only check the committed files equal it)
  build [--workers N]       regenerate every catalogue match into REGISTA_CATALOGUE_ROOT (default data/catalogue/matches)
  check                     build, then compare every match's events with its pin (regista.catalogue.pins)
  competitions              the 14 competitions: country, level, teams, people, uploaded matches, cameras
  reliability [--repeats N] [--out PATH] [--realism PATH] [--aggregates PATH]
                            measure every level on full regenerated seasons and write data/catalogue/reliability.json
                            and the realism verdicts beside it, data/catalogue/realism.json (a few minutes on ten
                            cores); --aggregates also writes the bare level aggregates
  levels [--scope S]        the percentile pools: per level (or competition, or all) and position, how many players
                            qualify on minutes, and which pools are small
  player ID [--scope S]     one player across the catalogue: career, then the position's default metrics per competition
"""

from __future__ import annotations

import argparse
import os
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


def _reliability(repeats: int, workers: int | None, out: str | None, aggregates: str | None,
                 realism_out: str | None = None) -> int:
    import json

    from regista.catalogue import reliability as rel
    from regista.catalogue import store
    from regista.catalogue.measure import level_aggregates, measure
    from regista.catalogue import realism as rea
    from regista.catalogue.realism import band_checks, order_checks
    from regista.season.league import load_league
    from regista.season.metrics import load_metrics

    league_path = store.competition_path(store.entry("co_eng_sp_men"))
    league = load_league(league_path)
    xt = load_metrics(league_path, Path(os.environ.get("REGISTA_SEASON_ROOT", "data/season/matches"))).xt
    comps = store.new_competitions()
    t = time.perf_counter()
    results = measure([league, *comps], repeats, xt, workers)
    data = rel.compute(league, comps, repeats, xt, results=results)
    path = Path(out) if out else rel.default_path()
    path.write_text(json.dumps(data, indent=1, sort_keys=True) + "\n")
    print(f"wrote {path}: {len(data['levels'])} levels, {sum(r['matches'] for r in results)} matches measured "
          f"({time.perf_counter() - t:.0f} s)")
    for level, lv in data["levels"].items():
        noisy = sum(1 for v in lv["metrics"].values() if v["noisy"])
        print(f"  {level:24s} {lv['matches']:5d} matches, half {lv['median_half_minutes']} min, {noisy} noisy")
    verdicts = rea.compute(league, comps, repeats, results)
    rpath = Path(realism_out) if realism_out else path.with_name(rea.FILE_NAME)
    rpath.write_text(json.dumps(verdicts, indent=1, sort_keys=True) + "\n")
    print(f"wrote {rpath}")
    for c in verdicts["bands"] + verdicts["orders"]:
        print(f"  {c['id']:28s} {c['verdict']}")
    if aggregates:
        agg = level_aggregates(results)
        Path(aggregates).write_text(json.dumps({"levels": agg, "bands": band_checks(agg), "orders": order_checks(agg)},
                                               indent=1, sort_keys=True) + "\n")
        print(f"wrote {aggregates}")
    return 0


def _levels(scope: str) -> int:
    from regista.catalogue.metrics import load_catalogue_metrics

    cm = load_catalogue_metrics()
    print(f"{'pool':34s} {'GK':>4s} {'DF':>4s} {'MF':>4s} {'FW':>4s}  (players qualified on minutes; * small, ! under 5)")
    for row in cm.pool_sizes(scope):
        cells = []
        for pos in ("GK", "DF", "MF", "FW"):
            n = row["positions"][pos]["size"]
            cells.append(f"{n:>3d}{'!' if n < cm.MIN_POOL else '*' if n < cm.SMALL_POOL else ' '}")
        print(f"{row['label']:34s} {' '.join(cells)}")
    return 0


def _player(gid: str, scope: str) -> int:
    from regista.catalogue.metrics import load_catalogue_metrics
    from regista.season.metrics import CATALOGUE, DEFAULT_COLUMNS

    cm = load_catalogue_metrics()
    view = cm.player(gid, scope=scope)
    if view is None:
        print(f"no player {gid!r} in the catalogue")
        return 1
    print(f"{view['name']} ({view['global_id']}), {view['bio'].get('nationality')}, age {view['bio'].get('age')}")
    for c in view["career"]:
        print(f"  {c['competition']} ({c['country']}, {c['tier']}/{c['age_group']}/{c['gender']}): {c['club']} "
              f"#{c['kit_number']} {c['position']}, {c['appearances']} apps, {c['minutes']} min")
    for row in view["rows"]:
        print(f"  [{row['competition_id']}, scope {scope}]")
        for key in DEFAULT_COLUMNS.get(row["position"], DEFAULT_COLUMNS[None]):
            c = row["metrics"][key]
            p = c["pool"]
            print(f"    {CATALOGUE[key].label:36s} {c['value']!s:>8}  pct {c['percentile']!s:>4}  pool {p['size']}"
                  f"{' small' if p['small'] else ''}{' noisy' if c['noisy'] else ''}")
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
    r = sub.add_parser("reliability")
    r.add_argument("--repeats", type=int, default=None)
    r.add_argument("--workers", type=int, default=None)
    r.add_argument("--out", default=None)
    r.add_argument("--aggregates", default=None)
    r.add_argument("--realism", default=None)
    lv = sub.add_parser("levels")
    lv.add_argument("--scope", default="level", choices=("level", "competition", "all"))
    pl = sub.add_parser("player")
    pl.add_argument("id")
    pl.add_argument("--scope", default="level", choices=("level", "competition", "all"))
    args = ap.parse_args(argv)
    if args.cmd == "reliability":
        from regista.catalogue.measure import DEFAULT_REPEATS

        return _reliability(args.repeats or DEFAULT_REPEATS, args.workers, args.out, args.aggregates, args.realism)
    if args.cmd == "levels":
        return _levels(args.scope)
    if args.cmd == "player":
        return _player(args.id, args.scope)
    if args.cmd == "define":
        return _define(args.check)
    if args.cmd == "build":
        return _build(args.workers)
    if args.cmd == "check":
        return _check(args.workers)
    return _competitions()


if __name__ == "__main__":
    sys.exit(main())
