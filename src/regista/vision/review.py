"""Asking a person who's who: plan step 3, "perfect the identification with Zaid in the loop".

The identity agent names every track by kit-number vote and decides who appears in each replay. Where it is unsure,
this module turns its doubt into a short list of questions a person can answer in seconds:

- ``track``: "Who is this player?" A main-camera track whose name is uncertain (two candidates close in the vote)
  or missing, with a crop of the player and the identity agent's top candidates.
- ``cutaway``: "Who is in this replay?" A replay, highlight or closeup whose involvement scores sit near the
  decision threshold, with a frame of it and the candidates.

Questions are ranked by how much a wrong answer costs (seconds of footage, how close the call was) so the first few
fix the most. Answers do three things:

1. Fix this match now: the track is renamed (and any other track holding that name at the same time loses it: one
   player per moment), the replay's players are set, and possession, events, appearances and clips are recomputed.
2. Become ``annotation`` records (``source: human``) with a snapshot of what was asked, so they survive the match.
3. Teach the kit-number reader: every frame of a corrected track becomes a labelled crop, and the reader is
   fine-tuned on them (``DigitClassifierReader.fine_tune``) for the next match.

On rendered footage the answers can be simulated from ground truth to measure what N questions are worth; those
records say ``source: synthetic`` and ``simulates: human`` and are never presented as a person's review.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from regista.schema import SCHEMA_VERSION

Record = dict[str, Any]
QUEUE_FILE = "identity_review.json"
ANSWERED_SUFFIX = ".answered.json"  # an answered queue is renamed, so it is never answered twice
ANSWERS_FILE = "identity_answers.jsonl"
NOT_A_PLAYER = "not_a_player"
UNKNOWN = "unknown"
ANNOTATOR_RE = re.compile(r"^[A-Za-z0-9_ .\-]{1,40}$")


def _roster(match: Record) -> dict[str, Record]:
    return {p["player_id"]: p for p in match["players"]}


def _who(match: Record, pid: str) -> dict[str, Any]:
    p = _roster(match).get(pid, {})
    team = next((t for t in match["teams"] if t["team_id"] == p.get("team_id")), {})
    return {"player_id": pid, "name": p.get("name", pid), "kit_number": p.get("kit_number"), "team": team.get("short_name", "")}


# ---------------------------------------------------------------------------- what to ask

def involvement_scores(cutaway: Record, cfg: Any) -> dict[str, float]:
    """Per candidate, how strongly the identity agent thinks they are in this replay: 0.5 is its decision line."""
    out = {}
    for pid, c in (cutaway.get("candidates") or {}).items():
        if cutaway["kind"] == "closeup":
            r = c.get("frac", 0.0) / 0.4
        else:
            r = max(c.get("on", 0.0) / max(1e-6, cfg.involved_on), c.get("near", 0.0) / max(1e-6, cfg.involved_near))
        out[pid] = round(min(1.0, r / 2.0), 3)
    return out


def identity_questions(result: Any, match: Record, k: int = 12, min_seconds: float = 1.0, cfg: Any = None) -> list[Record]:
    """The ``k`` identity calls most worth a person's glance, most valuable first."""
    fps = float(result.info.get("sample_fps", 5.0))
    items: list[tuple[float, Record]] = []
    for index, tr in enumerate(result.tracks):  # tids restart in every camera segment; the index is unique
        secs = len(tr.obs) / fps
        if secs < min_seconds or not tr.obs or getattr(tr, "reviewed", False):
            continue
        ranked = sorted(tr.votes.items(), key=lambda kv: -kv[1])
        margin = ranked[0][1] - (ranked[1][1] if len(ranked) > 1 else 0.0) if ranked else 0.0
        doubt = 1.0 if tr.player_id is None else max(0.0, 1.0 - margin)
        if doubt < 0.15:
            continue
        # The frame to show: the largest, least occluded view of the player.
        best = max(tr.obs, key=lambda o: (o.get("read_weight", 1.0), o.get("r", 0.0)))
        team = next((t for t in match["teams"] if t["team_id"] == tr.team_id), {})
        items.append((doubt * min(secs, 10.0), {
            "item_id": f"tr_{index}", "kind": "track", "track_index": index, "team_id": tr.team_id, "is_gk": tr.is_gk,
            "segment_id": best.get("segment_id") or _segment_of(result, best["t"]), "t0": round(tr.t0, 2), "t1": round(tr.t1, 2),
            "t": round(float(best["t"]), 3), "u": float(best["u"]), "v": float(best["v"]), "r": float(best["r"]),
            "current": tr.player_id, "confidence": round(float(tr.id_conf), 3),
            "candidates": [{**_who(match, pid), "p": round(float(pv), 3)} for pid, pv in ranked[:3]],
            "question": f"Who is this {team.get('short_name', '')} {'goalkeeper' if tr.is_gk else 'player'}?".replace("  ", " "),
        }))
    from regista.vision.identity import IdentityConfig

    cfg = cfg or IdentityConfig()
    for c in result.cutaway:
        if c.get("reviewed"):
            continue
        scores = involvement_scores(c, cfg)
        near = [s for s in scores.values() if 0.25 <= s <= 0.85]
        nobody = not c.get("players")
        if near:
            doubt = max(1.0 - abs(s - 0.5) / 0.35 for s in near)
        elif nobody:
            doubt = 1.0  # a replay or highlight with nobody in it: the clip rule finds no one to cut it for
        else:
            continue  # every candidate is clearly in or clearly out
        secs = float(c["t_end"]) - float(c["t"])
        items.append((max(0.2, doubt) * min(secs, 10.0) * 0.8, {
            "item_id": f"cw_{c['segment_id']}", "kind": "cutaway", "segment_id": c["segment_id"], "segment_kind": c["kind"],
            "t": round((float(c["t"]) + float(c["t_end"])) / 2, 3), "t0": float(c["t"]), "t1": float(c["t_end"]),
            "current": sorted(c.get("players", {})),
            "candidates": [{**_who(match, pid), "p": round(float(v), 3)} for pid, v in sorted(scores.items(), key=lambda kv: -kv[1])[:5]],
            "question": f"Who is in this {c['kind']}?",
        }))
    items.sort(key=lambda x: -x[0])
    return [it for _score, it in items[:k]]


