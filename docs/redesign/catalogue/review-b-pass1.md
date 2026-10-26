# The catalogue UI port: independent review B, pass 1

Branch `ux/catalogue` at bc4ae69. The diff reviewed is `git diff feature/catalogue...HEAD`: 60 files, 12 commits.
Written 2026-10-26.

**Lens:** product and data honesty.
- Does the app match the approved sandbox (words, layout, flows) at both widths?
- Do the numbers match the API, with their pool and sample?
- Is there one ranking rule?
- Are small pools, warnings and noisy marks visible?
- Is Femi Toure's basis stated?
- Is it demo-worthy and plain?

**How I checked.**
- My own server on port 8237: `REGISTA_DOTENV=`, `REGISTA_READONLY=1`, a scratch feedback folder, and the repo's
  `data/player` store, read only. I stopped it when I was done.
- The built-in browser at 1440 and 375 px, in one tab. I switched that tab between the app and the sandbox at :8060.
- curl reads against the same server.
- I wrote nothing to the live app, Azure or Fabric, and changed no code.

**Verdict: not signed off.** Two findings should be fixed. Nothing must be fixed. Most of the port matches the
sandbox and the API closely, and the verifier's checks hold up where I repeated them.

## Should fix

### 1. Profiles mix shots with and without penalties on one page

