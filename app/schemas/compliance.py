from pydantic import BaseModel, Field
from typing import List, Optional
from enum import Enum

class IssueCategory(str, Enum):
    TONE_AND_VOICE = "Tone and Voice"
    PROHIBITED_TERMINOLOGY = "Prohibited Terminology"
    MESSAGING_CONFLICT = "Messaging Conflict"
    UNSUPPORTED_CLAIM = "Unsupported Claim"
    OUTDATED_INFO = "Outdated Product Info"
    ACCESSIBILITY = "Accessibility"
    VISUAL_BRANDING = "Visual & Branding"

class SeverityEnum(str, Enum):
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"

class ConfidenceEnum(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"

class ComplianceFindingSchema(BaseModel):
    problematic_text: str = Field(
        ..., 
        description="The exact snippet of text from the content that triggered this finding."
    )
    issue_category: str = Field(
        ..., 
        description="One of: Tone and Voice, Prohibited Terminology, Messaging Conflict, Unsupported Claim, Outdated Product Info, Accessibility"
    )
    severity: SeverityEnum = Field(
        ..., 
        description="Severity: critical (violates law/policy, blocks publish), warning (needs modification), info (best practice)"
    )
    confidence: ConfidenceEnum = Field(
        ..., 
        description="Confidence level in this finding: high, medium, low. Clearly distinguished from severity."
    )
    applicable_rule_or_source: Optional[str] = Field(
        None, 
        description="Exact brand rule, guideline, or approved claim citation from provided Brand Memory. Never invent citations."
    )
    explanation: str = Field(
        ..., 
        description="Concise, plain-language explanation of why this text is problematic."
    )
    suggested_correction: str = Field(
        ..., 
        description="A suggested correction that preserves the creator's original intent while meeting brand compliance standards."
    )
    requires_human_verification: bool = Field(
        default=True, 
        description="Whether a human reviewer must verify this finding or claim."
    )

class ComplianceAnalysisSchema(BaseModel):
    overall_score: int = Field(
        ..., 
        ge=0, 
        le=100, 
        description="Overall compliance health score from 0 (many critical breaches) to 100 (fully compliant)."
    )
    summary: str = Field(
        ..., 
        description="A high-level summary of brand alignment, substantiated claims, and required corrections."
    )
    findings: List[ComplianceFindingSchema] = Field(
        default_factory=list, 
        description="List of detected compliance issues."
    )
