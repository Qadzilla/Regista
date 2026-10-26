# Catalogue closing fixes, round 2

Two should-fix findings from closing review round 2 (review A: design.md citations; review B: the heavy-touch
denominator). Both are wording only: nothing regenerated, England semi-pro men untouched (league.json, SEASON_PINS,
Femi Toure's 5 league goals), no code changed.

## 1. design.md §10's realism table no longer cites sources for orders they do not support

Checked against the served orders in `src/regista/catalogue/realism.py` (`ORDERS`) and `docs/catalogue/realism.md`.

- **Amateur row.** Was "sprint distance per 90 below semi-pro [S9]; pass completion below semi-pro [S10]". Now: pass
  completion lower and ball losses higher than semi-pro, a direction extended from [S10] (amateurs against
  internationals, small-sided games), not reported at these levels; the sprint order is an **assumed order** (no
  published band), against [S9] (no difference in sprinting between second-tier professionals and fourth-tier
  amateurs) and [S15] (none in match maximal speed between first-division professionals and fourth-division elite
  amateurs). This matches `amateur_sprint_distance` (`basis: "assumed"`, `contrary`), `amateur_pass_pct` and
  `amateur_ball_losses` (`extends`), and the corrected line 366 of the same document.
- **Women vs men row.** The >= 20 km/h order now cites [S1] only (S2 has no men), as `women_hi_distance_*` serve it.
  The pass-completion order cites [S1, S12] with its 8-point gap check, as served; the second-half drop is marked
  "not checked" (it is in `NOT_CHECKED`: the engine's metrics do not split halves).
- **Academy row.** Distance per 90 U17 < U18 is sourced [S8] (S8 covers U13-U18); distance U18 < U19 < U20 < senior and
  the whole peak-speed order U17 to senior are **assumed orders** ([S5, S6] stop at U17; peak speed holds by
  construction since the youth speed scales are interpolated), as `youth_distance`, `youth_distance_extension` and
  `youth_peak_speed_mean` serve them.
- A line above the table now says the served checks (`docs/catalogue/realism.md`, `regista.catalogue.realism.ORDERS`)
  supersede the design table where they differ.
- [S15] (Djaoui, Chamari, Owen, Dellal 2017, doi:10.1519/JSC.0000000000001642) was served by realism.py but missing
  from design.md's source list; it is added there.

## 2. The heavy-touch count is on the 60 catalogue matches, not 89

Recounted on the local `data/catalogue/matches/`: 89 folders, of which 60 are named in a competition file and 29 are
not (their manifest dates run 2026-10-31 to 2027-05-22, after the as-of date; pre-date-fix builds). The 60 current
matches hold all 597 heavy touches; the 29 stale ones hold 0. `data/synthetic/README.md` now reads "on the 60
catalogue matches (2026-10-25) 157 of 597 heavy touches (26%)"; fixes-close1.md section 1 carries the same correction
with a dated note.

Not done: the 29 stale local folders were left in place (git-ignored build output; deleting files was optional and is
left to Zaid: `data/catalogue/matches/` folders not named in `data/catalogue/competitions/`).

## Tests

Quick suite: 980 passed, 15 deselected. Slow suite: 15 passed. tests/test_backcompat.py and
tests/test_catalogue_backcompat.py untouched and green.
