"""Amazon Bedrock (Converse API) in place of the OpenAI-compatible gateway. Breaker and retries come from LlmClient."""

import time
from types import SimpleNamespace
from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from openai.types.chat import ChatCompletionMessageParam

from .config import Settings
from .llm import MAX_COMPLETION_TOKENS, LlmClient, LlmUnavailable


class BedrockLlmClient(LlmClient):
    def _connect(self, settings: Settings) -> Any:
        return boto3.client("bedrock-runtime", region_name=settings.aws_region,
                            config=Config(connect_timeout=5, read_timeout=settings.llm_timeout_seconds,
                                          retries={"total_max_attempts": 2}))

    def _create(self, messages: list[ChatCompletionMessageParam], deadline: float, json_mode: bool) -> Any:
        # json_mode is ignored: Converse has no response_format. The system prompt demands JSON and first_json copes.
        if deadline - time.monotonic() <= 0:
            raise LlmUnavailable("deadline exceeded")
        system = [{"text": str(m.get("content"))} for m in messages if m["role"] == "system"]
        turns = [{"role": m["role"], "content": [{"text": str(m.get("content"))}]}
                 for m in messages if m["role"] != "system"]
        try:
            response = self._client.converse(modelId=self.model, system=system, messages=turns,
                                             inferenceConfig={"maxTokens": MAX_COMPLETION_TOKENS})
            content = "".join(block.get("text", "") for block in response["output"]["message"]["content"])
            usage = SimpleNamespace(total_tokens=response["usage"]["totalTokens"])
        except (BotoCoreError, ClientError, KeyError) as exc:
            raise LlmUnavailable(type(exc).__name__) from exc
        message = SimpleNamespace(content=content)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)], model=self.model, usage=usage)

    def probe(self) -> str:
        return "configured"  # the runtime API has no free ping, and /readyz must not spend money
