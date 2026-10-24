# Part A review B, round 2: football and data science

I reviewed `git diff main...HEAD` on `feature/terminal-engine` at 253c2e9 on 2026-10-24, with a football and data-science
lens. I changed no code. Everything here is synthetic: invented players in an invented league.

**Method.** I rebuilt the committed season from `data/season/league.json` with `load_metrics` and `Season.build`, ran
`python -m regista.synth.report --league`, counted outcomes straight from the events files, and read the definitions in
`season/metrics.py`. `python3 -m pytest -q` gives 743 passed, 8 deselected.

**Verdict: not signed off.** Round 1's fixes hold up. Two metric families, though, still have no band and sit far from
Premier League norms: shot accuracy with save %, and keeper distribution. Under the task's rule 4, a new metric with a
Premier League norm needs a band with its source.

## Round 1 fixes: checked

| Fix | What I saw |
|---|---|
| The report no longer changes the stream | Holds; a test pins it |
| Save % leaves penalties out | `sot_faced` and `saves` leave penalties out, and the definitions say so |
| Attempt minimums scaled by club minutes / 90 | shots 2, take-ons 2, aerials 4, challenges 3; each rule says so |
| One percentile rule | Profile and terminal agree for every outfield player on goals, key passes, interceptions, take-ons won, assists and tackles won. Keepers still differ (nit 2) |
| Centre-back aerials | CB 3.83 contests per 90 is now the most of any role (ST 3.44) |
| Progressive passes per carry | 1.47, within its 1.2-3.0 band |
| Cross completion | 0.207, within its 0.16-0.26 band |
| Centre-back running | 9.32 km and 591 m at 20 km/h or more per 90 |
| Decelerations per acceleration | 2.06 |
| Walking and jogging bands | Individual against individual now |
| PPDA and possession bands | 10.7-14.0 and 45.4-53.9%, in band |
| Leaders and Toure | Toure scores 4 goals from 3.5 npxG (+14%), a believable finishing edge. All 11 leader bands pass over three pooled seasons |
| Definitions | Progressive passes and carries (last-six-passes reference, defending-40% and defending-50% exclusions, into-box rule), key passes, SCA/GCA, PPA (set pieces out), Wyscout PAdj and the FBref percentile rank match the cited rules |

## Must fix

### 1. Too many shots hit the target; no band for shot accuracy or save %

Shot outcomes in the committed season (259 shots):

| Outcome | Count | Share of shots |
|---|---|---|
| Goal | 32 | 12% |
| Saved | 94 | 36% |
| Blocked | 49 | 19% |
| Off target | 84 | 32% |

- **On target overall.** 49% of all shots are on target.
- **Without blocked shots, the Premier League's way of counting.** 60% are on target. The Premier League reports 49.9% for
  2023/24, a record, and 45.1% over two decades (premierleague.com/news/4027257).
- **Keepers.** League save % is 76%.
- **The star.** Femi Toure has 15 shots on target from 22 shots, or 4.76 per 90. Real leaders manage about 2 per 90.
  `demo.js` praises him for this: "the most shots on target per 90".