def _segment_of(result: Any, t: float) -> str | None:
    for fr in result.frames:
        if abs(fr["t"] - t) < 1e-6:
            return fr["segment_id"]
    return None


def write_crops(video: Path | str, items: list[Record], out_dir: Path | str) -> list[Record]:
    """A JPEG per question: a ringed close crop of the player (track), or the frame itself (cutaway)."""
    from PIL import Image, ImageDraw

    from regista.vision.frames import frame_at

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    for it in items:
        rgb = frame_at(video, it["t"])
        img = Image.fromarray(rgb)
        if it["kind"] == "track":
            half = max(32.0, it["r"] * 4.0)
            box = (int(it["u"] - half), int(it["v"] - half), int(it["u"] + half), int(it["v"] + half))
            d = ImageDraw.Draw(img)
            d.ellipse([it["u"] - it["r"] * 1.5, it["v"] - it["r"] * 1.5, it["u"] + it["r"] * 1.5, it["v"] + it["r"] * 1.5],
                      outline=(255, 205, 40), width=2)
            img = img.crop(box).resize((240, 240), Image.LANCZOS)
        else:
            img = img.resize((480, int(480 * img.height / img.width)), Image.LANCZOS)
        name = f"{it['item_id']}.jpg"
        img.save(out / name, quality=88)
        it["image"] = name
    return items


# ---------------------------------------------------------------------------- answers

