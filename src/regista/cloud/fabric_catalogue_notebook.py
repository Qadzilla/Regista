"""The second Fabric notebook: the catalogue's numbers, recomputed in Spark SQL from the raw catalogue tables alone.

It reads ``catalogue_competitions``, ``catalogue_players``, ``catalogue_matches``, ``catalogue_lineups``,
``catalogue_events`` and ``catalogue_possessions`` and works out, for every player-competition row, the appearances,
minutes, counts and per-90 rates of the checked stats, then each rate's percentile in its **level pool** by the
catalogue's rule (``regista.catalogue.metrics``), written again here:

- **appearances**: a starter, or a player who came on (a ``substitution`` event's ``related_player_id``), in a squad of
  that competition; **minutes**: the sum of their lineups' ``played_s`` / 60.
- **qualifying minutes, per competition**: a third of the minutes of the competition's busiest club (a club's minutes are
  the sum of its matches' ``played_s`` / 60), rounded to 0.1. England (the Regista League, ``source = 'league'``) keeps
  exactly that; every other competition needs at least 45 (one and a half 30-minute matches).
- **level pools**: the qualified rows of one position over every competition of the same tier, age group and gender
  (England and Germany semi-pro men share one), each row qualified under its own competition's rule.
- **percentile**: FBref's, 50 * (rows strictly below + rows at or below) / n on the unrounded rate (6 decimals), half to
  even; none from a pool of fewer than 5 rows, and none for a count of 0 (the catalogue's "none yet": the row stays in
  its pool, but gets no percentile).

It writes one row per (competition, player, stat) to ``catalogue_leaders_check``; ``python -m regista.season.fabric
check --catalogue`` reads that back and compares it with ``catalogue_player_season``, the numbers the catalogue pages show.

**Where the catalogue engine's stats differ from the league check's** (``regista.cloud.fabric_notebook``, which follows
the profiles, ``regista.season.profiles``): the catalogue pages use the Terminal's engine (``regista.season.metrics``),
so here **shots** leave penalties out (FBref Sh), **key passes** are FBref's (the completed pass, by a teammate of the
shooter, that the shooter received at the start of the possession he took a non-penalty shot from: the last such pass
between the previous possession record and the shot's own, in stream order), and a **tackle** with no outcome counts as
won. Goals, assists, take-ons won and interceptions are the same tests. The SQL matches the engine; the engine is not
changed.

Nothing here reuses ``regista.catalogue`` or ``regista.season``: ``catalogue_leaders_rule`` below is the same SQL step by
step in plain Python over the same tables, and a test compares it with Regista's rows offline, for every row.
"""

from __future__ import annotations

import base64
import json
from typing import Any

from regista.cloud.fabric import CATALOGUE_CHECK_STATS, ONELAKE_HOST

ENGLAND_SOURCE = "league"   # catalogue_competitions.source of the Regista League (England semi-pro men)
FLOOR_MINUTES = 45.0        # qualifying minutes are at least this outside England
MIN_POOL = 5                # no percentile from fewer qualified peers (level scope)
OUTFIELD = ("DF", "MF", "FW")
# stat -> the positions it is ranked for (keepers are not ranked on any of these; their pool size is 0)
STAT_POSITIONS: dict[str, tuple[str, ...]] = {s: OUTFIELD for s in ("goals", "assists", "shots", "key_passes",
                                                                    "take_ons_won", "tackles_won", "interceptions")}
# stat -> which events count (key passes come from their own view, cat_key_passes)
STAT_SQL: dict[str, str] = {
    "goals": "event_type = 'goal'",
    "assists": "event_type = 'assist'",
    "shots": "event_type = 'shot' AND NOT array_contains(qualifiers, 'penalty')",
    "take_ons_won": "event_type = 'take_on' AND outcome = 'success'",
    "tackles_won": "event_type = 'tackle' AND COALESCE(outcome, 'success') = 'success'",
    "interceptions": "event_type = 'interception'",
}
KEY_PASSES = "key_passes"

