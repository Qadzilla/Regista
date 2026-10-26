"""The catalogue's engine (docs/catalogue/build/design.md §7 and §11, item 8; docs/catalogue/build/engine.md): the same 127
metrics in every competition, percentiles drawn from peers at the same level, careers kept per competition, similar
players within and across levels, team style per competition, reliability and realism per level, and never a hidden
rating.

Every test reads the committed catalogue and the Regista League as the app builds them (``data/season/matches`` and
``data/catalogue/matches``, git-ignored, built once). Nothing here reaches Azure or writes anywhere else.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from regista.catalogue import reliability as cat_rel
from regista.catalogue import store
from regista.catalogue.metrics import (ALL_WARNING, FLOOR, MIN_POOL, SMALL_POOL, CatalogueMetrics, build_catalogue_metrics)
from regista.catalogue.realism import BANDS, ORDERS, band_checks, order_checks, realism
from regista.catalogue.taxonomy import BY_ID, COMPETITIONS, ENGLAND_ID
from regista.season.league import ATTRIBUTE_KEYS, load_league
from regista.season.metrics import (CATALOGUE, TEAM_CATALOGUE, fbref_percentile, load_metrics,
                                    qualifying_minutes, rank_value)

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "data" / "catalogue" / "catalogue.json"
MATCHES = ROOT / "data" / "catalogue" / "matches"
LEAGUE = ROOT / "data" / "season" / "league.json"
SEASON_ROOT = ROOT / "data" / "season" / "matches"
HIDDEN = set(ATTRIBUTE_KEYS) | {"attributes", "skill_offset", "stamina_offset", "speed_mult", "accel_mult", "height_shift",
                                "execution", "style_offset", "level_scale"}
STAR = "pl_bro_09"
GER = "co_ger_sp_men"


@pytest.fixture(scope="module")
def england():
    return load_metrics(LEAGUE, SEASON_ROOT)


@pytest.fixture(scope="module")
def cm(england) -> CatalogueMetrics:
    return build_catalogue_metrics(INDEX, MATCHES, LEAGUE, SEASON_ROOT, england=england)


def _hidden(obj, path="$"):
    found = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in HIDDEN:
                found.append(f"{path}.{k}")
            found += _hidden(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            found += _hidden(v, f"{path}[{i}]")
    return found


# ---------------------------------------------------------------------------- England stays what it is

def test_england_is_the_league_engine_itself(cm, england):
    assert cm.metrics[ENGLAND_ID] is england
    assert england.min_pool == 2 and england.min_minutes_floor == 0.0


def test_englands_competition_scope_is_todays_numbers_for_every_player_and_metric(cm, england):
    """Where the pool is the competition, every cell the existing endpoints serve is unchanged, field for field."""
    moved = []
    for gid, ps in england.players.items():
        for key in CATALOGUE:
            want = england.cell(ps, key)
            got = cm.cell(ENGLAND_ID, gid, key, "competition")
            if {k: got[k] for k in want} != want:
                moved.append((gid, key))
            assert got["pool"]["size"] == want["peers"] and got["pool"]["min_size"] == 2
    assert not moved, moved[:5]


def test_englands_competition_scope_similar_is_the_existing_one(cm, england):
    want = england.similar(STAR, 5)
    got = cm.similar(ENGLAND_ID, STAR, "competition", 5)
    assert [(r["global_id"], r["similarity"]) for r in got["similar"]] == [(r["global_id"], r["similarity"]) for r in want["similar"]]
    assert got["z"] == want["z"] and got["pool"] == want["pool"]


def test_default_arguments_reproduce_the_league(england):
    """from_streams' and Season.build's new keyword arguments default to the league's rules."""
    from regista.season.profiles import Season

    league = load_league(LEAGUE)
    assert england.min_minutes == qualifying_minutes(max(t["totals"].get("minutes", 0.0) for t in england.teams.values()))
    s = Season.build({**league, "fixtures": league["fixtures"][:3]}, SEASON_ROOT)
    assert s.min_minutes == qualifying_minutes(30.0) and s._min_pool == 2 and s._min_minutes_floor == 0.0


# ---------------------------------------------------------------------------- the other competitions

