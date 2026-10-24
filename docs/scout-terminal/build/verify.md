# Part A verification (independent)

Checked on 2026-10-23 against `feature/terminal-engine` at 93290f4 (four builder commits on top of `main` e3da71d). Main was read from a
detached worktree in the scratchpad, which was then removed. I re-ran every check myself and did not take the builders'
numbers on trust. Everything here is synthetic: the Regista League's players, clubs and matches are generated.

**Verdict.** Part A holds up.
- **Back-compat:** output without ratings is byte-identical to main.
- **Realism:** the league sits in every band (13 event, 5 league, 11 physical), for one season and for three pooled.
- **Femi Toure:** top scorer with 10 goals.
- **Players now differ:** within a role, most stats repeat from one half of the season to the other.
- **Metrics:** ten of the engine's metrics matched my hand recomputation exactly.
- **Ratings:** none reach any API payload.
- **Tests and server:** the suite passes, and the server and its pages work offline.

I made three small fixes (below). The open problems are listed at the end.

## 1. Back-compat (byte for byte against main)

I wrote a separate hashing script and ran it once with main's `src` and once with this branch's. Each run used the tree's
own `league.json` for the friendlies. Both runs hashed the same 38 cases, and every events hash and tracks hash matched:

- **Committed samples:** syn_0294, syn_0141 and syn_0142, with the same arguments as their manifests (demo profile).
- **Vision matches:** all 10 training seeds (101-110), all 6 development seeds (201-206), all 3 fresh seeds (301-303), and
  six event-spotter training seeds (121-126). Each used exactly the `MatchSpec` that `regista.vision.dataset.make_match`
  passes. Seed 201 is the source of vis_0201.
- **Realistic profile:** the CLAUDE.md demo seed (77, 45 min × 2), plus seeds 21, 22 and 23 (30 min).
- **Demo profile:** seeds 5 and 6.
- **Player-view friendlies:** `friendly_kwargs` and `roster_for` for Brookfield v Ashby and Eastwick v Calder. They call
  `generate_kwargs(ratings=False)` and use profile demo, so their footage keeps the format the vision layer was trained on.

**CLI check.** I also ran `python -m regista.synth` for 294, 141, 142 and the seed-77 demo on both trees. `diff -r` of the
output folders (events, tracks, clips, manifest) is empty. The committed events.jsonl and tracks.jsonl of all three samples
equal the regenerated ones. The committed clips.jsonl files differ from what the CLI writes on main as well as here, because
they carry the labels Foundry wrote. That is old and is not a regression.

**Determinism.** The same league and seed give the same match within a process and across processes with
`PYTHONHASHSEED` set to 1, 77 and random. The six built match folders I checked equal a fresh `generate()` exactly.

**Tests.** `tests/test_vision.py`, `test_vision_demo.py`, `test_backcompat.py` and `test_player*.py` gave 98 passed.

## 2. Realism

**`python -m regista.synth.report --league`, committed season.** All 13 event bands are in band, all 5 league-mode bands and
all 11 physical bands. With `--repeat 3` (90 matches), all 29 are in band. The realistic profile's own report (seeds 21-23,
30 min) gives 11 of 13 on both main and here, so nothing changed there.

**Sources checked against the pages themselves:**
- **The Analyst, PL 2024/25 (OA-PHYS):** every figure the bands quote is on the page. Murillo 8.5 km per 90 is the
  lowest regular, Kulusevski 12.3 the highest, Yarmoliuk 12.9 (600+ min). Outfield walking time runs from 54.2% (Soucek)
  to 77.6% (Cunha). Soucek's jogging share is 34.7%. Van de Ven is the only player above 37 km/h. Robinson has 702 sprints
  (the article is dated 23 March 2025).
- **Bradley 2023, Part 2 (FIFA-PHYS):** the team figures are on the page: 108.1 ± 3.6 km, 9,001 ± 850 m at 20 km/h and
  above, 2,345 ± 314 m at 25 km/h and above.
