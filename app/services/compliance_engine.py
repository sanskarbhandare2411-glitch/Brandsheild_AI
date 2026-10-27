import os
import re
import json
import logging
from typing import List, Dict, Any, Tuple
from sqlmodel import Session, select
from datetime import date

from app.core.models import (
    VoiceToneGuideline, TerminologyRule, TerminologyType,
    ProductFact, ApprovedClaim, VerificationStatus,
    BrandAssetRef, Severity, ConfidenceLevel
)
from app.schemas.compliance import (
    ComplianceAnalysisSchema, ComplianceFindingSchema,
    IssueCategory, SeverityEnum, ConfidenceEnum
)

logger = logging.getLogger(__name__)

class ComplianceEngine:
    """
    BrandShield AI Content Analysis Engine.
    Evaluates marketing copy and documentation against Brand Memory records.
    Supports Google Gemini Live evaluation with automatic deterministic fallback.
    """

    def __init__(self, session: Session):
        self.session = session
        self.gemini_api_key = os.getenv("GEMINI_API_KEY", "").strip()

    def fetch_brand_memory_context(self) -> Dict[str, Any]:
        """Retrieves active guidelines, terminology, facts, and claims before analysis."""
        voice_guidelines = self.session.exec(select(VoiceToneGuideline).where(VoiceToneGuideline.is_active == True)).all()
        terms = self.session.exec(select(TerminologyRule)).all()
        facts = self.session.exec(select(ProductFact)).all()
        claims = self.session.exec(select(ApprovedClaim)).all()
        assets = self.session.exec(select(BrandAssetRef).where(BrandAssetRef.is_deprecated == False)).all()

        return {
            "voice_guidelines": voice_guidelines,
            "terminology_rules": terms,
            "product_facts": facts,
            "approved_claims": claims,
            "brand_assets": assets
        }

    def evaluate(self, content_text: str, channel: str = "Multi-Channel") -> Tuple[ComplianceAnalysisSchema, str]:
        """
        Main entry point for evaluating content.
        Returns validated (ComplianceAnalysisSchema, engine_mode_string).
        """
        memory_context = self.fetch_brand_memory_context()

        # Check if live Gemini API is configured
        if self.gemini_api_key:
            try:
                result = self._evaluate_with_gemini(content_text, channel, memory_context)
                return result, "GEMINI_LIVE (Gemini 2.0 Flash)"
            except Exception as e:
                logger.warning(f"Gemini API invocation failed or rate-limited ({e}). Falling back to deterministic engine.")

        # Deterministic Development Engine (Offline, Rule-Based, Non-Fabricated)
        result = self._evaluate_deterministic(content_text, channel, memory_context)
        return result, "DETERMINISTIC_DEV (Offline Rule-Based Engine)"

    # ------------------------------------------------------------------
    # 1. LIVE GEMINI EVALUATION (Structured Output)
    # ------------------------------------------------------------------
    def _evaluate_with_gemini(
        self, 
        content_text: str, 
        channel: str, 
        memory_context: Dict[str, Any]
    ) -> ComplianceAnalysisSchema:
        """Invokes Google Gemini with structured Pydantic schema validation."""
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=self.gemini_api_key)

        # Build context prompt
        terms_summary = "\n".join([
            f"- Term: '{t.term}' | Type: {t.term_type.value} | Replacement: '{t.replacement_term or 'None'}' | Reason: {t.reason} | Citation: Category {t.category}"
            for t in memory_context["terminology_rules"]
        ])

        claims_summary = "\n".join([
            f"- Topic: {c.topic} | Claim: '{c.claim_statement}' | Evidence: {c.evidence_type} | Source: {c.source_reference} | Status: {c.verification_status.value} | Valid Until: {c.expiration_date or 'Active'}"
            for c in memory_context["approved_claims"]
        ])

        facts_summary = "\n".join([
            f"- Feature: {f.feature_name} | Spec: '{f.specification_detail}' | Verified Source: {f.verified_source} | Confidentiality: {f.confidentiality.value}"
            for f in memory_context["product_facts"]
        ])

        voice_summary = "\n".join([
            f"- Title: {v.title} | Tone: {v.tone_attributes} | DO: {v.dos_principles} | DONT: {v.donts_principles}"
            for v in memory_context["voice_guidelines"]
        ])

        system_instruction = f"""
You are the BrandShield AI Enterprise Compliance & Governance Engine.
Your duty is to audit submitted marketing content strictly against the provided Brand Memory records.

BRAND MEMORY RECORDS:
=== TERMINOLOGY RULES ===
{terms_summary}

=== APPROVED CLAIMS & EVIDENCE ===
{claims_summary}

=== VERIFIED PRODUCT FACTS ===
{facts_summary}

=== VOICE & TONE GUIDELINES ===
{voice_summary}

AUDIT RULES:
1. Check for:
   - Tone and voice inconsistencies.
   - Prohibited or incorrectly used terminology.
   - Conflicts with approved messaging.
   - Promotional claims that lack adequate supporting evidence (treat missing evidence as unverified, never automatically true).
   - Potentially outdated product information (e.g. expired claims or deprecated specs).
   - Accessibility issues (e.g. ALL CAPS shouting, unreadable acronyms).
2. For every finding:
   - Extract the exact problematic text snippet.
   - Provide the exact brand rule or source citation from Brand Memory when available. NEVER invent citations or assert a source supports something it does not.
   - Distinguish severity (critical, warning, info) and confidence (high, medium, low).
   - Propose a suggested correction that preserves the creator's intended message while complying with guidelines.
3. Compute an overall_score (0-100).
4. Return pure JSON matching the ComplianceAnalysisSchema schema.
"""

        prompt = f"Marketing Channel: {channel}\n\nContent to Analyze:\n\"\"\"\n{content_text}\n\"\"\""

        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                response_mime_type="application/json",
                response_schema=ComplianceAnalysisSchema,
                temperature=0.1,
            )
        )

        # Parse & Validate Output
        raw_json = response.text
        parsed_data = json.loads(raw_json)
        return ComplianceAnalysisSchema.model_validate(parsed_data)

    # ------------------------------------------------------------------
    # 2. DETERMINISTIC DEVELOPMENT ENGINE (Offline Rule-Based)
    # ------------------------------------------------------------------
    def _evaluate_deterministic(
        self, 
        content_text: str, 
        channel: str, 
        memory_context: Dict[str, Any]
    ) -> ComplianceAnalysisSchema:
        """
        Deterministic, rule-based compliance engine.
        Grounded in database records; does not fabricate artificial results.
        """
        findings: List[ComplianceFindingSchema] = []
        score = 100

        # --- A. Check Prohibited & Conditional Terminology ---
        for term_rule in memory_context["terminology_rules"]:
            pattern = re.compile(rf"\b{re.escape(term_rule.term)}\b", re.IGNORECASE)
            match = pattern.search(content_text)
            if match:
                problematic_snippet = match.group(0)
                if term_rule.term_type == TerminologyType.PROHIBITED:
                    findings.append(ComplianceFindingSchema(
                        problematic_text=problematic_snippet,
                        issue_category=IssueCategory.PROHIBITED_TERMINOLOGY.value,
                        severity=SeverityEnum(term_rule.severity.value),
                        confidence=ConfidenceEnum.HIGH,
                        applicable_rule_or_source=f"Terminology Policy: {term_rule.category}",
                        explanation=term_rule.reason,
                        suggested_correction=f"Replace '{problematic_snippet}' with '{term_rule.replacement_term}'" if term_rule.replacement_term else "Remove prohibited phrasing.",
                        requires_human_verification=True
                    ))
                    score -= 20 if term_rule.severity == Severity.CRITICAL else 10

        # --- B. Check for Unsupported Absolute Claims & Superlatives ---
        unsupported_patterns = [
            (
                r"\b100%\s+(?:unbreakable|secure|bug\s*free|guaranteed)\b", 
                "Absolute security and perfection claims are legally unprovable and violate Section 2.1 Claims Policy.",
                "military-grade defense with zero recorded perimeter breaches",
                "Legal Claims Policy §2.1 (Absolutes & Superlatives)",
                SeverityEnum.CRITICAL
            ),
            (
                r"\b(?:cuts|saves)\s+all\s+(?:operational\s+)?costs\s+in\s+half\b",
                "Unsubstantiated cost-halving claim. Audited benchmark #2026-42 only substantiates 'savings up to 42% on average'.",
                "delivers verified operational savings up to 42% on average",
                "Approved Asset Benchmark #2026-42",
                SeverityEnum.WARNING
            ),
            (
                r"\b(?:every|all)\s+(?:leading\s+)?Fortune\s+500\s+(?:company|companies)\b",
                "Customer roster exaggeration. Claims regarding universal Fortune 500 adoption exceed substantiated evidence.",
                "leading enterprise organizations worldwide",
                "Brand Identity §3.2 (Customer Testimonials & Reach)",
                SeverityEnum.WARNING
            ),
            (
                r"\bguarantees?\s+instant\s+audit\s+approval\b",
                "No software can guarantee regulatory audit outcomes. Treat missing evidence as unverified.",
                "accelerates compliance review readiness with structured audit logs",
                "Compliance Regulatory Guidance §4.0",
                SeverityEnum.WARNING
            ),
            (
                r"\bmagic(?:\s+AI)?\b",
                "Vague hyperbolic buzzword undermines technical credibility and enterprise trust.",
                "automated governance pipeline",
                "Global Tone of Voice & Phrasing (v3.2)",
                SeverityEnum.INFO
            )
        ]

        for regex, explanation, fix, source, sev in unsupported_patterns:
            matches = re.finditer(regex, content_text, re.IGNORECASE)
            for m in matches:
                # Cross-reference with ApprovedClaims: does an exact verified claim support this?
                matched_snippet = m.group(0)
                is_substantiated = any(
                    matched_snippet.lower() in c.claim_statement.lower() and c.verification_status == VerificationStatus.VERIFIED
                    for c in memory_context["approved_claims"]
                )
                if not is_substantiated:
                    findings.append(ComplianceFindingSchema(
                        problematic_text=matched_snippet,
                        issue_category=IssueCategory.UNSUPPORTED_CLAIM.value,
                        severity=sev,
                        confidence=ConfidenceEnum.HIGH,
                        applicable_rule_or_source=source,
                        explanation=explanation,
                        suggested_correction=fix,
                        requires_human_verification=True
                    ))
                    score -= 18 if sev == SeverityEnum.CRITICAL else 8

        # --- C. Check Outdated Claims or Deprecated Assets ---
        for claim in memory_context["approved_claims"]:
            if claim.expiration_date and claim.expiration_date < date.today():
                if claim.topic.lower() in content_text.lower():
                    findings.append(ComplianceFindingSchema(
                        problematic_text=claim.topic,
                        issue_category=IssueCategory.OUTDATED_INFO.value,
                        severity=SeverityEnum.WARNING,
                        confidence=ConfidenceEnum.HIGH,
                        applicable_rule_or_source=f"Approved Claim: {claim.topic} (Expired: {claim.expiration_date})",
                        explanation=f"The claim on '{claim.topic}' expired on {claim.expiration_date}. An updated audit is required.",
                        suggested_correction="Update claim to reference the current year's recertification report.",
                        requires_human_verification=True
                    ))
                    score -= 10

        # --- D. Accessibility & Visual Checks ---
        # 1. Shouting / Excessive ALL CAPS (3+ consecutive capitalized words, >= 4 chars each)
        caps_pattern = re.compile(r"\b[A-Z]{4,}(?:\s+[A-Z]{4,}){2,}\b")
        caps_match = caps_pattern.search(content_text)
        if caps_match:
            problematic_caps = caps_match.group(0)
            findings.append(ComplianceFindingSchema(
                problematic_text=problematic_caps,
                issue_category=IssueCategory.ACCESSIBILITY.value,
                severity=SeverityEnum.INFO,
                confidence=ConfidenceEnum.HIGH,
                applicable_rule_or_source="Content Accessibility Standard (WCAG 2.2 SC 3.1)",
                explanation="Consecutive uppercase words hinder readability for neurodivergent readers and disrupt screen-reader pronunciation.",
                suggested_correction=problematic_caps.capitalize(),
                requires_human_verification=False
            ))
            score -= 5

        # 2. Run-on sentences without punctuation (> 50 words)
        sentences = [s.strip() for s in re.split(r"[.!?]+", content_text) if s.strip()]
        for s in sentences:
            words = s.split()
            if len(words) > 50:
                findings.append(ComplianceFindingSchema(
                    problematic_text=" ".join(words[:12]) + "...",
                    issue_category=IssueCategory.ACCESSIBILITY.value,
                    severity=SeverityEnum.INFO,
                    confidence=ConfidenceEnum.MEDIUM,
                    applicable_rule_or_source="Content Readability Standards",
                    explanation=f"Sentence is {len(words)} words long without punctuation. Long sentences reduce user comprehension.",
                    suggested_correction="Break this thought into two concise, active sentences.",
                    requires_human_verification=False
                ))
                score -= 4
                break

        # 3. Missing Image Alt-Text in Markdown or HTML Snippets
        img_pattern = re.compile(r"!\[(.*?)\]\((.*?)\)|<img\s+([^>]*?)>", re.IGNORECASE)
        for match in img_pattern.finditer(content_text):
            md_alt = match.group(1)
            html_attrs = match.group(3)
            snippet = match.group(0)
            has_alt = False
            if md_alt is not None:
                has_alt = bool(md_alt.strip())
            elif html_attrs is not None:
                alt_attr = re.search(r'alt\s*=\s*["\'](.*?)["\']', html_attrs, re.IGNORECASE)
                if alt_attr and alt_attr.group(1).strip():
                    has_alt = True
            
            if not has_alt:
                findings.append(ComplianceFindingSchema(
                    problematic_text=snippet,
                    issue_category=IssueCategory.ACCESSIBILITY.value,
                    severity=SeverityEnum.WARNING,
                    confidence=ConfidenceEnum.HIGH,
                    applicable_rule_or_source="WCAG 2.2 Non-text Content (SC 1.1.1)",
                    explanation="Embedded asset or image lacks descriptive alternative text ('alt' text), rendering it inaccessible to screen reader users.",
                    suggested_correction="Add descriptive alt text describing the graphic context, e.g. ![BrandShield Architecture Diagram](url)",
                    requires_human_verification=False
                ))
                score -= 8

        # 4. Brand Color Compliance & Contrast Warnings
        # Brand standard primary dark is #020617 / Slate-950, primary brand is #6366f1 / Indigo-500
        # Flag poor contrast combinations in inline styles or markup (e.g., light-on-light or unapproved neon colors)
        color_patterns = [
            (
                r"#([fF]{6}|white|yellow)\s*(?:on|with|\/)\s*#([fF]{6}|white|#e2e8f0|#cbd5e1)",
                "Low contrast color pairing detected. Fails WCAG 2.2 AA minimal contrast ratio requirement (4.5:1).",
                "Use high-contrast pairing, such as white text on dark background (#020617).",
                SeverityEnum.WARNING
            ),
            (
                r"(?:color:\s*(?:#ff00ff|#00ffff|magenta|cyan))",
                "Unapproved neon accent color detected. Brand identity guidelines permit strictly Indigo, Sky, Emerald, and Slate palette.",
                "Replace with approved Brand Accent: Indigo (#6366f1) or Emerald (#10b981).",
                SeverityEnum.WARNING
            )
        ]
        for c_regex, c_exp, c_fix, c_sev in color_patterns:
            c_match = re.search(c_regex, content_text, re.IGNORECASE)
            if c_match:
                findings.append(ComplianceFindingSchema(
                    problematic_text=c_match.group(0),
                    issue_category=IssueCategory.VISUAL_BRANDING.value,
                    severity=c_sev,
                    confidence=ConfidenceEnum.HIGH,
                    applicable_rule_or_source="Brand Identity Guidelines §4: Color & Contrast Standards",
                    explanation=c_exp,
                    suggested_correction=c_fix,
                    requires_human_verification=True
                ))
                score -= 7

        # 5. Brand Asset & Deprecated Logo References
        for asset in memory_context.get("brand_assets", []):
            if asset.is_deprecated and asset.name.lower() in content_text.lower():
                findings.append(ComplianceFindingSchema(
                    problematic_text=asset.name,
                    issue_category=IssueCategory.VISUAL_BRANDING.value,
                    severity=SeverityEnum.CRITICAL,
                    confidence=ConfidenceEnum.HIGH,
                    applicable_rule_or_source=f"Brand Asset Repository: {asset.name}",
                    explanation=f"Referenced brand asset '{asset.name}' is marked DEPRECATED. {asset.usage_guidelines}",
                    suggested_correction="Use primary active brand asset: BrandShield Primary Wordmark & Shield.",
                    requires_human_verification=True
                ))
                score -= 15

        # Normalize score
        final_score = max(min(score, 100), 10)
        summary = (
            f"Content analysis detected {len(findings)} potential compliance issue(s). "
            f"{'Review suggested corrections before publication.' if findings else 'Content conforms cleanly to active brand guidelines.'}"
        )

        return ComplianceAnalysisSchema(
            overall_score=final_score,
            summary=summary,
            findings=findings
        )