def test_every_competition_has_its_engine_with_the_catalogue_rules(cm, england):
    assert cm.order == [c.competition_id for c in COMPETITIONS]
    for cid, sm in cm.metrics.items():
        if cid == ENGLAND_ID:
            continue
        club_minutes = max((t["totals"].get("minutes", 0.0) for t in sm.teams.values()), default=0.0)
        assert sm.min_minutes == max(FLOOR, qualifying_minutes(club_minutes)), cid
        assert sm.min_pool == MIN_POOL and sm.xt is england.xt, cid   # England's fitted grid, not one fitted on 3-8 matches
        assert len(sm.match_rows) == len(cm.comps[cid]["fixtures"])


def test_a_club_with_one_upload_leaves_its_players_unqualified(cm):
    """The 45-minute floor: one 30-minute match is not enough footage for a percentile."""
    seen = 0
    for cid in cm.order[1:]:
        sm = cm.metrics[cid]
        for ps in sm.players.values():
            club_matches = cm.sample(cid, ps)["club_matches"]
            if club_matches == 1:
                seen += 1
                assert ps.minutes < FLOOR and all(ps.percentiles.get(k) is None for k in CATALOGUE)
    assert seen > 0


# ---------------------------------------------------------------------------- pools

def test_a_level_pool_is_the_union_of_its_competitions_qualified_rows(cm):
    for key in ("npxg", "pass_pct", "tkl_int_padj", "distance"):
        for pos in CATALOGUE[key].positions:
            want = []
            for cid in (ENGLAND_ID, GER):
                sm = cm.metrics[cid]
                want += [rank_value(ps.values[key]) for ps in sm.players.values()
                         if ps.info["position"] == pos and sm.qualified(ps, CATALOGUE[key])]
            assert cm.pool_values(GER, key, pos, "level") == sorted(want) == cm.pool_values(ENGLAND_ID, key, pos, "level")


def test_level_percentiles_follow_fbrefs_rule_by_hand(cm):
    ps = cm.row(ENGLAND_ID, STAR)
    for key in ("npxg", "np_goals", "touches_in_box"):
        vals = cm.pool_values(ENGLAND_ID, key, "FW", "level")
        v = rank_value(ps.values[key])
        below, at = sum(1 for x in vals if x < v), sum(1 for x in vals if x <= v)
        assert cm.percentile(ENGLAND_ID, ps, key, "level") == round(50.0 * (below + at) / len(vals))
    # lower is better: inverted
    key = "dribbled_past"
    assert CATALOGUE[key].higher_is_better is False
    for cid in (ENGLAND_ID, GER):
        for ps in cm.metrics[cid].players.values():
            pct = cm.percentile(cid, ps, key, "level")
            if pct is not None:
                vals = cm.pool_values(cid, key, ps.info["position"], "level")
                assert pct == round(100.0 - fbref_percentile(vals, rank_value(ps.values[key])))
                break


def test_small_and_too_small_pools_say_so(cm):
    found_null = found_small = False
    for cid in cm.order:
        for ps in cm.metrics[cid].players.values():
            for key in ("save_pct", "npxg"):
                c = cm.cell(cid, ps.info["global_id"], key, "level")
                p = c["pool"]
                assert p["small"] == (p["size"] < SMALL_POOL) and p["min_size"] == MIN_POOL
                if ps.info["position"] not in CATALOGUE[key].positions:
                    assert c["percentile"] is None and p["reason"] == "not ranked for this position"
                elif p["size"] < MIN_POOL:
                    assert c["percentile"] is None and p["reason"] == f"fewer than {MIN_POOL} qualified peers"
                    found_null = True
                elif p["small"]:
                    found_small = True
    assert found_null and found_small


def test_scope_all_pools_every_level_of_one_gender_and_warns(cm):
    women = cm.scope_competitions("co_eng_sp_women", "all")
    men = cm.scope_competitions(ENGLAND_ID, "all")
    assert set(women) == {"co_eng_sp_women", "co_usa_col_women"}
    assert not set(women) & set(men) and len(men) == 12
    assert all(cm.labels[c]["gender"] == "men" for c in men)
    p = cm.pool(ENGLAND_ID, "npxg", "FW", "all")
    assert p["tier"] is None and p["age_group"] is None and p["gender"] == "men"
    assert cm.player(STAR, scope="all")["warning"] == ALL_WARNING


def test_a_level_with_one_competition_has_the_same_numbers_in_both_scopes(cm):
    """Ghana U17 is the only U17 competition: level scope is its competition scope, cell for cell."""
    cid = "co_gha_u17"
    assert cm.scope_competitions(cid, "level") == [cid]
    for gid in cm.metrics[cid].players:
        for key in CATALOGUE:
            a, b = cm.cell(cid, gid, key, "level"), cm.cell(cid, gid, key, "competition")
            assert a["percentile"] == b["percentile"] and a["pool"]["size"] == b["pool"]["size"], (gid, key)