- **Systematic review (HSR-REV):** about 760 m (618-1,001) above 19.8 km/h and about 200 m (153-295) above 25.1 km/h are
  quoted correctly.

**Two band notes were wrong; both are fixed in `regista.synth.report`:**
- The sprints note said Chmura 2017's 33 ± 11 sprints a match used "a lower threshold". The review's table gives
  above 25.2 km/h, which is slightly higher. The note now says so.
- The lowest-regular-distance band starts at 7.5 km, below the source's 8.5, and did not say that. The note now says the
  lower bound is ours and that anything under 8.5 is lower than any Premier League regular.

## 3. Femi Toure and the demo story

| Player | Goals | Penalties | Shots | npxG |
|---|---|---|---|---|
| Femi Toure (pl_bro_09) | 10 | 1 | 35 non-penalty | 4.37 |
| Amari Ustinov (next) | 6 | 1 | 35 | 4.35 |
| Third place | 3 | | | |

The audit gives these numbers. Toure's profile (`/players/pl_bro_09`) shows the same story:
- 10 goals in 279 minutes, 3.23 per 90, "best of the league's forwards"
- a goal evidence item for each of the 10 goals, each with its clip
- eight goal moments in the Best moments list (rounds 1, 3, 4 and 6)
- the summary sentence, and a 40-moment reel

This matches `demo.js`'s pinned clips (r01goal6 and the others). One caution: 3.2 goals per 90 is far above any real player
(see Problems).

## 4. Do players differ? Split-half reliability within kit slots

This uses the audit's method: per-90 rates in rounds 1-5 against rounds 6-10, centred on each kit slot's mean, then
correlated over the 66 starters. "Before" is main's league (its own generator and `league.json`), regenerated by me and
scored with the branch's `split_half` code. regista-data.md's table agrees with it wherever both report a stat. I also
centred on club as well as slot, to check that team strength is not doing the work. It is not: the values barely move.

| Stat | Before (main) | After, 1 season | After, slot + club | After, 3 seasons pooled |
|---|---|---|---|---|
| goals | -0.36 | 0.47 | 0.47 | 0.63 |
| xG (non-penalty) | -0.28 | 0.48 | 0.46 | 0.65 |
| key passes | -0.06 | 0.45 | 0.44 | 0.77 |
| take-ons | -0.11 | 0.13 | 0.19 | 0.31 |
| tackles | 0.16 | 0.39 | 0.34 | 0.22 |
| pass completion % | 0.10 | 0.16 | 0.14 | 0.28 |
| distance | none (no physical model) | 0.50 | 0.58 | 0.81 |
| passes | -0.06 | 0.73 | 0.74 | 0.91 |
| shots | -0.08 | 0.32 | 0.32 | 0.68 |
| interceptions | 0.00 | 0.76 | 0.79 | 0.84 |
| high-intensity distance | none | 0.55 | 0.62 | 0.81 |
| sprints | none | 0.74 | 0.73 | 0.85 |
| top speed (mean of match peaks) | none | 0.68 | | 0.86 |

- **Volume stats:** these now repeat. A ranking between two players in the same role carries signal.
- **Weak stats:** take-ons, tackles and pass completion % stay weak. Tackles fall from 0.39 to 0.22 when three seasons
  are pooled, so the single-season 0.39 was partly luck.
- **No signal:** aerial duels won (-0.08) and pressures (0.05) show none within a slot.

## 5. Physical, by role

These come from the committed season's physical records, per 90, for regulars (at least 40% of the most minutes anyone
played).

