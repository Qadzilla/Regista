# The 13 judgment calls: Zaid's decisions (2026-10-23)

The safeguard report (`safeguard.md`) left 13 items for Zaid. His picks, and what changed on this branch.

| # | Item | Decision | Change |
|---|---|---|---|
| 1 | "Clips" wording on other pages | Rename to Home | Footers on `/me`, `/scout`, `/players/{id}` say Home; links read "Watch on Home", "Open the match on Home", "Read it on Home"; Studio says "see it on Home" |
| 2 | Engine explanation only in the panel | Keep the landing clean | None |
| 3 | Meta description | Use the tagline | "Every moment. Every highlight. Every player. Found in seconds." |
| 4 | Match and player pickers in the header | Move them into the match view | The header holds only the brand; the pickers sit on the match view's title line |
| 5 | Phone match view | Panel after the clip | At 1100 px and under, the conversation panel comes right after the stage, before the recap and the moments (the clip starts at about 430 px at 375 px wide, was about 745) |
| 6 | Browser Back | Make Back work normally | Landing to results and results to a match each push a history entry; Back and Forward restore the view, the match and the moment; "Back to results" is the browser's Back |
| 7 | Which match a result comes from | Add one small line | Result cards show "Round 2 · CAL v BRO" (league) or the match's name (library); the match view's cards are unchanged |
| 8 | One name across matches | Keep the filter | None |
| 9 | Reels and downloads per match | Accept for now | None (a cross-match reel needs a backend change) |
| 10 | Foundry badge on results | Accept | None |
| 11 | "Shots from outside the box" prompt | Swap it until a distance filter exists | Replaced by "Find me the best saves this season" (read as "any player · save") |
| 12 | Foundry memory across matches | Keep one conversation | None |
| 13 | Realism report about an unseen match | Show it only in the match view | The "Show this match's numbers" link in How it works shows only in the match view |

Checked in the browser at 1440 px and 375 px: no sideways scroll, Back and Forward across landing, results and match,
the match title on one line beside the pickers at 1440 px.
