# The vision layer (private): broadcast video in, event stream out

This is v0 of Regista's private vision layer (CLAUDE.md §1.5, §2.3 steps 1 and 2): it watches a broadcast video, finds the shots, finds and names the players, decides who is on the ball, and writes the same event stream (`data/synthetic/README.md`) that the intelligence layer already consumes.

**What it is trained and measured on.** Real broadcast footage has not arrived yet. Every model here is trained and every number below is measured on Regista's own rendered broadcast (`python3 -m regista.render`). That footage has exact ground truth for free: `camera_segment` records give the shot kinds, the renderer's own camera projects every player and the ball into each frame, the roster gives kit numbers, and `possession` records give who had the ball. These are good numbers on easy footage: flat-coloured discs with printed numbers, one camera family, and no crowds, referees, motion blur, or real occlusion. They show that the pipeline is wired correctly and that each stage does its job. They say nothing yet about real broadcast accuracy. The last section lists what changes for real footage.

Code: `src/regista/vision/`. Tests: `tests/test_vision.py`.

## Agents

| Role | In → out | How (synthetic footage) |
|---|---|---|
| **shots** | video → `camera_segment` | Per-frame features at 128x72 that do not depend on one broadcaster: grass fraction, an 8x6 colour grid, texture, edges, motion, and motion averaged over a second (slow motion shows up there). A cut classifier works on frame pairs: colour-histogram change first, plus grey-level difference, edge change ratio, and a motion-compensated foreground jump that catches cuts between two wide shots of different moments. Two scikit-learn gradient-boosting classifiers (shot kind, and cut) are **trained on rendered frames labelled from `camera_segment` ground truth**. Shots between cuts take the class with the highest mean probability; a sustained class change splits a shot; adjacent main shots merge; very short shots fold into a neighbour. |
| **identity** | video + roster + segments → `track`, `appearance` | Per main-camera frame: (1) **calibration**: find the camera pan by rectifying the pitch and matching line, mown-stripe, and off-pitch profiles against a 105x68 pitch model; (2) **detection**: nearest-colour labelling against the roster's kit colours and the scene's neutrals (grass, shadows, lines, greys), filled and split into discs; the ball is a distance-transform peak in the white mask; (3) **team**: the kit cluster a disc belongs to; the palette is re-estimated from the footage first; (4) **kit number**: a **digit classifier (two scikit-learn MLP heads, tens and units) trained on crops cut from rendered frames** at detected positions, labelled from the roster, plus discs drawn with the renderer's font for every number 1-99; (5) **tracking**: Hungarian assignment on pitch distance, gated by team and goalkeeper kit; (6) **naming**: each track takes the team-sheet player with the highest summed number log-probability, with starters favoured over substitutes, and one player per moment. For replays and highlights: discs are tracked in image space and named the same way. A player "appears" when on the ball or near it for long enough; the thresholds are tuned on training matches. Closeups are read directly. |
| **possession_vision** | identity → `possession` | Nearest named player within 1.3 m of the ball. The frame sequence is mode-filtered, gaps are bridged, and short runs are dropped. `gained_by` / `lost_by` say `pass_received` / `pass` when the neighbouring possession is a team-mate's, else `unknown`. `touches` is estimated from duration. |
| **vision_writer** | everything → match directory | `events.jsonl` (match header, then `camera_segment`, `possession`, `appearance`), `tracks.jsonl`, `manifest.json`, validated against the schemas. |

`build_vision_workflow()` (`regista.vision.agents`) wires the four roles as a Microsoft Agent Framework workflow. It reuses `RoleExecutor`, `FinishExecutor`, and `DeadLetterExecutor` from `regista.agents.workflow`, so retries, dead letters, typed handoffs, and the trace format match the intelligence pipeline. Its output directory is the intelligence workflow's input.

```
vision_start ─▶ shots ─▶ identity ─▶ possession_vision ─▶ vision_writer ─▶ finish
                  └─────────┴──────────────┴─────────────────┴── DeadLetter ─▶ dead_letter
```