- **Cause.** Of the shots that are not goals, 40% are saved before skill is applied (`on_target`, `generator.py` around
  line 1941, copied from the back-compat path's 0.4). The finishing term then pushes elite shooters higher.
- **Fix.**
  - Add sourced bands for shot accuracy without blocks, for save % (or goals per shot on target), and for the leader's
    shots on target per 90.
  - Retune the league-mode split only: the back-compat path stays untouched.

### 2. Keepers almost never kick long

Each keeper's launch % (open-play passes over 40 yards) runs from 0 to 6.5%, 2.7% across the league. Their average pass
length is 18-21 m.

- **What real keepers do.** In the CIES Football Observatory's 2022 study, even the Premier League's six most
  short-passing keepers sent under 30% of passes 40 m or more. League figures ran from 36% to 58%.
- **Why it matters.** `gk_launch_pct` and `gk_avg_pass_length` are in the keeper defaults and the similarity template,
  and they get percentiles.
- **Fix.** Band both against a Premier League keeper source and retune keeper distribution. Until then, take both out of
  the defaults and say they are not realistic.

## Should fix

1. **The season people see misses 5 of 11 leader bands.** The pooled three seasons pass, but the app shows only the
   committed season.
   - **Over the band:**
     - Toure's shots per 90: 6.98 against a ceiling of 6.18 (the best real player had 4.75)
     - Toure's touches in the box: 17.8 against 14.0
     - key passes: 4.62 against 4.54
     - xA: 0.59 against 0.51
     - interceptions: 2.99 against 2.96
   - **What to do.** Check the committed season's leaders in a test, or show the sample size beside them (item 3).
2. **Clean sheet % is counted on 30-minute matches.** Keepers show 50-80% (the Premier League runs about 25-35%). The
   label reads "Clean sheets / full matches played" and cites FBref CS%, with no word on match length. Say "30-minute
   matches" on the metric, or leave it out of the defaults.
3. **Small samples are not flagged.** A regular plays about 300 minutes, about 3.3 full matches. The verifier and the
   fixer measured split-half r near 0 within a role for aerial duels won, and about 0.04-0.29 for pressures, tackles and
   interceptions. These metrics still get percentiles, and `demo.js` makes claims from them. `pressure_regains` is a
   default midfield column.
   - Show the season's sample size on the terminal and on profiles.
   - Mark metrics whose split-half r is below about 0.3 as mostly noise in one season. `regista.season.audit.split_half`
     already computes r.
4. **Other new metrics have a Premier League norm but no band.** Several look off. Band them with read sources, or mark
   them as unchecked:
   - **Passes into the box:** 3.8 per team per 90, against my recollection of about 9 for FBref PPA.
   - **Pressure regain %:** 12.3%. I recall StatsBomb-era pressure success on FBref at about 30%; the definitions differ
     slightly.
   - **Take-on success:** 57%. I recall about 45% in Opta-era FBref.
   - **Pass completion by length:**
     - medium: 79%, against about 87%
     - long: 45%, against about 55%
   - **Touches:** 1,392 per team per 90, about twice FBref's. The definition says so, but the source column still reads
     "FBref Touches".

   These real-world figures are my estimates, not citations.
5. **Two "Shots" give different numbers.** The profile counts penalty kicks and the terminal does not, under the same
   label. This was left open in round 1. The fix is cheap: rename the profile's stat "Shots (incl. penalties)".

## Nits

1. **A note claims a tie as a lead.** `demo.js` calls Farid Vargas the midfielder with "the most tackles won per 90". He
   and Bruno Lindqvist both have 15, 0.2 minutes apart: 97th against 92nd percentile. Say "joint most".
2. **Keepers get percentiles for outfield stats.** The profile still gives keepers percentiles for goals, shots and the
   rest, from a pool of 6, where the terminal gives none. That is 6 differences per stat, against the claim of one rule.
3. **Scripts without a main guard crash.** `build_all` uses a spawn process pool, so a script that calls `load_metrics`
   without `if __name__ == "__main__"` re-runs itself in each worker and fails on racing `rmtree` calls. It happened to me
   while reviewing. Document it, or fall back to sequential when imported from `__main__` without a guard.
4. **xT is still mostly carries** (69% of xT added). This is an open issue already; label it on the xT metrics.
5. **PPDA leaves out challenges.** Trainor's original rule counts challenges (failed tackles); this one counts tackles,
   interceptions and fouls. The definition states what it counts, so it is honest, but it is lighter than the cited rule.
6. **Toure is top scorer in only 4 of 12 seasons.** The committed season was picked among global settings because he is
   top in it. This is disclosed in `review-fixes-1.md`; say it plainly in the PR body for Zaid.