def validate_answers(items: list[Record], answers: list[Record], match: Record) -> dict[str, Record]:
    """Check every answer before anything is applied; raises ValueError naming the first bad one."""
    asked = {it["item_id"]: it for it in items}
    roster = _roster(match)
    out: dict[str, Record] = {}
    for a in answers:
        if not isinstance(a, dict) or a.get("item_id") not in asked:
            raise ValueError(f"answer for a question that was not asked: {a.get('item_id') if isinstance(a, dict) else a!r}")
        it = asked[a["item_id"]]
        if it["kind"] == "track":
            pid = a.get("player_id")
            if pid not in (NOT_A_PLAYER, UNKNOWN) and pid not in roster:
                raise ValueError(f"{pid!r} is not on the team sheet")
            if pid in roster and roster[pid]["team_id"] != it["team_id"]:
                raise ValueError(f"{pid} plays for the other team; this track is {it['team_id']}")
        else:
            players = a.get("players")
            if not isinstance(players, list) or len(players) > 6 or any(p not in roster for p in players):
                raise ValueError(f"players for {a['item_id']} must be a list of up to 6 team-sheet ids")
        out[a["item_id"]] = a
    return out


def apply_answers(result: Any, items: list[Record], answers: dict[str, Record]) -> dict[str, Any]:
    """Change the identity result in place. Returns what changed."""
    cut = {c["segment_id"]: c for c in result.cutaway}
    renamed, unnamed, confirmed, cutaways = [], [], [], []
    for it in items:
        a = answers.get(it["item_id"])
        if a is None:
            continue
        if it["kind"] == "track":
            tr = result.tracks[it["track_index"]] if it["track_index"] < len(result.tracks) else None
            pid = a["player_id"]
            if tr is None or pid == UNKNOWN:
                continue
            new = None if pid == NOT_A_PLAYER else pid
            index = it["track_index"]
            if new == tr.player_id:
                confirmed.append(index)
            elif new is None:
                unnamed.append(index)
            else:
                renamed.append((index, tr.player_id, new))
            if new is not None:
                # One player per moment, decided frame by frame: where another track carries this name in the same
                # frames, it loses the name there and keeps it everywhere else. (The tracker sometimes doubles a
                # player for a few frames or splits one into touching tracks; unnaming the whole other track would
                # undo frames that were right.)
                mine = {round(float(o["t"]), 3) for o in tr.obs}
                for j, other in enumerate(result.tracks):
                    if other is tr or other.player_id != new:
                        continue
                    clash = [o for o in other.obs if round(float(o["t"]), 3) in mine]
                    for o in clash:
                        o["player_id"], o["id_conf"] = None, 0.0
                    if clash:
                        unnamed.append(j)
            _set(tr, new, 1.0)
            tr.votes = {new: 1.0} if new else {}
            tr.reviewed = True
        else:
            c = cut.get(it["segment_id"])
            if c is not None:
                c["players"] = {p: 1.0 for p in a["players"]}
                c["reviewed"] = True
                cutaways.append(it["segment_id"])
    return {"renamed": renamed, "unnamed": sorted(set(unnamed)), "confirmed": confirmed, "cutaways": cutaways}


def _set(tr: Any, pid: str | None, conf: float) -> None:
    tr.player_id, tr.id_conf = pid, conf
    for o in tr.obs:
        o["player_id"], o["id_conf"] = pid, conf


