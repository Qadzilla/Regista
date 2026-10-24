# Part A, phase 1: player attributes and bio

Built 2026-10-23 on `feature/terminal-engine`. All of it is synthetic: invented players, no real people's bios.

## What was built

- **Every one of the 108 league players** in `data/season/league.json` now has:
  - a `role` (the 4-3-3 slot from the kit number: GK, FB, CB, DM, CM, AM, W, ST),
  - a public **bio**: `date_of_birth` (ages 17-35 on 1 August 2026), `height_cm`, `preferred_foot`, `nationality`,
  - hidden **ratings** under `attributes`: `finishing`, `passing`, `vision`, `dribbling`, `defending`, `aerial`, `stamina`
    (1-99), `shot_stopping`, `handling`, `distribution` (keepers only, 1-99), `top_speed_kmh`, `acceleration_ms2`.
- **One seeded function makes them:** `regista.season.league.assign_attributes`, called from `new_league`. It uses its
  own random stream (league seed + 1000003), so names, squads and fixtures are unchanged. A test pins a hash of them
  recorded on `main`. The file's top has an `attributes` block (version, seed, age date, where the scales are written up).
- **Scales are written up** in `data/synthetic/README.md`, section "League players: bio and hidden ratings".
- **The bio is public and the ratings are not.** `people()` drops `attributes`. `/api/season` squads, `/api/players` cards
  and `/api/players/{id}` gain `age`, `height_cm`, `preferred_foot`, `nationality` (plus `date_of_birth` on the profile and
  squads). The MCP `get_profile` tool gains `bio`. The generator gets the ratings through `player_attributes(league)`.
- **A back-compat test** (`tests/test_backcompat.py`) checks byte-identical output. It hashes the events and tracks of 8
  generator runs that use no attributes against hashes recorded from `main` (e3da71d, in a detached worktree): the
  samples syn_0294/0141/0142, vision dev 201/202, fresh 301, the realistic profile (seed 77) and a league-shaped run whose
  squads carry ids and names only. It also checks the committed syn_0294 files byte for byte. It runs in about 2 s. It
  is there for the generator phase.

## How it was checked

- `tests/test_attributes.py` (11 tests, about 2.5 s):
  - every field is present and inside its range;
  - foot and nationality spreads;
  - the role shape (centre-backs top aerial and tallest outfielders, wingers top dribbling and speed, holding
    midfielders out-defend CM/AM/W/ST, strikers top finishing, attacking midfielders top vision);
  - a real spread within each role;
  - standouts at least 10 clear;
  - Toure the best finisher by 5 or more;
  - determinism and the committed file;
  - no hidden key in any public payload: `/api/season`, `/api/players`, the profile, moments, compare, the rules Scout
    answer, and the MCP `search_players` / `get_profile` / `compare_players` bodies.
- The league's 30 fixture fingerprints hash the same on `main` and here. Match generation does not read attributes yet,
  so no league match changed. The `regista.synth.report` bands are therefore untouched; this phase adds no metric that
  needs a band.
- The full suite passes: **679 tests** in 3 min 11 s.

## Numbers (league seed 2026)

| Role | n | fin | pas | vis | dri | def | aer | sta | top km/h | acc m/s² | height |
|---|---|---|---|---|---|---|---|---|---|---|---|
| GK | 12 | 16 | 52 | 39 | 28 | 30 | 58 | 54 | 29.0 | 2.7 | 190 |
| FB | 18 | 43 | 67 | 60 | 66 | 71 | 62 | 80 | 33.8 | 3.9 | 178 |
| CB | 18 | 36 | 61 | 50 | 43 | 77 | 81 | 68 | 32.5 | 3.7 | 189 |
| DM | 12 | 50 | 77 | 66 | 58 | 74 | 61 | 78 | 32.2 | 3.6 | 180 |
| CM | 12 | 58 | 77 | 70 | 64 | 62 | 59 | 79 | 31.9 | 3.5 | 181 |
| AM | 6 | 65 | 70 | 79 | 75 | 42 | 45 | 66 | 32.7 | 3.9 | 175 |
| W | 18 | 68 | 65 | 69 | 78 | 39 | 46 | 72 | 35.5 | 4.4 | 172 |
| ST | 12 | 75 | 59 | 61 | 70 | 36 | 69 | 69 | 33.8 | 4.0 | 182 |

- **Foot:** right 83, left 21, both 4.
- **Ages:** 18-35, mean 25.9.
- **Nationalities:** 25 countries; England 28 (26%), France 12.
- **Finishing among forwards:** Femi Toure (pl_bro_09) 93, Amari Ustinov (pl_ash_09) 85, then 76s.
- **Toure:** striker, 184 cm, left foot, 35.5 km/h, aged 27.

## Open issues

- **Sources for the scales:**
  - Top-speed ranges come from Opta / The Analyst (Premier League 2024-25).
  - Acceleration is anchored only on Wyscout's 3 m/s² threshold; the spread is our choice.
  - Heights by role are plausible choices, not taken from a published source.
  - The docs say all three plainly.
- **The ratings are readable** in the committed league file (public repo). The app never serves them; the file is how the
  league regenerates.
- **Nationality is drawn apart from the name** (names are random first/last combinations), so a name and a nationality
  can look mismatched.
- **No page shows the bio yet.** The API carries it; the Scout and profile pages can add it. Fabric's `players` table
  does not carry the bio either.
- **Bench players have ratings but never play** until the generator adds substitutions.
- **Ratings do nothing until the generator phase** wires them in.
