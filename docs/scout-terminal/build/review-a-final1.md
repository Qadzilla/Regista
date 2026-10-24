# Review A, closing round 1: engineering

Reviewer A, closing round 1. I read `git diff main...HEAD` on `feature/terminal-engine` (code at bd33cc4; b68e601 only
adds review B's report). I read the earlier reviews and fixes first (`review-a-pass1/2`, `review-fixes-1/2`). Then I
re-read the generator's league mode, `physical.py`, `playing_time.py`, `build.py`, `metrics.py`, `reliability.py`,
`terminal_api.py`, the profile and season API changes, the schema, the contract docs and the tests, and ran every check
myself. I fixed nothing.

**Not signed off.** Nothing must be fixed. One thing should be fixed, and it is small. Everything round 2 asked for is
done, and I confirmed each item below.

## What I checked myself

- **Back-compat, independently of the branch's test.** I made a detached worktree at main (e3da71d) and ran one script
  against both trees, each importing its own `src`. The script hashed events and tracks for:
  - every vision training spec (101-110), development spec (201-206) and fresh spec (301-303);
  - four event-training specs (111-114);
  - the `demo` and `realistic` profiles on seeds 5 and 900;
  - two Player-view friendly films (`friendly_kwargs`, each tree's own league.json);
  - `derive_clips` (clips and labels) for every player of every committed sample.

  All 39 entries are identical. The worktree is removed. `tests/test_backcompat.py` passes too: 8 hashes plus the
  committed syn_0294 bytes.
- **Determinism.**
  - Four league fixtures (three from round 1, one from round 10), events and tracks, give one hash under
    `PYTHONHASHSEED` 1, 7 and 12345, each in its own process.
  - A cold parallel build is byte-identical to the local `data/season/matches`: 30 of 30 fixtures, events and clips.
  - So the committed `summaries.json`, `reliability.json` and the demo's claims were made from current matches.
- **Tests.**
  - `python3 -m pytest -q`: 755 passed, 9 deselected, in 4 min 31 s. This ran beside my back-compat script, so it is a
    little slower than it should be.
  - `python3 -m pytest -q -m slow`: 9 passed in 2 min 28 s.
  - Slowest tests:
    - **Fast suite:** the vision tests, unchanged from main (up to 30 s). The slowest part A test is
      `test_every_clip_the_demo_cites_exists_and_is_the_stars_goal` at 5.7 s. Nothing slow is left in the fast suite.
    - **Slow suite:** the six-season recomputation of `reliability.json` (64 s), and the six-season pool fixture
      (61 s).
- **Report and audit.**
  - `python -m regista.synth.report --league` takes 6.6 s. All event, league-mode, physical and style bands are in
    band. The leader bands read "indicative (under 6 seasons)", 8 of 12 in, as `review-fixes-2.md` reports.
  - `python -m regista.season.audit` takes 6.3 s. Femi Toure is outright top scorer with 4; next is Milan Brennan with 3.
- **Cold start and concurrency.**
  - **One cold build:** `build_all` on an empty folder takes 5.8 s on 10 cores, as CLAUDE.md says ("about 6 s").
  - **Two at once:** two processes each ran `build_all` on the same empty folder, while a third read every fixture's
    `events.jsonl` and `clips.jsonl` whenever `is_current` held. Both builds finished (12.3 s). The reader made 72,961
    reads with 0 errors, and no temporary folders were left.
  - **Under uvicorn:** a real app (`uvicorn regista.api:app`, empty season root, `REGISTA_DOTENV=`, read-only) served
    the terminal 7.5 s after launch. The spawn pool works when started from the warm-up thread under uvicorn, and the
    log has no traceback.
- **API, probed with TestClient on the built season.**
  - **Errors:**
    - `limit=0` gives 422; so does an unknown metric in a list, `age_min > age_max`, 17 columns, `group=bogus` and an
      unknown `metric`.
    - A bad player or club id gives 400; an unknown player or club gives 404.
    - The six squad players who never played give 404.
  - **Every metric works:** all 127 metrics return 200 from `rank` for every position, and from `evidence=KEY`.
  - **Speed:** cold `/api/metrics` (engine build, matches on disk) takes 2.3 s. Warm queries take 2-44 ms.
- **The demo's hard-coded claims** (`demo.js`), against the served season. All hold:
  - Toure is top for np goals and shots on target per 90 among the 18 qualified forwards.
  - pl_ash_10 is second among midfielders for take-ons won per 90.
  - pl_ash_09 is first among forwards for take-ons won per 90.
  - pl_dun_06 is third among midfielders for tackles won per 90.
  - pl_eas_03 is second among defenders for forward passes per 90.
- **Contract consistency.**
  - **Physical records:** the 890 records' `played_s` match `playing_time.played_seconds` to within 0.05 s, and they
    cover the same players.
  - **Keepers:** non-penalty saves equal shots on target faced minus goals for every keeper, and every `saved` shot is
    followed by a `save`.
  - **Docs:** CLAUDE.md now says 127 player and 19 team metrics, which matches the code. The README describes generator
    0.5.0 and the vision layer's 0.1.1 stamp; every vision, review, verdict and claim writer imports
    `LEGACY_SCHEMA_VERSION`.
- **Python 3.11 (Docker and CI).** This machine has no Python 3.11 (3.12 to 3.14 only), and the branch has no CI run
  yet. So I scanned every changed `.py` with the tokenizer for 3.12-only f-string syntax (nested
  same-quote strings, backslashes or newlines in replacement fields) and for 3.12+ stdlib calls. None found.

## Round 2 findings, checked

| Finding | Verdict |
|---|---|
| Contract docs stale for 0.4.0 | Fixed: README league mode describes 0.5.0 (aerial rule, team style, shot role, keepers, shot outcomes, take-ons, touches); CLAUDE.md §2.5 says 2 x 15 min, profile `league` |
| Vision layer stamps 0.2.0 | Fixed: vision, Who's who, verdicts and claims stamp `LEGACY_SCHEMA_VERSION` |
| Two "Shots" columns | Fixed by labels: "Shots (incl. penalties)", "Shots on target (incl. penalties)", "Saves (incl. penalties)", "Shots on target % (incl. penalties)" |
| One-season leader bands fail | Fixed: verdicts only over six pooled seasons; the slow test pools six and passes |
| Process pool bypasses the per-fixture lock | Fixed: `build_all` serialised per process; `materialise` keeps a folder another process finished first. Two tests, and my three-process race above |
| One-percentile test skipped differences | Fixed: it asserts equality |

## Should fix

1. **The build fingerprint cannot see a generator change made within one version.**
   - **What it hashes:** `build.fingerprint` covers the fixture's kwargs, league.json's `generator` block and the code's
     `LEAGUE_GENERATOR_VERSION`. It does not cover the tuning tables (`LEAGUE`, `MOTION`, `TEAM_STYLE`,
     `SKILL_CENTRE`, `SUB_COUNTS`) or the generator's code.
   - **The failure:** this branch retuned four generator versions in two days. Each time someone edits a table and
     re-runs things before bumping the version, the local `data/season/matches` stays "current" and is served as it is.
   - **What reads that folder:**
     - `python -m regista.season summarise`, which writes the committed `summaries.json`;
     - the fast test `test_the_committed_summaries_match_the_committed_league`;
     - the profiles and terminal of a local app, which is where the `demo.js` claims get checked.
   - **The result:** committed artifacts and the demo's claims can be produced from stale matches, while tests pass on
     that machine. A clean CI build would then disagree, or worse, agree with nothing anyone looked at.
   - **Prior notes:** `review-fixes-2.md` lists this as open issue 6 ("must be deleted by hand"). Today the local folder
     is current (checked above), so nothing committed is affected.
   - **The fix:** add a hash of `synth/generator.py` and `synth/physical.py` (or of the tuning tables) to the
     fingerprint's `data`. A rebuild costs 6 s on this laptop, and the Docker image builds the season fresh anyway.
     `reliability.league_fingerprint` has the same blind spot, but the slow test recomputes that file, so it matters
     less there.

## Nits

- **`last3_minus_season` in `SeasonMetrics.form` skips the 15-minute floor.** The mean, standard deviation and CV use the
  floor; this value does not. A 4-minute cameo gives pl_cal_16 a tackles-won "last three minus season" of +10.99 per 90.
  It only affects players below the qualifying minutes (36 players; none qualify). Apply the same floor, or pool counts
  over minutes for the last three.
- **The `rank` docstring is incomplete.** It says "Ratios rank only players with the minimum attempts". Per-90 metrics
  also list players below the qualifying minutes as unranked: `rank?metric=goals&min_minutes=0` returns 66 ranked and
  25 unranked.
- **`build_all` sizes its pool with `os.cpu_count()`.** On Linux containers in Python 3.11 that is the host's core count,
  not the cgroup's CPU limit. This only matters on a cold replica, and the image is built warm.
  `len(os.sched_getaffinity(0))` is closer; a cgroup-aware cap is closer still.
- **`materialise` still has a two-syscall window.** Between `is_current` and `rmtree(dest)`, another process can rename
  its folder in. A reader would then miss it, or our `rename` would fail onto a non-empty folder. My race test never
  hit this, and the gap is tiny.
- **The `demo.js` ranking claims are untested.** The fast suite checks the clip ids and pins three fixtures' bytes, and
  the pin's comment tells whoever re-records it to re-check `demo.js`. A test that asserts the five rank claims above
  would make that automatic.
- **Carried from round 2, still open as `review-fixes-2.md` lists:**
  - `rank`'s O(n^2) `rest` (and `similar`'s `target not in pool`, which compares dataclasses field by field);
  - `rank?metric=save_pct&position=FW` returns 200 with 18 forwards unranked;
  - the whole-table evidence cap: `evidence_limit=500` returns 1.95 MB for Toure;
  - two meanings of "regular" (the report's 40% against the terminal's third);
  - keepers get profile percentiles for outfield stats;
  - `club=` matches only exactly: `club=Brookfield` returns 0 and `club=BRO` returns 11;
  - `Body.s_prev` is not reset on `_place(stop=True)`;
  - `.gitignore` hides this folder.
- **The slow suite regenerates six seasons twice.** The reliability test and the `pooled` fixture each build them, about
  60 s each. A shared session fixture would halve the time.
- **`test_backcompat` covers 201, 202 and 301 of the vision seeds, and no friendly film.** My script shows the rest are
  byte-identical. Adding them costs about a second.
- **Fabric:** `lineups` gained a `played_s` column, and the notebook now reads it. The lakehouse needs the re-sync before
  the notebook's cross-check runs again. This is a deployment step, not a code defect.

## Numbers

| Check | Result |
|---|---|
| Fast suite | 755 passed, 9 deselected, 4 min 31 s |
| Slow suite | 9 passed, 2 min 28 s (10 cores) |
| Back-compat against main | 39 of 39 identical (vision 101-114, 201-206, 301-303; demo/realistic x 2 seeds; 2 friendlies; derived clips of every committed sample) |
| Determinism | 1 hash across 3 `PYTHONHASHSEED` values; cold build = local folder, 30 of 30 |
| Cold `build_all` | 5.8 s alone; 12.3 s each for two racing processes, 0 reader errors |
| Cold app to first terminal answer | 7.5 s (uvicorn, empty season root) |
| `report --league` / `season.audit` | 6.6 s / 6.3 s |
| Warm API | 2-44 ms per query; cold engine build 2.3 s |