def test_every_cell_carries_its_pool_and_sample(cm):
    for cid in cm.order:
        for gid in list(cm.metrics[cid].players)[:4]:
            for key in CATALOGUE:
                c = cm.cell(cid, gid, key)
                assert set(c["pool"]) >= {"scope", "tier", "age_group", "gender", "position", "size", "small", "min_size",
                                          "competitions", "reason"}
                assert c["pool"]["scope"] == "level" and cid in c["pool"]["competitions"]
                assert c["sample"]["competition_id"] == cid and c["sample"]["qualifying_minutes"] >= (0 if cid == ENGLAND_ID else FLOOR)
                assert isinstance(c["evidence_total"], int) and isinstance(c["noisy"], bool)


def test_evidence_opens_catalogue_matches(cm):
    gid = "pl_sot_09"
    ev = cm.evidence("co_esp_am_men", gid, "shots")
    assert ev["total"] >= 1
    for item in ev["items"]:
        assert item["match_id"].startswith("cm_eam_") and item["link"].startswith("/?match=cm_eam_")
        if item.get("clip_id"):
            assert item["video_url"].startswith(f"/api/matches/{item['match_id']}/clips/")
    assert cm.cell("co_esp_am_men", gid, "shots")["evidence_total"] == ev["moments"]


# ---------------------------------------------------------------------------- careers

def test_careers_keep_one_row_per_competition_and_sum_only_what_adds(cm):
    careers = store.load_index(INDEX)["careers"]
    assert len(careers) == 5
    for car in careers:
        gid = car["global_id"]
        view = cm.player(gid)
        assert [c["competition_id"] for c in view["career"]] == car["competitions"]
        assert [r["competition_id"] for r in view["rows"]] == car["competitions"], "minutes in both competitions"
        assert all(c["season"] == "2026/27" and c["appearances"] > 0 for c in view["career"])
        a, b = (cm.row(c, gid) for c in car["competitions"])
        assert a is not b and a.minutes > 0 and b.minutes > 0
        ov = view["overall"]
        assert ov["minutes"] == round(a.minutes + b.minutes, 1) and ov["appearances"] == a.appearances + b.appearances
        assert ov["totals"]["np_goals"] == round(a.totals.get("np_goals", 0.0) + b.totals.get("np_goals", 0.0), 3)
        assert set(ov) == {"competitions", "competitions_played", "appearances", "minutes", "totals", "note"}
        for row in view["rows"]:   # each row reads its own level's pool
            lv = BY_ID[row["competition_id"]].level_key
            for c in row["metrics"].values():
                assert c["pool"]["tier"] + "/" + c["pool"]["age_group"] + "/" + c["pool"]["gender"] == lv
        dates = [d for c in view["career"] for d in (c["first_match"], c["last_match"])]
        assert all(dates)
        all_dates = [cm.metrics[c["competition_id"]].match_rows[r["match_idx"]]["date"]
                     for c in view["career"] for r in cm.row(c["competition_id"], gid).matches]
        assert len(all_dates) == len(set(all_dates)), "never two matches on one date"


def test_a_squad_member_who_never_played_still_has_a_career_entry(cm):
    for gid, entries in cm.people.items():
        cid = entries[0][0]
        if gid not in cm.metrics[cid].players:
            view = cm.player(gid)
            assert view["career"][0]["appearances"] == 0 and view["rows"] == [] and view["overall"]["minutes"] == 0
            return
    pytest.skip("every squad member played")


# ---------------------------------------------------------------------------- similar players

def test_similar_within_level_and_across_levels(cm):
    lv = cm.similar(ENGLAND_ID, STAR, "level", 5)
    assert lv["z_basis"] == "level" and len(lv["similar"]) == 5
    assert all(r["competition_id"] in (ENGLAND_ID, GER) and r["same_level"] for r in lv["similar"])
    allv = cm.similar(ENGLAND_ID, STAR, "all", 8)
    assert allv["warning"] == ALL_WARNING
    assert all(r["gender"] == "men" and r["position"] == "FW" and r["global_id"] != STAR for r in allv["similar"])
    assert any(not r["same_level"] for r in allv["similar"])
    sims = [r["similarity"] for r in allv["similar"]]
    assert sims == sorted(sims, reverse=True)
    # a career player's other row is never his own match
    car = cm.similar("co_esp_am_men", "pl_sot_09", "all", 20)
    assert all(r["global_id"] != "pl_sot_09" for r in car["similar"])