**What happens.** The profile tiles and "Every number in this competition" use the profile engine's counts.
- Those counts include penalty kicks (`season/profiles.py` labels them "Shots (incl. penalties)", "Shots on target
  (incl. penalties)", "Saves (incl. penalties)").
- The app removes "(incl. penalties)" from the labels (`profile-view.js` `clean()`, `scout.js` lines 97, 1070, 1106).
- The ratio rows on the same page now come from the metrics engine (B3: "every ratio equals its METRIC_OF metric"), and
  that engine leaves penalties out.
- Find players, the Terminal and the agent rank on the metrics engine's `shots`, which also leaves penalties out.

**Example: Pavel Petrov (`/players/pl_dun_10`), who took the league's only penalty.**
- "Every number in this competition" reads Shots 4 (1.41 per 90, 53rd) and Shots on target 2.
- Two rows above, the page says "33.3% of shots on target (1 of 3)".
- Find players gives him 1.06 shots per 90 (3 shots), 44th percentile.

So one page, unlabelled, shows two shot counts.

**Why it matters.** In the sandbox the ratios were the profile engine's, so the page agreed with itself. B3 moved the
ratios to the metrics engine and left the counts where they were.

**Reach.** It affects every player who took a penalty (league round 4, plus 5 catalogue matches). It also affects
keepers' saves wherever a penalty was saved.

**Fix, either way:**
- keep "(incl. penalties)" wherever a number includes penalties, or
- serve the metrics engine's `shots`, `shots_on_target` and `saves` cells for these tiles, as B3 already does for
  passes. That gives one number everywhere.

### 2. Best moments on profiles lost the match clock

**What happens.**
- The sandbox's moment line reads "ON THE BALL · ROUND 1 · 05:48": the clock the clip's scoreboard draws, worked out
  from `periods`.
- The port map (§1, "Minutes") says moment cards show that clock.
- The app's line reads "On the ball · Round 1" and nothing more.

**Cause.** `profile-view.js` `minuteOf()` reads `m.minute`. The profile's moments carry `t` but no `minute`
(`/api/catalogue/players/pl_bro_09?include=profile`: `minute` is null on every moment). So nothing is printed.
`pages-profiles.md` says the engine's minute would show here. It does not.

**Why it matters.** Zaid kept the engine's minutes, so titles read "dribble at 58'" in 2 x 15-minute matches. The clock
next to the title is what ties the title to the video. The Clip view's cards and stage already show it ("ON THE BALL ·
58:05", "49:49–49:54"). Only the profile, the page the demo opens on, lost it.

**Fix.** Print the clock from `t` and the match's periods, as `product/app.js` `clockOf` does. Or have the API add
`minute` to profile moments.

## Checked and matching

**Find players (1440 and 375).**
- Filters and summary line as in the sandbox.
- Boards hold one level each. "None yet · 10 of the 12 … have none" is listed last with no place, and each board ends
  with its "20 of the 110 … have any goals so far" line.
- Pool lines read "98th percentile among 33 semi-pro men forwards".
- Small-pool flags carry their reasons.
- Femi Toure: 1.64, 98th of 33, 10 matches, 274 minutes. This matches `/api/catalogue/players`.

**Scout agent (rules engine).** "Who are the best U19 dribblers up front?" returns Hector Santos, 5.31 take-ons won per
90, 97th of 16. The answer shows what it understood, "Answered by Regista's rules", the ≈ legend and the steps.

**Femi Toure's profile.**
- Header, career, summary, the six tiles with pools, ratios, similar players and matches all match the sandbox word for
  word, apart from items 1 and 2 above and the ≈ marks (Zaid's decision).
- "These numbers count the Regista League fixtures only (10 matches)."
- My store has no done upload record for the friendly, so the "not counted" sentence did not appear here. The verifier's
  store had one, and that run shows it. The code adds `r.basis` whenever `not_counted` is non-empty.

**Sergio Cruz at 375.** Career story, both cards and "Show these numbers". The sample line is his own: "2 matches · 50
minutes … CF Torrevalle played 2 of the competition's 5 uploaded matches". The ≈ legend counts how many numbers are
noisy, and "None yet" lines carry their pools.

**Tyler Webb.** Every tile in a pool of 12 is flagged "SMALL POOL · only 12 qualified academy U18 men forwards to
compare with".

**Nigerian competition page.**
- Header, pools by position (goalkeepers flagged as a small pool), uploads with uploader and camera, the results
  table ("Uploaded matches only, not a league table") and squads with minutes.
- Identical to the sandbox except the sample paragraph (nit 1).

**Terminal, "most assists in England".**
- 3 lists, 141 players, 21 ranked. Zeros read "none yet" and carry no place.
- Goalkeepers have no percentile, and the Pool column is shown.
- The status line names each list's leader.
- Femi Toure's card states his sample.

**Overview.**
- "7 matches uploaded this week, in 4 competitions, up to 24 Oct 2026" counts from `as_of`, not from today, so the
  number holds through judging.
- New footage shows uploader and camera, and the shortlist tiles show country and level.

**Shortlist and Team needs.**
- Each item shows its strongest number with pool and sample.
- Team needs show "At your level" by value and "From below" by percentile in the player's own level, with the small
  pool flagged (Tyler Webb).

**/me (375).** Femi Toure has 10 matches and 5 goals (98th of 33, ≈). Assists read "None yet · 25 of the 33". Recent
activity is newest first with one date shape.

**Clip view.**
- `?match=cm_nam_02_irk_ads` shows "Round 2: Iroko Lions FC 1–0 Adire Stars FC". Under it: competition, country, level,
  date, uploader, and "filmed on a phone (the uploader's label)".
- The picker lists 94 matches, as "Round N · … · camera · uploaded by …".
- A "nutmegs" search gives 71 moments grouped by competition, each card with its upload line and clock.

**Phone width.** `scrollWidth` is 375 on every Scout section (two competition pages included), three profiles, /me, and
the Clip view.

**Honest uploads.**
- The camera is a label everywhere.
- The upload record stays `source: synthetic`, and the /me hint says the footage is Regista's own synthetic render.
- "on Azure Container Apps" appears only when the store is Azure (`me.js` lines 736 and 775).
- A catalogue upload needs a competition, a date inside the season and not in the future, a camera, and consent.

**One ranking rule.** No added `.sort(` ranks players by a metric. The added sorts order moments by watchability, rows
by minutes (choosing the default row), matches by date, and squads by number or minutes.

## Nits

1. **Competition sample paragraph** (engine's B7 words).
   - It drops the sandbox's "Small sample:" lead and "(0.7 full matches)".
   - It says "Per 90s rest on the 4 uploaded matches", which is not plain.
   - The next line repeats the percentile minimum.
2. **Agent answers show a shirt for some rows only.** In the U19 dribblers answer only Ruben Prieto has his shirt (7),
   because `agentRow` draws one only for players the page already loaded (the shortlist). Show it for all rows or for
   none.
3. **A shared place with different percentiles.** Emre Scholz and Amari Ustinov are both 3rd at 1.04 goals per 90, at
   the 92nd and 89th percentiles. The engine shares a place on the rounded value but computes the percentile on the
   unrounded one. This comes from PR #39's engine, not the port; it may confuse a viewer.
4. **A percentile from one attempt.** "100% of take-ons won (1 of 1) · 89th percentile among 27 amateur men forwards
   with enough attempts" (Sergio Cruz). The minimum attempts scale down to 1 in short competitions, so "with enough
   attempts" reads stronger than it is. This is the engine's rule from PR #39.
5. **Board order.** Find players lists the women's boards last (the API's order). The sandbox put semi-pro women right
   after semi-pro men. Either is fine.
6. **Less specific summary line.** Find players says "a player in two competitions appears once for each". The sandbox
   said "2 players play in two competitions and appear once for each".
7. **Reports read moments from the league endpoint.** They use `/api/players/{gid}` (`scout.js` `profile()`). On the
   live app that endpoint counts Femi Toure's friendly, so a report could cite a friendly moment that the profile says
   is not counted. Citing a moment is not counting it, but the bases differ.
8. **Worker failures show a machine path** (`FileNotFoundError: … '/private/tmp/…'`) on /me. This predates the port, as
   the verifier found. It now reaches catalogue players too.

## Tests

- `python3 -m pytest -q` on bc4ae69 (Mac): 1077 passed, 15 deselected, in 4 min 31 s.
- I did not re-run the slow suite. The verifier ran it at 8db521d (15 passed), and the later commits touch neither the
  generator nor the pins.