The vision layer emits no `event` records yet (passes, shots, tackles, nutmegs). Clips derived from vision output are therefore cut correctly but labelled only with their reason (`on_ball_main`, `replay_appearance`, …) until an event-spotting model exists.

## Measured numbers

Data: 10 training matches and 6 held-out matches, 5 minutes of play each (two of each set are 2 x 2.5-minute halves, which adds a half-time graphic). Each was rendered at 640x360, 10 fps, by `python3 -m regista.vision data`. **Every held-out match uses clubs and kit colours that never appear in training.** One held-out pairing is the demo's (Eastbury green vs Westfield purple); the green shirt sits about 17 ΔE from the grass. Identity, cutaway, and possession numbers use the true camera segments, so each stage is scored on its own. The end-to-end row runs every stage from the video.

| Stage | Metric (6 held-out matches unless noted) | Measured |
|---|---|---|
| Shots | frame accuracy after segmentation (19,752 frames) | **99.98%** (main 100%, replay 100%, highlight 99.75%, closeup 100%, crowd 100% on 50 frames, graphic 100%) |
| Shots | segment-boundary precision / recall / F1, within 0.5 s (77 true boundaries) | 0.959 / 0.909 / **0.933** |
| Camera calibration | mean error of the recovered pan | 0.05 m |
| Detection | player precision / recall (discs inside the frame, less than 40% covered; 8,421 frames at 5 fps) | **0.995 / 0.988** |
| Detection | ball precision / recall; mean ball position error | 0.993 / 0.991; 0.15 m |
| Team | team accuracy over matched detections | **99.99%** |
| Kit number | per-crop reading, number visible (69,202 crops: main / replay / highlight / closeup) | **99.5%** (99.6 / 98.1 / 99.1 / 100) |
| Kit number | free reading of fresh synthetic discs, numbers 1-99 (3,000) | 85.9% (84.9% for 12-99) |
| Identity | detections whose track is named, and named correctly | 97.4% named; **99.3%** of those correct (96.8% of all matched detections) |
| Position | mean / 95th-percentile pitch error of player ground points | **0.20 m** / 0.46 m |
| Cutaway appearances | replay, highlight, and closeup players vs generator appearances (66 true) | precision 0.75, recall **0.61** |
| Possession | frame accuracy (holder or nobody) / holder precision / holder recall | 0.81 / 0.90 / **0.72** |
| Possession | true possessions found (same player, time IoU ≥ 0.5) / predicted ones that match / player right when overlapping (429 true) | 0.72 / 0.82 / **0.97** |
| End to end (syn_0201, every stage from video) | clips for t_home_09 from the vision stream vs from ground truth: recall / precision at IoU ≥ 0.5; true clip-seconds covered | 0.80 / 1.00; 84% |
| End to end (syn_0201, all 22 starters) | clips recall / precision at IoU ≥ 0.5 (67 true clips); true clip-seconds covered | **0.75 / 0.96**; 73% |
| End to end, by clip reason (all starters) | on-ball main / replay / highlight / closeup recall | 0.81 (58) / 0.50 (2) / 0.17 (6) / 1.00 (1) |

Reproduce (about 25 minutes on a 10-core laptop: render 1.5, train 7.5, evaluate 15; everything is written under `/tmp/regista_vision`, nothing in the repo):

```bash
python3 -m regista.vision data                                     # render the 16 matches with ground truth
python3 -m regista.vision train    --models /tmp/regista_vision/models
python3 -m regista.vision evaluate --models /tmp/regista_vision/models --out /tmp/regista_vision/eval.json
```

Run the layer on one video and hand the result to the intelligence layer:

```bash
python3 -m regista.vision run /tmp/regista_vision/video/syn_0201_640x360_10fps.mp4 \
    --roster /tmp/regista_vision/matches/syn_0201 --out /tmp/regista_vision/out/vis_0201 \
    --models /tmp/regista_vision/models --workflow
python3 -m regista.validate /tmp/regista_vision/out/vis_0201
python3 -m regista.agents /tmp/regista_vision/out/vis_0201 --player t_home_09
python3 -m regista.vision compare /tmp/regista_vision/out/vis_0201 /tmp/regista_vision/matches/syn_0201 --player t_home_09
```