# ---------------------------------------------------------------------------- team style

def test_team_style_per_competition_with_its_level_rank(cm, england):
    base = england.team_style("cl_brookfield")
    got = cm.team_style(ENGLAND_ID, "cl_brookfield")
    for key in TEAM_CATALOGUE:
        assert {k: got["values"][key][k] for k in base["values"][key]} == base["values"][key]
        assert got["values"][key]["level_of"] >= base["values"][key]["of"]
    ghana = cm.team_style("co_gha_u17", "cl_rainforest")
    assert ghana["sample"]["small"] is True and ghana["matches"] == 1 and ghana["competition_id"] == "co_gha_u17"
    assert ghana["values"]["possession_pct"]["level_of"] == ghana["values"]["possession_pct"]["of"]


# ---------------------------------------------------------------------------- reliability and realism per level

def test_the_committed_level_reliability_is_current(cm):
    comps = store.new_competitions(INDEX)
    data = cat_rel.load(load_league(LEAGUE), comps, INDEX.with_name(cat_rel.FILE_NAME))
    assert "stale" not in data, data.get("stale")
    assert set(data["levels"]) == {c.level_key for c in COMPETITIONS}
    for level, lv in data["levels"].items():
        assert set(lv["metrics"]) == set(CATALOGUE)
        assert set(lv["competitions"]) == {c.competition_id for c in COMPETITIONS if c.level_key == level}
    assert cm.reliability is not None and "stale" not in cm.reliability


def test_noisy_reads_englands_table_in_competition_scope_and_the_level_table_elsewhere(cm, england):
    lv = cm.reliability["levels"]["semi_pro/senior/men"]["metrics"]
    for key in CATALOGUE:
        assert cm.noisy(ENGLAND_ID, key, "competition") == england.noisy(key)
        assert cm.noisy(ENGLAND_ID, key, "level") == bool(lv[key]["noisy"])
        assert cm.noisy(GER, key, "competition") == bool(lv[key]["noisy"])   # no per-competition table outside England
    d = cm.describe("npxg", GER)
    assert d["reliability"] == lv["npxg"] and d["reliability_source"] == "level semi_pro/senior/men"
    star = cm.metrics[ENGLAND_ID].players[STAR]   # England's competition scope keeps today's flag, whatever the minutes
    assert all(cm.cell(ENGLAND_ID, STAR, k, "competition")["noisy"] == england.noisy(k) for k in CATALOGUE)
    assert cm.cell(ENGLAND_ID, STAR, "npxg", "competition")["r_at_minutes"] is None and star.minutes > 200


def test_a_rows_noisy_flag_is_adjusted_to_its_own_minutes(cm):
    """Review B S4: the level's split-half r was measured on half-seasons; a row's flag adjusts it to the row's minutes
    with Spearman-Brown (r_k = k r / (1 + (k - 1) r), k = minutes / median half-season minutes) and is noisy below 0.3,
    so a short upload is flagged where half a season is not."""
    flipped = 0
    for cid in cm.order:
        if cid == ENGLAND_ID:
            continue
        lv = cm.reliability["levels"][cm.level[cid]]
        half = lv["median_half_minutes"]
        for gid, ps in cm.metrics[cid].players.items():
            if ps.minutes <= 0:
                continue
            for key in ("npxg", "pass_pct", "tackles_won", "distance"):
                r = lv["metrics"][key]["r"]
                cell = cm.cell(cid, gid, key, "level")
                if r is None:
                    continue
                k = ps.minutes / half
                want = r if r <= 0 else k * r / (1 + (k - 1) * r)
                assert cell["r_at_minutes"] == round(want, 3) and cell["noisy"] == (want < 0.3), (cid, gid, key)
                flipped += cell["noisy"] and not lv["metrics"][key]["noisy"]
    assert flipped > 0   # some short rows are noisy where the level's half-season flag is not
    assert cm.reliability_at(GER, "npxg", 0.0) is None


