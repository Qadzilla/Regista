# Review A, round 1: engineering

Reviewer A, round 1. I read `git diff main...HEAD` on `feature/terminal-engine` (up to 643d0a4): the generator's league
mode and its 10 Hz motion, `physical.py`, `league.py` (ratings), `playing_time.py`, the clip rule changes, the metrics engine,
`terminal_api.py`, the schema and contract docs, and the tests. I fixed nothing. **Not signed off**: nothing must be fixed,
but several things should be.

## What I checked myself

- **Back-compat, independently of the branch's test.** I made a detached worktree at main (e3da71d), hashed events and
  tracks there, and compared them with the branch. All match: vision dev seeds 201-206, fresh seeds 301-303, training seeds
  101-102, and the Player view's friendly film (`friendly_kwargs`, built from each side's own league.json). The branch's
  test covers only 201, 202 and 301 of these. Structurally the gate is sound too. Every non-league change either sits
  behind `self.league` or is a no-op without ratings (`_place` with no body, `tilt = 0.06 + 0.0`, `_substitutions_due`
  returning early, the `_kicker` fallback).
- **Determinism.** The same league fixture gives the same hash under PYTHONHASHSEED 1, 2 and 3 in separate processes.
  `new_league(seed)` regenerates the committed league.json exactly.
- **Tests.** `python3 -m pytest -q` gives 737 passed and 5 deselected (the slow ones) in 4 min 15 s.
- **API, probed with TestClient.** Unknown metric gives 422, unknown player or club 404, `age_min > age_max` 422. The
  shapes are right. No ratings appear (the verifier checked this across 422 responses).
- **Timing.** One league match: 1.1 s to generate, 1.17 s to materialise. A cold season: about 37 s for 30 matches. Warm
  `build_season`: 1.1 s.

## Should fix

1. **`compute_metrics` mutates the caller's records.** `report.physical_metrics` writes `_role` and `_who` into every
   `physical` record it is given. Those records then fail the events schema (`unevaluatedProperties: false`); I
   reproduced it on a two-minute league match. Nothing writes a stream after a report today: `synth/__main__.py` writes
   first. But the fast tests depend on order. The module-scoped `matches` fixture in `tests/test_league_mode.py` is
   mutated by the report tests, and the schema test passes only because it runs first. Work on copies or side dicts.
2. **Cold season build is about 5x slower, and CLAUDE.md §2.5 still says "0.2 s each".** Per match it is now 1.1-1.2 s;
   a cold build of 30 matches takes about 37 s on this laptop, probably more on a 1-CPU replica. `load_metrics` holds a
   global lock throughout, and `/scout`, profiles and terminal requests wait on the warm-up. A fresh revision starts with
   an empty disk, so judges can land on a cold replica. Options: update the doc, materialise in a process pool, or build
   the season into the image at docker build time.
3. **The goals of part A are guarded only by slow tests that CI never runs.** `pyproject.toml` adds `-m 'not slow'`, and
   CI runs plain `python -m pytest -q`. So "Femi Toure is top scorer", "every band passes" and "players in a role differ"
   go unchecked on every push. No fast test pins a league fixture's output across commits either. Any generator edit can
   silently change the committed season, and with it `demo.js`'s hard-coded clip ids and claims ("ten goals", "behind
   only Ustinov"), the storyboard's "ten goals" and the committed summaries. Suggestions: a fast hash pin on one or two
   league fixtures (as `test_backcompat` does for the old path), a fast test that every clip id in `demo.js` exists in the
   built season, and a scheduled or manual CI job for `-m slow`.
4. **The profile and the terminal give different percentiles for the same stat** (verifier's finding, confirmed in the
   code). `profiles.py` keeps its own rule; `metrics.py` uses FBref's mean rank with qualifying minutes and attempt
   minimums. A scout sees "higher than 6%" on one page and "8th percentile" on the other. Use one rule, or label the two
   differently.
5. **Save % counts penalties.** `analyse_match` counts a penalty that is scored or saved in `sot_faced`, but the metric
   cites "FBref Save%". The project's own research (industry-metrics.md row 4) says FBref leaves penalties out of shots
   on target, and the engine already does that for shooters (`shots_on_target` is non-penalty only). Leave penalties out
   of `sot_faced` and `saves`, as `penalties_faced` and `penalties_saved` are already counted apart, or change the rule
   text.
6. **The evidence parameters do not do what their docs say.** `GET /api/players/{id}/metrics?evidence=KEY` is documented
   as "full evidence (up to 500)". With the default `evidence_limit=10` it returns 10 items (checked: goals, 10 of 10).
   `evidence_limit=0` returns no event evidence but every physical item. In `SeasonMetrics.evidence`, `items[:limit] if
   limit else items` treats 0 as "all", while the event branch treats 0 as none.
7. **The fast suite carries a 23 s test.** `test_league_matches_validate_and_say_they_are_league_mode` runs the
   jsonschema check on about 100k track records. It is the slowest test in the suite (22.7 s). Validate a sample of tracks
   and every non-track record.

## Nits

- `test_backcompat` could add 203-206, 302, 303 and the friendly film: about a second in all, and they are byte-identical
  (checked above).
- `report.py` decides league mode with `version >= "0.2.0"`, a string comparison: "0.10.0" would compare as older.
- `build.fingerprint` hashes league.json's `generator.version`, not the code's `LEAGUE_GENERATOR_VERSION`. If the
  generator code changes without regenerating league.json, the stale `data/season/matches` folders keep being served
  locally.
- The `club=` filter on `/api/terminal/*` matches only an exact id, name or short name: `club=Brookfield` returns 0 and
  `club=BRO` returns 11. Say so, or match on prefixes.
- `MAX_COLUMNS` in `terminal_api.py` is never used; `KEYS_PATTERN` sets the limit.
- `_move_league`'s once-a-second wander test (`int(t*10) % 10 == 0`) can fire twice in a second, or not at all, once
  partial steps knock `t` off the 0.1 s grid. This is harmless noise, but it is not "each second".
- `Body.s_prev` is not reset when `_place(..., stop=True)` zeroes velocity. The next step then reads a phantom
  deceleration. It only counts when held for 1 s, so it is unlikely to matter.
- In `_league_pass`, `aim != target.pos` is checked after the ball's flight, when the target has moved. It is nearly
  always true, so `_reach` runs for ordinary passes too. This is harmless, but it does not match the comment.
- `.gitignore` still ignores `docs/scout-terminal/build/`, so every report has to be force-added.

## Fine as it is

- League mode refuses half-rated squads (`_team_specs`). Motion has its own random stream, so the match's own draws
  never shift.
- Physical records close the stream. Nothing downstream sorts on a fixed set of record types (I grepped for it).
- `materialise` is safe across threads: a lock per fixture, then a temporary folder renamed into place.
- The engine's rules have hand-made-stream tests at their edges: progressive passes, the six-pass window, key-pass
  linking, SCA stopping at the opponent's possession, PPDA, pressure regains, possession adjustment, keepers and xT.
- The hidden ratings stay out of every response: `people()` drops `attributes`, and tests cover the season, profile and
  terminal JSON.
