# BrandShield AI — Brand Governance Platform (Codex 48)

BrandShield AI is an AI-powered brand governance platform that checks marketing content against approved brand guidelines, identifies unsupported claims, suggests grounded corrections, and provides human-controlled approval workflows.

---

## AI Content Analysis Engine Overview

The **Content Analysis Engine** (`ComplianceEngine`) audits submitted marketing copy against active Brand Memory records before publication.

### Core Audit Checks
1. **Tone & Voice Inconsistencies**: Checks against `VoiceToneGuideline` principles, detecting superlatives, competitor disparagement, and vague promises.
2. **Prohibited & Restricted Terminology**: Detects banned vocabulary from `TerminologyRule` and provides approved replacements.
3. **Conflicts with Approved Messaging**: Cross-references against `ProductFact` specifications and approved corporate positioning.
4. **Unsubstantiated Claims**: Flags promotional assertions lacking evidence in `ApprovedClaim`.
   - *Key Safeguard*: Missing evidence is treated as **unverified**, never invented or assumed true.
5. **Outdated Product Info**: Detects claims referencing expired benchmark dates or deprecated asset specifications.
6. **Accessibility Checks**: Identifies continuous ALL CAPS shouting (WCAG SC 3.1) and run-on sentences lacking punctuation.

### Structured Response Schema (`ComplianceAnalysisSchema`)
Every finding includes:
- `problematic_text`: Exact problematic string from the source copy.
- `issue_category`: Clearly classified policy area.
- `severity`: Clearly distinguished (`critical`, `warning`, `info`).
- `confidence`: Clearly distinguished (`high`, `medium`, `low`).
- `applicable_rule_or_source`: Grounded citation to Brand Memory (e.g. *Legal Claims Policy §2.1*, *Benchmark Report #2026-42*). Never hallucinates citations.
- `explanation`: Plain-language governance rationale.
- `suggested_correction`: Context-preserving replacement that satisfies brand compliance.
- `requires_human_verification`: Boolean flag indicating mandatory human auditor sign-off.

### Dual Evaluation Modes
- **Live Gemini API (`GEMINI_LIVE`)**: Uses Google Gemini 2.0 Flash with structured JSON schema output when `GEMINI_API_KEY` is set.
- **Deterministic Dev Engine (`DETERMINISTIC_DEV`)**: Transparent, offline, rule-grounded evaluation engine when operating without external API keys. Never fabricates artificial mock results.

### Governance Auto-Approval Safeguard
In compliance with enterprise AI safety guidelines, **content is never marked approved automatically** regardless of how high its score is. All submissions require human sign-off from a Reviewer (`Morgan Vance`).

---

## How to Run & Test

### Run the App
```powershell
cd C:\Users\ACER\.gemini\antigravity\scratch\brandshield-ai
.venv\Scripts\python.exe run.py
```
Open: **[http://127.0.0.1:8000](http://127.0.0.1:8000)**

### Automated Tests
- **Compliance Engine & Schema Verification Suite**:
  ```powershell
  .venv\Scripts\python.exe test_compliance_engine.py
  ```
- **Brand Memory Module Suite**:
  ```powershell
  .venv\Scripts\python.exe test_brand_memory.py
  ```
- **End-to-End Server Suite**:
  ```powershell
  .venv\Scripts\python.exe test_server.py
  ```
