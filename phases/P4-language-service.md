# P4: Language & Voice Service (words → untrusted command)

> Parallel phase. Worktree `phase/p4-language`. **Write only inside `services/language/**`.**

## Read first
`CLAUDE.md` · `phases/shared/{ARCHITECTURE,CONTRACTS,OWNERSHIP,TOOLING}.md` (CONTRACTS §3, §7) · `FULL_PROJECT_CONTEXT.md` §8 (parser stages, rules grammar) and §21 item 5 (the old LLM prompt omitted two operations, so don't repeat that) · `packages/contracts/fixtures/commands.examples.json`.

## Mission
A **stateless FastAPI service** that turns language into a *candidate* command dict (never trusted, never geometry), classifies room labels and transcribes speech, **fully offline by default**. Free LLMs reached through **OmniRoute** improve coverage but are never required.

## Endpoints (CONTRACTS §7), all behind `X-Internal-Token`
`POST /v1/commands/parse` · `POST /v1/rooms/classify` · `POST /v1/speech/transcribe`

## 1. Command parsing
`CommandParser` interface with three implementations, selected by `COMMAND_PARSER`:

- **`rules`** (offline regex/grammar, deterministic). Handlers are tried in order: `rename → set_scale → add_wall (explicit coordinates only) → move → resize → add door/window → delete`. It understands:
  - units `mm / millimetres / cm / m / metres / px / pixels` (convert cm and m to mm), number words up to twenty, decimals
  - directions `left/right/up/down`, plus `north/south/east/west`, `top/bottom` (→ UP/DOWN) and `towards the X` where unambiguous
  - "between the X and the Y", "the X wall", "at 30 %", "in the middle", "900 wide", "make the kitchen bigger by 500 mm to the right" (RESIZE EXPAND), "shrink…" (CONTRACT)
  - "rename / call / label the room … as …" → RENAME_ROOM (+ `room_type` via the lexicon)
  - "this wall is 3.6 m" / "set the scale: wall … is 3600 mm" → SET_SCALE
  - targets: put the human phrase into `target_query` (e.g. `"between kitchen and living room"`, `"bedroom"`). **Never invent ids or coordinates.**
  - non-edit text → `UNKNOWN` with a helpful `detail` that suggests an example.
- **`llm`**: OpenAI SDK pointed at **OmniRoute** (`LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL` = an OmniRoute *combo* for automatic free-provider fallback).
  - System prompt: the full schema of **all 10 operations** (generated from `aec_contracts` JSON Schema, so it never drifts), the rules (one JSON object only, no ids, no coordinates except ADD_WALL when the user gave them, use `target_query`, `{"operation":"UNKNOWN"}` for non-edits), and 10–15 few-shot examples drawn from the fixtures. The user message is the `PlanBrief` (rooms, counts, has_scale) plus the instruction.
  - Request `response_format={"type":"json_object"}` when supported, and fall back to tolerant extraction (first balanced `{…}`). Validate with `COMMAND_ADAPTER`. On a validation failure, **retry once** with the error appended. Then give up → `ERROR`.
  - `call_with_retry` on transport errors only, `LLM_TIMEOUT_SECONDS`, and a circuit breaker so a dead gateway fails fast.
  - Never log the API key. Log the model, latency, token usage (if returned) and outcome.
- **`hybrid`** (default): rules first. `PARSED` → return it (`provider="rules"`). `UNKNOWN` → LLM. LLM `ERROR` or unavailable → return the rules `UNKNOWN` (the service never fails because the LLM is down).

The service returns the **raw dict**. Validation here is only a quality gate. Downstream (geometry) re-validates it as untrusted.

## 2. Room-label classification
`rules` uses `aec_contracts.lexicon.room_type_for_text`. Labels that are still `UNKNOWN` go to the LLM in **one batched call** (a JSON array in, a JSON array out, restricted to the `RoomType` enum, with confidence). Validate the output, and drop anything not in the enum. Order is preserved. Rules-only when the LLM isn't configured.

## 3. Speech-to-text
`SpeechService` interface: **`whisper`** (default, via **faster-whisper**: model `WHISPER_MODEL`=`base.en`, `WHISPER_COMPUTE_TYPE=int8`, CPU, VAD filter on, loaded lazily once and reused across requests, transcription in a threadpool) and **`stub`** (deterministic canned transcript for tests).
- Accept the content types in CONTRACTS §7. Check the size (10 MiB) and duration (60 s). Decode via PyAV (bundled with faster-whisper), so **Safari `audio/mp4` works** (the original rejected it).
- Bias toward domain vocabulary with `initial_prompt` ("wall, door, window, kitchen, bedroom, millimetres, move left…").
- Clip the transcript to 500 chars. Return `duration_ms`.

## 4. Runtime: OmniRoute
- `services/language/compose.yaml` runs `language` **and** an `omniroute` service (official image; confirm the name and port with context7 or the repo README), plus a named volume for its config. Internal only, not published.
- `services/language/docs/OMNIROUTE.md`: how to add free providers (Groq, Google AI Studio, OpenRouter free models, Cerebras, Mistral), create the API key and a fallback combo, and which free models work well for JSON output.
- `GET /readyz` reports `llm: configured|unreachable|disabled` and `stt: loaded|lazy|stub` without failing when the LLM is down.

## Tests (offline, no network)
- **Rules parser**: every case in `commands.examples.json` (target ≥ 95 % exact match; list any misses in the HANDOFF), plus unit conversion, number words, every direction synonym, rename and set-scale phrasings, and nonsense → `UNKNOWN`.
- **LLM parser**: a fake OpenAI-compatible server via **respx**. Cover valid JSON, JSON wrapped in prose, invalid then corrected on retry, invalid twice → ERROR, timeout → ERROR, and assert the system prompt contains all 10 operation names.
- **Hybrid**: rules hit → no LLM call. Rules miss → LLM. LLM down → UNKNOWN (not 5xx).
- **Classify**: rules, batched LLM, enum filtering, order preserved.
- **STT**: the stub provider. A whisper test marked `slow` that's skipped if the model isn't cached. Content-type and size limits.
- **API**: 401, and every response validates against the contract models.
- Optional live smoke test (`-m live`, skipped by default) against a running OmniRoute.

## Done when
- [ ] All three endpoints match CONTRACTS §7. Fully works offline (rules + stub or local whisper).
- [ ] The OmniRoute integration is documented and runs in compose.
- [ ] Tests, ruff and mypy are green. `HANDOFF.md` has the parser coverage table and its misses.
- [ ] `/ponytail-review` + `code-review-and-quality` + `security-and-hardening` done (prompt-injection note: the brief carries user-authored room labels, so treat them as data).

## Tooling
**context7** (OpenAI Python SDK, faster-whisper, FastAPI, respx, OmniRoute README), `test-driven-development`, `security-and-hardening`, `context-engineering` (for the prompt), `observability-and-instrumentation`.