def annotation_records(items: list[Record], answers: dict[str, Record], match_id: str, annotator: str,
                       simulated: bool = False) -> list[Record]:
    """One ``annotation`` per answer, with a snapshot of the question."""
    if not ANNOTATOR_RE.match(annotator):
        raise ValueError("annotator must be 1-40 letters, digits, spaces, or . _ -")
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    out = []
    for n, it in enumerate(items, start=1):
        a = answers.get(it["item_id"])
        if a is None:
            continue
        if it["kind"] == "track":
            pid = a["player_id"]
            verdict = "confirm" if pid == it["current"] else ("reject" if pid in (NOT_A_PLAYER, UNKNOWN) else "correct")
            correction, target_type, target = {"player_id": None if pid in (NOT_A_PLAYER, UNKNOWN) else pid, "answer": pid}, "track", f"trk_{it['track_index']}"
        else:
            verdict = "confirm" if sorted(a["players"]) == sorted(it["current"]) else "correct"
            correction, target_type, target = {"players": sorted(a["players"])}, "appearance", f"seg_{it['segment_id']}"
        rec: Record = {"type": "annotation", "id": f"an_id_{match_id}_{it['item_id']}_{n:03d}", "match_id": match_id,
                       "schema_version": SCHEMA_VERSION, "source": "synthetic" if simulated else "human", "confidence": 1,
                       "t": float(it["t"]), "target_id": target, "target_type": target_type, "verdict": verdict,
                       "correction": correction, "annotator": annotator, "annotated_at": now,
                       "context": {"item_id": it["item_id"], "question": it["question"], "kind": it["kind"], "current": it["current"],
                                   "candidates": [c["player_id"] for c in it["candidates"]], "confidence": it.get("confidence")}}
        if simulated:
            rec["simulates"] = "human"
        out.append(rec)
    return out


# ---------------------------------------------------------------------------- learning from corrections

def correction_crops(video: Path | str, result: Any, match: Record, segments: list[Record], answers: dict[str, Record],
                     items: list[Record], max_per_track: int = 40, reader: Any = None) -> tuple[np.ndarray, np.ndarray]:
    """Labelled kit-number crops from tracks a person named: the track's visible frames, labelled with the named
    player's number. These are the reader's hardest cases: it got them wrong or was unsure.

    A person names a track from one picture, and a track can swap players partway. With ``reader`` given, frames the
    reader confidently reads as a different number (90% or more) are left out: they are more likely another player
    than a misread, and training on them would teach the reader the wrong digits."""
    from regista.vision.frames import iter_frames
    from regista.vision.identity import adapt_palette
    from regista.vision.kitnumber import crop_disc

    roster = _roster(match)
    want: dict[float, list[tuple[dict, int]]] = {}
    for it in items:
        a = answers.get(it["item_id"])
        if it["kind"] != "track" or a is None or a["player_id"] not in roster:
            continue
        tr = result.tracks[it["track_index"]] if it["track_index"] < len(result.tracks) else None
        if tr is None:
            continue
        number = int(roster[a["player_id"]]["kit_number"])
        visible = [o for o in tr.obs if o.get("read_weight", 1.0) >= 1.0]
        step = max(1, len(visible) // max_per_track)
        for o in visible[::step][:max_per_track]:
            want.setdefault(round(float(o["t"]), 3), []).append((o, number))
    if not want:
        return np.zeros((0,)), np.zeros((0,), dtype=int)
    palette = adapt_palette(video, match, segments)
    crops, numbers = [], []
    fps = float(result.info.get("sample_fps", 5.0))
    for _fi, t, rgb in iter_frames(video, sample_fps=fps):
        for o, number in want.get(round(t, 3), []):
            kit = palette.kits[_kit_index(palette, o)]
            crops.append(crop_disc(rgb, o["u"], o["v"], o["r"], kit.lab))
            numbers.append(number)
    if not crops:
        return np.zeros((0,)), np.zeros((0,), dtype=int)
    C, N = np.stack(crops), np.array(numbers, dtype=int)
    if reader is not None:
        keep = []
        for rd, n in zip(reader.read(C), N):
            best = int(np.argmax(rd.tens)) * 10 + int(np.argmax(rd.units))
            keep.append(best == n or float(np.max(rd.tens)) * float(np.max(rd.units)) < 0.9)
        C, N = C[np.array(keep, dtype=bool)], N[np.array(keep, dtype=bool)]
    return C, N


def _kit_index(palette: Any, o: Record) -> int:
    for i, k in enumerate(palette.kits):
        if k.team_id == o["team_id"] and bool(k.is_gk) == bool(o.get("is_gk")):
            return i
    return 0


# ---------------------------------------------------------------------------- simulated answers (measurement on rendered footage only)

def simulated_answers(items: list[Record], result: Any, truth: Any, match: Record) -> list[Record]:
    """What a careful person would answer, read from the generator's ground truth: the true player behind most of
    the track's frames, or the players the generator lists for the replay."""
    out = []
    appearances = getattr(truth, "appearances", None)
    for it in items:
        if it["kind"] == "track":
            tr = result.tracks[it["track_index"]]
            votes: Counter = Counter()
            for o in (tr.obs if tr else [])[::2]:
                ft = truth.objects_at(o["t"])
                best = min(ft.players, key=lambda g: (g.cx - o["u"]) ** 2 + (g.cy - o["v"]) ** 2, default=None)
                if best is not None and (best.cx - o["u"]) ** 2 + (best.cy - o["v"]) ** 2 <= max(25.0, (1.5 * o["r"]) ** 2):
                    votes[best.player_id] += 1
                else:
                    votes[NOT_A_PLAYER] += 1
            pid = votes.most_common(1)[0][0] if votes else UNKNOWN
            if pid not in (NOT_A_PLAYER, UNKNOWN) and _roster(match)[pid]["team_id"] != it["team_id"]:
                pid = NOT_A_PLAYER  # the track's team is wrong; the honest answer is "not this team's player"
            out.append({"item_id": it["item_id"], "player_id": pid})
        else:
            # The generator lists who appears in each cutaway; predicted segment ids differ, so match by time.
            segs = {sg["id"]: sg for sg in truth.scene.segments}
            players = sorted({a["player_id"] for a in appearances() if a["segment_id"] in segs
                              and segs[a["segment_id"]]["kind"] == it["segment_kind"]
                              and segs[a["segment_id"]]["t"] < it["t1"] and it["t0"] < segs[a["segment_id"]]["t_end"]})
            out.append({"item_id": it["item_id"], "players": players[:6]})
    return out


def save_queue(items: list[Record], out_dir: Path | str) -> Path:
    path = Path(out_dir) / "review" / QUEUE_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"items": items}, indent=1, default=float) + "\n", encoding="utf-8")
    return path