APPEARED_SQL = """
CREATE OR REPLACE TEMP VIEW cat_came_on AS
SELECT DISTINCT match_id, related_player_id AS player_id
FROM catalogue_events
WHERE event_type = 'substitution' AND player_id IS NOT NULL AND related_player_id IS NOT NULL
"""

APPEARANCES_SQL = """
CREATE OR REPLACE TEMP VIEW cat_appeared AS
SELECT l.competition_id, l.match_id, l.player_id, l.global_id, l.played_s
FROM catalogue_lineups l
JOIN catalogue_players p ON p.competition_id = l.competition_id AND p.global_id = l.global_id
LEFT JOIN cat_came_on o ON o.match_id = l.match_id AND o.player_id = l.player_id
WHERE l.starter OR o.player_id IS NOT NULL
"""

PLAYED_SQL = """
CREATE OR REPLACE TEMP VIEW cat_played AS
SELECT competition_id, global_id, COUNT(*) AS appearances, SUM(played_s / 60.0D) AS minutes_raw
FROM cat_appeared
GROUP BY competition_id, global_id
"""

KEY_PASSES_SQL = """
CREATE OR REPLACE TEMP VIEW cat_poss AS
SELECT match_id, possession_id, seq, gained_by, LAG(seq) OVER (PARTITION BY match_id ORDER BY seq) AS prev_seq
FROM catalogue_possessions
"""

KEY_PASS_EVENTS_SQL = """
CREATE OR REPLACE TEMP VIEW cat_key_passes AS
SELECT match_id, player_id FROM (
  SELECT e.match_id, e.player_id, ROW_NUMBER() OVER (PARTITION BY s.match_id, s.seq ORDER BY e.seq DESC) AS k
  FROM catalogue_events s
  JOIN cat_poss p ON p.match_id = s.match_id AND p.possession_id = s.possession_id AND p.gained_by = 'pass_received'
  JOIN catalogue_events e ON e.match_id = s.match_id AND e.seq < p.seq AND e.seq > COALESCE(p.prev_seq, -1)
    AND e.event_type IN ('pass', 'cross') AND e.outcome = 'success' AND e.team_id = s.team_id
    AND e.related_player_id = s.player_id
  WHERE s.event_type = 'shot' AND s.player_id IS NOT NULL AND NOT array_contains(s.qualifiers, 'penalty')
)
WHERE k = 1 AND player_id IS NOT NULL
"""


def tallies_sql(stats: list[str]) -> str:
    parts = [f"SELECT match_id, player_id, '{s}' AS stat FROM catalogue_events WHERE player_id IS NOT NULL AND ({STAT_SQL[s]})"
             for s in stats if s != KEY_PASSES]
    if KEY_PASSES in stats:
        parts.append(f"SELECT match_id, player_id, '{KEY_PASSES}' AS stat FROM cat_key_passes")
    union = "\n  UNION ALL\n  ".join(parts)
    return f"""
CREATE OR REPLACE TEMP VIEW cat_tallies AS
SELECT a.competition_id, a.global_id, x.stat, COUNT(*) AS n
FROM (
  {union}
) x
JOIN cat_appeared a ON a.match_id = x.match_id AND a.player_id = x.player_id
GROUP BY a.competition_id, a.global_id, x.stat
"""


def rates_sql(stats: list[str]) -> str:
    names = ", ".join(f"'{s}'" for s in stats)
    rateable = " OR ".join(f"(s.stat = '{s}' AND p.position IN ({', '.join(repr(x) for x in STAT_POSITIONS[s])}))"
                           for s in stats)
    return f"""
CREATE OR REPLACE TEMP VIEW cat_rates AS
SELECT pl.competition_id, pl.global_id, p.position, pl.appearances, pl.minutes_raw, s.stat,
  CAST(COALESCE(t.n, 0) AS INT) AS count, ({rateable}) AS rateable
FROM cat_played pl
JOIN catalogue_players p ON p.competition_id = pl.competition_id AND p.global_id = pl.global_id
CROSS JOIN (SELECT explode(array({names})) AS stat) s
LEFT JOIN cat_tallies t ON t.competition_id = pl.competition_id AND t.global_id = pl.global_id AND t.stat = s.stat
"""


