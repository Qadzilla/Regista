"""The renderer must honour the stream: segment durations, captions, replay badges, clips."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image

from regista.clips import derive_clips
from regista.render.clips import main as clips_main
from regista.render.draw import COLOUR_HIGHLIGHT, COLOUR_REPLAY, Style, frame_info, render_frame
from regista.render.scene import Scene
from regista.render.video import count_frames, frame_times, has_ffmpeg, render_video
from regista.synth import generate

REPO = Path(__file__).resolve().parents[1]
SAMPLE = REPO / "data" / "synthetic" / "sample" / "syn_0109"
PLAYER = "t_home_10"
SMALL = Style(width=320, height=180)
FPS = 5.0


@pytest.fixture(scope="module")
def result():
    return generate(seed=109, minutes=3.0, track_hz=1.0)


@pytest.fixture(scope="module")
def scene(result):
    return Scene.from_records(result.stream, result.tracks)


def _close(a: float, b: float, tol: float) -> bool:
    return abs(a - b) <= tol


# ----------------------------------------------------------------------------- scene

def test_scene_positions_are_interpolated_between_samples(scene):
    pid = next(iter(scene.players))
    tl = scene.players[pid]
    # Find two consecutive samples one gap apart and check the midpoint lies between them.
    for i in range(len(tl.ts) - 1):
        if _close(tl.ts[i + 1] - tl.ts[i], scene.sample_gap, 0.05):
            mid = (tl.ts[i] + tl.ts[i + 1]) / 2
            pos = scene.positions_at(mid)[pid]
            assert _close(pos[0], (tl.xs[i] + tl.xs[i + 1]) / 2, 1e-6)
            assert _close(pos[1], (tl.ys[i] + tl.ys[i + 1]) / 2, 1e-6)
            return
    pytest.skip("no adjacent samples found")


def test_score_and_clock_follow_the_events(scene):
    goals = [e for e in scene.events if e["event_type"] == "goal"]
    assert goals, "test match must contain a goal"
    g = goals[0]
    before, after = scene.score_at(g["t"] - 0.01), scene.score_at(g["t"] + 0.01)
    assert after[g["team_id"]] == before[g["team_id"]] + 1
    assert scene.clock_at(0.0) == "00:00"
    assert scene.clock_at(61.0) == "01:01"
    period_end = scene.match["periods"][0]["t_end"]
    assert scene.clock_at(period_end + 1.0) == "HT"


# ----------------------------------------------------------------------------- frame info and pixels

def test_goal_caption_appears_in_the_right_frame_range(scene):
    g = next(e for e in scene.events if e["event_type"] == "goal")
    # Caption timing is decided by the scene; the director may cut away before the 4 s window ends.
    assert scene.caption_at(g["t"] + 0.5).kind == "goal"
    assert scene.caption_at(g["t"] + 3.9).kind == "goal"
    late = scene.caption_at(g["t"] + 4.5)
    assert late is None or late.kind != "goal"
    early = scene.caption_at(g["t"] - 0.1)
    assert early is None or early.kind != "goal"
    assert frame_info(scene, g["t"] + 0.5)["kind"] == "main"
    assert frame_info(scene, g["t"] + 0.5)["caption"].startswith("GOAL!")
    # Pixel check: the caption strip's accent bar is drawn at the left edge only while a caption is active.
    s = SMALL
    probe = (2, int(s.height - 68 * s.s))
    with_caption = render_frame(scene, g["t"] + 0.5, s).getpixel(probe)
    assert with_caption == COLOUR_HIGHLIGHT
    quiet_t = next(t for t in (5.0, 7.0, 9.0, 11.0, 13.0) if frame_info(scene, t)["caption"] is None and frame_info(scene, t)["kind"] == "main")
    without = render_frame(scene, quiet_t, s).getpixel(probe)
    assert without == s.surround


def test_replay_frames_carry_the_badge_and_map_time(scene):
    replays = [seg for seg in scene.segments if seg["kind"] == "replay"]
    assert replays, "test match must contain a replay"
    seg = replays[0]
    t = seg["t"] + 1.0
    info = frame_info(scene, t)
    assert info["kind"] == "replay"
    assert info["badge"]["text"] == "REPLAY"
    assert info["caption"].startswith("REPLAY")
    win = seg["replays_window"]
    assert win["t"] <= info["scene_t"] <= win["t_end"]
    speed = seg["playback_speed"]
    later = frame_info(scene, t + 1.0)
    assert _close(later["scene_t"] - info["scene_t"], speed, 1e-6)
    # Pixel check: the badge box top-right is replay red.
    s = SMALL
    img = render_frame(scene, t, s)
    probe = (int(s.width - 30 * s.s), int(22 * s.s + 6 * s.s))
    assert img.getpixel(probe) == COLOUR_REPLAY
    # And a main-view frame has no badge there (surround colour).
    main_t = next(sg["t"] + 0.5 for sg in scene.segments if sg["kind"] == "main")
    assert render_frame(scene, main_t, s).getpixel(probe) == s.surround


def test_every_segment_kind_renders(scene):
    kinds = {}
    for seg in scene.segments:
        kinds.setdefault(seg["kind"], seg)
    assert {"main", "replay", "closeup"} <= set(kinds)
    for kind, seg in kinds.items():
        img = render_frame(scene, seg["t"] + 0.2, SMALL)
        assert img.size == (SMALL.width, SMALL.height), kind


def test_title_card_is_drawn_when_requested(scene):
    s = SMALL
    card = {"t": 0.0, "t_end": 2.0, "title": "Test title", "subtitle": "tags", "watchability": 0.8}
    probe = (int(40 * s.s + 4 * s.s), int(s.height - 150 * s.s))
    assert render_frame(scene, 0.5, s, card).getpixel(probe) == COLOUR_HIGHLIGHT
    assert render_frame(scene, 0.5, s).getpixel(probe) != COLOUR_HIGHLIGHT


# ----------------------------------------------------------------------------- video files

def test_frame_count_matches_segment_durations(scene, tmp_path):
    out = tmp_path / "match.mp4"
    manifest = render_video(scene, out, fps=FPS, style=SMALL, workers=1)
    expected = len(frame_times(0.0, scene.duration, FPS))
    assert manifest["frames"] == expected
    assert count_frames(manifest["path"]) == expected
    # Segments tile the timeline, so per-segment frame counts must add up to the same total.
    per_segment = sum(len(frame_times(sg["t"], sg["t_end"], FPS)) for sg in scene.segments)
    assert abs(per_segment - expected) <= len(scene.segments)


@pytest.mark.skipif(not has_ffmpeg(), reason="parallel parts need ffmpeg concat")
def test_parallel_render_matches_single_process(scene, tmp_path):
    t1 = 20.0
    single = render_video(scene, tmp_path / "one.mp4", fps=FPS, style=SMALL, workers=1, t1=t1)
    multi = render_video(scene, tmp_path / "many.mp4", fps=FPS, style=SMALL, workers=2, t1=t1)
    assert single["frames"] == multi["frames"] == len(frame_times(0.0, t1, FPS))
    assert count_frames(multi["path"]) == multi["frames"]
    assert multi["parts"] > 1


def test_keyframes_are_dumped_with_an_index(scene, tmp_path):
    frames_dir = tmp_path / "frames"
    render_video(scene, tmp_path / "k.mp4", fps=FPS, style=SMALL, workers=1, t1=12.0, frames_dir=frames_dir)
    index = json.loads((frames_dir / "frames.json").read_text())
    assert index and all((frames_dir / row["file"]).exists() for row in index)
    assert index[0]["frame"] == 0
    with Image.open(frames_dir / index[0]["file"]) as im:
        assert im.size == (SMALL.width, SMALL.height)


def test_clip_videos_exist_for_every_clip_record(result, scene, tmp_path):
    clips, labels = derive_clips(result.stream, PLAYER)
    assert clips
    match_dir = tmp_path / "match"
    match_dir.mkdir()
    (match_dir / "events.jsonl").write_text("\n".join(json.dumps(r) for r in result.stream) + "\n")
    (match_dir / "tracks.jsonl").write_text("\n".join(json.dumps(r) for r in result.tracks) + "\n")
    (match_dir / "clips.jsonl").write_text("\n".join(json.dumps(r) for r in clips + labels) + "\n")
    out = tmp_path / "clips"
    assert clips_main([str(match_dir), "--player", PLAYER, "--out", str(out), "--fps", str(FPS), "--size", "320x180"]) == 0
    index = json.loads((out / "index.json").read_text())
    assert {c["clip_id"] for c in index["clips"]} == {c["id"] for c in clips}
    total = 0
    for c in index["clips"]:
        path = Path(c["path"])
        assert path.exists() and path.stat().st_size > 0
        want = len(frame_times(c["t"], c["t_end"], FPS))
        assert count_frames(path) == want, c["clip_id"]
        total += want
    assert count_frames(index["reel"]["path"]) == total
    # The reel is best-first.
    watch = {c["clip_id"]: c["watchability"] for c in index["clips"]}
    order = [watch[i] for i in index["reel"]["order"]]
    assert order == sorted(order, reverse=True)


def test_clip_cutter_derives_clips_for_a_player_not_in_clips_file(result, tmp_path):
    match_dir = tmp_path / "match"
    match_dir.mkdir()
    (match_dir / "events.jsonl").write_text("\n".join(json.dumps(r) for r in result.stream) + "\n")
    (match_dir / "tracks.jsonl").write_text("\n".join(json.dumps(r) for r in result.tracks) + "\n")
    other = next(p["player_id"] for p in result.match["players"] if p["player_id"] != PLAYER and p["starter"] and p["team_id"] == "t_away")
    out = tmp_path / "clips"
    code = clips_main([str(match_dir), "--player", other, "--out", str(out), "--fps", str(FPS), "--size", "320x180", "--no-reel"])
    assert code in (0, 1)  # 1 only if that player genuinely has no clips
    if code == 0:
        assert (out / "index.json").exists()


@pytest.mark.parametrize("seed", [5, 77])
def test_untuned_seeds_render(seed, tmp_path):
    r = generate(seed=seed, minutes=1.0, track_hz=1.0)
    sc = Scene.from_records(r.stream, r.tracks)
    manifest = render_video(sc, tmp_path / f"s{seed}.mp4", fps=4.0, style=Style(256, 144), workers=1)
    assert manifest["frames"] == len(frame_times(0.0, sc.duration, 4.0))
    for seg in sc.segments:
        render_frame(sc, seg["t"] + 0.1, Style(256, 144))


def test_cli_runs_on_the_committed_sample(tmp_path):
    out = tmp_path / "sample.mp4"
    frames = tmp_path / "frames"
    cmd = [sys.executable, "-m", "regista.render", str(SAMPLE), "--out", str(out), "--fps", "2", "--size", "320x180",
           "--workers", "2", "--frames-dir", str(frames), "--end", "60"]
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=REPO)
    assert proc.returncode == 0, proc.stderr
    assert "wrote" in proc.stdout
    assert out.exists() or out.with_suffix(".gif").exists()
    index = json.loads((frames / "frames.json").read_text())
    assert index
