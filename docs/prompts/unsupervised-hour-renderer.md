# Unsupervised hour: 2D renderer and what follows

Paste the block below as a single message. It assumes the session is in `~/Desktop/Regista` with `CLAUDE.md` loaded.

---

I'm away for about one hour. Work continuously and autonomously until the whole list is done or the hour is up. Do not ask me questions; make reasonable calls, record them in `CLAUDE.md` section 5 if they're open questions, and keep going.

## Before anything else: keep the Mac awake

Call the app's keep-awake tool (`request_keep_awake`) for 75 minutes so the machine does not sleep while you work. If that tool is unavailable or refuses, run `caffeinate -dims -t 4500` in the background with the Bash tool and confirm it is running. Do this before the first file edit.

## Guardrails (absolute)

- Do not create, modify, or pay for any Azure resource, and do not make any call that needs an Azure or Foundry key. Design for them; don't provision them.
- Do not make the GitHub repo public, change its settings, or open issues or PRs. Commit to `main` and push after each milestone.
- Do not download or use any real match footage, video-game footage, or research datasets. Every pixel in this repo must come from our own generator.
- Keep `python3 -m pytest -q` green at every commit. If a milestone can't be finished cleanly, commit what works, note what's missing in the commit message, and move on.
- Keep `CLAUDE.md` current: update section 3.0 (code layout) and the README quickstart whenever you add a module or command.
- Install only via `pip install` into the current environment, pinned in `pyproject.toml`. Prefer libraries already present (check first); `ffmpeg` may be used if it is installed, otherwise fall back to GIF or frame sequences without stopping.

## Milestone 1: the 2D broadcast renderer (the main deliverable)

Build `src/regista/render/` that turns a sample match directory (`events.jsonl`, `tracks.jsonl`, `clips.jsonl`) into a watchable, broadcast-style 2D animation we own outright.

Requirements:
- A `python3 -m regista.render <match_dir> --out <file>` CLI, MP4 via ffmpeg when available, GIF otherwise, plus `--frames-dir` to also dump PNG keyframes.
- Draw a proper pitch (lines, boxes, centre circle, goals), players as kit-coloured discs with their kit numbers, goalkeepers in GK colours, the ball, a scoreboard with team short names, score, and match clock, and a small Regista watermark.
- Honour `camera_segment` records exactly. `main` segments use a panning camera window that follows the ball (same 48 m window as the generator). `replay` segments show a REPLAY badge, run at the segment's `playback_speed`, re-render the `replays_window` from the main view, and use a visibly different framing per `angle` (for example mirrored for `reverse`, tighter for `behind_goal`). `closeup` fills the frame with the in-frame player's disc, number, and name. `crowd` is a stylised crowd card. `highlight` shows a HIGHLIGHTS banner.
- Overlay a caption strip for notable events as they happen (goal, shot, nutmeg, skill move, take-on, foul, save), timed off `event.t`, using the player name and kit number from the match header.
- Render at a frame rate that keeps a 3-minute match under 60 seconds of render time on this machine; interpolate between track samples so motion is smooth even at 1 Hz tracks. Resolution 1280x720.
- Add `python3 -m regista.render.clips <match_dir> --player t_home_10 --out <dir>` that cuts one video per `clip` record and one concatenated "reel" ordered by watchability, each with the label's title burned in for the first two seconds. This is the product's core output, so make it look intentional.
- Tests in `tests/test_render.py`: frame count matches segment durations, a goal caption appears in the right frame range, replay frames carry the badge, clip videos exist for every clip record, and the CLI runs on the committed sample.
- Commit as "Add 2D broadcast renderer and clip cutter".

## Milestone 2: review with agents, then fix

After milestone 1, run three reviewers as subagents in parallel and act on their findings before moving on:

1. **Visual QA agent.** Give it the frames directory and the clip reel. Have it read a dozen keyframes as images (kick-off, a pass, the goal, the goal replay, a closeup, the highlight package, two clip title cards) and report anything illegible, overlapping, off-pitch, mis-timed, or ugly, with the frame filename for each. Fix everything it reports that is real; re-render; have it confirm.
2. **Code review agent.** Review the diff of milestone 1 for correctness bugs and anything that will break on a longer match or a different seed. Fix the confirmed findings.
3. **Judge simulator agent.** Give it `CLAUDE.md` section 1.1 and the README, and ask it to score the repo as a hackathon judge would on the five criteria, with the single most valuable improvement per criterion that could be done in under 20 minutes. Do the ones that fit the remaining time and don't need Azure.

Commit after fixes as "Address visual QA, code review, and judge feedback on renderer".

## Milestone 3: the local Librarian (chatbot v0, no cloud)

Build `src/regista/librarian.py` and `python3 -m regista.librarian <match_dir> "find me Valente doing a nutmeg"`. Pure local: parse a natural-language query into a player (by surname, kit number, or team), tags (nutmeg, goal, shot, skill move, take-on, assist, replay), and optional time window; rank matching `label` records by watchability; print clip ids, titles, times, and the explanation. Design it as a tool interface (`search_clips(query) -> list[dict]`) with a docstring that states exactly how it becomes an MCP tool for the Foundry agent later. Add tests with five phrasings including a misspelt surname and a query with no results. Commit.

## Milestone 4: the demo storyboard and architecture note

Write `docs/demo-storyboard.md`: a shot-by-shot plan for the sub-2-minute demo video using only our rendered output, with timestamps, what's on screen, what the voiceover says, and which hero technology is named on screen at each beat. Write `docs/architecture.md`: the two-layer architecture, the six agents from `CLAUDE.md` section 3.1 mapped to concrete Microsoft Agent Framework roles with their tools, the MCP tool list (the Librarian's search, the clip cutter, the validator), the Azure services per pipeline stage, and what runs where in a demo deployment on Azure Container Apps. No provisioning. Commit.

## Milestone 5: only if time remains, in this order

1. Second period in the generator (`match.periods` already supports it): teams swap ends, clock continues from 45', tests updated.
2. A `--teams` option to pick kit colours and names, so the demo can show two different matches.
3. Run the renderer on three other seeds and save their reels under `data/synthetic/sample/` only if the total committed size stays under 25 MB; otherwise save them to `docs/demo/` ignored by git and list the commands to regenerate them.

## Final report (last message, for when I'm back)

In this order: what was built with the command to run each piece; the reviewer agents' findings and which were fixed or deliberately skipped and why; test count and status; commits pushed; anything you'd flag before I record the demo; and the three decisions you'd want me to make next.