QUALIFYING_SQL = f"""
CREATE OR REPLACE TEMP VIEW cat_qualifying AS
WITH club_minutes AS (
  SELECT competition_id, club_id, SUM(played_s / 60.0D) AS club_min
  FROM (SELECT competition_id, home_club_id AS club_id, played_s FROM catalogue_matches
        UNION ALL SELECT competition_id, away_club_id AS club_id, played_s FROM catalogue_matches)
  GROUP BY competition_id, club_id
)
SELECT c.competition_id, c.tier, c.age_group, c.gender,
  CASE WHEN c.source = '{ENGLAND_SOURCE}' THEN ROUND(MAX(m.club_min) / 3.0D, 1)
       ELSE GREATEST(ROUND(MAX(m.club_min) / 3.0D, 1), {FLOOR_MINUTES}D) END AS min_minutes
FROM catalogue_competitions c JOIN club_minutes m ON m.competition_id = c.competition_id
GROUP BY c.competition_id, c.tier, c.age_group, c.gender, c.source
"""

# The level pool: PARTITION BY tier, age group, gender (the level), position and stat, over the qualified, rateable rows.
LEADERS_SQL = f"""
WITH flagged AS (
  SELECT r.*, q.tier, q.age_group, q.gender, q.min_minutes, ROUND(r.minutes_raw, 1) AS minutes,
    CASE WHEN r.minutes_raw > 0 THEN ROUND(CAST(r.count AS DOUBLE) * 90.0D / r.minutes_raw, 2) END AS per90,
    CASE WHEN r.minutes_raw > 0 THEN ROUND(CAST(r.count AS DOUBLE) * 90.0D / r.minutes_raw, 6) END AS rank_value,
    (r.minutes_raw > 0 AND r.minutes_raw >= q.min_minutes) AS qualified
  FROM cat_rates r JOIN cat_qualifying q ON q.competition_id = r.competition_id
),
ranks AS (
  SELECT competition_id, global_id, stat,
    RANK() OVER (PARTITION BY tier, age_group, gender, position, stat ORDER BY rank_value) - 1 AS below,
    COUNT(*) OVER (PARTITION BY tier, age_group, gender, position, stat ORDER BY rank_value
                   RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS at_or_below,
    COUNT(*) OVER (PARTITION BY tier, age_group, gender, position, stat) AS n
  FROM flagged WHERE qualified AND rateable
),
pools AS (
  SELECT tier, age_group, gender, position, stat, COUNT(*) AS pool_size
  FROM flagged WHERE qualified AND rateable
  GROUP BY tier, age_group, gender, position, stat
)
SELECT f.competition_id, f.global_id, f.position, f.tier, f.age_group, f.gender, f.stat,
  CAST(f.appearances AS INT) AS appearances, f.minutes, f.min_minutes AS qualifying_minutes, f.count, f.per90, f.qualified,
  CAST(COALESCE(pl.pool_size, 0) AS INT) AS pool_size,
  CASE WHEN r.n >= {MIN_POOL} AND f.count > 0
       THEN CAST(BROUND(CAST(r.below + r.at_or_below AS DOUBLE) * 50.0D / r.n, 0) AS INT) END AS percentile,
  current_timestamp() AS computed_at
FROM flagged f
LEFT JOIN ranks r ON r.competition_id = f.competition_id AND r.global_id = f.global_id AND r.stat = f.stat
LEFT JOIN pools pl ON pl.tier = f.tier AND pl.age_group = f.age_group AND pl.gender = f.gender
  AND pl.position = f.position AND pl.stat = f.stat
ORDER BY f.stat, f.competition_id, f.per90 DESC, f.global_id
"""

TABLES = ["catalogue_competitions", "catalogue_players", "catalogue_matches", "catalogue_lineups", "catalogue_events",
          "catalogue_possessions"]


