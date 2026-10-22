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

## The API and the page (Player P, built)

- `src/regista/player_api.py`: `POST /api/player/uploads` (admin key; multipart `video` mp4 up to 300 MB, `global_id`,
  `opponent_club_id`, `side`; the body is read only after the key is checked and its declared size is checked first; the
  video streams from the spooled upload to the store), `GET /api/player/uploads[?global_id=]` and `/{upload_id}` (public,
  with stages), `GET …/questions` and `…/crops/{name}` ("is this you?": the Who's who items about the uploader),
  `POST …/answers` (admin key; yes/no per item, applied through `api._apply_identity_review`, the uploader's clips cut
  again, the folder pushed back to the store, the record set to done; no answers finishes as the agents left it).
- Finished matches (`done`, `needs_review`) are fetched from the store into `REGISTA_PLAYER_MATCHES` (default
  `data/player/matches`) on first use and again when the record changes; `api._match_dir` serves `pv_…` from there, so
  clips, video, reels and the Clip view work as for any match.
- Profiles: `uploaded_matches()` lists done uploads (30 s cache); `regista.season.profiles` counts each in its uploader's
  profile only (`source: upload`, `upload_id`), shown on the profile as "Filmed by the player · cut from video".
- The answer path needs, in the match folder, `.vision_work/identity.joblib`; it downloads the upload's video beside the
  matches and points the manifest at it, and uses the models the run recorded, else `REGISTA_MODELS`, else the store's
  `models/vision/`.
- `/me` (`static/me/`): pick a player, upload (admin key as in the Studio), live progress per agent, "is this you?"
  cards, the moments in place, links to the Clip view and the profile. Header link "Player" on every view.
- Checked locally end to end (offline, local store, the real vision layer on a rendered friendly via a stand-in worker):
  upload, progress, two questions about the uploader, answers recomputed in 3 s, moments played, profile and Clip view.

