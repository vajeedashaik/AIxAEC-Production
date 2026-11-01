# services/language (Language, :8003)

Rules + LLM (OmniRoute) command parser, room-label classification, local speech-to-text.

Owned by **P4** (see `phases/shared/OWNERSHIP.md`). Contracts: `phases/shared/CONTRACTS.md`.
Status: see `HANDOFF.md`. Works fully offline (rules parser + lexicon + local Whisper or stub). An LLM via OmniRoute only widens coverage: `docs/OMNIROUTE.md`.

| Env | Values |
|---|---|
| `COMMAND_PARSER` | `hybrid` (default: rules, then LLM on a miss) / `rules` (offline) / `llm` |
| `STT_PROVIDER` | `whisper` (default, downloads `WHISPER_MODEL` on first use) / `stub` |

## Run
```powershell
cd services/language
py -m uv sync
copy .env.example .env
py -m uv run uvicorn app.main:app --reload --port 8003
```

Every `/v1` route needs `X-Internal-Token: <INTERNAL_SERVICE_TOKEN>` (401 otherwise).

## Test
```powershell
py -m uv run pytest            # -m slow: real Whisper (if cached), -m live: real OmniRoute
py -m uv run ruff check .
py -m uv run mypy app
```

## Docker
Build context is the repo root (the image copies `packages/contracts`):
`docker build -f services/language/Dockerfile .` or `docker compose up language` from the root.
