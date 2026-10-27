# Live demo: independent review A, round 1

Reviewed 2026-10-27 on `feature/live-demo` (ee1201c + 7e28ecc; `git diff main...HEAD`). Lens: a judge seeing Regista
for the first time. Is the tour clear, short, plain and impressive? Does /demo make the product and the Microsoft stack
obvious in 30 seconds? Does the phone layout work? Is anything claimed that does not run? I fixed nothing.

## How I checked

- My own server: `REGISTA_DOTENV= uvicorn regista.api:app` on 127.0.0.1:8270, with an empty cache folder.
- The built-in browser at 1440x900. I started on /demo and took all 15 steps, measuring each step's element against
  the card. I pressed the Goal reel, the U19 dribblers chip, Hector Santos's link (the tour moved to step 12 by
  itself), Take-ons won and the terminal search.
- The browser at 375x812. I started from Home and checked steps 1, 2, 3, 5 and 9. On step 5 I opened the recap and
  clicked a sentence.
- Live app, GET only: `/api/health` reports all eight services, and `/api/player/uploads?global_id=pl_bro_09` shows
  `up_8807d7835c` done, with its ten stages.
- `pytest tests/test_tour.py tests/test_warm.py tests/test_live_check.py tests/test_access.py`: 69 passed.
- `python3 src/regista/live_check.py --url http://127.0.0.1:8270 --services ""`: 9 of 9 passed.
- What wrote: the server log has a single POST, `/api/scout/ask` from the chip I pressed (Data Search). There were no
  console errors. At the end I exited the tour, the tour's store key was gone, and I closed my tab and stopped the
  server.

## What works

- **The highlight and the card.** At 1440 every step's element was highlighted and on screen, and the card never
  covered it.
