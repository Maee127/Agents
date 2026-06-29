"""
Analyzer: turn a single contract Chunk into a structured verdict.

Uses Claude's tool-use feature to force a structured response rather
than asking for "JSON please" in plain text -- the model is
constrained to the schema, not just instructed to follow it.

Key design choice: the model must quote the exact source text behind
any risk flag (`quoted_text`). A flag with no quotable basis is a
flag we shouldn't trust, so the schema makes that impossible to skip.
"""

import json
from dataclasses import dataclass
from typing import Literal

import anthropic

from chunking import Chunk

ClauseType = Literal[
    "payment", "liability", "termination", "confidentiality",
    "indemnification", "intellectual_property", "dispute_resolution",
    "term_renewal", "administrative", "other",
]
RiskLevel = Literal["low", "medium", "high"]


@dataclass
class ClauseVerdict:
    chunk_index: int
    heading: str | None
    clause_type: ClauseType
    summary: str
    risk_level: RiskLevel
    risk_reason: str
    quoted_text: str  # exact substring from the source clause


# The tool schema is the actual contract between us and the model.
# Every field is required -- an incomplete verdict is worse than a
# slow one, because a partially-filled risk report erodes trust fast.
ANALYZE_CLAUSE_TOOL = {
    "name": "record_clause_verdict",
    "description": "Record the structured analysis of one contract clause.",
    "input_schema": {
        "type": "object",
        "properties": {
            "clause_type": {
                "type": "string",
                "enum": list(ClauseType.__args__),
                "description": "The category this clause falls into. Use "
                                "'administrative' for titles, definitions, "
                                "or boilerplate with no real obligation.",
            },
            "summary": {
                "type": "string",
                "description": "One plain-language sentence: what this "
                                "clause commits the reader to.",
            },
            "risk_level": {
                "type": "string",
                "enum": list(RiskLevel.__args__),
                "description": "low: standard/favorable terms. "
                                "medium: unusual or one-sided but not "
                                "extreme. high: significant exposure, "
                                "e.g. uncapped liability, auto-renewal "
                                "with short opt-out, one-sided "
                                "indemnification.",
            },
            "risk_reason": {
                "type": "string",
                "description": "Plain-language explanation of WHY this "
                                "risk level was assigned. Empty string "
                                "if risk_level is 'low'.",
            },
            "quoted_text": {
                "type": "string",
                "description": "The exact substring from the clause "
                                "text that justifies the risk_reason. "
                                "Must be copied verbatim from the input. "
                                "Empty string if risk_level is 'low'.",
            },
        },
        "required": [
            "clause_type", "summary", "risk_level",
            "risk_reason", "quoted_text",
        ],
    },
}

SYSTEM_PROMPT = """You are a contract-review assistant. You analyze one \
clause at a time from a business contract and report what it means and \
whether it poses risk to the party receiving/signing the contract.

Rules:
- Be conservative: only flag medium/high risk when there is a concrete, \
specific reason -- not because a clause merely exists.
- "high" risk means real, significant exposure: uncapped liability, \
one-sided indemnification, auto-renewal with an unreasonably short \
opt-out window, broad non-competes, unilateral termination rights for \
one party only, etc.
- If you flag any risk, quoted_text MUST be copied verbatim from the \
clause text you were given. Never paraphrase into quoted_text and \
never invent text that isn't there.
- If the clause is administrative (titles, definitions, table of \
contents fragments) or genuinely low risk, say so plainly -- do not \
manufacture risk to seem thorough.
- You are not providing legal advice. Flag risk in plain business \
terms, not legal conclusions."""


class AnalyzerError(Exception):
    """Raised when the model's response can't be turned into a verdict."""


def analyze_chunk(
    chunk: Chunk,
    client: anthropic.Anthropic,
    model: str = "claude-sonnet-4-6",
) -> ClauseVerdict:
    response = client.messages.create(
        model=model,
        max_tokens=1000,
        system=SYSTEM_PROMPT,
        tools=[ANALYZE_CLAUSE_TOOL],
        tool_choice={"type": "tool", "name": "record_clause_verdict"},
        messages=[{
            "role": "user",
            "content": (
                f"Clause heading: {chunk.heading or '(none)'}\n\n"
                f"Clause text:\n{chunk.text}"
            ),
        }],
    )

    tool_use_block = next(
        (b for b in response.content if b.type == "tool_use"), None
    )
    if tool_use_block is None:
        raise AnalyzerError(
            f"Model did not return a tool_use block for chunk {chunk.index}"
        )

    data = tool_use_block.input

    # Verify any quoted_text is actually present in the source --
    # catches the model inventing or paraphrasing a "quote".
    quoted = data.get("quoted_text", "")
    if quoted and quoted.strip() not in chunk.text:
        raise AnalyzerError(
            f"Chunk {chunk.index}: quoted_text not found verbatim in "
            f"source clause -- possible hallucinated citation.\n"
            f"Quoted: {quoted!r}"
        )

    return ClauseVerdict(
        chunk_index=chunk.index,
        heading=chunk.heading,
        clause_type=data["clause_type"],
        summary=data["summary"],
        risk_level=data["risk_level"],
        risk_reason=data["risk_reason"],
        quoted_text=quoted,
    )