def prepare_review(out_dir: Path | str, video: Path | str, result: Any, match: Record, k: int = 12) -> list[Record]:
    """Write the questions and crops for a match directory so a person can answer later (the viewer's "Who's who").
    Leaves an existing queue alone."""
    queue = Path(out_dir) / "review" / QUEUE_FILE
    if queue.exists():
        return json.loads(queue.read_text())["items"]
    items = identity_questions(result, match, k=k)
    if items:
        write_crops(video, items, Path(out_dir) / "review" / "crops")
        save_queue(items, out_dir)
    return items


def close_queue(out_dir: Path | str) -> None:
    """Set the answered queue aside; ``prepare_review`` may then ask the next most uncertain questions."""
    queue = Path(out_dir) / "review" / QUEUE_FILE
    if queue.exists():
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        queue.rename(queue.with_name(f"identity_review.{stamp}{ANSWERED_SUFFIX}"))


def terminal_reviewer(request: Any, match: Record, ask: Any = input, say: Any = print) -> Any:
    """Answer an ``IdentityReviewRequest`` at the terminal: open the crop shown, type the number of a candidate, a
    kit number, x (not a player) or ? (can't tell); for a replay, candidate numbers separated by commas, or 0 for
    nobody. Enter skips."""
    from regista.vision.agents import IdentityAnswers

    roster = _roster(match)
    by_number = {(p["team_id"], int(p["kit_number"])): pid for pid, p in roster.items()}
    answers = []
    say(f"\n{request.question}  (crops in {Path(request.review_dir) / 'crops'})")
    for it in request.items:
        say(f"\n{it['question']}  {it.get('image', '')}  now: {it['current'] or 'unnamed'}")
        for n, c in enumerate(it["candidates"], start=1):
            say(f"  {n}. {c['name']} ({c['kit_number']}, {c['team']})  {round(c['p'] * 100)}%")
        reply = ask("  answer: ").strip().lower()
        if not reply:
            continue
        if it["kind"] == "track":
            if reply in ("x", "?"):
                answers.append({"item_id": it["item_id"], "player_id": NOT_A_PLAYER if reply == "x" else UNKNOWN})
            elif reply.isdigit() and 1 <= int(reply) <= len(it["candidates"]):
                answers.append({"item_id": it["item_id"], "player_id": it["candidates"][int(reply) - 1]["player_id"]})
            elif reply.lstrip("#").isdigit() and (it["team_id"], int(reply.lstrip("#"))) in by_number:
                answers.append({"item_id": it["item_id"], "player_id": by_number[(it["team_id"], int(reply.lstrip("#")))]})
            else:
                say("  not understood; skipped")
        else:
            picks = [x.strip() for x in reply.split(",") if x.strip()]
            if picks == ["0"]:
                answers.append({"item_id": it["item_id"], "players": []})
            elif all(x.isdigit() and 1 <= int(x) <= len(it["candidates"]) for x in picks):
                answers.append({"item_id": it["item_id"], "players": [it["candidates"][int(x) - 1]["player_id"] for x in picks]})
            else:
                say("  not understood; skipped")
    annotator = ask("Your name for the record [zaid]: ").strip() or "zaid"
    return IdentityAnswers(answers=answers, annotator=annotator)