def test_womens_speed_zone_numbers_say_they_use_the_mens_thresholds(cm):
    """Review B S8: women's pools read the men's FIFA zones (20 and 25 km/h), so their zone numbers carry a note."""
    from regista.catalogue.realism import WOMEN_ZONE_NOTE, ZONE_KEYS

    for cid in ("co_eng_sp_women", "co_usa_col_women", GER):
        gid = next(iter(cm.metrics[cid].players))
        for key in ZONE_KEYS:
            cell = cm.cell(cid, gid, key, "level")
            assert cell.get("threshold_note") == (WOMEN_ZONE_NOTE if cid != GER else None)
            assert (cm.describe(key, cid)["realism"]["zone_note"] is not None) == (cid != GER)
        assert "threshold_note" not in cm.cell(cid, gid, "npxg", "level")


def test_youth_speed_zone_numbers_say_they_use_the_senior_thresholds(cm):
    """levels.md: youth match peaks sit near 27-29 km/h, so the men's senior 25 km/h zone says so in youth pools."""
    from regista.catalogue.realism import YOUTH_ZONE_NOTE, ZONE_KEYS

    for cid in ("co_gha_u17", "co_eng_u18", "co_esp_u19", "co_bra_u20"):
        gid = next(iter(cm.metrics[cid].players))
        for key in ZONE_KEYS:
            assert cm.cell(cid, gid, key, "level").get("threshold_note") == YOUTH_ZONE_NOTE
            assert cm.describe(key, cid)["realism"]["zone_note"] == YOUTH_ZONE_NOTE
        assert "threshold_note" not in cm.cell(cid, gid, "distance", "level")


def test_realism_claims_only_what_is_checked():
    eng = realism("pass_pct", ENGLAND_ID)
    assert eng["kind"] == "reference" and eng["tuned"] and "Premier-League-calibrated scale" in eng["note"]
    assert "overstate" in eng["note"] and "within their pools" in eng["note"]
    assert [o["id"] for o in eng["orders"]] == ["amateur_pass_pct", "women_pass_pct_semi_pro"]
    ger = realism("npxg", GER)
    assert ger["kind"] == "reference" and not ger["tuned"] and ger["premier_league_bands"]
    assert realism("pass_pct", "co_esp_am_men")["kind"] == "order"
    assert realism("peak_speed_mean", "co_gha_u17")["kind"] == "band"
    assert realism("peak_speed_mean", "co_gha_u17")["band"]["low"] == 24.9
    assert realism("npxg", "co_eng_u18")["kind"] == "none"
    assert realism("distance", "co_usa_col_women")["kind"] == "reference"
    for c in COMPETITIONS:   # Premier League bands never stand below senior semi-pro and college men
        r = realism("goals", c.competition_id)
        if c.level_key not in ("semi_pro/senior/men", "college/college/men"):
            assert r["premier_league_bands"] == []


def test_the_committed_realism_verdicts_are_current_and_served():
    """Review B M1: a served realism note says what was checked and what was measured, with the committed verdict, never
    the source's sentence as a fact. Since the level retune (docs/catalogue/build/levels.md) the U17 band, the amateur
    pass order and the women's ball-loss and pass-gap orders pass, each with its measured value in the note."""
    from regista.catalogue import realism as rea

    data = rea.load(INDEX.with_name(rea.FILE_NAME), load_league(LEAGUE), store.new_competitions(INDEX))
    assert "stale" not in data, data.get("stale")
    assert [b["id"] for b in data["bands"]] == [b["id"] for b in BANDS]
    assert [o["id"] for o in data["orders"]] == [o["id"] for o in ORDERS]
    assert all(c["verdict"] in ("pass", "fail", "not separated") for c in data["bands"] + data["orders"])
    u17 = realism("peak_speed_mean", "co_gha_u17", data)
    assert u17["kind"] == "band" and u17["verdict"] == "pass"
    assert u17["band"]["low"] <= u17["band"]["value"] <= u17["band"]["high"]
    assert "inside the band" in u17["note"] and "the source reports" in u17["note"]
    assert f"{u17['band']['value']:,.2f}" in u17["note"]
    amateur = realism("pass_pct", "co_esp_am_men", data)
    assert amateur["verdict"] == "pass" and "as reported" in amateur["note"]
    by = {o["id"]: o for o in data["orders"]}
    assert by["women_ball_losses_semi_pro"]["verdict"] == "pass" and by["women_ball_losses_semi_pro"]["steps"][0]["separated"]
    gap = by["women_pass_pct_semi_pro"]
    assert gap["verdict"] == "pass" and gap["gap"] == list(rea.WOMEN_PASS_GAP) and not gap["steps"][0]["outside_gap"]
    assert "inside the sourced gap of 5-11" in realism("pass_pct", "co_eng_sp_women", data)["note"]
    for o in data["orders"]:   # each step's verdict follows its margin, its noise and any sourced gap
        for st in o["steps"]:
            sep = abs(st["margin"]) >= rea.SEPARATION_SE * st["se"]
            assert st["separated"] == sep
            want = "not separated" if not sep else "pass" if st["margin"] > 0 else "fail"
            if st.get("outside_gap") and want == "pass":
                want = "fail"
            assert st["verdict"] == want
    for c in COMPETITIONS:   # no served note states a checked direction without its measured verdict
        for key in ("pass_pct", "ball_losses", "peak_speed_mean", "distance", "sprint_distance", "hi_distance"):
            r = realism(key, c.competition_id, data)
            for o in r["orders"]:
                assert o["verdict"] and o["values"]
            if r["kind"] in ("band", "order"):
                assert r["verdict"] and ("Measured" in r["note"])