def statements(stats: list[str] | None = None) -> list[str]:
    stats = stats or CATALOGUE_CHECK_STATS
    return [APPEARED_SQL, APPEARANCES_SQL, PLAYED_SQL, KEY_PASSES_SQL, KEY_PASS_EVENTS_SQL, tallies_sql(stats),
            rates_sql(stats), QUALIFYING_SQL]


# ============================================================================ the same rule, in plain Python

EVENT_TESTS = {
    "goals": lambda e: e["event_type"] == "goal",
    "assists": lambda e: e["event_type"] == "assist",
    "shots": lambda e: e["event_type"] == "shot" and "penalty" not in (e["qualifiers"] or []),
    "take_ons_won": lambda e: e["event_type"] == "take_on" and e["outcome"] == "success",
    "tackles_won": lambda e: e["event_type"] == "tackle" and (e["outcome"] if e["outcome"] is not None else "success") == "success",
    "interceptions": lambda e: e["event_type"] == "interception",
}


def catalogue_leaders_rule(tables: dict[str, list[dict[str, Any]]], stats: list[str] | None = None) -> list[dict[str, Any]]:
    """The notebook's SQL, view by view, in plain Python over the same raw catalogue tables: one
    ``catalogue_leaders_check`` row per (competition, player, stat). It reuses nothing from ``regista.catalogue`` or
    ``regista.season``, so comparing it with ``catalogue_player_season`` checks the rule offline."""
    stats = stats or CATALOGUE_CHECK_STATS
    assert set(EVENT_TESTS) | {KEY_PASSES} == set(STAT_SQL) | {KEY_PASSES}
    events, lineups = tables["catalogue_events"], tables["catalogue_lineups"]
    squad = {(p["competition_id"], p["global_id"]): p for p in tables["catalogue_players"]}
    came_on = {(e["match_id"], e["related_player_id"]) for e in events                     # cat_came_on
               if e["event_type"] == "substitution" and e["player_id"] is not None and e["related_player_id"] is not None}
    appeared: dict[tuple[str, str], tuple[str, str]] = {}                                  # cat_appeared
    played: dict[tuple[str, str], list[float]] = {}                                        # cat_played
    for r in lineups:
        if (r["competition_id"], r["global_id"]) in squad and (r["starter"] or (r["match_id"], r["player_id"]) in came_on):
            appeared[(r["match_id"], r["player_id"])] = (r["competition_id"], r["global_id"])
            a = played.setdefault((r["competition_id"], r["global_id"]), [0, 0.0])
            a[0] += 1
            a[1] += r["played_s"] / 60.0
    credits: list[tuple[str, str, str]] = []                                               # the tallies' union
    for e in events:
        if e["player_id"] is not None:
            for s in stats:
                if s != KEY_PASSES and EVENT_TESTS[s](e):
                    credits.append((e["match_id"], e["player_id"], s))
    if KEY_PASSES in stats:                                                                # cat_poss, cat_key_passes
        poss_by_match: dict[str, list[dict[str, Any]]] = {}
        for p in tables["catalogue_possessions"]:
            poss_by_match.setdefault(p["match_id"], []).append(p)
        poss: dict[tuple[str, str], tuple[int, int | None, str | None]] = {}
        for mid, ps in poss_by_match.items():
            ps = sorted(ps, key=lambda p: p["seq"])
            for i, p in enumerate(ps):
                poss[(mid, p["possession_id"])] = (p["seq"], ps[i - 1]["seq"] if i else None, p["gained_by"])
        by_match: dict[str, list[dict[str, Any]]] = {}
        for e in events:
            by_match.setdefault(e["match_id"], []).append(e)
        for s in events:
            if s["event_type"] != "shot" or s["player_id"] is None or "penalty" in (s["qualifiers"] or []):
                continue
            hit = poss.get((s["match_id"], s["possession_id"]))
            if hit is None or hit[2] != "pass_received":
                continue
            p_seq, prev = hit[0], -1 if hit[1] is None else hit[1]
            cands = [e for e in by_match[s["match_id"]] if prev < e["seq"] < p_seq and e["event_type"] in ("pass", "cross")
                     and e["outcome"] == "success" and e["team_id"] == s["team_id"] and e["related_player_id"] == s["player_id"]]
            if cands:
                best = max(cands, key=lambda e: e["seq"])
                if best["player_id"] is not None:
                    credits.append((s["match_id"], best["player_id"], KEY_PASSES))
    tallies: dict[tuple[str, str, str], int] = {}                                          # cat_tallies
    for mid, pid, s in credits:
        who = appeared.get((mid, pid))
        if who:
            tallies[(*who, s)] = tallies.get((*who, s), 0) + 1
    comps = {c["competition_id"]: c for c in tables["catalogue_competitions"]}             # cat_qualifying
    club_min: dict[tuple[str, str], float] = {}
    for m in tables["catalogue_matches"]:
        for club in (m["home_club_id"], m["away_club_id"]):
            k = (m["competition_id"], club)
            club_min[k] = club_min.get(k, 0.0) + m["played_s"] / 60.0
    min_minutes: dict[str, float] = {}
    for cid, c in comps.items():
        top = [v for (c2, _club), v in club_min.items() if c2 == cid]
        if not top:
            continue
        third = round(max(top) / 3.0, 1)
        min_minutes[cid] = third if c["source"] == ENGLAND_SOURCE else max(third, FLOOR_MINUTES)
    rows = []                                                                              # cat_rates, flagged
    for (cid, gid), (apps, mins) in played.items():
        if cid not in min_minutes:
            continue
        c, pos = comps[cid], squad[(cid, gid)]["position"]
        for s in stats:
            n = tallies.get((cid, gid, s), 0)
            rows.append({"competition_id": cid, "global_id": gid, "position": pos, "tier": c["tier"],
                         "age_group": c["age_group"], "gender": c["gender"], "stat": s, "appearances": apps,
                         "minutes": round(mins, 1), "qualifying_minutes": min_minutes[cid], "count": n,
                         "per90": round(n * 90.0 / mins, 2) if mins > 0 else None,
                         "qualified": mins > 0 and mins >= min_minutes[cid], "pool_size": 0, "percentile": None,
                         "_value": round(n * 90.0 / mins, 6) if mins > 0 else None,
                         "_rateable": pos in STAT_POSITIONS[s]})
    pools: dict[tuple, list[dict[str, Any]]] = {}                                          # ranks, pools
    for r in rows:
        if r["qualified"] and r["_rateable"]:
            pools.setdefault((r["tier"], r["age_group"], r["gender"], r["position"], r["stat"]), []).append(r)
    for r in rows:
        r["pool_size"] = len(pools.get((r["tier"], r["age_group"], r["gender"], r["position"], r["stat"]), []))
    for group in pools.values():
        n = len(group)
        for r in group:
            below = sum(1 for o in group if o["_value"] < r["_value"])
            at_or_below = sum(1 for o in group if o["_value"] <= r["_value"])
            if n >= MIN_POOL and r["count"] > 0:
                r["percentile"] = int(round((below + at_or_below) * 50.0 / n))
    for r in rows:
        del r["_value"], r["_rateable"]
    return rows


