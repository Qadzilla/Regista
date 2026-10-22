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
| **events_vision** | identity + possessions → `event` | Passes, crosses, shots, saves, goals, tackles, interceptions, carries, take-ons, nutmegs. Geometric candidates (every hand-over between possessions; every moment the carrier passes a goal-side opponent; every stretch the carrier moves the ball 3 m), decided by two scikit-learn gradient-boosting classifiers; saves and goals follow from a spotted shot by broadcast logic. See "Event spotting" below. |
| **vision_writer** | everything → match directory | `events.jsonl` (match header, then `camera_segment`, `possession`, `event`, `appearance`), `tracks.jsonl`, `manifest.json`, validated against the schemas. |

`build_vision_workflow()` (`regista.vision.agents`) wires the five roles as a Microsoft Agent Framework workflow. It reuses `RoleExecutor`, `FinishExecutor`, and `DeadLetterExecutor` from `regista.agents.workflow`, so retries, dead letters, typed handoffs, and the trace format match the intelligence pipeline. Its output directory is the intelligence workflow's input.

```
vision_start ─▶ shots ─▶ identity ─▶ identity_review ─▶ possession_vision ─▶ events_vision ─▶ vision_writer ─▶ finish
                  └─────────┴──────────────┴───────────────────┴─────────────────┴────────────────┴── DeadLetter ─▶ dead_letter
```

Clips derived from vision output now carry event tags (nutmeg, shot, take-on, pass, …), so the Librarian can answer "find me X doing a nutmeg" from footage. How well each event is found is measured below.

**Models in use (2026-10-21): v4, in `models/vision_v4/`**: shot model, kit-number reader, identity configuration and event spotter, all trained on footage without captions, name labels or a ring on the ball holder (see "Name labels" below). Pass `--models models/vision_v4`; the default `models/vision/` still holds the v3 set (shot model v3, reader and identity configuration v2, event spotter v2), and `models/vision_v2/` the v2 shot model.

## Captions: a leak the first audit missed

The renderer burns broadcast captions into the picture: "REPLAY · goal by …", "NUTMEG! … through the legs of …". The v2 models were trained and measured on footage with captions. Rendering the development matches without them showed the v2 shot model had been leaning on the caption strip for replays:

| Shot model, development matches without captions | v2 (trained with captions) | v3 (trained without) |
|---|---|---|
| Replay frames recognised | 0% | 92.3% |
| Frame accuracy | 94.4% | 99.6% |
| Cut boundaries F1 (within 0.5 s) | 0.75 | 0.92 |

With captions, v2 had scored 100% on replays and 0.93 on boundaries; those figures (in the v2 tables below) overstate what it does without them. Real footage carries no such captions, so all vision footage is now rendered without them (`make_match(..., captions=False)` is the default) and the shot model was retrained (v3). The event spotter never sees captions in training or testing.

## Name labels and the holder ring: a second leak, checked

The browser audit (2026-10-21) found that captions were not the only graphic naming the play. The renderer draws a name label over the ball holder (and over a clip's focus player) and a yellow ring under them, and `captions=False` left both on. So vision footage showed, on screen, who had the ball and what their name was. That could have leaked possession and identity ground truth into what the models see. The Who's who crops of the demo match `vis_0201` printed the answer to their own question ("Quinn", "Weber", "L. Toure" above the player being asked about).

**Fix.** The renderer's `Style` has two switches, `labels` and `holder_ring` (on for the Product's broadcast videos). Vision footage turns both off (`regista.vision.dataset.vision_style`; `make_match(..., labels=False)` is the default, file names end `_nocap_nolabels`), and the holder is then drawn in depth order like everyone else, not last. A test renders a vision-style frame and checks there is no label box or ring around the holder.

**Did the models lean on them?** The frozen v3 models were scored on the development matches twice, once on the old footage (labels and ring) and once without them; nothing was retrained first. Then everything was retrained on footage without them (v4: `python3 -m regista.vision data`, `train`, `train-events`, into `models/vision_v4/`) and scored on the development matches again. Same code, same matches, identity on true camera segments for the stage rows:

