# Regista demo video: storyboard (target 1:54, hard limit 2:00)

Rewritten 2026-10-26 for what is live now, and on 2026-10-27 to follow the guided tour step for step: the clip powerhouse, the Scout terminal, and the catalogue (14 competitions of
uploaded footage in 10 countries, CLAUDE.md §2.11). The order stays as agreed (CLAUDE.md §2.8): **the clip powerhouse
first, then Microsoft, AI and agents shown working, then the paths Regista serves.** Every shot shows something that
runs on the live app (revision `regista-api--d1026204656` or later) or from this repository today. Anything not built
appears only in the close, as "where it goes next". Numbers below were read from the live app on 2026-10-26.

## Rules for this video

- **Footage.** Only footage we own: Regista's rendered broadcast and synthetic film, and our own recorded match if it is
  ready, filmed with every player's written consent (CLAUDE.md §1.5). Never Premier League or other broadcast footage,
  video-game footage or research datasets.
- **Name only what runs.** Microsoft technologies that may be named on screen or in the voiceover:
  - Microsoft Foundry and Microsoft Agent Framework;
  - the Azure MCP Server;
  - Azure Container Apps (the app and the vision job);
  - Azure Blob Storage and Storage queues;
  - Azure Cosmos DB and Azure AI Search;
  - Application Insights;
  - Microsoft Fabric and GitHub Actions.

  Never GitHub Copilot.
- **Synthetic, said plainly.** Every player, club and competition is invented; countries and levels are labels. A
  caption says so whenever the catalogue is on screen.
- **Live app read-only on camera.** Record against https://regista-api.kindfield-ba17f67b.francecentral.azurecontainerapps.io.
  - No uploads, verdicts or answers on the live app on camera: they write and need the token, which never appears on
    screen.
  - The Studio view key is pasted off camera.
  - The upload shown is the one already processed (`up_8807d7835c`).
- **Numbers.** Only numbers the app shows, or from `docs/vision.md`, `docs/realism-report.md`,
  `docs/catalogue/realism.md`, `docs/catalogue/fabric.md` or `docs/criteria.md`, captioned with what they were measured
  on. Vision numbers come from rendered footage; say so.
- **Music.** None, or a track whose licence we can show. Judges may stop at 2:00; the cut ends at 1:54.

## Shot list and voiceover

**The video is the guided tour.** Record it by taking the tour on the live app (`/demo`, then Take the tour), with
the tour card hidden (its Hide button) while recording. Each beat below is one tour step, in the same order, with the
same clicks, so a judge who watches the video can then repeat it click for click. Cutaways that the tour cannot show
(the Azure portal, Application Insights, Fabric) are marked as cutaways. About 220 words of voiceover, at about 2 words
a second.

| # | Tour step | Time | On screen (live unless a cutaway) | Voiceover |
|---|---|---|---|---|
| 1 | 1 · Every goal, found | 0:00–0:08 (8 s) | `/players/pl_bro_09`: press **Goal reel**. Femi Toure's five league goals, none a penalty, each once, in match order | "Every Femi Toure goal this season. Found in seconds." |
| 2 | 2 · Every moment of a match | 0:08–0:18 (10 s) | Clips on the demo match: the timeline's marks; click one and it plays | "Regista cuts every moment a player is on the ball, plus every replay and highlight they appear in." |
| 3 | 3 · Then you just ask | 0:18–0:28 (10 s) | With **Data Search** picked: "his nutmegs", Ask; then "now the replays", Ask | "Then you just ask, in plain words, and follow up." |
| 4 | 4 · Recaps and replay packages | 0:28–0:38 (10 s) | Open **Match recap**, click a sentence and its moment plays; **Play recap reel** | "Every match gets a recap where each sentence plays the moment it describes, and its reel is a replay package." |
| 5 | 5 · Video in | 0:38–0:50 (12 s) | `/me?player=pl_bro_09`: the processed upload, agent by agent with its times, then his moments. Caption: "measured on Regista's rendered footage". If our own match is ready, its vision output can replace this shot | "Upload a match and Regista's vision agents find the players and the ball, in Azure: Blob Storage, a queue and a Container Apps job." |
| 6 | 6 · Microsoft Foundry and MCP | 0:50–1:06 (16 s) | Pick **Ask Microsoft Foundry**, press Ask, open "How Regista answered": the agent and each tool with its server. Cutaways (2 s each): the workflow graph (`docs/workflow.md`), the resource group in the Azure portal, a trace in Application Insights | "A Foundry agent on Microsoft Agent Framework answers through two MCP servers, Regista's and Azure's, and every step is traced." |
| 7 | 7 · A catalogue, checked in Fabric | 1:06–1:18 (12 s) | A competition page (`/scout#competition/co_esp_u19`): who filmed each match, the camera. Cutaway: the Fabric notebook's result, 7,399 of 7,399 rows (2026-10-26). Caption: "synthetic: invented players, clubs and competitions" | "It's a catalogue of matches uploaded below the professional level, in ten countries, and Microsoft Fabric recomputes its numbers to check them." |
| 8 | 8 · Scouts: fair comparisons | 1:18–1:28 (10 s) | `/scout#find`: press "Who are the best U19 dribblers up front?": Hector Santos, 5.31 take-ons won per 90, 97th percentile among 16 academy U19 forwards | "Scouts compare players only with their own level, age and gender." |
| 9 | 9 · Every number opens its moments | 1:28–1:38 (10 s) | Hector Santos's profile: press **Take-ons won**, pick a moment, it plays | "And every number opens the moments it was counted from." |
| 10 | 10 · The Scout terminal | 1:38–1:46 (8 s) | `/scout#terminal`: "most goals in England", Search: Femi Toure first | "127 metrics, each with its source." |
| 11 | 11 · That's Regista | 1:46–1:54 (8 s) | `/demo`: the four paths, then the name | "Next: real footage from players and teams. Regista directs every touch." |

Captions name the technology in each shot (beats 5 to 7) and label synthetic data as synthetic. If the Foundry answer
in beat 6 lists only Regista's MCP server, ask it again or use Home's search with Ask Microsoft Foundry, where the
Azure MCP Server's `search_index_query` was verified. Never say "both servers" over a trace that shows one.

## Before recording

- **Warm clips.** A fresh revision now renders every clip the tour uses at startup (`REGISTA_PRERENDER`, about 50
  files). Before recording, check that the Studio's prerender count has reached its total, or play the tour once.
- **Foundry rehearsal.** One Ask Foundry question and one Foundry recap before recording; the limits are 5 a minute
  and 40 an hour per visitor. Check that "How Regista answered" lists both MCP servers.
- **Fabric shot.** The lakehouse `regista_league` in the workspace "Regista": the `catalogue_*` tables and the
  `regista_catalogue_check` notebook's last run (Completed, 83 s). Or run
  `python -m regista.season.fabric check --catalogue --no-run` in a terminal: it prints "7399 of 7399 match".
- **Proof shots.**
  - The Azure portal, resource group `regista-rg`: Foundry, Cosmos DB, AI Search, Container Apps and the job, the
    storage account, Application Insights.
  - A trace with `invoke_agent` and `execute_tool` spans.
- **Our own match (optional).** If it's ready, run the vision layer on it locally and use its output in beat 4,
  captioned "our own match, filmed with consent".

Screen-record at 1920x1080, with the browser zoomed so text reads on a phone. Hide bookmarks, other tabs,
notifications, keys and the subscription id.
