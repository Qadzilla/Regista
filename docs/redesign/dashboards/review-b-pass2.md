# Review B, round 2: fidelity and UX

Reviewer B looked at `ux/dashboards` at 77abbfd and compared it with the sandbox, side by side. The app ran offline on port 8142 and the sandbox on port 8143, at 1440 px and 375 px. I fixed nothing.

**Verdict: signed off.** All five round 1 findings are fixed. Nothing else must or should be fixed. The nits below are optional.

## Round 1 fixes, checked

1. **Find players.** It now follows the sandbox order:
   - Ask the Scout agent, with the Data Search / Foundry picker kept.
   - Three filters: Name or club, Position ("Any"), Sort by.
   - The cards, in 4 columns at 1440 px. The league table sits under them.
   - The tagline, the Synthetic badge and the engine paragraph are gone.
   - "More filters" opens Club, Minimum minutes and Reset. It sets `aria-expanded`, moves focus to Club, and changes its label to "Fewer filters". Nothing scrolls sideways at 375 px.
2. **Compare.** It now has the sandbox's line, "Per 90 minutes this season. Pick a number to see the moments behind it."
   - A midfielder against a forward gives the sandbox's 8 rows in the sandbox's order.
   - "Nth percentile" is gone. Hover text and labels say, for example, "Higher than 53% of the league's midfielders".
   - Clicking a number opens its moments, and focus moves to the moments' heading.
3. **Card wording.** Cards, Team needs and shortlist items read "Not above any of the league's midfielders". In the Scout agent's answer the rank now says among whom: "1st of 18 midfielders", "joint 2nd of 18 forwards".
4. **Caveats.**
   - Scout Settings no longer has the Password row.
   - Sign out forgets the tab's admin key, as on /me.
   - The synthetic notes are gone from the profile page and from /me My profile. The footer keeps its one line.
   - The browser-storage line appears once in each Messages section and each Settings.
5. **Upload steps.** I ran `plain()` against every note the worker and the API write.
   - "13 files saved as match pv_…" becomes "13 files saved".
   - "2 answer(s) …" becomes "2 answers …", and one answer reads "1 answer".
   - Notes without ids are left as they were.

## Looked at again

- **Left panel.** It is right on Home, `/me`, `/scout` and `/players/{id}`:
  - `aria-current` is on the parent link and on the current section.
  - On phones the sections are a second row of tabs, scrolled to the current one.
- **Sideways scroll.** None at 375 px in any section of either dashboard, on the profile page, or on Home.
- **Labels.** Every form control has a label.
- **Scout bar.** It is on `/players/{id}`. /me My profile renders the same page without it, under "This is what scouts see when they open your profile."
- **Settings.** The seeded values match the sandbox, and so do the Player dashboard's Overview, Matches & videos, Messages and Team.
- **Tests.** The page tests pass (137).

## Nits (optional)

- Scout Overview's activity still reads "Gino Mensah is on your shortlist: Offer". The sandbox says "Farid Vargas moved to Trial". This is the round 1 nit, still open.
- Shortlist items for midfielders can lead with passes completed, for example Hugo Delgado's "65.32 passes completed per 90". The sandbox picks from recoveries, tackles won and key passes only (`BY_POSITION.MF` in `scout.js`).
- Sort by lists "Shots on target" twice, once in each group. The sandbox labels read "Goals per 90" and so on.
- The Scout agent's "Understood" line can say "players with at least 120.4 minutes". This comes from the API, and `main` does the same.
- Reports has an intro line the sandbox does not have, plus the storage line. The brief asks for the storage line in Messages and Settings only.
- The Scout agent's example chip reads "Forwards with the most goals". The sandbox says "Forwards who score the most".
- Still open from round 1:
  - "← Back to Scout" (the sandbox says "← Back").
  - The longer Numbers introduction on the profile.
  - The seeded Femi report quotes 11 matches. Offline he has 10.
  - The unread count has no hidden "unread" text.
  - Mute and Block announce their state twice.
- In the /me squad list, the "You" badge has no space before it ("Femi ToureYou" in the page text).