| Development matches (seeds 201-206) | v3, footage with labels and ring | v3, without | v4, without |
|---|---|---|---|
| Shots: frame accuracy; replay frames; boundary F1 | 99.59%; 92.3%; 0.925 | 99.59%; 92.3%; 0.932 | 99.99%; 100%; 0.898 |
| Detection: player precision / recall | 0.994 / 0.988 | **0.9999** / 0.990 | 0.9999 / 0.990 |
| Kit number, per crop | 99.48% | 99.51% | 99.51% |
| Identity: named; named correctly | 97.1%; 99.26% | 98.3%; 99.60% | 98.3%; 99.60% |
| Ball precision / recall | 0.993 / 0.992 | 0.995 / 0.995 | 0.995 / 0.995 |
| Possession: frame accuracy / holder precision / holder recall | 0.81 / 0.90 / 0.72 | 0.82 / 0.92 / 0.75 | 0.82 / 0.92 / 0.75 |
| Possession: found / match / player right (429 true) | 0.72 / 0.83 / 0.97 | 0.74 / 0.84 / 0.97 | 0.74 / 0.84 / 0.97 |
| Cutaway appearances: precision / recall (66 true) | 0.80 / 0.59 | 0.79 / 0.58 | 0.79 / 0.58 |
| End to end, all 22 starters, six matches: clip recall / precision (470 true) | 0.743 / 0.918 | 0.749 / 0.917 | 0.749 / 0.910 |
| Events end to end: pass (256) | 0.97 / 0.78 | 0.96 / 0.77 | 0.97 / 0.77 |
| shot (26) | 0.85 / 0.65 | 0.89 / 0.62 | 0.89 / 0.65 |
| ball won (82) | 1.00 / 0.59 | 0.94 / 0.56 | 0.94 / 0.56 |
| take-on (24) | 0.93 / 0.58 | 0.82 / 0.58 | 0.89 / 0.67 |
| nutmeg (11) | 0.83 / 0.45 | 0.67 / 0.36 | **0.89 / 0.73** |
| tackle (36); carry (197) | 1.00 / 0.72; 0.80 / 0.81 | 1.00 / 0.72; 0.80 / 0.80 | 1.00 / 0.69; 0.79 / 0.80 |

What this says:

- **Identity and possession did not lean on them; they were noise.** The label text is drawn in white and dark on the pitch, and the detector took pieces of it for players: 952 false player detections on the development matches with labels, 18 without. Without labels more tracks get named (97.1% → 98.3%) and possession recall rises a little. The same frozen models do slightly better on footage without them, so the earlier identity and possession numbers were not inflated by the leak.
- **The event spotter was the one stage trained on it.** It learned how events measure from vision output of footage with the ring. On footage without it, v3's take-on and nutmeg precision fell (one lost nutmeg and one invented, on 11). Retrained on footage without them, v4 is better than v3 was on either footage: 8 of 11 nutmegs instead of 5. Development matches were only scored, never tuned against, and v4 was chosen over v3 here before the fresh matches were looked at.
- **The v4 shot model** recognises every replay frame (v3 called 80 replay frames highlights) but finds cuts slightly less well (boundary F1 0.898 against 0.932: 66 of 77 cuts found instead of 69, and 4 invented instead of 2).
- **Clips did not move** (0.749 either way). The per-match swing is larger than the total: syn_0201 lost 6 of 67 clips and syn_0205 gained 6 of 75.

**Fresh matches, scored once more.** Because the footage changed, seeds 301-303 were rendered without labels and ring and scored once with the frozen v4 models (file fingerprints checked before and after). This is the third time these matches have been scored, each time with frozen models after a footage change (captions, then labels); nothing was tuned on them. The table under "Measured numbers" is that scoring.

## Measured numbers

Data: 10 training matches, 6 development matches (seeds 201-206), and 3 fresh matches (seeds 301-303), 5 minutes of play each (some are 2 x 2.5-minute halves, which adds a half-time graphic). Each was rendered at 640x360, 10 fps, by `python3 -m regista.vision data`. Identity, cutaway, and possession numbers use the true camera segments, so each stage is scored on its own. The end-to-end rows run every stage from the video.

**Development set, not held out.** No model is trained on seeds 201-206, but they were used while building: detector fixes, the possession thresholds (`PossessionConfig` defaults), and cut tuning were checked against them. Their numbers are development numbers and flatter the pipeline. Their clubs are not in training, but three of their kit colours are (an exact reuse in seeds 201, 205, and 206), so they do not test unseen colours either.

