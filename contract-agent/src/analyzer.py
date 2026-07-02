"""
Analyzer: turn a single contract Chunk into a structured verdict.

Uses Groq's API (via the OpenAI-compatible SDK) for the LLM call.
Structured output is enforced by:
  1. A strict JSON-only system prompt
  2. Schema validation in code after parsing
  3. A hallucination guard that verifies quoted_text exists verbatim
     in the source clause -- the single most important trust mechanism.

Do NOT remove the hallucination guard to "simplify" things. A risk
flag that can't point to exact source text is untrustworthy and will
erode client confidence immediately in a live demo.
"""

import json
import re
from dataclasses import dataclass
from typing import Literal

from openai import OpenAI

from chunking import Chunk

RiskLevel = Literal["low", "medium", "high"]
ClauseType = Literal[
    "payment", "liability", "termination", "confidentiality",
    "indemnification", "intellectual_property", "dispute_resolution",
    "term_renewal", "administrative", "other",
]


@dataclass
class ClauseVerdict:
    chunk_index: int
    heading: str | None
    clause_type: ClauseType
    summary: str
    risk_level: RiskLevel
    risk_reason: str      # empty string if risk_level is "low"
    quoted_text: str      # verbatim from source; empty string if risk_level is "low"


class AnalyzerError(Exception):
    """Raised when a clause can't be turned into a reliable verdict."""


SYSTEM_PROMPT = """\
You are a contract-review assistant. You analyze one clause at a time \
from a business contract and report what it means and whether it poses \
risk to the party receiving or signing the contract.

You MUST respond with ONLY a raw JSON object. No markdown, no code \
fences, no explanation before or after. Just the JSON object.

Required JSON schema:
{
  "clause_type": one of: payment | liability | termination | \
confidentiality | indemnification | intellectual_property | \
dispute_resolution | term_renewal | administrative | other,
  "summary": "One plain-language sentence: what this clause commits \
the reader to.",
  "risk_level": one of: low | medium | high,
  "risk_reason": "Plain-language explanation of WHY this risk level \
was assigned. Empty string if risk_level is low.",
  "quoted_text": "The exact substring from the clause text that \
justifies risk_reason. Must be copied verbatim. Empty string if \
risk_level is low."
}

Rules:
- Use administrative for titles, definitions, or boilerplate with no \
real obligation.
- Only flag medium/high when there is a concrete, specific reason.
- high means real exposure: uncapped liability, one-sided \
indemnification, auto-renewal with short opt-out, broad non-competes, \
unilateral termination for one party only, etc.
- quoted_text MUST be copied verbatim from the clause -- never \
paraphrase it and never invent text that is not there.
- You are flagging business risk, not giving legal advice.\
"""


def _extract_json(text: str) -> dict:
    """
    Parse JSON from the model response, handling the common case
    where the model wraps it in markdown code fences despite being
    told not to.
    """
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise AnalyzerError(
            f"Model returned invalid JSON: {e}\nRaw response: {text!r}"
        )


REQUIRED_FIELDS = {"clause_type", "summary", "risk_level", "risk_reason", "quoted_text"}
VALID_RISK_LEVELS = {"low", "medium", "high"}
VALID_CLAUSE_TYPES = {
    "payment", "liability", "termination", "confidentiality",
    "indemnification", "intellectual_property", "dispute_resolution",
    "term_renewal", "administrative", "other",
}


def _validate(data: dict, chunk_index: int) -> None:
    missing = REQUIRED_FIELDS - data.keys()
    if missing:
        raise AnalyzerError(
            f"Chunk {chunk_index}: model response missing fields: {missing}"
        )
    if data["risk_level"] not in VALID_RISK_LEVELS:
        raise AnalyzerError(
            f"Chunk {chunk_index}: invalid risk_level {data['risk_level']!r}"
        )
    if data["clause_type"] not in VALID_CLAUSE_TYPES:
        data["clause_type"] = "other"


def analyze_chunk(
    chunk: Chunk,
    client: OpenAI,
    model: str = "llama-3.3-70b-versatile",
) -> ClauseVerdict:
    """
    Analyze one chunk and return a ClauseVerdict.

    Raises AnalyzerError if:
    - The API call fails
    - The response is not valid JSON with required fields
    - quoted_text is not found verbatim in the source (hallucination guard)
    """
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"Clause heading: {chunk.heading or '(none)'}\n\n"
                        f"Clause text:\n{chunk.text}"
                    ),
                },
            ],
            temperature=0.1,
            max_tokens=1024,
        )
    except Exception as e:
        raise AnalyzerError(
            f"Chunk {chunk.index}: API call failed: {e}"
        ) from e

    raw = response.choices[0].message.content
    data = _extract_json(raw)
    _validate(data, chunk.index)

    # --- Hallucination guard ---
    # Verify quoted_text actually appears verbatim in the source clause.
    # A quote the model invented or paraphrased is a fabrication --
    # a client who spots one loses trust in everything else the tool says.
    quoted = data.get("quoted_text", "").strip()
    if quoted and quoted not in chunk.text:
        raise AnalyzerError(
            f"Chunk {chunk.index}: quoted_text not found verbatim in "
            f"source clause -- possible hallucination.\n"
            f"Quoted: {quoted!r}\n"
            f"Source: {chunk.text[:200]!r}"
        )

    return ClauseVerdict(
        chunk_index=chunk.index,
        heading=chunk.heading,
        clause_type=data["clause_type"],
        summary=data["summary"],
        risk_level=data["risk_level"],
        risk_reason=data.get("risk_reason", ""),
        quoted_text=quoted,
    )
