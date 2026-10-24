# Regista demo video: storyboard (target 1:52, hard limit 2:00)

Rewritten 2026-10-23 to the agreed order (CLAUDE.md §2.8): **the clip powerhouse first, then Microsoft, AI and agents
shown working, then the paths Regista serves.** Every shot shows something that runs on the live app or from this
repository today; anything not built appears only in the close, as "where it goes next". Numbers checked against the
regenerated league (generator 0.7.1, the same season on every platform) on 2026-10-24.

## Rules for this video

- **Footage.** Only footage we own: Regista's rendered broadcast and synthetic film, and our own recorded match if it is
  ready, filmed with every player's written consent (CLAUDE.md §1.5). Never Premier League or other broadcast footage,
  video-game footage or research datasets.
- **Name only what runs.** Microsoft technologies named on screen or in the voiceover: Microsoft Foundry, Microsoft Agent
  Framework, Azure MCP Server, Azure Container Apps (the app and the vision job), Azure Blob Storage and Storage queues,
  Azure Cosmos DB, Azure AI Search, Application Insights, Microsoft Fabric, GitHub Actions. Never GitHub Copilot.
- **Live app read-only on camera.** Record against https://regista-api.kindfield-ba17f67b.francecentral.azurecontainerapps.io.
  No uploads, verdicts or answers on camera on the live app: they write and need the token, which never appears on
  screen. The Studio view key is pasted off camera. The upload shown is the one already processed (`up_8807d7835c`).
- **Numbers.** Only numbers from the app, `docs/vision.md`, `docs/realism-report.md`, `docs/criteria.md` or measured on our
  own match, captioned with what they were measured on. Vision numbers come from rendered footage; say so.
