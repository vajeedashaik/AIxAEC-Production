from aec_contracts import ClassifyRoomsResult, ParseResult, PlanBrief, TranscribeResult

from .base import ServiceClient

TRANSCRIBE_TIMEOUT_SECONDS = 90.0


class LanguageClient(ServiceClient):
    def parse(self, instruction: str, brief: PlanBrief) -> ParseResult:
        # No retry: the language service already falls back across LLM providers.
        return self.post("/v1/commands/parse", ParseResult.model_validate, retry=False,
                         json={"instruction": instruction, "brief": brief.model_dump(mode="json")})

    def classify(self, labels: list[str]) -> ClassifyRoomsResult:
        return self.post("/v1/rooms/classify", ClassifyRoomsResult.model_validate, retry=False,
                         json={"labels": labels})

    def transcribe(self, audio: bytes, filename: str, content_type: str) -> TranscribeResult:
        return self.post("/v1/speech/transcribe", TranscribeResult.model_validate,
                         timeout=TRANSCRIBE_TIMEOUT_SECONDS, files={"audio": (filename, audio, content_type)})