**Fresh matches.** Seeds 301-303 were created after the audit, with new clubs and primary and goalkeeper colours at least 20 ΔE from every training kit and from the development kits (and well away from the grass and neutrals). They were first scored once with the frozen v2 models; nothing was changed after seeing the result. After each footage change (captions, then name labels) they were scored once more with frozen models. These are the numbers to quote.

**Current models (v4) on footage without captions, name labels or holder ring** (scored once on 2026-10-21, models frozen and fingerprinted):

| Stage | Metric (3 fresh matches, seeds 301-303) | Measured |
|---|---|---|
| Shots | frame accuracy after segmentation | **99.7%** (main, replay, highlight, crowd 100%; closeup 88.9%; graphic 99.3%) |
| Shots | segment-boundary precision / recall / F1, within 0.5 s (45 true boundaries) | 0.973 / 0.800 / **0.878** |
| Camera calibration | mean error of the recovered pan | 0.05 m |
| Detection | player precision / recall | **0.9998 / 0.987** (0.9998, 0.9996, 0.9999 per match) |
| Detection | ball precision / recall; mean ball position error | 0.996 / 0.996; 0.15 m |
| Team | team accuracy over matched detections | **99.98%** |
| Kit number | per-crop reading, number visible (33,628 crops: main / replay / highlight / closeup) | **99.3%** (99.6 / 95.9 / 98.9 / 100) |
| Identity | detections whose track is named, and named correctly | 98.9% named; **99.0%** of those correct (98.0% of all matched detections) |
| Position | mean / 95th-percentile pitch error of player ground points | **0.18 m** / 0.43 m |
| Cutaway appearances | replay, highlight, and closeup players vs generator appearances (36 true) | precision 0.76, recall **0.53** |
| Possession | frame accuracy / holder precision / holder recall | 0.82 / 0.88 / **0.76** |
| Possession | true possessions found (IoU ≥ 0.5) / predicted ones that match / player right when overlapping (209 true) | 0.76 / 0.85 / **0.95** |
| End to end (each match, every stage from video, all 22 starters) | clip recall / precision at IoU ≥ 0.5; true clip-seconds covered | syn_0301: 0.66 / 0.94; 67%. syn_0302: 0.79 / 0.91; 80%. syn_0303: 0.78 / 0.96; 79% |
| End to end (all three, 234 true clips) | clip recall / precision at IoU ≥ 0.5 | **0.75 / 0.94** |
| End to end, t_home_09 only | clip recall / precision at IoU ≥ 0.5 | 0.78 / 1.00, 0.71 / 0.83, 1.00 / 1.00 (9, 7, 4 true clips) |

**What changed from the previous scoring** (v3 models on footage with labels and ring): detection precision 0.966 → 0.9998; the drop on syn_0302 (0.916), put down to its unseen colours, was the name labels. Identity named 98.2% → 98.9%, named correctly 99.2% → 99.0%. Cutaway precision 0.60 → 0.76. Boundary F1 **fell**, 0.918 → 0.878 (v4 finds 36 of 45 cuts where v3 found 39). Possessions found 0.77 → 0.76, player right 0.97 → 0.95. End to end 0.76 / 0.94 → **0.75 / 0.94**: syn_0301 up (0.63 → 0.66), syn_0303 down (0.86 → 0.78). Earlier scorings: v2 on footage with captions gave 0.76 / 0.94, but its 100% replay recognition depended on the captions (see "Captions" above).

