# Catalogue review A, closing round 1: engineering

Branch `feature/catalogue` at 179cd25, reviewed against `main` (`git diff main...HEAD`). This round looks mainly at what
changed since review round 3: fixes-3.md, levels.md, docs.md and verify-2.md. My lens is engineering:
- determinism and pins;
- back-compat and the existing app;
- API shapes and validation;
- the ranking rule on every surface;
- the generator change staying inert for England;
- tests and how long they take;
- whether the docs match the code.

Nothing was fixed in this round, and this file is the only change.

**Verdict: not signed off.** One item should be fixed, a short documentation gap in the data contract. Nothing must be
fixed: the code, data, pins and endpoints hold up under this lens. Everything else is a nit, or a decision for Zaid
that I list but do not judge.

## Should fix

### S1. The data contract does not describe the heavy-touch records the generator now writes

`data/synthetic/README.md` calls itself the contract, record by record, and its league-mode section describes every
event pattern the generator writes. A catalogue side with `execution` now writes a new pattern
(`MatchSim._heavy_touch`, generator.py about line 1512):
1. a `touch` with `outcome: "fail"` and the qualifiers `first_touch` and `heavy_touch`;
2. the possession ends with `lost_by: "dispossessed"`;
3. a `recovery` by whoever is nearest the loose ball;
4. a new possession with `gained_by` `rebound` (the same team) or `loose_ball` (the other team).

The README mentions only that `execution` lowers "first touches". Until now, a failed `touch` meant `out_of_play`
(generator.py about line 2300), so anyone reading the contract cannot tell the two cases apart. The schema accepts the
record (qualifiers are free snake_case tags), so no schema bump is needed. The fix is a short bullet in the league-mode
or Catalogue section, saying when it happens (`exec_touch` × execution, ×2 under pressure, the first touch of a
received pass) and that a teammate's recovery still counts as a ball loss.

That last point is the existing convention for loose balls: a failed take-on works the same way (generator.py about
lines 1707-1719). I measured how often it happens on six catalogue matches (three Ghana U17, three US college women):
25 of 98 heavy touches were recovered by the same team. Every ball-loss order still passes by a wide margin (the
smallest margin is 20 standard errors), so this is for the contract, not a verdict.

## What I checked, and what holds

**England is untouched**
- `data/season/league.json`: SHA-256 04dbb30f…0b1a34, the same as on `main`.
- `git diff main...HEAD` touches neither `season/pins.py` nor `tests/test_backcompat.py`.
  `tests/test_catalogue_backcompat.py` and `tests/data/catalogue_backcompat.json` are unchanged since ab3bb02, where
  they were recorded on main's code.
- `data/season/reliability.json` differs from `main` by one line only: `league_fingerprint`, a hash of the generator
  source. Every number is identical.

**The generator change is inert without `execution`**
- Every new term in the generator checks `team.execution` first:
  - `goal_probability`, `_league_pass`, the lose and shoot weights in `_play_possession`;
  - the heavy-touch branch, where the `and` chain tests `team.execution` before `rng.random()`, so no random number is
    drawn without it.
- `_team_specs` copies the key only when it is truthy. `generate_kwargs` adds it only when both `ratings` and
  `level.execution` are set, and `league.json` has no `level`.
- `test_england_kwargs_never_carry_execution` covers all 30 fixtures. The verifier's rebuild found pin drift `{}`, and
  Germany (execution 0) kept its 8 pins.
- The exponentials go through `self.m.exp` (detmath), and the heavy touch's Gaussian comes from the match's own detmath
  stream.

**Determinism in the definition**
- `define._coverage` shuffles the whole round robin with its own seeded detmath stream before it drops unplayed
  fixtures.
- `AS_OF` is a constant. Nothing in `regista.catalogue` reads the clock or lists a directory. The sets are used only
  for membership tests.
- `python -m regista.catalogue define --check` passes.

