# A6: Bedrock command parsing

**Switch:** `LLM_PROVIDER=bedrock` (default `openai`, meaning OmniRoute). Needs `AWS_REGION`, `LLM_MODEL`.

**Goal:** the LLM parser can call Bedrock. The LLM stays untrusted: `LlmParser`'s validation doesn't change, and hybrid mode still falls back to rules.

**Files**
- New `services/language/app/llm_bedrock.py`: `BedrockLlmClient(LlmClient)` overriding `_connect`, `_create` and `probe`.
- Edit `app/llm.py` (extract `_connect` so the breaker and retry code is shared, not copied), `app/parsers.py` (`build_llm_client`), `app/config.py`.

**Requirements**
- Use the Converse API. Move `system` messages to the `system` field and send the others as text content blocks. Cap tokens with `MAX_COMPLETION_TOKENS`.
- Honour the deadline check. Client timeouts come from `LLM_TIMEOUT_SECONDS`, and retries stay low so the deadline holds.
- Converse has no `response_format`, so `json_mode` is ignored. The system prompt already demands JSON and `first_json` handles stray prose.
- Botocore errors and malformed responses become `LlmUnavailable`, so the breaker and fallback behave as they do today. No API key is needed, so `COMMAND_PARSER=llm` validation must not demand `LLM_API_KEY` for Bedrock.
- `probe()` returns `"configured"` without making a paid call.

**Tests (Stubber):** the request shape passes botocore validation, system text is separated, content and model come back from `complete`, `ClientError` → `LlmUnavailable` and trips the breaker, a full `LlmParser` parse works, hybrid falls back to rules on failure, `build_llm_client` picks the right class.

**Check in M0:** which model IDs are enabled in the chosen region.
