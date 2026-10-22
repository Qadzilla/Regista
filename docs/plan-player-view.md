# Plan: the Player view (`/me`)

Decided 2026-10-22 (CLAUDE.md §2.6): a synthetic player uploads their own (synthetic) match footage; Regista's vision
workflow runs on it in Azure; the match joins their profile.

## The contract (`src/regista/player/store.py`)

| Where | What |
|---|---|
| `uploads/{upload_id}/video.mp4` | the uploaded footage (max 300 MB) |
| `uploads/{upload_id}/record.json` | `UploadRecord`: global_id, club_id, opponent_club_id, side, kit_number, status (queued, running, needs_review, done, failed), stages, match_id, error |
| queue `vision-jobs` | `{"upload_id": "up_…", "kind": "vision"}` |
| `matches/{match_id}/` | the match folder the worker writes (`pv_…`): events, tracks, clips, manifest, review/, .vision_work/ |
| `models/vision/` | the trained vision models (private) |

Backends: Azure (`REGISTA_STORAGE_ACCOUNT`, keyless) or a local folder (`REGISTA_PLAYER_DIR`, tests and offline).

## Pieces

| Piece | Who | Files |
|---|---|---|
| Store, film, roster | done (foundation) | `player/store.py`, `player/film.py` |
| **Worker**: queue → vision workflow → clips → match folder → status; models push; Container Apps Job entry point | session "Player W" | `player/worker.py`, `player/models.py`, tests |
| **Upload API + `/me` page + profiles**: upload, status, sync of finished matches, "is this you?", profile inclusion | session "Player P" | `player_api.py`, `static/me/`, `season/profiles.py` (uploads), small `api.py` hooks, tests |
| **Azure**: storage account, containers, queue, Container Apps Job with a queue scaler and managed identity, roles, image with vision extras | main session | `infra/`, `Dockerfile`, workflow |