The default model directory is `models/vision/`. Trained models are build artefacts and must not be committed.

### Weak spots, measured

- **Cutaway appearances are the weakest stage.** The generator's ground truth for a replay lists the players *in the replayed event* (scorer, fouled player, defender beaten). Some of them are not near the ball in the rendered replay at all. The vision rule ("on the ball, or near it for long enough") finds the ball carrier reliably and misses the rest, and it sometimes adds a team-mate who had the ball earlier in the replay window. The product rule (CLAUDE.md §2.3: any replay the player appears in) is broader than this ground truth, so these numbers are a strict reading.
- **Possession frame recall is about 0.7.** In about 12% of frames inside a true possession (measured on syn_0202), the rendered ball is more than 1.3 m from the holder (interpolation around passes). Possession windows also start and end a few tenths of a second off. When a possession is found, the player is right about 97% of the time.
- **Back-to-back highlights with the same framing** are the boundaries the shot agent misses most often. The camera is clamped at the same goal, so only the players jump.
- **Highlight appearances end to end (0.17 recall on syn_0201)** combine both weaknesses above: a missed boundary between back-to-back highlights merges two segments, so even a right player no longer overlaps the true segment at IoU ≥ 0.5.
- **On-ball clips end to end (0.81 recall, 1.00 precision)** inherit the possession recall. Missed clips are short possessions; no clip is invented.
- **Kit numbers 12-99** have never been seen in rendered matches (the synthetic league plays 1-11). On fresh synthetic discs, free reading of numbers 1-99 is about 86% correct, against 99.5% on the crops of numbers 1-11 from rendered matches. On real footage the team sheet constrains the answer anyway.
- **Kits close to the grass** work down to about 17 ΔE (the Eastbury green), but are not guaranteed: a shirt within about 5 ΔE of the grass (tried, then dropped from the test set as unrealistic) is invisible to this detector.
- **Speed**: about 95 s for a 5.5-minute match at 640x360 on a laptop CPU (shots 12 s, identity 80 s at 5 analysed frames per second, about 50 ms per frame).

## What changes for real broadcast footage

Every stage keeps its interface. The things that change are listed here plainly. None of them is done yet.

- **Shots.** The same code retrains on human-labelled segments (`train_shot_model` takes any list of video + segments). Real replay cues are different: branded wipes and stingers, slow motion, unusual angles, and dissolves, which a hard-cut detector misses. On the renderer, the REPLAY badge and slow motion are the strongest cues. Expect to label a few matches per broadcaster. A learned boundary model (for example TransNetV2, hosted in Microsoft Foundry) is the upgrade path.
- **Detector.** Players are people, not discs. `DiscDetector` becomes a person detector: a YOLO-class model fine-tuned on broadcast football and hosted in Foundry, or Azure AI Vision object detection. The ground point becomes the bottom-centre of the box. Team assignment keeps the kit-colour clustering on torso pixels, with referees and goalkeepers as extra clusters. The ball needs its own small-object detector with temporal filtering.
- **OCR backend.** `AzureVisionOCRReader` is the slot for Azure AI Vision Read (OCR) on torso crops. It is deliberately not implemented and makes no calls. Numbers on real shirts are visible in a minority of frames (back turned, side-on, small), so the track vote that already absorbs hidden numbers matters more. Faces are never used (§1.5).
- **Homography.** The synthetic calibrator solves one unknown (the pan). A real camera pans, tilts, and zooms through a distorting lens, so calibration becomes a per-frame homography from pitch-line and keypoint detection with RANSAC, tracked over time. `HomographyMapping` already implements the mapping interface.
- **Replay cues and mapping.** Replays should be mapped back to live time (`replays_window`) by matching player layouts, so replay appearances can use the live identities. Today they are named independently.
- **Labels.** Human labels replace `regista.vision.truth`: shot kinds marked in a review tool, player boxes and numbers on sampled frames, possessions on short windows. They are stored as `annotation` records with `source: human`.
