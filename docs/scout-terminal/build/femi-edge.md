# Femi Toure's edge: the league's clear star

Built 2026-10-24 on `feature/terminal-engine`. Zaid's decision: make Femi Toure (`pl_bro_09`) clearly the league's star.
Everything here is synthetic: invented players and simulated matches.

## The problem

In the committed season (generator 0.7.1), Femi Toure was top scorer by only one goal:

- He scored 3 goals, one a penalty. Amari Ustinov, Milan Brennan and Kenan Petrov scored 2 each.
- Ustinov led non-penalty goals per 90 (0.67 against 0.60) and npxG per 90 (0.67 against 0.56).

Over six pooled seasons Femi already led npxG per 90 by 1.71 times. The band's ceiling is 1.75, so there was almost no
room to give him more chances. The extra edge had to come mostly from **turning chances into goals**, and no match could
be rigged.

## What changed

Only Femi's hidden ratings changed. They are stored as `STAR_RATINGS` in `src/regista/season/league.py`, and the
league file's attributes version went from 1 to 2.

| Rating | Before | Now | What it does in the generator (it works the same way for every player) |
|---|---|---|---|
| finishing | 97 (the standouts' cap) | **99**, the league's only 99 | more of his shots go in (`goal_probability`), he shoots more from close in (`shot_drive`), teammates look for him near goal (`find_finisher`, `cross_finisher`) |
| dribbling | 66 (drawn; the striker mean is 70) | **72** | he carries the ball toward goal more often and faster (`carry_drive`, `carry_pace`), loses it less (`lose_dribbler`), and tries more take-ons |

- **What stayed the same:**
  - The generator: still 0.7.1, with no code or tuning changes.
  - Every other player's ratings: `STAR_RATINGS` is applied after the draws and the standouts.
  - His public bio.
  - Names, squads and fixtures.
- **Brookfield's 10 fixtures changed. The other 20 are byte-identical.** `season/pins.py` was re-recorded for those 10.
- **Back-compat holds.** `generate()` without ratings is byte-identical to `main` (`tests/test_backcompat.py`, 9 passed).
- **Cross-platform determinism is unchanged:** the same `detmath` code paths run, and CI checks the pins on Linux.

### How the pair was chosen (stated plainly)

Any change to Femi's ratings re-draws Brookfield's 10 matches, so the committed season is one draw. I tried **13
Femi-only rating sets** on the committed season:

- finishing 99 on its own;
- aerial raised to 80 or 87;
- dribbling at 66, 68, 70, 72, 74 or 78;
- some of these combined.

Four sets made him top scorer by two or more **and** leader in both per-90 charts:

- finishing 99 with dribbling 72;
- finishing 99 with dribbling 74, aerial at 66 or 87;
- finishing 99, dribbling 78 and aerial 87.

I chose the smallest of the four that also keeps every six-season band:

- **Dribbling 78** pushed his npxG lead over 12 seasons to 1.84 times the next player, above the band.
- **Dribbling 74** left the six-season leader npxG low (0.58 per 90, below the band's 0.61).
- **Dribbling 72** passes every band.

So the committed season is a **favourable draw**, chosen from a small set of principled options. It was not designed
match by match. How often these ratings give this result is below.

## His numbers and the next best players

### The committed season (what the app serves)

The terminal's own figures (`regista.season.metrics`), with a qualifying pool of 100.5 minutes (18 regular forwards):

| Per 90 | Femi Toure | Next best | Third |
|---|---|---|---|
| Goals | **1.64** (5 in 274 min) | Amari Ustinov 1.04 (3 in 261) | Leon Whitfield 1.03 (3 in 263) |
| Non-penalty goals | **1.64** (5; no penalties) | Amari Ustinov 1.04 (3) | Leon Whitfield 1.03 (3) |
| npxG | **1.15** (3.51) | Amari Ustinov 0.77 (2.22) | Emeka Dubois 0.53 (1.79) |
| Shots | **6.23** (19) | Amari Ustinov 4.49 (13) | Gino Reyes 4.31 (14) |
| Shots on target | **2.95** (9) | Leon Whitfield 2.05 (6) | Gino Reyes 1.85 (6) |
| Non-penalty goals minus xG | 0.49 (+1.49) | Leon Whitfield leads with 0.69 (+2.01) | Milan Brennan 0.32 |

- **Top scorers** (`python3 -m regista.season.audit`): Toure 5, Ustinov 3, Leon Whitfield 3, Haruki Adeyemi 2, Milan
  Brennan 2. He leads by two.
- **His goals:**
  - round 1 at Eastwick, 6' (5.6 m) and 56' (4.4 m, a headed shot after his own carry);
  - round 6 against Eastwick, 49' (15.9 m);
  - round 8 against Fairhaven, 6' (11.4 m, after a 13.9 m carry into the box);
  - round 10 against Ashby, 8' (8.1 m).
- Every goal is assisted, and four of the five come from inside 12 m.
- His Goal reel (on the ball, match order) runs **42.2 s**, rendered locally at 1280 wide.
- **His npxG lead is 1.49 times the next player.** That is closer to the Premier League's 1.28 (Haaland 1.04 against
  Isak 0.81, the report's source) than the six-season ceiling of 1.75.
- **Still a weakness:** he won 1 of his 14 take-ons. The dashboard seeds keep that as his "Concerns".

### Six pooled seasons (`python3 -m regista.synth.report --league --repeat 6`)

| | Femi Toure | Next best | Band (source) | Before |
|---|---|---|---|---|
| npxG per 90 | 0.74 | Amari Ustinov 0.48 | leader 0.61-1.22 | 0.79 |
| npxG gap (leader / second) | **1.56** | | 1.0-1.75 (Premier League 1.28) | 1.71 |
| Goals per 90 | 1.18 (22 goals in 1,672 min, 18 non-penalty) | Amari Ustinov 0.63 (11) | leader 0.61-1.64 | 0.93 |
| Goals gap | **1.88** | | 1.0-2.0 (Premier League 1.13) | 1.66 |
| Non-penalty goals per 90 | 0.97 | Amari Ustinov 0.63 | no band | 0.67 |
| Shots per 90 | 5.17 | Amari Ustinov 3.14 | leader 3.09-6.18 | 5.06 |
| Top npxG share (of his club's) | 0.337 | | 0.20-0.40 (Haaland 35.5% of Man City's) | 0.382 |

- **His finishing over the six seasons:**
  - He scored 18 non-penalty goals from 13.80 npxG, 30% above xG.
  - What his ratings lead you to expect is 16.2 (18% above): 24% above xG on shots with his feet, slightly below xG on
    headers (aerial 66). The rest is luck.
  - The model is unchanged: a top finisher beats xG by about a quarter on his foot shots.
- **Not an impossible outlier.** 0.97 non-penalty goals per 90 is about Haaland's 2022/23 rate (29 non-penalty goals in
  about 2,770 minutes, roughly 0.94; our arithmetic). His npxG lead fell from 1.71 to 1.56, closer to Haaland's 1.28.

### How often these ratings give a season like this (24 regenerated seasons, seeds shifted by 1000)

| In a season | Now | Before |
|---|---|---|
| Outright top scorer | 11 of 24 | 6 of 24 |
| Top scorer by two or more | 10 of 24 | 3 of 24 |
| Leads non-penalty goals per 90 (100+ min) | 12 of 24 | 5 of 24 |
| Leads npxG per 90 (100+ min) | 17 of 24 | 11 of 24 |
| All three (the committed season's result) | 8 of 24 | 2 of 24 |
| Pooled npxG per 90, leader / second | 0.748 / 0.495 (1.51) | 0.711 / 0.505 (1.41) |
| Pooled non-penalty goals per 90, leader / second | 0.997 / 0.581 | 0.697 / 0.568 |

A Regista season gives a regular about 300 minutes, so who tops the scoring chart is partly luck in any season. The
ratings roughly quadruple his chance of all three, but they do not guarantee it.

## Realism

- **Six seasons pooled: every band holds.** That is 13/13 event rates, 11/11 league-mode, 14/14 physical, 4/4 team
  style, 14/14 individual leaders and 8/8 role shapes.
- **One season (indicative, as before):**
  - 13/13 event rates, 14/14 physical, 4/4 team style, 8/8 role shapes.
  - League-mode is **10/11**: penalties are low, with one in the season (Brookfield's matches no longer have Femi's).
    Penalties are a verdict only over six seasons.
  - Individual leaders are **12/14**, with two high, both indicative:
    - leader shots per 90 is Femi's 6.23, against a ceiling of 6.18;
    - top npxG share is his 46% of Brookfield's npxG, against 0.40.
  - Before, the two high ones were the interceptions leader and a 0.43 top npxG share.
- **The reviewers' earlier concern** was that the star should not be the league's only scoring threat:
  - Over six seasons he takes 34% of his club's npxG (it was 38%), and his npxG lead is 1.56 (it was 1.71). Both are
    in band and lower than before.
  - In the committed season alone his 46% share is high. One season is indicative only, and the report says so.

## Artifacts regenerated

- `data/season/league.json`: attributes version 2, and Femi's finishing and dribbling.
- `src/regista/season/pins.py`: Brookfield's 10 fixture hashes.
- `tests/test_league_mode.py`: the full hash of `rl_r01_eas_bro`, and the penalty fixture, now `rl_r04_dun_bro`.
- `data/season/summaries.json` (102 players, rules, from scratch) and `data/season/reliability.json`.
- `src/regista/static/shared/demo.js` (the dashboards' seeds):
  - his clips: five goals and two failed take-ons;
  - "Five league goals, two more than anyone", "in four different matches", "none from the penalty spot";
  - "you carry it into the box yourself and finish" (the round 8 clip);
  - "four of his five goals from inside 12 metres", "one of his fourteen take-ons";
  - Priya's message is now about his two goals at Eastwick in round 1;
  - shortlist ranks: Delgado 4th for take-ons won, Ustinov 2nd for shots, Mensah 9th for key passes; Vargas is still
    3rd for passes.
- `src/regista/cloud/foundry.py`: the Scout agent's example answer is now Haruki Fontaine, 2.5 per 90 (8 in 288 minutes).
- `docs/realism-report.md`: the season section regenerated, and the summary table updated.
- `docs/demo-storyboard.md`:
  - beat 1: five goals, a 42.2 s reel, and the 56' goal not called a header;
  - beat 7: **Sami Okafor (Calder Town), 12.82 recoveries per 90 (42 in 294.8 minutes)**, the rules Scout's answer now.
    Amari Haddad is 2nd with 11.58.
- `data/synthetic/README.md` and `CLAUDE.md`: the star's ratings and the new numbers.

## Tests

- **New:**
  - `test_femi_tourés_edge_in_the_terminal` (quick suite, so CI runs it on Linux): in the terminal he leads goals,
    non-penalty goals and npxG per 90, he is two or more goals clear, and his npxG lead is inside the band ceiling.
  - `test_femi_toure_is_the_leagues_top_scorer` (slow) now requires two clear.
  - `test_attributes` pins `STAR_RATINGS` and checks that he is the league's only 99 finisher.
- **Updated:** the dashboard seed tests check every new claim against the league: the counts, the ranks, the round 8
  carry ending in the box, the goal distances, and the two goals in round 1.
- **Results on the Mac (Python 3.13):** 798 passed, 13 slow passed, `tests/test_backcompat.py` 9 passed.
- **CI on Linux (Python 3.11, numpy 2.4.x), commit ec47e56:** both runs green.
  - Push run: https://github.com/Qadzilla/Regista/actions/runs/40132000170
  - PR run: https://github.com/Qadzilla/Regista/actions/runs/40132001275
  - 797 passed, 1 skipped.
  - The image's smoke test printed `{"check": "season-pins", "ok": true, ..., "differs": {}}`, so Linux
    generates the same season.

## Open issues

- **Microsoft Fabric** still holds the 0.7.0 season, so it is now two changes behind. Run
  `python -m regista.season.fabric push` and `check` before storyboard beat 5 is recorded. This job did not touch
  Fabric.
- **The committed season is a favourable draw** (8 of 24 seasons give all three). Any later generator change re-draws it,
  and the new tests will then fail until he leads again or the decision is revisited.
- **One-season indicative highs** (his shots per 90 and his 46% npxG share) and **low penalties** in the committed
  season. Six seasons are in band.
- **Open findings from review closing round 3** remain: corners, the headed-shot rate, progressive passes and
  `cross_choice`. His round 1 goal at 56' is one of those headed shots after his own carry.
- **Merging PR #36 and deploying** are left to the orchestrator and Zaid. After the deploy, re-check beats 1, 5 and 7
  on the live app (five goals and a 42.2 s reel; Sami Okafor).
