# OmniRoute setup

OmniRoute is a self-hosted, OpenAI-compatible gateway that routes to free LLM tiers and falls back between them. The language service works without it: with no LLM, the rules parser and lexicon handle everything they can, and the rest comes back as `UNKNOWN`. Set it up to widen coverage.

Compose runs it as `omniroute` on the internal `aec` network, with its config in the `omniroute-data` volume. The port (20128) isn't published, so you need a temporary override to reach the dashboard.

## 1. Open the dashboard

From the repo root:

```powershell
docker compose -p aec -f services/language/compose.yaml -f services/language/compose.dashboard.yaml up -d omniroute
```

Open <http://localhost:20128>. The first visit runs a wizard that creates the admin password. `INITIAL_PASSWORD` isn't set, so **nobody has a password until you do this**, which is another reason to keep the port on `127.0.0.1`.

## 2. Add free providers

Go to **Dashboard → Providers**, choose a provider and click **Add API Key**.

| Provider | Get a key at | Why |
|---|---|---|
| Groq | <https://console.groq.com/keys> | Very fast, generous free tier. Best first choice. |
| Google AI Studio | <https://aistudio.google.com/apikey> | Reliable JSON output. |
| OpenRouter | <https://openrouter.ai/keys> | Many `:free` models, with low shared rate limits. |
| Cerebras | <https://cloud.cerebras.ai> | Very fast. Check the current terms: OmniRoute's README notes a card may be required. |
| Mistral | <https://console.mistral.ai/api-keys> | Free "Experiment" plan with strict rate limits. |

Free tiers change often, so check each provider's terms. Prompts include room labels from your drawings and the text of each command, and some free tiers may use prompts for training.

## 3. Create a fallback combo

Go to **Dashboard → Combos → Create New**.

- **Name:** `aec-parser` (this becomes `LLM_MODEL`)
- **Strategy:** Priority, which tries the first model and moves on only on error
- **Models:** two or more `provider/model` ids from different providers, so one provider's outage or quota can't take out the combo

**Which models to use.** You want a small model that follows a JSON schema and is low-latency. Look for these families in the dashboard's model list, and use the exact ids it shows because they change often:

1. Llama 3.3 70B or newer on Groq
2. Gemini Flash on Google AI Studio
3. A Llama or Qwen `:free` model on OpenRouter
4. Mistral Small on Mistral

Avoid reasoning models that put long thinking text before the answer. The parser tolerates prose around the JSON, but they use up the timeout budget.

**Leave OmniRoute's prompt compression off for this combo.** It rewrites prompts, and this one is a schema that has to survive exactly.

## 4. Create a client key

Go to **Dashboard → API Keys → New Key** and limit it to chat if the form offers a scope. Compose sets `REQUIRE_API_KEY=true`, so requests without a key are refused.

## 5. Point the language service at it

In `services/language/.env` (gitignored):

```
LLM_API_KEY=<the key from step 4>
LLM_MODEL=aec-parser
```

Compose sets `LLM_BASE_URL` to `http://omniroute:20128/v1`. If you run the service outside Docker with the dashboard override up, leave the `.env.example` default of `http://127.0.0.1:20128/v1`.

Then close the published port and restart:

```powershell
docker compose up -d --force-recreate omniroute language
```

## 6. Check it

`GET /readyz` on the language service reports the LLM state and never fails because of it:

| `llm` | Meaning |
|---|---|
| `disabled` | `LLM_API_KEY` or `LLM_MODEL` is missing, or `COMMAND_PARSER=rules` |
| `configured` | The gateway answered. This doesn't prove the key or combo work. |
| `unreachable` | The gateway isn't answering. Parsing falls back to rules. |

To prove the whole path, run the live smoke test while the dashboard override is up. It sends one real request through the combo:

```powershell
cd services/language
$env:LLM_API_KEY = "<key>"; $env:LLM_MODEL = "aec-parser"
py -m uv run pytest -m live
```

## Behaviour when it fails

- A transport failure or 5xx is retried once. `LLM_TIMEOUT_SECONDS` (default 20) caps the whole parse, including retries.
- After 3 failed calls in a row, the circuit breaker stops calling the gateway for 30 s, so a dead gateway fails fast.
- In `hybrid` mode (the default) any LLM failure returns the rules parser's `UNKNOWN`. It's never a 5xx.
- Logs carry the model, latency, token usage and outcome. They never carry the API key or command text.