def test_the_image_smoke_test_checks_the_realism_verdicts(tmp_path):
    from regista.cloud.smoke import catalogue_realism_checks

    [ok] = catalogue_realism_checks(INDEX)
    assert ok["ok"] and ok["checks"] == len(BANDS) + len(ORDERS)
    (tmp_path / "data" / "catalogue").mkdir(parents=True)
    fake = tmp_path / "data" / "catalogue" / "catalogue.json"
    fake.write_text(INDEX.read_text())
    [bad] = catalogue_realism_checks(fake)
    assert not bad["ok"]


def test_band_and_order_checks_read_level_aggregates():
    agg = {"academy/U17/men": {"peak_speed_mean": 26.0}, "amateur/senior/men": {"pass_pct": 80.0},
           "semi_pro/senior/men": {"pass_pct": 84.0}}
    b = {x["id"]: x for x in band_checks(agg)}
    assert b["u17_peak_speed_mean"]["verdict"] == "pass"
    o = {x["id"]: x for x in order_checks(agg)}
    assert o["amateur_pass_pct"]["verdict"] == "pass" and o["youth_distance"]["verdict"] is None
    agg["amateur/senior/men"]["pass_pct"] = 85.0
    assert {x["id"]: x for x in order_checks(agg)}["amateur_pass_pct"]["verdict"] == "fail"
    assert len(BANDS) == 1 and all(bool(o["sources"]) != (o.get("basis") == "assumed") for o in ORDERS)
    assert all(o["covers"]["sources"] and o["covers"]["span"] for o in ORDERS if o.get("basis") == "assumed")
    # with per-season values a small margin inside the noise is not separated
    per = {"amateur/senior/men": [{"pass_pct": v} for v in (83.0, 85.0, 87.0)],
           "semi_pro/senior/men": [{"pass_pct": v} for v in (83.5, 84.0, 84.5)]}
    agg["amateur/senior/men"]["pass_pct"] = 84.0 - 0.2
    o = {x["id"]: x for x in order_checks(agg, per)}["amateur_pass_pct"]
    assert o["verdict"] == "not separated" and o["steps"][0]["se"] > 0
    b = band_checks({"academy/U17/men": {"peak_speed_mean": 29.68}})[0]
    assert b["verdict"] == "fail" and b["outside_by"] == 0.98
    # a sourced gap: women's pass completion must sit 5-11 points below men's, not merely below
    for women, verdict in ((78.0, "fail"), (74.0, "pass"), (70.0, "pass"), (60.0, "fail")):
        o = {x["id"]: x for x in order_checks({"semi_pro/senior/women": {"pass_pct": women},
                                               "semi_pro/senior/men": {"pass_pct": 80.0}})}["women_pass_pct_semi_pro"]
        assert o["verdict"] == verdict and o["steps"][0]["outside_gap"] == (verdict == "fail"), (women, o)


# ---------------------------------------------------------------------------- privacy and pools at a glance

def test_no_hidden_rating_or_scale_in_anything_the_engine_returns(cm):
    out = [cm.pool_sizes(s) for s in ("level", "competition", "all")]
    for cid in cm.order:
        gid = next(iter(cm.metrics[cid].players))
        out += [cm.player(gid, scope=s) for s in ("level", "competition", "all")]
        out += [cm.similar(cid, gid, s, 3) for s in ("level", "competition", "all")]
        out.append(cm.team_style(cid, next(iter(cm.metrics[cid].teams))))
        out.append(cm.describe("npxg", cid))
        out.append(cm.card(cid, cm.metrics[cid].players[gid]))
    for car in store.load_index(INDEX)["careers"]:
        out.append(cm.player(car["global_id"], metrics=list(CATALOGUE)))
    bad = _hidden(out)
    assert not bad, bad[:5]