- **The Scout terminal.** Only what part A built may appear: the metrics engine (`regista.season.metrics`: 127 player
  metrics and 19 team-style metrics, each with its definition and source) and its read-only API (`regista.terminal_api`:
  `/api/metrics`, `/api/terminal/screen|rank|scatter`, a player's metrics, form and similar players, team style). It runs
  from this repository's `feature/terminal-engine` branch and is not on the live app until that branch is merged and
  deployed. The terminal's screens are not built: never show a mock-up as if it worked. Until they exist, the terminal is
  "where it goes next" in the close, on top of an engine that is built.
- **Music.** None, or a track whose licence we can show. Judges may stop at 2:00; the cut ends at 1:52.

## Shot list and voiceover

About 230 words of voiceover at an easy pace (roughly 2 words a second) fit 1:52 with room for the hook to breathe.

| # | Time | Beat | On screen (all live unless noted) | Voiceover |
|---|---|---|---|---|
| 1 | 0:00–0:08 (8 s) | **Hook** | Femi Toure's profile (`/players/pl_bro_09`), the **Goal** reel: his five league goals, two more than anyone (generator 0.7.1, league attributes version 2: round 1 at 6' and 56', both at Eastwick; round 6 at 49'; round 8 at 6', after his own carry into the box; round 10 at 8'), none a penalty, one clip each, in match order. Do not call the round 1 goal at 56' a header: the generator stages it as his 6 m carry along the ground, then a headed shot (an open finding, CLAUDE.md §4.2). The reel runs 42.2 s; the hook uses its opening seconds (built, see below) | "Every Femi Toure goal this season. Found in seconds." |
| 2 | 0:08–0:22 (14 s) | **Clip powerhouse: every moment** | Clips (`/`) on the demo match: the timeline marks every touch, replay, highlight and close-up; ask "his nutmegs", then "now the replays"; the stage plays each | "Regista watches a match and cuts every moment a player is on the ball, plus every replay and highlight they appear in. Then you just ask." |
| 3 | 0:22–0:34 (12 s) | **Explained and recapped** | The **Recap** panel, told from Castellanos's side: click a sentence, its moment plays; switch the engine to Foundry; Play recap reel | "Every moment is labelled and explained, and every match gets a recap where each sentence plays the moment it describes." |
| 4 | 0:34–0:48 (14 s) | **Video in** | Player view (`/me?player=pl_bro_09`): the processed upload, agent by agent with its times (shots 17 s, identity 2 min 6 s, then possession, events, clips); his moments appear. If our own match is ready, its vision output can replace this shot | "Give it footage and Regista's vision agents find the players, follow the ball, and spot every pass, shot and nutmeg. Measured on our rendered footage." |
| 5 | 0:48–0:58 (10 s) | **The data engine** | Scout's league table, then `docs/realism-report.md`'s verdicts at a glance (one season: 13 of 13 event rates, 14 of 14 physical measures at 10 Hz; six seasons pooled: every band); the Fabric lakehouse `regista_league` with the season's tables and the notebook's cross-check: 756 of 756 rows match (2026-10-24, on the season this branch serves: generator 0.7.1, the star's version 2 ratings) | "And it generates its own data: a whole synthetic season, realistic to Premier League rates down to every sprint, with the truth for every frame, cross-checked in Microsoft Fabric." |
| 6 | 0:58–1:16 (18 s) | **Microsoft, AI and agents, working** | Ask Foundry on `/`: open "How Regista answered" (the Foundry agent, `search_clips` on Regista's MCP server, `search_index_query` on the Azure MCP Server); the workflow graph (`docs/workflow.md`); the Azure portal resource group; a trace in Application Insights | "Under the hood: Microsoft Agent Framework workflows hand work between agents. Foundry agents answer through two MCP servers, Regista's and Azure's. Uploads go through Blob Storage and a queue to a Container Apps job, and every step is traced." |
| 7 | 1:16–1:44 (28 s) | **The paths** | Four quick cuts. **Fans and creators**: Download reel and Export moments on `/`. **Broadcasters**: a recap with its reel. **Scouts**: on `/scout`, ask "midfielders who win the ball back", open Sami Okafor (Calder Town; the rules Scout's top midfielder for ball recoveries with generator 0.7.1 and the star's version 2 ratings: 12.82 per 90, 42 in 294.8 minutes), click a number and its moments play. **Players**: `/me`, an upload becomes part of the profile | "One engine, four paths. Fans and creators get any moment, as a reel. Broadcasters get recaps and replay packages. Scouts get every player across a season, where every number opens the moment behind it. And players upload their own match and build their profile." |
| 8 | 1:44–1:52 (8 s) | **Close** | The four views, then the name | "Next: the scouting terminal on our metrics engine, and real broadcasts. Regista directs every touch." |

**Beats 1, 5 and 7 depend on a deploy.** Their numbers (Toure's five league goals and 42.2 s reel, 14 of 14 physical
measures at 10 Hz, Sami Okafor's 12.82 recoveries per 90) are this branch's league (generator 0.7.1, league attributes
version 2). The live app
still serves `main`'s league: a read-only GET of `/api/players/pl_bro_09` on 2026-10-24 gave 6 goals in 303.9 minutes,
and `main`'s beat 7 named Kenan Nakamura. "All live" holds for these beats only after `feature/terminal-engine` is merged
and deployed (see "To build before recording").

Captions on screen name the technology as it appears in each shot (beats 4 to 6) and label synthetic data as synthetic.

## To build before recording

- ~~**One clip per goal in the hook's reel.**~~ **Done (2026-10-23).** The profile's Goal reel used to take the best clips
  tagged goal, which mixed each goal with its replays (24 goal moments for Toure then, of which 6 on the ball; 20 now, of which 5). The reel
  endpoint now takes `reason=on_ball_main` (only on-the-ball clips) and `order=match` (round, then time), and the Goal
  chip uses both: Toure's reel is his goals, once each, in match order, labelled "all N goals, in match order, each once"
  (six goals and 44 s before player ratings; the count moved as the league was tuned through generator versions 0.3.0
  to 0.7.0, recorded in `docs/scout-terminal/build/`). With generator 0.7.0 (checked 2026-10-24) the reel is his three
  league goals, rounds 2 (a penalty), 5 and 6, and runs 23.6 s at 1280 wide; 0.7.1 keeps the same three goal clips
  (4.95 + 13.17 + 5.48 s, checked 2026-10-24). With the star's version 2 ratings (2026-10-24,
  docs/scout-terminal/build/femi-edge.md) the reel is his five league goals, rounds 1 (two), 6, 8 and 10, none a
  penalty, and runs 42.2 s (rendered locally at 1280 wide, 2026-10-24). Up to 8 goals fit (the reel's cap); a
  player with more gets 8 of them and the label says so.
- ~~**The Fabric cross-check passes again.**~~ **Done (2026-10-24).** The season with generator 0.7.0 was pushed to the
  lakehouse on 2026-10-24 (events 33,624, clips 10,620, labels 10,620, player_season 3,024 rows); the notebook's check
  then matched only 328 of 756 rows, all differences in the percentile, because `LEADERS_SQL` still used the old rule.
  The SQL now uses Regista's (FBref's percentile, unrounded rates, a pool of a third of a club's minutes), a test applies
  that rule offline and compares it with `Season.build`, and `REGISTA_DOTENV= python3 -m regista.season.fabric check`
  matched **756 of 756** rows (notebook run 52 s). Beat 5 can show it.
- ~~**Re-sync Fabric with generator 0.7.1's season, then re-run the check.**~~ **Done (2026-10-24).** The season
  this branch serves (generator 0.7.1, the same bits on Linux and macOS; the star's version 2 ratings) was pushed to
  the lakehouse (events 33,758, clips 10,661, labels 10,661, player_season 3,024, uploads 1 rows) and
  `REGISTA_DOTENV= python3 -m regista.season.fabric check` matched **756 of 756** rows (notebook run 52 s), Femi
  Toure's five goals among them. Beat 5 can show it.
- **Merge and deploy `feature/terminal-engine`, then re-check beats 1, 5 and 7 on the live app.** Until then the live
  app serves `main`'s league, and those beats' numbers do not hold there (see the note under the shot list). After the
  deploy, check read-only: Toure's Goal reel (five goals, 42.2 s), the realism verdicts quoted in beat 5, and the rules
  Scout's top midfielder for ball recoveries in beat 7.

## Assets to prepare

| Asset | How |
|---|---|
| Live app, warmed | Before recording, play Toure's Goal reel, the demo match's clips and the recap reel once, so the on-demand renders are cached |
| Foundry rehearsal | One Ask Foundry question and one Foundry recap before recording (limits: 3 a minute, 20 an hour per visitor); check "How Regista answered" lists both MCP servers |
| Fabric shot | The `regista_league` lakehouse (the season pushed again 2026-10-24) in the Fabric workspace "Regista"; the `regista_leaders_check` notebook run, or `python -m regista.season.fabric check` in a terminal (756 of 756 on 2026-10-24, on the 0.7.1 season with the star's version 2 ratings) |
| Proof shots | Azure portal, resource group `regista-rg` (Foundry, Cosmos DB, AI Search, Container Apps and the job, the storage account, Application Insights); a trace with `invoke_agent` and `execute_tool` spans |
| Our own match (optional) | If ready: run the vision layer on it locally and use its output in beat 4, captioned "our own match, filmed with consent" |

Screen-record at 1920x1080, browser zoomed so text reads on a phone. Hide bookmarks, other tabs, notifications, keys and
the subscription id.

## If the Home search learns the whole season

Beat 1 then types "every Femi Toure goal this season" into Home instead of opening the profile's Goal reel. Until that is
built and live, the profile reel is the honest shot.
