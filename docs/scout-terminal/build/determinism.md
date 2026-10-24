# Cross-platform determinism: one league season on every machine

2026-10-24, branch `feature/terminal-engine` (PR #36). Short version: league matches now come out bit for bit the
same on macOS and Linux. CI's test job passes on Linux, and the built image checks its own season against the pins.

## The failure

PR #36's CI test job failed on Linux (Python 3.11, numpy 2.4.6, glibc). The same suite passed on Zaid's Mac (arm64,
Python 3.13.9, numpy 2.3.5). Three tests failed:
[run 40093049314](https://github.com/Qadzilla/Regista/actions/runs/40093049314) (push) and
[run 40093052019](https://github.com/Qadzilla/Regista/actions/runs/40093052019) (pull request).

- `test_league_mode.py::test_the_committed_season_is_pinned`: fixture 1's `events.jsonl` hashed `8b1615d2…` on Linux,
  where the Mac gave `9f6735b1…`. Fixtures 0 and 2 matched.
- `test_scout_agent.py::test_the_committed_summaries_match_the_committed_league`: the stored summaries had been
  "written from other numbers", and `check_sentences` raised "the number 5 is not in the facts that sentence cites".
- `test_shared_dashboard.py::test_seeded_claims_hold_in_the_league`: Femi Toure had 8 take-ons on Linux and 7 on the
  Mac.

The live app builds the league on demand inside the Linux image. The season users would see was therefore not the one
the summaries, the demo seeds and the docs had been checked against.

## The cause

**libm.** The league generator called `math.exp`, `math.log`, `math.sin` and `math.hypot`, plus `random.gauss`, which
uses libm's `log`, `cos` and `sin` internally. These are the C library's functions. Apple's libm and glibc may return
different last bits for the same input, and glibc even picks a different routine on CPUs with FMA. Most 1-ulp
differences are absorbed by rounding. Now and then one tips an `rng.random() < p` comparison, and every draw after it
lands on a different branch. From that point the match is a different match.

How it was pinned down:

1. **Not Python or numpy.** A Python 3.11 + numpy 2.4.6 environment on the same Mac reproduced the Mac hashes exactly
   (`0ea2fbf9…`, `9f6735b1…`, `7333c6c4…`). The generator imports no numpy.
2. **libm is not correctly rounded on the Mac, and the generator leans on it.** One league match makes about 3,500
   distinct `exp` calls, 42,000 `log`, 41,500 `cos` and 41,500 `sin` (from `gauss`), and 1.66 million `hypot` calls.
   Against mpmath at 200 bits, macOS's results are not correctly rounded for 7 of the `exp` inputs, 35 `log`,
   1,585 `sin` and 1,849 `cos`. glibc rounds a different set. CPython's own `hypot` was correctly rounded for every
   one of 200,000 sampled inputs.
3. **Confirmation.** With the transcendental functions swapped for platform-independent ones, the Mac produced
   `8b1615d2…` for fixture 1. That is exactly the hash Linux had produced, so glibc and the new functions agree on the
   call that had flipped it.
4. **The summaries error was a second, latent bug.** `summaries.basis(p)` fingerprinted only the player's own minutes,
   counts and moments. A summary says "3rd of the league's 24 defenders", and that rank moves when *other* players'
   numbers move. On Linux, a player whose own counts were unchanged kept a summary whose rank was stale, and the
   sentence then failed its own check. The same thing happened here: regenerating with `summarise` (which keeps
   summaries whose basis matches) left 9 players with stale ranks.

## The fix

- **`src/regista/detmath.py`**: `exp`, `log`, `sin` and `cos` ported from fdlibm (Sun's freely distributable libm,
  also FreeBSD's). They use only IEEE-754 double `+ - * /`, `math.sqrt` (correctly rounded everywhere), exact
  `frexp`/`ldexp` and `floor`. Python rounds every operation to double and never fuses a multiply and an add across
  operations, so each function returns the same double on any machine and any Python version. Accuracy stays under
  1 ulp of the true value, about libm's. `hypot` is `sqrt(x*x + y*y)`. `detmath.Random` is `random.Random` with a
  `gauss` that uses these functions; it makes the same Mersenne Twister draws in the same order as CPython's.
- **Generator (league mode only).** `self.m = detmath`, `self.dist = _det_dist`, and `detmath.Random` for `rng` and
  `move_rng`. `_logit` and `_sigmoid` (league-only) also go through detmath, and squares are written as products
  (float `** 2` calls libm's `pow`). `physical.Body.stop` uses `detmath.hypot`. Without ratings the generator keeps
  `math` and `random.Random`: `tests/test_backcompat.py` is green on both platforms, and the committed samples and
  vision seeds are byte-identical. `LEAGUE_GENERATOR_VERSION` is now 0.7.1, the tuning is unchanged, and `detmath`
  joins `build.BUILT_BY`/`GENERATED_BY`.
- **Metrics.** `season/metrics.py` writes its squares as products and computes distances with `detmath.hypot`.
- **Summaries.** `basis(season, p)` now fingerprints the summary's facts, ranks included. A regression test changes
  only a rank and checks the summary goes stale.
- **Reliability.** `noisy` is decided on the r the table shows. One r of 0.29996 was shown as 0.3 yet marked noisy.
- **Checks that would catch drift:**
  - `tests/test_detmath.py`: golden bits for each function and for `gauss`, recorded on the Mac and checked on Linux
    in CI. Another test sets a trap on every libm function and random's internals and fails if a league match calls
    any of them.
  - `src/regista/season/pins.py`: the first 16 hex digits of all 30 fixtures' `events.jsonl`. They are checked by
    `test_league_mode.py::test_the_whole_committed_season_is_the_same_on_every_platform` (CI, Linux), and by
    `python -m regista.cloud.smoke` (`season-pins`) **inside the built image**, against the season its Dockerfile
    built. That is the live app's own platform.

Python version independence was measured, not only argued. All 30 fixtures hash the same under Python 3.11 and 3.13 on
the Mac, and so do the season's metric cells, profiles, rules summaries and league diagnostics.

## What changed in the season

Generator 0.7.1 is a regenerated season, not a retune. Against 0.7.0's Mac season, 5 of the 30 matches have different
event lists (fixtures 4, 9, 10, 16 and 25). Most others differ only in a position or a physical record. Seven are
identical apart from the version stamp.

What the demo and the docs quote mostly holds:

- **Femi Toure** keeps 3 league goals, one a penalty, in the same three clips (rounds 2, 5 and 6; his reel is
  4.95 + 13.17 + 5.48 = 23.6 s). He is still the outright top scorer and still the top forward for goals and shots on
  target.
- **Amari Haddad** still leads midfielders for recoveries (13.97 per 90, 45 in 289.9 minutes).

These moved, and were updated in `src/regista/static/shared/demo.js` and its test:

- Femi's take-ons went from 7 (1 won) to 10 (1 won).
- Farid Vargas went from 2nd to 3rd among midfielders for passes.
- Gino Mensah went from 5th to 6th among defenders for key passes.
- The Foundry Scout agent's example answer went from 2.47 to 2.46 per 90 (Haruki Fontaine, 8 in 292 minutes).

Regenerated: `data/season/summaries.json` (rules-v0, 102 players, `--fresh`) and `data/season/reliability.json`
(6 seasons). Three metrics are now noisy that were not (`carries_into_box`, `sca`, `short_passes_completed`), and
`progressive_passes_received` is no longer noisy.

Realism (`python3 -m regista.synth.report --league`, `docs/realism-report.md` section 1 regenerated):

- **One season:** 13 of 13 event bands, 11 of 11 league-mode bands (penalties were low on 0.7.0's season; on one
  season the rare-event verdicts are only indicative), 14 of 14 physical, 4 of 4 style, and 12 of 14 leaders
  (indicative; the same two are high as before).
- **Six seasons pooled** (`--repeat 6`): every band (13, 11, 14, 4, 14 of 14 leaders) and all 8 role shapes.

`python3 -m regista.season.audit` runs; its top scorers are Femi Toure on 3 goals, then three players on 2.

Docs updated to 0.7.1 where they describe the current season:

- README
- CLAUDE.md
- `docs/architecture.md`
- `docs/criteria.md`
- `docs/demo-storyboard.md`
- `data/synthetic/README.md`, including the six-season saves figure (now about 70%) and the corner counts (70 of 115)
- `docs/scout-terminal/regista-data.md`

## Not done here

- **Microsoft Fabric still holds the 0.7.0 season.** The 756 of 756 cross-check describes that season. This job did
  not touch Fabric. Before storyboard beat 5 is recorded, run `python -m regista.season.fabric push` and then `check`
  again. The storyboard, CLAUDE.md, README, criteria and architecture all say so.
- **The slow tests are not run on Linux.** CI deselects `-m slow`; they pass on the Mac (13 of 13). The whole-season
  pin test is in the quick suite, so a Linux drift in any fixture still fails CI.
- **Trigonometric arguments beyond ±400,000.** `detmath.sin`/`cos` raise for these: fdlibm's long reduction is not
  ported. Nothing in the generator comes close; its arguments are under 2π.

## Evidence

- Local (Mac): `python3 -m pytest -q`: 797 passed, 13 deselected. `python3 -m pytest -q -m slow`: 13 passed.
- CI on Linux after the fix: the test job passed (795 passed, 1 skipped), as did the image build and the smoke test:
  [run 40124110276](https://github.com/Qadzilla/Regista/actions/runs/40124110276) (push) and
  [run 40124112916](https://github.com/Qadzilla/Regista/actions/runs/40124112916) (pull request).
- CI on Linux with the season pins (commit 1c864ef): the test job passed (796 passed, 1 skipped), the image was built,
  and the smoke test inside it printed `{"check": "season-pins", "ok": true, "root": "/app/data/season/matches",
  "differs": {}}`. That is the 30 matches the image's Dockerfile built on python:3.11-slim, the live app's platform,
  and they equal the Mac's bit for bit:
  [run 40125927677](https://github.com/Qadzilla/Regista/actions/runs/40125927677) (push) and
  [run 40125929263](https://github.com/Qadzilla/Regista/actions/runs/40125929263) (pull request).