def test_pool_sizes_cover_every_level_and_position(cm):
    rows = cm.pool_sizes("level")
    assert {r["label"] for r in rows} == {c.level_key for c in COMPETITIONS}
    semi = next(r for r in rows if r["label"] == "semi_pro/senior/men")
    assert semi["competitions"] == [ENGLAND_ID, GER]
    eng_fw = sum(1 for ps in cm.metrics[ENGLAND_ID].players.values()
                 if ps.info["position"] == "FW" and ps.minutes >= cm.metrics[ENGLAND_ID].min_minutes)
    assert semi["positions"]["FW"]["size"] > eng_fw


def test_select_filters_rows_across_the_catalogue(cm):
    rows = cm.select(tier="academy", position="FW")
    assert rows and all(cm.labels[c]["tier"] == "academy" and ps.info["position"] == "FW" for c, ps in rows)
    assert all(ps.minutes >= cm.metrics[c].min_minutes for c, ps in rows)
    car = cm.select(career=True, min_minutes=0)
    assert {ps.info["global_id"] for _c, ps in car} == {c["global_id"] for c in store.load_index(INDEX)["careers"]}
    phone = cm.select(camera="phone", min_minutes=0)
    assert phone and all(any((cm.uploads[r["match_id"]])["camera"] == "phone" for r in ps.matches) for _c, ps in phone)
    ranked = cm.sort(cm.select(gender="men", position="FW"), "npxg")
    assert ranked[0][1].values["npxg"] >= ranked[-1][1].values.get("npxg") or ranked[-1][1].values.get("npxg") is None


def test_catalogue_profiles_give_moments_across_competitions_and_results_of_uploads():
    from regista.catalogue.profiles import RESULTS_NOTE, build_catalogue_profiles

    cp = build_catalogue_profiles(INDEX, MATCHES, LEAGUE, SEASON_ROOT)
    ms = cp.moments("pl_sot_09")
    assert ms and {m["competition_id"] for m in ms} == {"co_esp_u19", "co_esp_am_men"}
    w = [m["watchability"] for m in ms]
    assert w == sorted(w, reverse=True)
    rows, note = cp.results("co_gha_u17")
    assert note == RESULTS_NOTE and sum(r["played"] for r in rows) == 2 * len(cp.seasons["co_gha_u17"].matches)
    table, note = cp.results(ENGLAND_ID)
    assert note is None and table[0]["position"] == 1
    assert all(m["camera"] and m["uploader"] for cid in cp.order for m in cp.matches(cid))
    assert cp.seasons["co_gha_u17"].min_minutes == FLOOR


# ---------------------------------------------------------------------------- measurement seasons

def test_measurement_seasons_are_full_round_robins_on_their_own_seeds():
    from regista.catalogue.define import round_robin
    from regista.catalogue.measure import MEASURE_OFFSET, full_fixtures, halves, measurement_league

    committed = {fx["seed"] for fx in load_league(LEAGUE)["fixtures"]}
    committed |= {fx["seed"] for c in store.new_competitions(INDEX) for fx in c["fixtures"]}
    seen: set[int] = set()
    for comp in [load_league(LEAGUE), *store.new_competitions(INDEX)]:
        full = full_fixtures(comp)
        n = len(comp["clubs"])
        assert len(full) == sum(len(r) for r in round_robin(n))
        pairs = {(f["home"], f["away"]) for f in full}
        assert len(pairs) == n * (n - 1), "every ordered pair once"
        first, second = halves(full)
        assert not first & second and len(first) == len(second)
        for k in range(2):
            seeds = [f["seed"] for f in measurement_league(comp, k)["fixtures"]]
            assert min(seeds) > MEASURE_OFFSET and not set(seeds) & committed and not set(seeds) & seen
            seen |= set(seeds)


