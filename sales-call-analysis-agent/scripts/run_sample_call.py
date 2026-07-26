"""Entry point for running a single sample call through the analysis pipeline.

The pipeline is not implemented yet. This script exists so the eventual
end-to-end flow (ingestion -> audio -> transcription -> diarization ->
speaker identity -> evaluation) has a stable entry point from day one.
"""

import sys


def main() -> int:
    message = "sales-call-analysis-agent: the analysis pipeline is not implemented yet."
    print(message, file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
