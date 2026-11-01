# HANDOFF: services/language (P4)

## Status
| Item | Status |
|---|---|
| `POST /v1/commands/parse`: `rules` / `llm` / `hybrid` (default) | TESTED (LLM against a fake gateway via respx) |
| `POST /v1/rooms/classify`: lexicon + one batched LLM call | TESTED |
| `POST /v1/speech/transcribe`: faster-whisper (`base.en`, int8, CPU, VAD) / `stub` | TESTED (stub + decoder). Real Whisper ran once in Docker on a silent WAV: model download, load, empty transcript, `stt: loaded`. |
| `GET /readyz` → `llm: configured\|unreachable\|disabled`, `stt: loaded\|lazy\|stub` | TESTED |
| Docker image + `compose.yaml` (`language` + `omniroute`, named volumes, internal only) | IMPLEMENTED. The language container was built and smoke-tested healthy. **The OmniRoute container was never started**: Docker Hub's CDN kept dropping the image pull (EOF) on this machine. |
| OmniRoute live path (real free provider through a combo) | NOT VERIFIED. Needs a human: `docs/OMNIROUTE.md`, then `pytest -m live`. |

Checks: `uv run pytest` gives 276 passed, 1 skipped (the slow Whisper test when the model isn't cached locally) and 1 deselected (live). `ruff check .` and `mypy app` (strict) are clean.

## How to run
See `README.md`. Offline: `COMMAND_PARSER=rules` plus `STT_PROVIDER=stub` (or `whisper`, which downloads `base.en` on the first transcription and caches it in the `whisper-models` volume). OmniRoute setup is in `docs/OMNIROUTE.md`.

## Rules parser coverage (`packages/contracts/fixtures/commands.examples.json`)
Exact dict equality against `expected_command`, which is stricter than the fixture's "compare target_query by words" note.

| Expected | Cases | Exact match |
|---|---|---|
| MOVE_WALL | 8 | 8 |
| ADD_WALL | 3 | 3 |
| DELETE_WALL | 4 | 4 |
| RESIZE_ROOM | 5 | 5 |
| ADD_DOOR | 5 | 5 |
| ADD_WINDOW | 4 | 4 |
| DELETE_DOOR | 3 | 3 |
| DELETE_WINDOW | 2 | 2 |
| RENAME_ROOM | 4 | 4 |
| SET_SCALE | 3 | 3 |
| UNKNOWN | 10 | 10 |
| **Total** | **51** | **51 (100 %)** |

**Misses:** none in the fixtures. Known phrasings the rules deliberately return as `UNKNOWN` (so hybrid sends them to the LLM):
- compound number words ("twenty five mm", "three hundred mm") and "half a metre". Words only go up to twenty, plus "N point M"
- "towards the kitchen" (the direction depends on geometry the parser never sees)
- more than one edit in a sentence ("… and delete …", "…, then …")
- quantifiers ("all doors", "every wall") and pronoun targets ("rename it …")
- a px length in SET_SCALE, or a mm thickness on ADD_WALL (px is never treated as mm)

## Design notes for P3 / P7
- `ParseResult.command` is the raw dict. It's gated here with `COMMAND_ADAPTER` plus a finite-number check (`thickness_px` accepts `inf`), but geometry must still re-validate it.
- LLM guardrails beyond schema validation: `target_id` is refused, and ADD_WALL coordinates must be numbers that appear in the instruction. Either failure triggers one corrective retry, then `ERROR`.
- The brief and the instruction go to the LLM as one JSON object in the user message, and the system prompt states they are data (the room labels are user-authored, so this is the prompt-injection boundary). The system prompt holds the generated JSON Schema of all 10 operations plus 15 few-shots taken from the fixtures, and a test keeps the few-shots in sync with them.
- `LLM_TIMEOUT_SECONDS` bounds a whole parse, including the correction retry and one transport retry. The circuit breaker opens after 3 consecutive failures for 30 s. P3's HTTP client timeout to language should be above 20 s, or lower `LLM_TIMEOUT_SECONDS`.
- Logs never contain the API key or command text, and the OpenAI/httpx debug loggers are pinned to WARNING.
- The OpenAI SDK is pinned `<3`. openai 3.x swaps its transport to `httpx2`, which respx can't intercept. Revisit when respx supports it.
- Audio decoding is our own PyAV loop. It enforces 60 s **while decoding** (browser recordings often have no duration header), and Safari `audio/mp4` (AAC) is covered by a test. Bodies are refused above 10 MiB, plus multipart framing, from `Content-Length` before they are spooled.

## Contract change requests
None.

## Requests to other phases
- **P3 (api):** treat `/v1/commands/parse` `status=ERROR` (only possible with `COMMAND_PARSER=llm`) like `UNKNOWN` for the user, and show `detail`. Forward the browser's audio `Content-Type` unchanged, including `;codecs=` (it's accepted).
- **P7:** the root `compose.yaml` now also gets the `omniroute` service and the `whisper-models` / `omniroute-data` volumes through the language fragment. Pull `diegosouzapw/omniroute:3.8.52` on a healthy network and run the `pytest -m live` smoke test.

## Known limitations
- `shortcut:` a chunked upload with no `Content-Length` is only capped after spooling. That's fine while the service is internal-only.
- `shortcut:` a very large classify batch (up to 200 labels) may exceed the 4000-token completion cap. The truncated JSON fails to parse and those labels stay rules-only.
- Whisper runs on CPU. A cold load of `base.en` took about 14 s in Docker including the download, and later calls reuse the model.
- The image is 2.1 GB (ctranslate2 + onnxruntime + PyAV).
- Reviews: `/ponytail-review` and the `code-review-and-quality` / `security-and-hardening` passes were done in-session against this diff. The fixes are already in (DEBUG-log leak, ambiguous "left right", lone "between"). context7 was unavailable (not authenticated), so library APIs were checked against the installed sources and the OmniRoute README/docs on GitHub instead.