def learn_from_reviews(match_dirs: list[Path | str], models_dir: Path | str, *, save: bool = True) -> dict[str, Any]:
    """Fine-tune the kit-number reader on every answered identity review in ``match_dirs`` (plan step 6: train again
    on the growing labelled corpus). The previous reader is kept as ``kit_number_reader.previous.joblib``."""
    import shutil

    import joblib

    from regista.schema import iter_jsonl
    from regista.vision.kitnumber import READER_FILE, DigitClassifierReader, load_replay_set

    reader = DigitClassifierReader.load(models_dir)
    crops, numbers, used = [], [], []
    for d in map(Path, match_dirs):
        answered = sorted((d / "review").glob(f"identity_review.*{ANSWERED_SUFFIX}"))
        recs = list(iter_jsonl(d / "review" / ANSWERS_FILE)) if (d / "review" / ANSWERS_FILE).exists() else []
        if not answered or not recs:
            continue
        items = [it for f in answered for it in json.loads(f.read_text())["items"]]
        by_item = {r.get("context", {}).get("item_id"): r for r in recs}
        answers = {}
        for it in items:
            r = by_item.get(it["item_id"])
            if r is not None and it["kind"] == "track" and r["correction"].get("player_id"):
                answers[it["item_id"]] = {"item_id": it["item_id"], "player_id": r["correction"]["player_id"]}
        if not answers:
            continue
        stream = list(iter_jsonl(d / "events.jsonl"))
        match = stream[0]
        manifest = json.loads((d / "manifest.json").read_text())
        segs = [{"id": r["id"], "t": r["t"], "t_end": r["t_end"], "kind": r["kind"]} for r in stream if r["type"] == "camera_segment"]
        result = joblib.load(d / ".vision_work" / "identity.joblib")
        c, n = correction_crops(manifest["video"]["path"], result, match, segs, answers, items, reader=reader)
        if len(n):
            crops.append(c)
            numbers.append(n)
            used.append({"match": d.name, "answers": len(answers), "crops": int(len(n))})
    if not crops:
        return {"fine_tuned": False, "reason": "no answered track corrections with usable crops", "matches": used}
    replay = load_replay_set(models_dir)
    reader.fine_tune(np.concatenate(crops), np.concatenate(numbers),
                     replay_crops=replay[0] if replay else None, replay_numbers=replay[1] if replay else None)
    if save:
        current = Path(models_dir) / READER_FILE
        shutil.copy2(current, current.with_name("kit_number_reader.previous.joblib"))
        reader.save(models_dir)
    return {"fine_tuned": True, "crops": int(sum(len(n) for n in numbers)), "matches": used, "replay_crops": int(len(replay[1])) if replay else 0}
