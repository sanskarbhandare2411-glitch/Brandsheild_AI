# BrandShield AI — Brand Governance Platform

BrandShield AI is an AI-powered brand governance platform that checks marketing content against approved brand guidelines, identifies unsupported claims, suggests grounded corrections, and provides human-controlled approval workflows.

## AI Content Analysis Engine

The Content Analysis Engine (`ComplianceEngine`) audits submitted marketing copy against active Brand Memory records before publication.

### Core Audit Checks

1. **Tone and Voice Inconsistencies:** Checks content against brand voice guidelines and detects superlatives, competitor disparagement, and vague promises.
2. **Prohibited Terminology:** Detects banned vocabulary and suggests approved replacements.
3. **Conflicts with Approved Messaging:** Cross-references content against product facts and approved corporate positioning.
4. **Unsubstantiated Claims:** Flags promotional assertions without supporting evidence. Missing evidence is treated as unverified, never assumed true.
5. **Outdated Product Information:** Detects claims referencing expired benchmarks or deprecated specifications.
6. **Accessibility Checks:** Identifies excessive capitalization and punctuation issues.

### Structured Analysis Results

Each finding can include:

- `problematic_text` — The exact problematic text.
- `issue_category` — The category of the issue.
- `severity` — Critical, warning, or informational.
- `confidence` — High, medium, or low.
- `applicable_rule_or_source` — The applicable brand rule or evidence source.
- `explanation` — A plain-language explanation.
- `suggested_correction` — A context-preserving correction.
- `requires_human_verification` — Whether human verification is required.

### Evaluation Modes

- **Live Gemini API:** Uses Google Gemini when `GEMINI_API_KEY` is configured and supported by the application.
- **Deterministic Development Engine:** Provides rule-based analysis without requiring an external API key.

### Human Approval Safeguard

Content is not automatically approved based on its score. Human review and sign-off are required before approval.

## Installation and Setup

### Requirements

- Python 3
- pip
- The packages listed in `requirements.txt`

### Run Locally

Open a terminal in the project directory and run:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python run.py
```

Open the local address displayed by the application in your browser. If the application uses the default port, try `http://127.0.0.1:8000`.

### Run Tests

```powershell
python test_compliance_engine.py
python test_brand_memory.py
python test_server.py
```

Additional tests are available in the repository.

## Configuration

If the application requires Gemini, configure `GEMINI_API_KEY` through your local environment or your hosting provider's environment-variable settings.

**Never commit API keys, passwords, or `.env` files to GitHub.**

## Deployment

This project can be deployed to a compatible Python hosting platform. Hosting configuration may be required depending on the application's framework, entry point, database, and file-storage needs.

## Project Repository

GitHub: https://github.com/sanskarbhandare2411-glitch/Brandsheild_AI