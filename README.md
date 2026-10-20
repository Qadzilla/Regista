# Touchline

**Every touch. Every replay. Every player. Found instantly.**

Touchline is an AI system for the Microsoft × Premier League **Inside the Game: Developer Hackathon** (October 2026). It watches a full 90-minute football broadcast, learns to recognise players, cuts every moment a chosen player is on the ball plus every replay and highlight they appear in, labels those moments, and lets you find them through a chatbot:

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

Initial plan (will evolve): Microsoft Foundry, Microsoft Agent Framework, Azure MCP, Azure AI Vision and Video Indexer, Azure AI Speech and Translator, Azure Cosmos DB / Microsoft Fabric, Azure Container Apps, Azure Functions, GitHub Copilot Agent Mode.

## Status

Day 0. Project scaffolded; idea and criteria captured in `CLAUDE.md`.

## Licence

MIT. No broadcast footage is included in this repository.
