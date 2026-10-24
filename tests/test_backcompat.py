"""Back-compat: ``generate()`` without player attributes writes exactly what ``main`` wrote.

Player attributes (``regista.season.league``) are allowed to change the league's matches, and only those. Everything that
calls the generator without them must not move a byte: the committed samples (syn_0294, syn_0141, syn_0142), the vision
layer's development seeds (201-206) and its untouched fresh set (301-303), and both tuning profiles. Each case below writes
its events and tracks as ``regista.schema.write_jsonl`` would and compares their SHA-256 with the hash recorded on
``main`` (e3da71d, 2026-10-23, from a detached worktree; ``python tests/test_backcompat.py --record`` prints them).

A case's ``teams`` carry squads with ``global_id`` and ``name`` only (what ``generate_kwargs`` passed on ``main``), and the
league's generator settings as they were on ``main`` (profile "realistic"), so the league-shaped case keeps testing the
no-attributes path after the league file gained ratings and the "league" profile.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]

# Team strings as in regista.vision.dataset (TEST_SPECS / FRESH_SPECS) and the CLAUDE.md demo seed command.
EAS, WES = "Eastbury Rovers,EAS,#00A650,#FFFFFF,#F97316", "Westfield Town,WES,#6A0DAD,#FFFFFF,#FDE047"
COR, LAK = "Corrin,COR,#DC2626,#FFFFFF,#22D3EE", "Lakeside,LAK,#2563EB,#FFFFFF,#A3E635"
HRT, PEN = "Hartwell,HRT,#1717E6,#FFFFFF,#F28D61", "Penrose,PEN,#B28F59,#000000,#55E617"

# case -> (sha256 of events.jsonl, sha256 of tracks.jsonl), recorded on main e3da71d; the kwargs are in cases()
EXPECTED: dict[str, tuple[str, str]] = {
    "sample_syn_0294": ("cb30071d95f55147f3a6ecd73c355f23313a5f48c1e37f955279ac3bd03f3833",
                        "a499d7183af4ac0362bf6fe89d5ccb0ad72bc4563396462b576a4614a8c3d81d"),
    "library_syn_0141": ("ba171e068244b6cf571deef64511004e14cf4deb746ce74ffb150d52584ae04e",
                         "bb195010158e5120d7dd390b49fd402cc9ebab503b1d4495d42e9e148d35867e"),
    "library_syn_0142": ("df0f7c87808f3a25747deaf99eecffb2c17e2182447fe19160de38ee329c043c",
                         "55a7845118a5b9d4499d6422fc04bbe426f92b1f30d5ef47dad8cff894cddc31"),
    "vision_dev_201": ("b5ffbf9d0c2ee77c978b43e92495099d5fff42559cfd121681ad97c45e9e3ee4",
                       "cad6e8bcfc9c3fe0408922733074a5086dd49b08b8125358af8b6e36504aef92"),
    "vision_dev_202": ("84917ef04f69a8798998d73bf134f39ee23b499e6122097f138ccf9f8e53d94a",
                       "5cfefb8ac08de861302479cf97e4cf98a68d2de72665e70dcc8d8ca2a8898fc5"),
    "vision_fresh_301": ("c88bde64fd390ebb5ff92c8d9c390013b8b8ed80d470e0a585f8cde4f667c2ae",
                         "7380ab5bde0a51bd639e24d5f605b7696460931e13815a38215373bbd30b9719"),
    "realistic_77": ("9e129a08ad82fa8b67b93fd80382c579c890f19e143a2bcfac62b0aacccc06c4",
                     "aa2c24b7b9ad1f489c67be14b189a49086b4142e873a40e64c3132f5778265e9"),
    "league_squads_r01": ("44b86bda22d3c87d575153402367f33056ed7eb3a454a4401b04b9fd8982e88e",
                          "fab2ef2c0e380ff7c4eb5d29fad97598429e859d864a5d31df792a0ca3437652"),
}


def cases(league_path: Path | str = ROOT / "data" / "season" / "league.json") -> dict[str, dict[str, Any]]:
    from regista.synth.generator import parse_team_arg

    def teams(home: str, away: str) -> list[dict[str, Any]]:
        return [parse_team_arg(home), parse_team_arg(away)]

    league = json.loads(Path(league_path).read_text())
    fx = league["fixtures"][0]
    clubs = {c["club_id"]: c for c in league["clubs"]}

    def side(cid: str) -> dict[str, Any]:
        c = clubs[cid]
        return {"name": c["name"], "short_name": c["short_name"], "kit": c["kit"], "club_id": c["club_id"],
                "squad": [{"global_id": p["global_id"], "name": p["name"]} for p in c["squad"]]}

    g = {"minutes": 15.0, "periods": 2, "track_hz": 1.0, "profile": "realistic"}  # the league's settings on main
    return {
        "sample_syn_0294": dict(seed=294, minutes=3.0, track_hz=1.0, profile="demo"),
        "library_syn_0141": dict(seed=141, minutes=3.0, track_hz=1.0, profile="demo"),
        "library_syn_0142": dict(seed=142, minutes=3.0, track_hz=1.0, profile="demo"),
        "vision_dev_201": dict(seed=201, minutes=5.0, track_hz=2.0, teams=teams(EAS, WES)),
        "vision_dev_202": dict(seed=202, minutes=2.5, periods=2, track_hz=2.0, teams=teams(COR, LAK)),
        "vision_fresh_301": dict(seed=301, minutes=5.0, track_hz=2.0, teams=teams(HRT, PEN)),
        "realistic_77": dict(seed=77, minutes=10.0, periods=2, track_hz=1.0, profile="realistic", teams=teams(EAS, WES)),
        "league_squads_r01": dict(seed=fx["seed"], minutes=g["minutes"], periods=g["periods"], track_hz=g["track_hz"],
                                  profile=g["profile"], teams=[side(fx["home"]), side(fx["away"])], match_id=fx["match_id"]),
    }


def _sha(records: list[dict[str, Any]]) -> str:
    h = hashlib.sha256()
    for rec in records:  # byte for byte what regista.schema.write_jsonl writes
        h.update(json.dumps(rec, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
        h.update(b"\n")
    return h.hexdigest()


def digest(kwargs: dict[str, Any]) -> tuple[str, str]:
    from regista.synth.generator import generate

    result = generate(**kwargs)
    return _sha(result.stream), _sha(result.tracks)


@pytest.mark.parametrize("name", list(EXPECTED))
def test_generate_without_attributes_matches_main(name):
    assert digest(cases()[name]) == EXPECTED[name], f"{name}: events or tracks differ from main"


def test_the_committed_sample_is_still_what_the_generator_writes():
    # The committed syn_0294 files themselves, not only a recorded hash.
    events, tracks = digest(cases()["sample_syn_0294"])
    d = ROOT / "data" / "synthetic" / "sample" / "syn_0294"
    assert hashlib.sha256((d / "events.jsonl").read_bytes()).hexdigest() == events
    assert hashlib.sha256((d / "tracks.jsonl").read_bytes()).hexdigest() == tracks


if __name__ == "__main__" and "--record" in sys.argv:
    league = sys.argv[sys.argv.index("--record") + 1] if len(sys.argv) > sys.argv.index("--record") + 1 else None
    for n, kw in cases(*( [league] if league else [])).items():
        print(f"    {n!r}: {digest(kw)!r},")