| Role | n | km per 90 (range) | ≥ 20 km/h, m | ≥ 25 km/h, m | Sprints | Mean match peak, km/h | Fastest, km/h |
|---|---|---|---|---|---|---|---|
| GK | 6 | 4.0 (3.9-4.1) | 21 | 3 | 0.1 | 21.0 | 28.3 |
| FB | 12 | 9.4 (9.2-9.6) | 658 | 220 | 13.1 | 31.8 | 35.1 |
| CB | 12 | 8.0 (7.75-8.45) | 300 | 76 | 4.5 | 28.4 | 33.6 |
| DM | 6 | 10.9 (10.6-11.3) | 733 | 143 | 9.0 | 29.6 | 34.1 |
| CM | 6 | 11.2 (10.9-11.7) | 802 | 170 | 10.5 | 29.4 | 33.1 |
| AM | 6 | 10.3 (9.7-11.1) | 1125 | 239 | 14.5 | 29.8 | 34.1 |
| W | 12 | 9.6 (8.9-10.4) | 986 | 319 | 18.5 | 33.2 | 36.0 |
| ST | 6 | 9.5 (9.2-9.8) | 899 | 256 | 15.7 | 31.0 | 34.3 |

**The shape is right.** Central midfielders run most, wide roles cover the most distance at 20 km/h and above and are
fastest, and centre-backs run least. The league's fastest (36.0 km/h) is under van de Ven's 37+.

**Nothing impossible:**
- No match peak exceeds the player's own top-speed rating (0 of 889 records).
- The highest single-match rate is 13.3 km per 90.
- In two matches' 1 Hz tracks (53,680 steps), only 3 imply more than 38 km/h. All three are substitutes appearing, which
  is placement, not running (see Problems).

**Where it is unlike the Premier League:**
- Centre-backs average 8.0 km per 90, and every one sits below the PL's lowest regular (Murillo, 8.5).
- Centre-backs' 300 m at 20 km/h and above is under the World Cup's 0.5-0.8 km for central roles.
- Full-backs (9.4 km) are also low.

## 6. Metrics: hand recomputation, evidence, hidden ratings

**Hand recomputation.** I wrote my own pass over the raw events.jsonl files. It does not import `regista.season.metrics`.
Its rules follow the catalogue's written definitions. I recomputed 10 metrics for Femi Toure (FW), Kenan Nakamura (AM)
and Sami Popescu (DM, Fairhaven), plus save % for Brookfield's keeper and PPDA for Brookfield and Fairhaven:
- non-penalty xG
- xA
- shot-creating actions
- progressive passes
- pressure regains
- possession-adjusted tackles + interceptions
- distance per 90
- season top speed
- save %
- PPDA

Minutes, which I computed separately from the substitution and red-card events, matched as well. All 29 values match the
engine to floating-point precision.

| | Toure | Nakamura | Popescu |
|---|---|---|---|
| minutes | 279.06 | 242.33 | 294.11 |
| npxG per 90 | 1.409 | 0.214 | 0.000 |
| xA per 90 | 0.028 | 1.298 | 0.104 |
| SCA per 90 | 4.52 | 11.51 | 2.14 |
| progressive passes per 90 | 2.58 | 12.26 | 5.20 |
| pressure regains per 90 | 0.00 | 1.49 | 3.06 |
| Tkl+Int per 30 min opponent possession | 0.32 | 1.82 | 3.32 |
| distance per 90 | 9,650 m | 10,540 m | 10,809 m |
| top speed | 34.3 | 32.7 | 31.9 |

- **Save %:** Brookfield's keeper (pl_bro_01) has 14 saves from 16 shots on target faced, with 2 goals conceded: 87.5%.
- **PPDA:** Brookfield 15.31, Fairhaven 18.57.

**Toure's 0 pressure regains.** His 64 pressures never led to a regain within 5 s; the nearest came 5.1 s after the
pressure. That fits chance, since regains are rare for forwards (Ustinov 7 of 68). It is not a bug.

What this proves is that the engine computes and aggregates what its definitions say. It does not prove the definitions
are the providers' own; the definitions match the FBref, StatsBomb and Wyscout wording quoted in the catalogue.

**Evidence links.** I followed 309 evidence items: 11 metrics for 4 players, up to 50 items each.
- Every `event_id` exists in its match with the stated `t`.
- All 269 items that carry a clip resolve to a clip in `/api/matches/{id}/clips`.
- Every `link` opens that match and clip.
- The 40 items without a clip carry a match link.
- One `video_url` rendered on demand: 200, video/mp4, 485 KB, in 1.3 s.