**The report is current**
- `python -m regista.synth.report --catalogue` exits 0, and its output equals `docs/catalogue/realism.md` (apart from
  print's trailing newline).
- The report never regenerates by default (a test guards this). It refuses mixed or orphan arguments.
- `--league` still defaults to one season.

**Packaging and CI**
- The Dockerfile copies `data/catalogue/{catalogue.json,competitions,reliability.json,realism.json}` and builds the 60
  matches at image build time. `.dockerignore` drops `data/catalogue/matches/`.
- The smoke test checks the catalogue pins, reliability and realism inside the image, and the three MCP tools.
- The image workflow's `paths` include `data/catalogue/**` and `data/season/**`.

**The API, offline** (`TestClient`, `REGISTA_DOTENV=`). I sent 22 probes; the first cold load took 2.5 s and every
later one 0.01 s or less.
- **One level, six surfaces:** a single competition's goals on `/api/catalogue/rank`, `/api/catalogue/players`,
  `/api/competitions/{id}/players`, `/api/players`, `/api/terminal/rank` and `/api/terminal/screen` all give
  `rank_by: value` and `boards: null`, with the same leader on every surface.
- **Invalid `rank_by`:** a 422 on all five REST surfaces. The MCP tool returns an error message.
- **Other validation:** `limit=0`, `offset=-1`, an unknown `tier` and an unknown `scope` give 422. An unknown metric
  gives 422 with a hint.
- **`rank_by=pool` on `/api/terminal/screen` with no catalogue filter:** one board per gender and position, as
  `RANK_RULE` says (the GK board comes first).

**The ranking rule**
- `choose_mode`, `board_by`, `group_boards` and `boards` are one implementation, used by every surface, with one board
  shape.
- Value mode across levels sorts the whole list, then groups it by level with a stable sort. Pool mode needs exactly
  one position.
- `materialise_match` now removes a stale folder under `season.build.match_lock`, re-checking inside it. The lock is not
  re-entrant, but it is never nested: `materialise` takes it again only after release and checks the folder again.

**Tests**
- Quick suite: 979 passed, 15 deselected, in 4 min 25 s.
- Slow suite: 15 passed, in 2 min 9 s.
- The slowest catalogue tests take 5.2 s (`test_execution_lowers_pass_completion_and_adds_heavy_touches`, which
  generates two U17 matches twice), 4.3 s and 4.1 s. None is among the six slowest tests, which are all vision tests.

**Docs against the code.** CLAUDE.md §2.11, §3.0 and §4.2, the data README's Catalogue section, `architecture.md` and
`criteria.md` agree with the code and with each other:
- 14 competitions, 10 countries, 66 clubs, 1,183 people, 90 matches;
- 11 of 11 sourced checks; of 6 assumed orders, 5 hold and 1 fails;
- 979 quick tests and 15 slow;
- not pushed, not merged, not deployed.

## Nits (not needed for sign-off)

- **The MCP tool's hint reads "pass position, gender or competition to read one board further".** When the boards are
  levels, only `competition` (or `tier` + `age_group` + `gender`) gives one board. I checked England's goals:
  - `gender=men` still gives two level boards (semi-pro men 66, U18 men 43);
  - `position=FW` switches to pool mode with gender boards, which is a different ranking, not the same board read
    further.
  The rows are correct and labelled, but an agent that follows the hint gets a different list from the one it expected.
  The docstring in `mcp_server.py` says the same thing.
- **`docs/architecture.md`'s MCP table leaves `rank_by` out of `search_catalogue_players`' arguments** (the verifier
  noted this too).
- **On the MCP tool, `order` defaults to `"desc"` and cannot be omitted.** So `RANK_RULE`'s "without order, best first"
  never applies there: for a lower-is-better metric, the worst comes first unless the agent passes `asc`. This is
  documented, and the same as the league's `search_players`, but the served `rank_rule` describes a default this surface
  does not have.
- **`--repeat 0` with `--league` silently becomes one season** (`args.repeat or 1`). With `--catalogue --regenerate` it
  becomes six.
- **Boards come in the order of each level's first competition, not in level order.** Men's boards always come before
  women's (the verifier noted this too).
- **Carried from earlier rounds, unchanged:**
  - `catalogue_fingerprint` hashes label wording;
  - an unknown `country` gives an empty 200;
  - `/api/teams` ignores `scope`;
  - `/api/catalogue/matches` waits for the full metrics engine;
  - `store.repo_root` assumes where the index is;
  - pool ties share a rank on (percentile, value);
  - levels.md's two hand-written figures that docs.md corrects.

## Outside this lens, or Zaid's call (not judged)

- **Linux CI has not run this branch.** 52 of the 60 catalogue pins were re-recorded on macOS in levels.md, and the
  report tests and the level slow test have not run on Linux either. Nothing new reads libm or the clock: the new
  generator terms use detmath, and the dates never reach a draw. Still, the PR's CI is the first proof, and it should be
  green before the branch merges.
- **amateur_sprint_distance** now rests on S10 alone, a small-sided-games study. The full-match S9 finds no difference
  between second-tier professionals and fourth-tier amateurs. Counting it as an assumed order instead would change the
  counts in CLAUDE.md, the data README and criteria.md (verifier's item).
- **Extrapolations stated in the labels:** S10 compares amateurs with internationals but stands in for semi-pro men,
  and the U17 band is the spread across players used as a band for the mean.
- **The assumed order running distance U18 < U19 fails.** Execution sizes other than the women's are assumptions.
