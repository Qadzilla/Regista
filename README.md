# Regista

**Regista directs every touch.** Every touch. Every replay. Every player. Found instantly.

*Regista* (Italian, "director"): the deep-lying playmaker who sees the whole pitch and directs every move, and the word for a film director. Both meanings are the product.

Regista is an AI system for the Microsoft × Premier League **Inside the Game: Developer Hackathon** (October 2026). It watches a full 90-minute football broadcast, learns to recognise players, cuts every moment a chosen player is on the ball plus every replay and highlight they appear in, labels those moments, and lets you find them through a chatbot:

> "Find me Pogba doing a nutmeg."

## Who it is for

- **Content creators** building highlight reels and edits.
- **Scouts and analysts** who need every on-ball moment of a player, instantly.
- **Broadcasters and studios** producing per-player replay packages.
- **Fans** who want a personalised reel of their favourite player.

## How it works

```
Broadcast feed ──▶ Ingest ──▶ Interpret ──▶ Explain ──▶ Render ──▶ Personalize
                   segment     track +       label +     cut        chatbot
                   replays     identify      score       clips      search
                               players       moments
```

The system emits a **synthetic, football-realistic event dataset** (touches, positions, replay markers, clip labels) and a searchable clip library. See [CLAUDE.md](CLAUDE.md) for the full project source of truth, hackathon criteria, and architecture.

## Microsoft and Azure technologies

**Planned, not yet wired** (no Azure resources exist yet): Microsoft Foundry, Microsoft Agent Framework, Azure MCP, Azure AI Vision and Video Indexer, Azure AI Speech and Translator, Azure Cosmos DB / Microsoft Fabric, Azure Container Apps, Azure Functions. What runs today runs locally with no cloud dependency; see Status.

## Quickstart

```bash
pip install -e ".[dev]"
python3 -m pytest -q
python3 -m regista.synth --minutes 3 --seed 294 --player t_home_09 --out data/synthetic/sample
python3 -m regista.validate data/synthetic/sample/syn_0294
python3 -m regista.render data/synthetic/sample/syn_0294 --out docs/demo/syn_0294.mp4
python3 -m regista.render.clips data/synthetic/sample/syn_0294 --player t_home_09 --out docs/demo/clips_t_home_09
```

The renderer turns the event and track streams into a broadcast-style 1280x720 MP4: a perspective pitch with kit-coloured numbered players, a camera that follows the ball, replays at the director's slow-motion speed with a REPLAY badge and a different framing per angle, player closeups, crowd shots, a highlights package, a live scoreboard and clock, and timed captions for goals, shots, nutmegs, skill moves, fouls, and saves. The clip cutter writes one video per clip plus a best-first reel with title cards. A 3-minute match renders in about 15 seconds on an 8-core Mac. Nothing in the output comes from real footage.

The generator writes `events.jsonl` (match header, camera segments, possessions, events, appearances, human annotations), `tracks.jsonl` (sampled positions), and `clips.jsonl` (the clip rule applied to one player, with labels and watchability scores). The contract is documented in [data/synthetic/README.md](data/synthetic/README.md).

## Status

Day 1. The event-stream contract is defined, schema-validated, and exercised end to end by the synthetic generator, the clip rule, and a 2D broadcast renderer that produces demo footage we own. Next: the Librarian (clip search) and the agents.

## Licence

MIT. No broadcast footage is included in this repository.