**Hidden ratings.** I scanned 422 JSON responses for any key named after a hidden rating or `attributes`: every player's
profile, metrics, form and similar endpoints, every club's style, plus screen, rank, scatter, compare, season, players and
metrics. None was found. Built match files and match headers carry no ratings either.

## 7. Suite and offline server

- **Full suite:** 736 passed, 5 deselected before my fixes. After them, 737 passed, 5 deselected: one new test, and the
  rest unchanged.
- **Server:** `REGISTA_DOTENV= uvicorn regista.api:app --port 8151` starts offline. These answer 200: `/`, `/me`,
  `/scout`, `/players/pl_bro_09` and `/studio`, every static file those pages load, and all nine new terminal endpoints
  plus the existing season ones. Hot terminal queries take 1-16 ms; the first `/api/metrics` takes 0.9 s.
- **Browser:** I loaded the four pages in the browser pane. None logged a console error. The profile, `/me` and `/scout`
  render Toure's season.

## Fixes made (committed with this report)

1. **`src/regista/synth/report.py`:** corrected the Chmura threshold wording, and said plainly that the 7.5 km lower bound
   of the lowest-regular band is ours, below the source.
2. **`src/regista/static/player/profile-view.js`:** the profile showed "39% aerial duels won %" with no counts, because
   the renderer's RATIOS map lacked the new `aerial_win` ratio. It now reads "39% aerial duels won (7 of 18)", checked in
   the browser. A new test, `test_every_profile_ratio_has_its_count_and_words_in_the_renderer` in
   `tests/test_player_page.py`, fails on the old file.

## Problems (not fixed)

1. **Distances are low.**
   - The league's outfield mean is 9.65 km per 90, near the bottom of its 9.5-11.5 band.
   - Every regular centre-back (7.75-8.45 km) is below the PL's lowest regular (8.5), and the band only passes because its
     floor is ours (now labelled).
   - Centre-backs' 300 m at 20 km/h and above is under the cited central-role range.
   - Walking (59.8%) and jogging (33.2%) sit at the PL's extremes: the average synthetic player jogs like the league's
     highest jogger.
   - The physical builder found that raising distance broke the event bands. This needs a motion retune, not a band change.
2. **Toure's 3.2 goals per 90 is not credible for one player.** The league totals are fine. Thirty-minute matches force
   the edge; longer matches would make individual rates honest.
3. **Some stats still do not tell players apart within a role:** aerial duels won, pressures, take-on volume,
   pass completion % and tackles. Aerial duels won is about 0 even pooled. Shown as percentiles, these are mostly noise
   for now.
4. **The profile and the terminal give different percentiles for the same stat.** For Toure: key passes "higher than 6%"
   on the profile against 8th in the engine, and take-ons won 29% against 23rd. The rules differ (scout.py versus
   FBref's). Unify them when profiles adopt the engine.
5. **Save % counts penalties in shots on target faced.** I could not confirm whether FBref's Save% excludes them. Worth
   checking, since the catalogue names FBref as the rule.
6. **Placement jumps.**
   - Substitutes and some placements still jump in the 1 Hz tracks: 3 of 53,680 steps imply more than 38 km/h.
   - Strikers log 79 m per 90 of `relocated_m`, against 12-22 m for other outfield roles.
   - These are excluded from distance, but a tracks-based speed check would see them.
7. **Builders' open issues.** Those still standing that I re-saw, without re-measuring:
   - progressive carries are high (about 60 per team per 90, 92% of xT added)
   - penalty conversion is 1.0 in the committed season (19/22 pooled)
   - the player summaries are rules-engine only until `summarise --cloud` is run
8. **Gitignore.** `.gitignore` still ignores `docs/scout-terminal/build/`, so these reports need `git add -f`.
