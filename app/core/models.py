from enum import Enum
from datetime import datetime, timezone, date
from typing import Optional, List
from sqlmodel import SQLModel, Field, Relationship

def get_utc_now():
    return datetime.now(timezone.utc)

class Role(str, Enum):
    CREATOR = "creator"
    REVIEWER = "reviewer"
    ADMIN = "admin"

class ContentStatus(str, Enum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    AI_REVIEW = "ai_review"
    HUMAN_REVIEW = "human_review"
    APPROVED = "approved"
    CHANGES_REQUESTED = "changes_requested"
    REJECTED = "rejected"
    # Distinct legacy string values so any un-migrated row loads safely:
    FLAGGED = "flagged"
    PENDING_REVIEW = "pending_review"
    REVISION_REQUESTED = "revision_requested"

class Severity(str, Enum):
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"

class ConfidenceLevel(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"

class TerminologyType(str, Enum):
    PROHIBITED = "prohibited"
    APPROVED = "approved"
    CONDITIONAL = "conditional"

class VerificationStatus(str, Enum):
    VERIFIED = "verified"
    PENDING_REVIEW = "pending_review"
    REJECTED = "rejected"
    EXPIRED = "expired"

class ConfidentialityLevel(str, Enum):
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"

class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    email: str = Field(unique=True, index=True)
    role: Role = Field(default=Role.CREATOR)
    avatar_color: str = Field(default="bg-indigo-600")

# --- BRAND MEMORY MODULE MODELS ---

class VoiceToneGuideline(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    title: str
    audience: str = "General Audience"
    tone_attributes: str
    dos_principles: str
    donts_principles: str
    example_positive: Optional[str] = None
    example_negative: Optional[str] = None
    is_active: bool = True
    created_at: datetime = Field(default_factory=get_utc_now)
    updated_at: datetime = Field(default_factory=get_utc_now)

class TerminologyRule(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    term: str = Field(index=True)
    term_type: TerminologyType = Field(default=TerminologyType.PROHIBITED)
    replacement_term: Optional[str] = None
    category: str = "General"
    reason: str
    severity: Severity = Field(default=Severity.WARNING)
    created_at: datetime = Field(default_factory=get_utc_now)
    updated_at: datetime = Field(default_factory=get_utc_now)

class ProductFact(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    product_name: str = Field(index=True)
    category: str = "Specifications"
    feature_name: str
    specification_detail: str
    verified_source: str
    confidentiality: ConfidentialityLevel = Field(default=ConfidentialityLevel.INTERNAL)
    created_at: datetime = Field(default_factory=get_utc_now)
    updated_at: datetime = Field(default_factory=get_utc_now)

class ApprovedClaim(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    topic: str
    claim_statement: str
    evidence_type: str
    source_reference: str
    verified_by: str = "Pending Review"
    verification_status: VerificationStatus = Field(default=VerificationStatus.PENDING_REVIEW)
    review_date: Optional[date] = None
    expiration_date: Optional[date] = None
    notes: Optional[str] = None
    is_confidential: bool = False
    created_at: datetime = Field(default_factory=get_utc_now)
    updated_at: datetime = Field(default_factory=get_utc_now)

class BrandAssetRef(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    category: str = "Logo"
    usage_guidelines: str
    attribution_text: Optional[str] = None
    file_reference: Optional[str] = None
    is_deprecated: bool = False
    created_at: datetime = Field(default_factory=get_utc_now)
    updated_at: datetime = Field(default_factory=get_utc_now)

# --- WORKFLOW, REVISIONS & REVIEW DECISIONS ---

class ContentSubmission(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    title: str
    campaign: str
    channel: str = "Multi-Channel"
    content_text: str
    status: ContentStatus = Field(default=ContentStatus.SUBMITTED)
    compliance_score: Optional[int] = Field(default=None)  # 0 to 100
    engine_used: Optional[str] = Field(default=None)
    author_name: str
    author_role: Role = Field(default=Role.CREATOR)
    current_version: int = Field(default=1)
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None
    is_demo: bool = Field(default=False)
    created_at: datetime = Field(default_factory=get_utc_now)
    updated_at: datetime = Field(default_factory=get_utc_now)
    
    issues: List["ComplianceIssue"] = Relationship(back_populates="submission")
    revisions: List["ContentRevision"] = Relationship(back_populates="submission")
    decisions: List["ReviewDecision"] = Relationship(back_populates="submission")

class ContentRevision(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    submission_id: int = Field(foreign_key="contentsubmission.id", index=True)
    version_number: int = Field(default=1)
    content_text: str
    change_summary: str = Field(default="Initial draft submission")
    submitted_by: str
    submitted_at: datetime = Field(default_factory=get_utc_now)
    compliance_score: Optional[int] = None
    engine_used: Optional[str] = None
    status_at_submission: str = Field(default="submitted")
    
    submission: Optional[ContentSubmission] = Relationship(back_populates="revisions")

class ReviewDecision(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    submission_id: int = Field(foreign_key="contentsubmission.id", index=True)
    revision_version: int = Field(default=1)
    reviewer_name: str
    reviewer_email: str
    reviewer_role: Role = Field(default=Role.REVIEWER)
    decision: str  # approved, changes_requested, rejected
    comments: str
    decided_at: datetime = Field(default_factory=get_utc_now)
    
    submission: Optional[ContentSubmission] = Relationship(back_populates="decisions")

class ComplianceIssue(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    submission_id: int = Field(foreign_key="contentsubmission.id")
    rule_category: str
    severity: Severity = Field(default=Severity.WARNING)
    confidence: ConfidenceLevel = Field(default=ConfidenceLevel.HIGH)
    claim_text: str
    explanation: str
    suggested_fix: str
    rule_citation: str
    requires_human_verification: bool = Field(default=True)
    
    submission: Optional[ContentSubmission] = Relationship(back_populates="issues")

class ActivityLog(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_name: str
    action: str
    target_title: str
    icon: str = "file-text"
    badge_color: str = "text-indigo-400 bg-indigo-500/10"
    timestamp: datetime = Field(default_factory=get_utc_now)

# Legacy compatibility
class BrandGuideline(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    title: str
    category: str
    version: str = "1.0"
    rules_count: int = 0
    is_active: bool = True
    updated_at: datetime = Field(default_factory=get_utc_now)

class ApprovedAsset(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    title: str
    asset_type: str
    claim_statement: str
    evidence_reference: str
    verified_by: str = "Legal & Compliance"
    created_at: datetime = Field(default_factory=get_utc_now)
