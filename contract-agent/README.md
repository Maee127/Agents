# Contract Agent

An AI-powered contract analysis agent that extracts key terms, flags risks, and summarizes legal agreements with intelligent memory of past documents.

## Overview

The Contract Agent is designed to help users quickly understand and analyze contracts by:

1. **Extracting Key Terms** — Automatically identifies and extracts:
   - Key obligations and commitments
   - Important dates and deadlines
   - Payment terms and renewal clauses
   - Liability caps and other critical clauses

2. **Risk Flagging** — Highlights potential issues with:
   - Unusual or non-standard clauses
   - Missing standard protections
   - Ambiguous or unclear wording
   - Plain-language explanations of why each issue is flagged

3. **Smart Summarization** — Provides a concise one-paragraph summary of what the document commits you to

4. **Document Memory** — Remembers past contracts from the same client, enabling comparative analysis like:
   - "This clause is stricter than your usual contracts"
   - Identification of deviations from established patterns

## Features

- 📄 PDF and email thread support
- 🚩 Intelligent risk detection with explanations
- 💾 Client-based document memory and comparison
- 🤖 Powered by OpenAI
- ⚡ Fast contract analysis and summarization

## Tech Stack

- **Python** 3.13
- **OpenAI API** — For additional capabilities
- **PyPDF** — PDF processing and extraction
- **PyTorch & Transformers** — NLP and model support
- **Accelerate** — GPU acceleration support
- **python-dotenv** — Environment configuration

## Installation

### Prerequisites
- Python 3.13
- API keys for OpenAI


## Project Structure

```
contract-agent/
├── app/                    # Application code
├── src/                    # Source modules
├── tests/                  # Test suite
├── train-agent.ipynb      # Training and demonstration notebook
├── check_files.py         # File structure validation script
├── requirements.txt       # Python dependencies
└── .env                   # Environment variables 
```


### Running the Script

Check the file structure and verify required files:
```bash
python check_files.py
```

## Usage Example

(Implementation details will depend on the specific agent code in `src/` and `app/`)

```python
# Example usage pattern
from contract_agent import ContractAnalyzer

analyzer = ContractAnalyzer()
result = analyzer.analyze_contract("path/to/contract.pdf")

# Output includes:
# - Key terms extracted
# - Risk flags with explanations
# - Executive summary
# - Comparison with past client documents
```


## Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| ollama | 2.5-7b | qwen2.5-7b |
| pypdf | 6.14.2 | PDF document parsing |
| torch | Latest | Deep learning framework |
| transformers | Latest | NLP models and utilities |
| accelerate | Latest | GPU acceleration |
| python-dotenv | Latest | Environment configuration |

## Future Enhancements

- [ ] Support for additional document formats (DOCX, RTF)
- [ ] Multi-language contract analysis
- [ ] Integration with contract management systems
- [ ] Custom risk threshold configuration
- [ ] Batch contract processing
- [ ] Web interface for easy access

---

**Note:** This agent is designed for analysis and summary purposes. Always have qualified legal professionals review contracts before signing.