The fresh numbers sit close to the development numbers: identity, kit numbers, detection and shots carry over to unseen colours, and end-to-end recall varies by match (0.66 to 0.79) with possession recall. Reproduce: `python3 -m regista.vision evaluate --set fresh --root /tmp/regista_events --models models/vision_v4` (the end-to-end row runs on the set's first match unless `--e2e-seed` is given; the all-starters rows run every fresh match end to end). These runs include two fixes made after the audit: appearance and possession records no longer run past the end of their shot, and vision roles no longer retry deterministic failures.

### Development set (seeds 201-206)

v2 models on footage with captions and name labels (the shot rows overstate replay recognition; see "Captions"; for v3 and v4 on footage without labels, see "Name labels"). Re-scored with the same frozen models and today's code, after the two fixes above; no figure moved by more than 0.02.

| Stage | Metric (6 development matches unless noted) | Measured |
|---|---|---|
| Shots | frame accuracy after segmentation (19,752 frames) | **99.98%** (main 100%, replay 100%, highlight 99.75%, closeup 100%, crowd 100% on 50 frames, graphic 100%) |
| Shots | segment-boundary precision / recall / F1, within 0.5 s (77 true boundaries) | 0.959 / 0.909 / **0.933** |
| Camera calibration | mean error of the recovered pan | 0.05 m |
| Detection | player precision / recall (discs inside the frame, less than 40% covered; 8,421 frames at 5 fps) | **0.995 / 0.988** |
| Detection | ball precision / recall; mean ball position error | 0.993 / 0.991; 0.15 m |
| Team | team accuracy over matched detections | **99.99%** |
| Kit number | per-crop reading, number visible (69,202 crops: main / replay / highlight / closeup) | **99.5%** (99.6 / 98.1 / 99.1 / 100) |
| Kit number | free reading of fresh synthetic discs, numbers 1-99 (3,000) | 85.9% (84.9% for 12-99) |
| Identity | detections whose track is named, and named correctly | 97.2% named; **99.3%** of those correct (96.6% of all matched detections) |
| Position | mean / 95th-percentile pitch error of player ground points | **0.20 m** / 0.46 m |
| Cutaway appearances | replay, highlight, and closeup players vs generator appearances (66 true) | precision 0.77, recall **0.61** |
| Possession | frame accuracy (holder or nobody) / holder precision / holder recall | 0.81 / 0.90 / **0.72** |
| Possession | true possessions found (same player, time IoU ≥ 0.5) / predicted ones that match / player right when overlapping (429 true) | 0.71 / 0.83 / **0.97** |
| End to end (syn_0201, every stage from video) | clips for t_home_09 from the vision stream vs from ground truth: recall / precision at IoU ≥ 0.5; true clip-seconds covered | 0.80 / 1.00; 84% |
| End to end (syn_0201, all 22 starters) | clips recall / precision at IoU ≥ 0.5 (67 true clips); true clip-seconds covered | **0.75 / 0.96**; 73% |
| End to end, by clip reason (all starters) | on-ball main / replay / highlight / closeup recall | 0.81 (58) / 0.50 (2) / 0.17 (6) / 1.00 (1) |

Reproduce the development-set numbers (about 25 minutes on a 10-core laptop: render 1.5, train 7.5, evaluate 15; everything is written under `/tmp/regista_vision`, nothing in the repo):

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
- **Speed**: about 95 s for a 5.5-minute match at 640x360 on a laptop CPU (shots 12 s, identity 80 s at 5 analysed frames per second, about 50 ms per frame). Measured separately at about 0.3x real time, a 90-minute match at 640x360 would take about half an hour, at 1280x720 about an hour, and at 1080p several hours. The frame reader decodes every frame at full size and drops the unsampled ones in Python, and one run decodes the video about four times; sampling inside ffmpeg and probing once are the first speed fixes.

### Limits of what was tested

- **One format.** Every training and test video is 640x360 at 10 fps. At 1280x720 the shot model classed every replay frame as a highlight (replay accuracy 0%). At 25 fps replay accuracy fell to 76% and boundaries were found later, because sampling 10 of 25 frames gives uneven gaps and the motion features (slow motion is the replay cue) were learned at even 0.1 s gaps. Identity held at about 99.7% in both. Real footage needs the shot model retrained on its own format, with features normalised by the frame gap.
- **What inference is given.** Besides the team sheet and kit colours, the vision run receives the match header's period start and end times and attacking directions. On a real broadcast those come from the broadcast log or the on-screen clock, which v0 does not read. Inference also knows the renderer's camera model and its grass, shadow, and line colours; the 0.05 m pan and 0.20 m position errors depend on that prior.
- **Kit colours.** The detector takes its colours from the roster, so unseen colours mainly test the colour clustering and the number reader's normalisation; the fresh matches cover that.

## A full 90-minute match

Everything above was measured on 5-minute matches. The product is meant for a full broadcast, so two full matches were generated (2 x 45 minutes, realistic profile, new clubs, no captions; v3 models on footage that still drew the holder's name label and ring, not re-run since) and run end to end: render, shots, identity, possession, events, clips, Librarian.

**First full match (seed 901), as a probe.** It exposed what 5-minute demo-profile matches had hidden: v1 interception precision of 0.11 (realistic play wins loose balls back as "recoveries", which v1 called interceptions), goals and shots timed up to two seconds early, and a renderer that held every position record in memory (4.6 GB). All three were fixed (spotter v2 above; the renderer now streams tracks, 225 MB). Because it was looked at, this match is a development match from here on.

**Second full match (seed 902), scored once with frozen models** (file fingerprints checked before and after):

| Measure (90.7 minutes of video) | Result |
|---|---|
| Whole vision pipeline | 30.6 minutes (0.34x real time; 21.6 minutes, 0.24x, on the first match, which ran without other load). Identity is 80-86% of it; shots 3 minutes; possession and events under a second each |
| Peak memory / identity result on disk | 2.4 GB / 211 MB |
| Records | 152 shots, 1,096 possessions, 1,650 events, 3,986 appearances; 12 identity questions prepared |
| Goals | **5 of 5**, at the right time, by the right player |
| Pass (768 true) | precision 0.97, recall 0.90 |
| Shot (27) | 0.91 / 0.78 |
| Save (8) | 1.00 / 0.63 |
| Tackle (33) | 0.88 / 0.85 |
| Ball won after a pass (192) | 0.98 / 0.61 |
| Take-on (25) | 0.70 / 0.64 |
| Cross (37) | 0.74 / 0.54 |
| Carry (467) | 0.71 / 0.90 |
| Nutmeg (1) | missed |
| **Clips for all 22 starters** (1,182 true clips) | **recall 0.86, precision 0.94** |
| Librarian and conversation on the full match | under 0.1 s per question |

Clip quality at full length is better than on the 5-minute matches (0.76 / 0.94 then, 0.75 / 0.94 with v4), mainly because realistic play has fewer, longer possessions. Nutmegs stay the weak spot: rare at full length (one in this match) and still missed.

**Speed and memory fixes from these runs.** Probing a video reads the container's metadata instead of decoding it (a full pass per probe before; a run probes several times). Sampling happens inside ffmpeg: whole-number ratios (25 -> 5, 30 -> 5, 10 -> 5) keep exactly every k-th frame, pixel for pixel the same as before but without decoding and copying the rest into Python; other ratios and variable-frame-rate phone recordings are spaced evenly by timestamp. Neither shows on our 640x360 renders, where identity dominates; both matter for a 1080p phone recording. The renderer streams tracks into its timelines instead of holding a million records.

## Who's who: a person corrects identity (plan step 3)

The identity agent names tracks by kit-number vote and decides who appears in each replay. Where it is unsure, `regista.vision.review` turns that into a short list of questions, ranked by how much a wrong call costs (seconds of footage, how close the vote was):

- **"Who is this player?"** for a track whose top two candidates are close, or that has no name: a ringed crop of the player and the top candidates.
- **"Who is in this replay?"** for a replay, highlight or closeup whose involvement scores sit near the decision line, or that has nobody in it (the clip rule then cuts it for no one).

**Three ways to answer.** In the vision workflow (`python3 -m regista.vision run VIDEO --roster ... --out ... --workflow --review`), an `identity_review` step after identity pauses the Agent Framework run with a request for answers (`request_info`), and the run resumes with them applied before possession, events and clips run. Every vision run also leaves the questions and crops in `OUT/review/`, so they can be answered later in the viewer's **Who's who?** panel (`GET`/`POST /api/matches/{id}/identity-review`; writes need the token) or at the terminal.

**What an answer does.** The track is renamed, and a track holding that name *in the same frames* loses it there, and only there. The tracker sometimes doubles a player for a few frames or splits one player into touching tracks, so unnaming the whole other track would undo frames that were right; the first version did that and made identity worse. Replays get the players named. Possession, events, appearances and clips are recomputed. Answers become `annotation` records (`target_type` `track` or `appearance`, `source: human`) in `OUT/review/identity_answers.jsonl` and the feedback folder. Reviewed calls are never asked again; the next most uncertain ones are prepared.

**Measured on the development matches with simulated answers** (v3 models, footage with name labels; not re-run since). Answers here are read from the generator's ground truth, standing in for a careful person; they say so (`source: synthetic`, `simulates: human`) and are never presented as a person's review. Identity on true camera segments, 12 questions per match:

| Development match | Identity (named correctly, of matched detections) | Replay appearances precision / recall |
|---|---|---|
| syn_0201 | 99.31% → 99.88% | 0.60 / 0.33 → 1.00 / 1.00 |
| syn_0202 | 99.06% → 99.90% | 0.71 / 0.56 → 1.00 / 0.89 |
| syn_0203 | 95.91% → 97.59% | 0.73 / 0.57 → 1.00 / 0.93 |
| syn_0204 | 98.28% → 98.98% | 0.69 / 0.64 → 0.91 / 0.71 |
| syn_0205 | 93.19% → 97.74% | 0.78 / 0.64 → 0.78 / 0.64 |
| syn_0206 | 98.27% → 98.90% | 0.60 / 0.33 → 1.00 / 1.00 |

Through to the product, for all 22 starters on the six matches (470 true clips): clip recall 0.764 → **0.830**, precision 0.918 → **0.954**; pass recall 0.746 → 0.777, take-on recall 0.583 → 0.667.

**Learning from the answers (plan step 6).** `python3 -m regista.vision learn-from-reviews MATCH_DIR ...` turns every answered track into labelled kit-number crops and fine-tunes the reader (`DigitClassifierReader.fine_tune`), keeping the previous reader beside it. The first version made the reader worse on matches nobody reviewed (per-crop accuracy 99.6% → 96.1-99.2%): a track that swaps players gets one name for all its frames, and rehearsing only synthetic discs pulled the reader away from rendered shirts. Now frames the reader confidently reads as another number are left out, and fine-tuning rehearses 17,070 real crops from training matches beside synthetic discs. Corrections from dev matches 201-203, then identity on 204-206 (unreviewed): reader errors per crop 0.36% → 0.30%, 0.37% → 0.33%, 0.42% → 0.32%; identity unchanged within ±0.15%. On rendered footage the reader is near its ceiling, so the immediate fix is where review pays; on real footage, where the reader starts weaker, the learning half matters more, and that is unmeasured until Zaid's match.

**On the live app: the demo vision match `vis_0201`.** The library ships one vision match so the human-in-the-loop step can be seen online. It is the vision layer's output (v4 models) on development match syn_0201, which Regista rendered itself (640x360, 10 fps, no captions, no name labels or holder ring), run offline and packaged by `python3 -m regista.vision.package`. The package is 2.0 MB: events, clips for t_home_09 (7 clips; against ground truth recall 0.70, precision 1.00), the 3 open questions (1 player, 1 replay, 1 highlight) with their crops, and tracks thinned to 1 Hz. The first package (v3 models, footage with name labels) had 11 questions, and its crops printed the answer above the player being asked about; footage without labels names more tracks confidently, so fewer calls are close. The Studio view key shows judges the questions and crops read-only.

**Answering it.** Answering needs three things that never leave the machine that ran the vision layer: the identity result (`.vision_work/identity.joblib`, 11 MB), the video, and the vision models. On that machine the full vision output lives in `data/vision/vis_0201/` (git-ignored and left out of the image; `REGISTA_VISION_WORK` moves the root), with the video in `data/vision/video/`. `.vision_work/run.json` records which models made it. `POST /api/matches/vis_0201/identity-review` finds that folder (`regista.vision.package.work_dir_for`), applies the answers there, recomputes possession, events and clips, and packages the match again (`repackage`): the answers and the next questions land in the committed `data/synthetic/sample/vis_0201`, still small and free of machine paths, and the next deploy puts them live. On the live app there is no such folder, so the same request is refused with 409 even with the admin key, and nothing changes: no file, no annotation, and the questions stay open. If the identity result were ever shipped, an answer would land on the replica's disk, which Container Apps wipes on every restart and every new revision; identity answers are not copied to Cosmos DB (only clip verdicts are). To recreate the full output on another machine:

```bash
python3 -m regista.vision run data/vision/video/syn_0201_640x360_10fps_nocap_nolabels.mp4 --roster /tmp/regista_vision/matches/syn_0201 \
    --out data/vision/vis_0201 --match-id vis_0201 --workflow --models models/vision_v4
python3 -m regista.vision.package data/vision/vis_0201 data/synthetic/sample/vis_0201 --player t_home_09 --derive-clips --note "..." --rendering '{...}'
```

(the video comes from `make_match(TEST_SPECS[0])`, i.e. `python3 -m regista.vision data`; the note and rendering are in the committed manifest).

## Event spotting

**What makes events visible.** In the generator's first version a nutmeg moved the ball and the players exactly like any take-on, so no camera could have told them apart. The generator now records each one-on-one as a camera would see it: the defender steps into the carrier's path, goal-side; for a nutmeg the ball goes straight through him while the carrier goes round; for a plain take-on carrier and ball go round together; a failed take-on has him step across in front. Only the recorded positions around those moments change, applied after the match is simulated so the defender steps in smoothly; the events, possessions and every random draw are unchanged (a test pins the committed sample).

**Data.** Footage rendered without captions (and, since v4, without name labels or holder ring), positions recorded at 10 Hz. Training: vision output of 40 rendered matches (the 10 training matches plus 30 more with the same clubs and colours), plus 60 matches that are only generated, sampled at the vision layer's 5 frames a second with its measured noise (about 0.2 m) and run through the same possession agent. Vision examples weigh three times a generated one: the generated data supplies volume for rare events (53 nutmegs, 274 take-ons in training), the vision data supplies how events measure through the camera (it reads a ball crossing a defender as about 1 m from him where generated positions say 0.4 m). Development: seeds 201-206. Fresh: seeds 301-303, scored once with frozen models (file fingerprints checked before and after).

The tables below are spotter v1, the first version. A full 90-minute match (next section) exposed two weaknesses, and spotter v2 fixes what can be fixed:

- **Timing.** A possession often ends a beat before the kick, so v1 timed passes and shots up to two seconds early and missed a goal it had found. v2 times passes, crosses and shots at the first moment the ball moves at kicking speed, and goals when the ball first reaches the goal mouth; training labels are matched there too.
- **Interception or recovery cannot be seen.** After a misplaced pass the generator calls the opponent's win an interception or a ball recovery at random, with identical movement; the dense demo profile says interception, the realistic profile mostly says recovery. v1 called every one an interception, which looked fine on demo-profile matches (0.96 precision) and fell to 0.11 on a realistic 90-minute match. v2 spots what footage shows, the opponent winning the ball after a pass, and it is scored against interceptions and recoveries together (`ball_won`). Telling them apart would need the generator to make them look different, as it now does for nutmegs. Clearances are not spotted: the clearing player never holds the ball long enough to count as a possession.
- **Both profiles in training.** The 60 generated training matches alternate the demo and realistic profiles.

**Spotter v4 (current), trained on footage without name labels or holder ring, scored once on the fresh matches** (identity on true segments; the end-to-end figures are the same because the shot model gets every main-camera frame right): pass 1.00 / 0.76, shot 0.80 / 0.80, goal 1 of 1, save 3 of 4, ball won 0.85 / 0.62, tackle 1.00 / 0.44, take-on 0.82 / 0.50, **nutmeg 0.67 / 0.67** (4 of 6), carry 0.85 / 0.84 (precision / recall). Against spotter v2 below (v3 identity, footage with labels): nutmegs and take-on recall better; shots, tackles, saves and ball won worse. Development matches: pass 0.97 / 0.77, shot 0.89 / 0.65, goal 2 of 2, take-on 0.89 / 0.67, nutmeg 0.89 / 0.73, tackle 1.00 / 0.69 ("Name labels" above has v3 against v4).

Spotter v2, scored once on the fresh 5-minute matches (identity on true segments): pass 0.99 / 0.81, shot **0.93 / 0.93**, save 4 of 4, ball won 0.96 / 0.68, tackle 1.00 / 0.56, take-on 0.89 / 0.44, nutmeg 0.50 / 0.33, carry 0.86 / 0.83 (precision / recall). Development matches: pass 0.96 / 0.78, shot 0.85 / 0.65, goal 2 of 2, nutmeg 0.83 / 0.46, tackle 1.00 / 0.69 (the broader ball-won class absorbs a few tackles: v1 had 0.72).

**Spotter v1. Fresh matches, scored once, end to end** (shot model v3 finds the segments, then identity, possession and events; a prediction matches a true event of the same type within 1 s; only events in main-camera footage count):

| Event | True | Precision | Recall | Right player |
|---|---|---|---|---|
| Pass (completed) | 129 | 0.98 | 0.80 | 97% |
| Shot | 15 | 0.87 | 0.87 | 100% |
| Goal | 1 | 1 of 1 | 1 of 1 | 100% |
| Save | 4 | 1.00 | 1.00 | 100% |
| Interception | 35 | 0.96 | 0.71 | 100% |
| Tackle | 18 | 1.00 | 0.56 | 100% |
| Carry | 117 | 0.86 | 0.85 | 91% |
| Take-on (successful) | 18 | 0.89 | 0.44 | 100% |
| **Nutmeg** | 6 | **0.50** | **0.33** | 100% |
| Cross | 1 | 0.50 | 1.00 | 100% |

Through the clip rule: of the 6 true nutmegs, 2 can be found as a nutmeg-tagged clip of the right player; of the 4 nutmeg-tagged clips, 2 are real.

**Development matches, end to end:** pass 0.95 / 0.74, shot 0.89 / 0.65, goal 2 of 2, save 1.00 / 0.50, interception 1.00 / 0.64, tackle 0.96 / 0.72, carry 0.80 / 0.81, take-on 0.93 / 0.58, nutmeg 0.80 / 0.36 (11 true), cross 0.46 / 0.50 (precision / recall).

**Why recall is lower than precision.** Most missed events are missed upstream: the possession agent finds about 72% of possession frames, so a hand-over it never sees cannot be classified, and a duel needs both players named in the frames around it. When a candidate exists, the decision is usually right. Nutmegs fail in all three places (no possession, players unnamed, or a measured ball path that looks like a plain take-on) and are rare (6 in the fresh matches), so their numbers are both weak and noisy. Crosses are capped by the generator itself: it calls only 70% of wide final-third balls crosses, at random, so no position-based model can separate them fully.

Reproduce: `python3 -m regista.vision train-events --models models/vision_v4` (renders the event footage under `/tmp/regista_events`, runs identity on it with that folder's reader, trains, writes `event_spotter.joblib` there), then `python3 -m regista.vision evaluate-events --set dev --models models/vision_v4` (event spotting alone, identity on true segments; `--with-labels` scores the older footage). The end-to-end figures run the full `run_vision` on each video.

## What changes for real broadcast footage

Every stage keeps its interface. The things that change are listed here plainly. None of them is done yet.

- **Shots.** The same code retrains on human-labelled segments (`train_shot_model` takes any list of video + segments). Real replay cues are different: branded wipes and stingers, slow motion, unusual angles, and dissolves, which a hard-cut detector misses. On the renderer, the REPLAY badge and slow motion are the strongest cues. Expect to label a few matches per broadcaster. A learned boundary model (for example TransNetV2, hosted in Microsoft Foundry) is the upgrade path.
- **Detector.** Players are people, not discs. `DiscDetector` becomes a person detector: a YOLO-class model fine-tuned on broadcast football and hosted in Foundry, or Azure AI Vision object detection. The ground point becomes the bottom-centre of the box. Team assignment keeps the kit-colour clustering on torso pixels, with referees and goalkeepers as extra clusters. The ball needs its own small-object detector with temporal filtering.
- **OCR backend.** `AzureVisionOCRReader` is the slot for Azure AI Vision Read (OCR) on torso crops. It is deliberately not implemented and makes no calls. Numbers on real shirts are visible in a minority of frames (back turned, side-on, small), so the track vote that already absorbs hidden numbers matters more. Faces are never used (§1.5).
- **Homography.** The synthetic calibrator solves one unknown (the pan). A real camera pans, tilts, and zooms through a distorting lens, so calibration becomes a per-frame homography from pitch-line and keypoint detection with RANSAC, tracked over time. `HomographyMapping` already implements the mapping interface.
- **Replay cues and mapping.** Replays should be mapped back to live time (`replays_window`) by matching player layouts, so replay appearances can use the live identities. Today they are named independently.
- **Events.** The event spotter's features are pitch geometry (who had the ball, where it went, who was passed), so they carry over from rendered discs to tracked people once identity and homography do. What has to be relearned is how events measure through a real camera, from Zaid's labels on his recorded match. A nutmeg on real footage is still the same geometric fact (the ball crosses the defender's ground position while the carrier goes round), but it needs the ball tracked through a crowd of legs, which the disc renderer never tests.
- **Labels.** Human labels replace `regista.vision.truth`: shot kinds marked in a review tool, player boxes and numbers on sampled frames, possessions on short windows. They are stored as `annotation` records with `source: human`.
