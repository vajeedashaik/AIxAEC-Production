"""CommandParser interface and the COMMAND_PARSER selection (rules / llm / hybrid)."""

from typing import Protocol

from aec_contracts import ParseResult, PlanBrief

from .config import Settings
from .llm import LlmClient, LlmParser
from .llm_bedrock import BedrockLlmClient
from .rules import UNKNOWN_DETAIL, parse_rules


class CommandParser(Protocol):
    def parse(self, instruction: str, brief: PlanBrief) -> ParseResult: ...


class RulesParser:
    def parse(self, instruction: str, brief: PlanBrief) -> ParseResult:
        command = parse_rules(instruction)
        if command is None:
            return ParseResult(status="UNKNOWN", provider="rules", detail=UNKNOWN_DETAIL)
        return ParseResult(status="PARSED", command=command, provider="rules")


class HybridParser:
    """Rules first. The LLM only widens coverage: its failure is never the caller's failure."""

    def __init__(self, llm: CommandParser | None) -> None:
        self.rules = RulesParser()
        self.llm = llm

    def parse(self, instruction: str, brief: PlanBrief) -> ParseResult:
        result = self.rules.parse(instruction, brief)
        if result.status == "PARSED" or self.llm is None:
            return result
        answer = self.llm.parse(instruction, brief)
        return result if answer.status == "ERROR" else answer


def build_llm_client(settings: Settings) -> LlmClient | None:
    """None when the LLM is off: unconfigured, or COMMAND_PARSER=rules (which means fully offline)."""
    if settings.command_parser == "rules" or not settings.llm_model:
        return None
    if settings.llm_provider == "bedrock":
        return BedrockLlmClient(settings)
    return LlmClient(settings) if settings.llm_api_key else None


def build_parser(settings: Settings, client: LlmClient | None) -> CommandParser:
    if settings.command_parser == "rules":
        return RulesParser()
    llm = LlmParser(client) if client else None
    if settings.command_parser == "hybrid":
        return HybridParser(llm)
    assert llm is not None  # Settings refuses COMMAND_PARSER=llm without a usable LLM configuration
    return llm