@pytest.mark.slow
def test_a_levels_reliability_reproduces():
    """The per-level table is deterministic: re-measuring the U17 level (Ghana, six full seasons) gives the committed
    numbers. The whole file takes a few minutes (python -m regista.catalogue reliability)."""
    import json

    from regista.catalogue.measure import measure

    data = json.loads(INDEX.with_name(cat_rel.FILE_NAME).read_text())
    comps = [c for c in store.new_competitions(INDEX) if c["competition"]["competition_id"] == "co_gha_u17"]
    results = measure(comps, data["seasons"], load_metrics(LEAGUE, SEASON_ROOT).xt)
    again = json.loads(json.dumps(cat_rel.table(results), sort_keys=True))
    assert again["academy/U17/men"] == data["levels"]["academy/U17/men"]
    # ... and the same seasons give the committed U17 band verdict (data/catalogue/realism.json)
    from regista.catalogue import realism as rea
    from regista.catalogue.measure import level_aggregates

    committed = json.loads(INDEX.with_name(rea.FILE_NAME).read_text())
    agg = json.loads(json.dumps(level_aggregates(results), sort_keys=True))
    assert agg["academy/U17/men"] == committed["levels"]["academy/U17/men"]
    band = rea.band_checks(agg)[0]
    assert {k: band[k] for k in ("value", "outside_by", "verdict")} == \
        {k: committed["bands"][0][k] for k in ("value", "outside_by", "verdict")}


def test_the_image_smoke_test_checks_the_level_reliability(tmp_path):
    from regista.cloud.smoke import catalogue_reliability_checks

    [ok] = catalogue_reliability_checks(INDEX)
    assert ok["ok"] and len(ok["levels"]) == 9
    (tmp_path / "data" / "catalogue").mkdir(parents=True)
    fake = tmp_path / "data" / "catalogue" / "catalogue.json"
    fake.write_text(INDEX.read_text())
    [bad] = catalogue_reliability_checks(fake)   # no reliability.json beside it, no competition files: reported, not raised
    assert not bad["ok"]


def test_youth_orders_claim_only_the_span_their_sources_cover():
    """Review B round 2 #3: [S8] covers U13-U18 and [S5, S6] U13-U17, so only the U17 to U18 distance step is sourced; the
    steps beyond are assumed orders worded "no published band", the youth speed steps hold by construction, and an
    assumed order never makes a metric's kind "order"."""
    from regista.catalogue import realism as rea

    by = {o["id"]: o for o in ORDERS}
    assert by["youth_distance"]["levels"] == ["academy/U17/men", "academy/U18/men"] and by["youth_distance"]["sources"]
    ext, speed = by["youth_distance_extension"], by["youth_peak_speed_mean"]
    assert ext["basis"] == speed["basis"] == "assumed" and not ext["sources"] and not speed["sources"]
    assert speed["construction"] and "construction" not in ext
    for o in ORDERS:   # a sourced order never names a youth level its sources do not cover
        if o.get("basis") != "assumed" and o["metric"] in ("distance", "peak_speed_mean"):
            assert not {"academy/U19/men", "academy/U20/men"} & set(o["levels"])
    data = rea.load(INDEX.with_name(rea.FILE_NAME))
    for cid in ("co_eng_u18", "co_esp_u19", "co_bra_u20", "co_gha_u17"):
        for key in ("distance", "peak_speed_mean"):
            r = realism(key, cid, data)
            assert "U19 < U20 < senior: the source reports" not in r["note"]
            for o in r["assumed_orders"]:
                assert o["basis"] == "assumed" and o["verdict"] and o["values"]
            if r["assumed_orders"]:
                assert "Assumed order, no published band" in r["note"]
            if key == "peak_speed_mean" and r["assumed_orders"]:
                assert "By construction" in r["note"] and r["assumed_orders"][0]["by_construction"]
            assert all(o["basis"] == "sourced" for o in r["orders"])
            notes = r["note"].split("Assumed order")[0]
            assert "U19" not in notes and "U20" not in notes      # nothing sourced is said about U19, U20 or beyond
    assert realism("peak_speed_mean", "co_esp_u19", data)["kind"] == "none"
    assert realism("distance", "co_esp_u19", data)["kind"] == "none"
    assert realism("distance", "co_eng_u18", data)["kind"] == "order"
    assert rea.level_kinds("academy/U19/men")["orders"] == [] and rea.level_kinds("academy/U19/men")["assumed_orders"]


def test_the_committed_realism_verdicts_match_their_own_aggregates():
    """``recheck`` re-runs every check on the committed file's stored aggregates: the committed verdicts are what the
    checks say about them (so a wording or span change is re-stamped, never hand-edited)."""
    import json

    from regista.catalogue import realism as rea

    data = json.loads(INDEX.with_name(rea.FILE_NAME).read_text())
    again = rea.recheck(data)
    assert again["bands"] == data["bands"] and again["orders"] == data["orders"]
