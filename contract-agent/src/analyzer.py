"""
Analyzer module: uses Groq API to analyze individual contract clauses.
Each clause is evaluated for risk level, summary, and identified issues.
"""

from dataclasses import dataclass, field
from openai import OpenAI
from typing import Optional, List
import json
import re


@dataclass
class ClauseVerdict:
    """Result of analyzing a single clause/chunk."""
    clause_index: int
    clause_text: str
    heading: Optional[str] = None  # Store the heading from chunking
    risk_level: str = "unknown"  # "low", "medium", "high"
    summary: str = ""
    issues: List[str] = field(default_factory=list)
    recommendation: Optional[str] = None


class AnalyzerError(Exception):
    """Raised when analysis of a single clause fails."""
    pass


def analyze_chunk(
    chunk,  # Expects a Chunk object with .index, .heading, .text
    client: OpenAI,
    model: str = "llama-3.3-70b-versatile"
) -> ClauseVerdict:
    """
    Analyze a single clause/chunk using the Groq API.

    Args:
        chunk: A Chunk object with .index, .heading, and .text attributes
        client: Initialized OpenAI client configured for Groq
        model: Groq model to use

    Returns:
        ClauseVerdict with analysis results

    Raises:
        AnalyzerError: If the API call or parsing fails
    """
    try:
        # Build the context with heading if available
        heading_context = f" (Heading: {chunk.heading})" if chunk.heading else ""
        
        # Build the prompt for clause analysis
        prompt = f"""You are a legal contract analyst. Analyze the following clause from a contract and provide a structured assessment.

Clause {chunk.index}{heading_context}:

Provide your analysis in the following JSON format:
{{
    "risk_level": "low" or "medium" or "high",
    "summary": "Brief 1-2 sentence summary of what this clause does",
    "issues": ["Issue 1", "Issue 2", ...],
    "recommendation": "Specific recommendation for negotiation or revision"
}}

Consider these factors:
- Does the clause create significant liability?
- Is the language favorable or unfavorable to the party?
- Are there any ambiguities or loopholes?
- Does it comply with common legal standards?
"""

        # Make the API call to Groq
        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": "You are a legal contract analyst. Always respond with valid JSON."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.1,  # Low temperature for consistency
            max_tokens=1024,
            # Note: Groq doesn't support response_format parameter yet
        )
        
        # Extract and parse the JSON response
        result_text = response.choices[0].message.content
        
        # Try to parse JSON, with fallback for non-JSON responses
        try:
            result = json.loads(result_text)
        except json.JSONDecodeError:
            # Fallback: try to extract JSON from the text using regex
            json_match = re.search(r'\{.*\}', result_text, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group())
            else:
                # If no JSON found, create a default structure from the text
                result = {
                    "risk_level": "medium",
                    "summary": result_text[:200],  # First 200 chars as summary
                    "issues": ["Could not parse structured response"],
                    "recommendation": "Review clause manually"
                }
        
        # Create and return the ClauseVerdict
        return ClauseVerdict(
            clause_index=chunk.index,
            clause_text=chunk.text,
            heading=chunk.heading,
            risk_level=result.get("risk_level", "medium").lower(),
            summary=result.get("summary", "No summary provided"),
            issues=result.get("issues", []),
            recommendation=result.get("recommendation")
        )
        
    except Exception as e:
        # Catch any API or parsing errors and wrap them
        raise AnalyzerError(
            f"Failed to analyze chunk {chunk.index} (heading: {chunk.heading}): {str(e)}"
        ) from e


def analyze_chunks_batch(
    chunks,
    client: OpenAI,
    model: str = "llama-3.3-70b-versatile",
    max_concurrent: int = 5,
    verbose: bool = False
) -> List[ClauseVerdict]:
    """
    Analyze multiple chunks in batch (with rate limiting and progress tracking).
    """
    results = []
    total_chunks = len(chunks)
    
    for i, chunk in enumerate(chunks):
        if verbose:
            print(f"Analyzing chunk {i+1}/{total_chunks} (Index: {chunk.index})...")
        
        try:
            verdict = analyze_chunk(chunk, client, model)
            results.append(verdict)
            if verbose:
                print(f"  ✓ Risk: {verdict.risk_level}")
        except AnalyzerError as e:
            if verbose:
                print(f"  ✗ Error: {e}")
            # Create a fallback verdict
            results.append(ClauseVerdict(
                clause_index=chunk.index,
                clause_text=chunk.text,
                heading=chunk.heading,
                risk_level="unknown",
                summary="Analysis failed",
                issues=[str(e)],
                recommendation="Manual review recommended"
            ))
    
    return results


# Helper function to get a summary of the analysis
def summarize_report(report) -> str:
    """
    Generate a human-readable summary of a ContractReport.
    """
    total_clauses = len(report.verdicts)
    failed_count = len(report.failed_chunk_indices)
    
    summary = f"""
    Contract Analysis Summary
    =========================
    File: {report.file_path}
    Total clauses analyzed: {total_clauses}
    Failed clauses: {failed_count}
    
    Risk Distribution:
    - High risk: {report.high_risk_count}
    - Medium risk: {report.medium_risk_count}
    - Low risk: {total_clauses - report.high_risk_count - report.medium_risk_count}
    """
    
    # Add details for high-risk clauses
    high_risk_clauses = [v for v in report.verdicts if v.risk_level == "high"]
    if high_risk_clauses:
        summary += "\n\nHigh-Risk Clauses:\n"
        for v in high_risk_clauses[:5]:  # Show first 5
            heading_info = f" (Heading: {v.heading})" if v.heading else ""
            summary += f"  - Clause {v.clause_index}{heading_info}: {v.summary[:100]}...\n"
        if len(high_risk_clauses) > 5:
            summary += f"  ... and {len(high_risk_clauses) - 5} more high-risk clauses\n"
    
    return summary