# ============================================================================ the notebook

def _code(src: str) -> dict[str, Any]:
    return {"cell_type": "code", "execution_count": None, "metadata": {}, "outputs": [],
            "source": src.strip("\n").splitlines(keepends=True)}


def _md(src: str) -> dict[str, Any]:
    return {"cell_type": "markdown", "metadata": {}, "source": src.strip("\n").splitlines(keepends=True)}


def notebook(workspace_id: str, lakehouse_id: str, lakehouse_name: str, stats: list[str] | None = None) -> dict[str, Any]:
    """The catalogue notebook as ipynb JSON, with the lakehouse attached as its default and its tables read by OneLake
    path. It reads only the catalogue_* tables and writes only catalogue_leaders_check."""
    stats = stats or CATALOGUE_CHECK_STATS
    base = f"abfss://{workspace_id}@{ONELAKE_HOST}/{lakehouse_id}/Tables"
    cells = [
        _md("""
# Regista: the catalogue's numbers, recomputed in Fabric

The catalogue holds 14 competitions in 10 countries (England semi-pro men is the Regista League). Its pages show every
player's goals, assists, shots, key passes, take-ons won, tackles won and interceptions per 90 minutes, as a percentile
among peers of the same level: tier, age group, gender and position, over every competition of that level. This notebook
works the same numbers out again in Spark SQL from the raw `catalogue_*` tables (each competition's qualifying minutes,
the level pools, FBref's percentile, no percentile from fewer than 5 peers or for a count of 0) and writes them to
`catalogue_leaders_check`. `python -m regista.season.fabric check --catalogue` runs it and compares
`catalogue_leaders_check` with `catalogue_player_season`. It never reads or writes the league's tables.
"""),
        _code(f'BASE = "{base}"\nSTATS = {json.dumps(stats)}\nTABLES = {json.dumps(TABLES)}'),
        _code('for name in TABLES:\n'
              '    spark.read.format("delta").load(f"{BASE}/{name}").createOrReplaceTempView(name)\n'
              'print({name: spark.table(name).count() for name in TABLES})'),
        _code("STATEMENTS = " + json.dumps(statements(stats), indent=1) + "\nfor sql in STATEMENTS:\n    spark.sql(sql)\n"
              'display(spark.sql("SELECT * FROM cat_qualifying ORDER BY competition_id"))'),
        # rebuilt from scratch each run, without deletion vectors, so delta-rs on Regista's side can read it back
        _code("LEADERS = " + json.dumps(LEADERS_SQL) + "\n"
              "leaders = spark.sql(LEADERS)\n"
              'spark.conf.set("spark.databricks.delta.properties.defaults.enableDeletionVectors", "false")\n'
              'if notebookutils.fs.exists(f"{BASE}/catalogue_leaders_check"):\n'
              '    notebookutils.fs.rm(f"{BASE}/catalogue_leaders_check", True)\n'
              'leaders.write.format("delta").option("delta.enableDeletionVectors", "false")'
              '.save(f"{BASE}/catalogue_leaders_check")\n'
              'print(spark.read.format("delta").load(f"{BASE}/catalogue_leaders_check").count(), '
              '"rows in catalogue_leaders_check")'),
        _code('leaders.createOrReplaceTempView("cat_leaders")\n'
              'display(spark.sql("SELECT tier, age_group, gender, stat, competition_id, global_id, minutes, count, per90, '
              'percentile, pool_size FROM (SELECT *, ROW_NUMBER() OVER (PARTITION BY tier, age_group, gender, stat '
              'ORDER BY percentile DESC NULLS LAST, per90 DESC, global_id) AS k FROM cat_leaders WHERE stat = \'goals\') '
              'WHERE k <= 3 ORDER BY gender, tier, age_group, k"))'),
    ]
    return {
        "nbformat": 4, "nbformat_minor": 5, "cells": cells,
        "metadata": {
            "kernel_info": {"name": "synapse_pyspark"},
            "kernelspec": {"name": "synapse_pyspark", "display_name": "Synapse PySpark", "language": "Python"},
            "language_info": {"name": "python"},
            "dependencies": {"lakehouse": {"default_lakehouse": lakehouse_id, "default_lakehouse_name": lakehouse_name,
                                           "default_lakehouse_workspace_id": workspace_id}},
        },
    }


def definition(workspace_id: str, lakehouse_id: str, lakehouse_name: str, stats: list[str] | None = None) -> dict[str, Any]:
    """The Items API's notebook definition: the ipynb, base64 inline."""
    payload = base64.b64encode(json.dumps(notebook(workspace_id, lakehouse_id, lakehouse_name, stats), indent=1).encode()).decode()
    return {"format": "ipynb", "parts": [{"path": "notebook-content.ipynb", "payload": payload, "payloadType": "InlineBase64"}]}
