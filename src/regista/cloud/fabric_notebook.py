"""The Fabric notebook that recomputes the league leaders from the raw tables, independently of Regista's Python.

It reads ``players``, ``matches``, ``lineups`` and ``events`` from the lakehouse, and in Spark SQL works out each
player's appearances, minutes, counts and per-90 rates for the headline stats, then each rate's percentile among players
in the same position (only players with at least 40% of the most minutes are ranked, as on Regista's profiles). It
writes one row per (player, stat) to the table ``leaders_check``; ``regista.season.fabric check`` reads that back and
compares it with ``player_season``, the numbers Regista's profiles show.

Nothing here reuses ``regista.season.profiles``: what counts as a goal, a key pass or a tackle won is written again below
in SQL from the event contract (data/synthetic/README.md), so a disagreement means one side has it wrong.
"""

from __future__ import annotations

import base64
import json
from typing import Any

from regista.cloud.fabric import CHECK_STATS, ONELAKE_HOST

# stat -> which events count, in Spark SQL over the events table (the same tests as regista.season.profiles.STATS)
STAT_SQL: dict[str, str] = {
    "goals": "event_type = 'goal'",
    "assists": "event_type = 'assist'",
    "shots": "event_type = 'shot'",
    "key_passes": "event_type IN ('pass', 'cross') AND array_contains(qualifiers, 'key_pass')",
    "take_ons_won": "event_type = 'take_on' AND outcome = 'success'",
    "tackles_won": "event_type = 'tackle' AND outcome = 'success'",
    "interceptions": "event_type = 'interception'",
}

PLAYED_SQL = """
CREATE OR REPLACE TEMP VIEW played AS
SELECT l.global_id, COUNT(*) AS appearances, SUM(l.played_s / 60.0D) AS minutes_raw
FROM lineups l
WHERE l.played_s > 0 AND l.global_id IS NOT NULL
GROUP BY l.global_id
"""


def tallies_sql(stats: list[str]) -> str:
    sums = ",\n  ".join(f"SUM(CASE WHEN {STAT_SQL[s]} THEN 1 ELSE 0 END) AS {s}" for s in stats)
    return f"""
CREATE OR REPLACE TEMP VIEW tallies AS
SELECT global_id,
  {sums}
FROM events
WHERE global_id IS NOT NULL
GROUP BY global_id
"""


def rates_sql(stats: list[str]) -> str:
    pairs = ", ".join(f"'{s}', COALESCE(t.{s}, 0)" for s in stats)
    return f"""
CREATE OR REPLACE TEMP VIEW rates AS
SELECT global_id, position, appearances, minutes_raw, stat, CAST(n AS INT) AS count,
  CASE WHEN minutes_raw > 0 THEN ROUND(CAST(n AS DOUBLE) * 90.0D / minutes_raw, 2) ELSE 0.0D END AS per90
FROM (
  SELECT p.global_id, p.position, COALESCE(pl.appearances, 0) AS appearances, COALESCE(pl.minutes_raw, 0.0D) AS minutes_raw,
    stack({len(stats)}, {pairs}) AS (stat, n)
  FROM players p
  LEFT JOIN played pl ON pl.global_id = p.global_id
  LEFT JOIN tallies t ON t.global_id = p.global_id
)
"""


LEADERS_SQL = """
WITH flagged AS (
  SELECT *, ROUND(minutes_raw, 1) AS minutes,
    appearances > 0 AND ROUND(minutes_raw, 1) >= 0.4D * MAX(ROUND(minutes_raw, 1)) OVER () AS ranked
  FROM rates
),
ranks AS (
  SELECT global_id, stat,
    RANK() OVER (PARTITION BY position, stat ORDER BY per90) - 1 AS below,
    COUNT(*) OVER (PARTITION BY position, stat) AS n
  FROM flagged WHERE ranked
)
SELECT f.global_id, f.position, f.stat, CAST(f.appearances AS INT) AS appearances, f.minutes, f.count, f.per90,
  CASE WHEN r.n > 1 THEN CAST(BROUND(CAST(r.below AS DOUBLE) * 100.0D / (r.n - 1), 0) AS INT) END AS percentile,
  current_timestamp() AS computed_at
FROM flagged f LEFT JOIN ranks r ON r.global_id = f.global_id AND r.stat = f.stat
ORDER BY f.stat, f.per90 DESC, f.global_id
"""


def _code(src: str) -> dict[str, Any]:
    lines = src.strip("\n").splitlines(keepends=True)
    return {"cell_type": "code", "execution_count": None, "metadata": {}, "outputs": [], "source": lines}


def _md(src: str) -> dict[str, Any]:
    return {"cell_type": "markdown", "metadata": {}, "source": src.strip("\n").splitlines(keepends=True)}


def notebook(workspace_id: str, lakehouse_id: str, lakehouse_name: str, stats: list[str] | None = None) -> dict[str, Any]:
    """The notebook as ipynb JSON, with the lakehouse attached as its default and its tables read by OneLake path."""
    stats = stats or CHECK_STATS
    base = f"abfss://{workspace_id}@{ONELAKE_HOST}/{lakehouse_id}/Tables"
    statements = [PLAYED_SQL, tallies_sql(stats), rates_sql(stats)]
    cells = [
        _md("""
# Regista: the league leaders, recomputed in Fabric

Regista's profiles count every player's goals, assists, shots, key passes, take-ons won, tackles won and interceptions
from the synthetic event stream, per 90 minutes and as a percentile within the position. This notebook works the same
numbers out again in Spark SQL from the raw `events`, `lineups`, `matches` and `players` tables, and writes them to
`leaders_check`. `python -m regista.season.fabric check` runs it and compares `leaders_check` with `player_season`.
"""),
        _code(f'BASE = "{base}"\nSTATS = {json.dumps(stats)}'),
        _code('for name in ["players", "matches", "lineups", "events"]:\n'
              '    spark.read.format("delta").load(f"{BASE}/{name}").createOrReplaceTempView(name)\n'
              'print({name: spark.table(name).count() for name in ["players", "matches", "lineups", "events"]})'),
        _code("STATEMENTS = " + json.dumps(statements, indent=1) + "\nfor sql in STATEMENTS:\n    spark.sql(sql)"),
        # leaders_check is rebuilt from scratch each run, without deletion vectors (Fabric turns them on for new tables),
        # so delta-rs on Regista's side can read it back
        _code("LEADERS = " + json.dumps(LEADERS_SQL) + "\n"
              "leaders = spark.sql(LEADERS)\n"
              'spark.conf.set("spark.databricks.delta.properties.defaults.enableDeletionVectors", "false")\n'
              'if notebookutils.fs.exists(f"{BASE}/leaders_check"):\n'
              '    notebookutils.fs.rm(f"{BASE}/leaders_check", True)\n'
              'leaders.write.format("delta").option("delta.enableDeletionVectors", "false").save(f"{BASE}/leaders_check")\n'
              'print(spark.read.format("delta").load(f"{BASE}/leaders_check").count(), "rows in leaders_check")'),
        _code('leaders.createOrReplaceTempView("leaders")\n'
              'display(spark.sql("SELECT stat, global_id, minutes, count, per90, percentile FROM (SELECT *, ROW_NUMBER() '
              'OVER (PARTITION BY stat ORDER BY per90 DESC, global_id) AS k FROM leaders) WHERE k <= 3 ORDER BY stat, k"))'),
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