- **Filled boxes.** The steps that fill a box filled it ("his nutmegs", "now the replays", "every nutmeg in the
  library", "most goals in England") and never sent it.
- **The Goal reel.** It played "Goal reel · clip 1 of 5 · Round 1 · 05:48" at once.
- **The terminal.** It put Femi Toure first (1.64 goals per 90, 98th percentile).
- **Phone layout.** At 375 px the card is a strip along the bottom, and the highlighted element sits under the header
  with room below it. Clicking a recap sentence scrolls to the stage and plays the nutmeg replay.
- **Home.** "Take the tour" and "What is Regista?" sit under the switch on both widths and read well.
- **/demo.** The page is clean and quick to read. The four path cards link into the right live views, and the
  services come from `/api/health` with Home's icons.

## Must fix

1. **Step 1 claims more than happened.** It says "Regista found every one in the footage." Femi's goals are league
   matches (`rl_r01_eas_bro` …): Regista's match generator wrote their event streams, and the clips are cut from those
   events. No vision ran on that footage.
   - The storyboard's voiceover is softer: "Found in seconds."
   - Step 1 is also the first time a judge hears "Regista League", and nothing yet says it is invented.
   - Suggested text: "Femi Toure is the top scorer in Regista's synthetic league: five goals, none a penalty. Here is
     every one, in match order."
2. **Step 2 is false for this match.** It says "Regista watched this match and cut every moment…". The match is
   `syn_0294`, whose own manifest says "Three minutes from Regista's match generator". The vision layer has not run on
   it.
   - CLAUDE.md §4 says to name only what runs, and a judge who reads the repo can check this.
   - Suggested text: "This match comes from Regista's match generator. Regista cut every moment Sami Castellanos is
     on the ball…"
   - Leave the claim that Regista watches footage to step 6, which shows the real vision run (`up_8807d7835c`).

## Should fix

1. **The tour is long and moves between pages a lot.** It has 15 steps across 10 page loads: /players, /, /me, /,
   /scout, /, /scout, /players, /scout, /me, /demo.
   - Steps 6 and 14 open the same URL (`/me?player=pl_bro_09#matches`).
   - Steps 3 and 4 share one box.
   - Step 10 (the stage actions) goes back to / just after Scout.
   - Merging 6 and 14, 3 and 4, and folding 10 into 5 (the recap and its reel already are the broadcasters' package)
     gives 12 steps and about 7 page loads. Each Clips load is the heaviest page.
2. **Step 14 points the judge at a dead end.** It highlights "Add a match". On the live app that button asks for the
   operator's key, so a curious judge ends up at a token prompt. Point the merged players step at the processed
   upload (its "Watch in the Clip view") or its agent list instead.
3. **Step 9's title does not match what it highlights.** The title is "Checked in Microsoft Fabric", but the highlight
   is the "Uploaded matches" heading, and nothing about Fabric is on that page.
   - The card makes two points at once: who filmed each match, and Fabric's 7,399 of 7,399.
   - Either retitle the step "Who filmed it", with Fabric as a second, clearly separate sentence ("Not in this app:
     …"), or move the Fabric sentence onto step 8.
4. **Step 6's action line is not an action.** "Measured on Regista's own rendered footage." appears in the accent
   style that every other step uses for "do this", and nothing on the card is a measurement. Either give the number
   it qualifies (as the storyboard does) or drop the line.
5. **/demo's first screen at 1440x900 does not show the Microsoft stack.** "Running on this server right now" starts
   at y = 794, so the tiles are below the fold. The hero names Foundry and Agent Framework in a sentence, but the
   icon row is the 30-second proof. Move that section above "One engine, four paths", or put a compact icon row
   under the Take the tour button.
6. **/demo's second hero sentence overstates Foundry's role.** It says "Its agents, on Microsoft Foundry and
   Microsoft Agent Framework, label and explain each moment, write match recaps…".
   - Most moments the judge sees (the league, the catalogue, the demo match) are labelled by Regista's rules, the
     same labeller the Label agent uses. Foundry labels only the uploaded library matches.
   - Recaps are rules by default; Foundry recaps are optional.
   - Suggested text: "Agents on Microsoft Agent Framework label and explain each moment and write match recaps;
     Microsoft Foundry answers questions and can write the recap."
   - Related, and also on Home: the AI Search tile says "Indexes every labelled clip", but the index holds the
     library's clips (8 documents), not all 94 matches. Better: "Indexes the library's labelled clips".
7. **Steps 3 and 4 can spend a Foundry call.** The engine switch lives in memory on the Clips page. A judge who picks
   Ask Microsoft Foundry at step 7 and then presses Back to 4, 3 or 5 stays on Foundry. Pressing Ask there spends a
   Foundry call, and opening the recap may ask for a Foundry recap. Meanwhile step 3 still says "Data Search … no AI
   model is called".
   - Either have those steps say "with Data Search picked",
   - or have the tour switch the engine back to rules on those steps. The switch only changes how the page answers;
     it writes nothing.
8. **The docs judges read do not mention /demo or the tour yet.** README's judges' tour should lead with /demo and
   "Take the tour". The storyboard's rehearsal still gives the old Foundry limits (3 a minute and 20 an hour; now 5
   and 40). The pitch could close on the /demo URL. Zaid wants to work on all three next.

## Nits

- **Step 8's highlight** is a single line, 18 px tall (the count line). The list of competitions under it would show
  more.
- **"Try Download reel."** (step 10) downloads an MP4 to the judge's machine. "Play reel (11)" shows the same point on
  screen with no file.
- **The last step** shows both Finish and "Exit tour", which do the same thing.
- **"Demo" in the left panel** could read "For judges" or "Start here", so it doesn't look like a sample or a fake
  view.
- **/demo on a local run with no Azure**: `azure_mcp` reports true, so the page lists Agent Framework and the Azure MCP
  Server with the live-server note. It never shows its local-run sentence ("runs without Azure"). This does not
  affect the live app (8 of 8 services).
- **/demo hero, third sentence**: "a catalogue of footage uploaded below the professional level". Add "synthetic"
  there. The synthetic note is two sections down, and a 30-second reader may not reach it.
- **The live check's email** goes to whoever last changed the workflow's schedule (GitHub's rule for scheduled
  runs), not necessarily the repository owner. Zaid should merge it himself, or the comment should say so.
- **Warm-up on the live replica**: with one CPU and render concurrency 1, a judge's first click on a clip that is not
  warmed waits behind the warm-up for several minutes after each deploy. Avoid pushing to main during judging.

## Not checked here

These were also open in verify.md:

- On the live app:
  - Step 6's agent list.
  - Step 7's Foundry answer, and that "How Regista answered" names both MCP servers. The Foundry check costs one
    question.
  - How long the warm-up takes on the replica.
- Step 6 on phones shorter than 812 px.

After the deploy, take the tour once on the live app at 1440 and 375 px and press Ask Microsoft Foundry once.

## Verdict

**Not signed off.** Two claims in the first two steps say Regista watched or found things in footage when the
generator wrote them (must fix 1 and 2). These are one-line text changes. The rest is shortening and clarity work
that would make the tour tighter for a first-time judge.
