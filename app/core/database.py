from sqlmodel import SQLModel, create_engine, Session, select, text
from datetime import datetime, timezone, timedelta, date
from app.config import settings
from app.core.models import (
    User, Role, BrandGuideline, ApprovedAsset,
    ContentSubmission, ContentStatus, ComplianceIssue, Severity, ActivityLog,
    VoiceToneGuideline, TerminologyRule, TerminologyType,
    ProductFact, ConfidentialityLevel,
    ApprovedClaim, VerificationStatus,
    BrandAssetRef, ContentRevision, ReviewDecision
)

connect_args = {"check_same_thread": False}
engine = create_engine(settings.DATABASE_URL, echo=False, connect_args=connect_args)

def get_session():
    with Session(engine) as session:
        yield session

def migrate_schema():
    """Applies lightweight migrations for SQLite schema enhancements."""
    with engine.connect() as conn:
        cursor = conn.connection.cursor()
        
        # 1. contentsubmission table migration
        cursor.execute("PRAGMA table_info(contentsubmission)")
        sub_cols = [row[1] for row in cursor.fetchall()]
        if sub_cols:
            if "engine_used" not in sub_cols:
                conn.execute(text("ALTER TABLE contentsubmission ADD COLUMN engine_used VARCHAR"))
            if "current_version" not in sub_cols:
                conn.execute(text("ALTER TABLE contentsubmission ADD COLUMN current_version INTEGER DEFAULT 1"))
            if "approved_by" not in sub_cols:
                conn.execute(text("ALTER TABLE contentsubmission ADD COLUMN approved_by VARCHAR"))
            if "approved_at" not in sub_cols:
                conn.execute(text("ALTER TABLE contentsubmission ADD COLUMN approved_at TIMESTAMP"))

        # 2. complianceissue table migration
        cursor.execute("PRAGMA table_info(complianceissue)")
        issue_cols = [row[1] for row in cursor.fetchall()]
        if issue_cols:
            if "confidence" not in issue_cols:
                conn.execute(text("ALTER TABLE complianceissue ADD COLUMN confidence VARCHAR DEFAULT 'HIGH'"))
            if "requires_human_verification" not in issue_cols:
                conn.execute(text("ALTER TABLE complianceissue ADD COLUMN requires_human_verification BOOLEAN DEFAULT 1"))

        # 3. Normalise legacy status values → canonical workflow enum values
        #    (Rows written by Phase 1/2 code before the full workflow was defined)
        conn.execute(text(
            "UPDATE contentsubmission SET status = 'changes_requested' "
            "WHERE status IN ('flagged', 'revision_requested')"
        ))
        conn.execute(text(
            "UPDATE contentsubmission SET status = 'human_review' "
            "WHERE status = 'pending_review'"
        ))

        # 4. Ensure confidence values are uppercase
        conn.execute(text("UPDATE complianceissue SET confidence = 'HIGH' WHERE confidence = 'high' OR confidence IS NULL"))
        conn.commit()

def init_db():
    SQLModel.metadata.create_all(engine)
    migrate_schema()
    with Session(engine) as session:
        seed_missing_data(session)

def seed_missing_data(session: Session):
    now = datetime.now(timezone.utc)

    # 1. Users (Creator, Reviewer, Administrator)
    if not session.exec(select(User)).first():
        alex = User(name="Alex Chen", email="alex.chen@brandshield.internal", role=Role.CREATOR, avatar_color="bg-sky-600")
        morgan = User(name="Morgan Vance", email="morgan.vance@brandshield.internal", role=Role.REVIEWER, avatar_color="bg-emerald-600")
        jordan = User(name="Jordan Cross", email="jordan.cross@brandshield.internal", role=Role.ADMIN, avatar_color="bg-violet-600")
        session.add(alex)
        session.add(morgan)
        session.add(jordan)
    else:
        # Check if Admin Jordan Cross exists
        admin = session.exec(select(User).where(User.role == Role.ADMIN)).first()
        if not admin:
            jordan = User(name="Jordan Cross", email="jordan.cross@brandshield.internal", role=Role.ADMIN, avatar_color="bg-violet-600")
            session.add(jordan)

    # 2. Voice & Tone
    if not session.exec(select(VoiceToneGuideline)).first():
        v1 = VoiceToneGuideline(
            title="Global Enterprise Tone of Voice",
            audience="Enterprise Buyers, Compliance Officers, and Security Architects",
            tone_attributes="Authoritative, Transparent, Precision-driven, Empowering",
            dos_principles="• Use active voice and concise phrasing.\n• Ground all performance claims with audited metrics.\n• Emphasize human control, security, and governance stability.",
            donts_principles="• Never use hyperbolic absolutes ('100% unbreakable', 'best in the world', 'foolproof').\n• Do not disparage competitors directly.\n• Avoid unsubstantiated AI buzzwords ('magic', 'miraculous').",
            example_positive="BrandShield AI delivers 99.99% verified uptime across multi-region clusters with zero model training retention on customer documents.",
            example_negative="Our bulletproof AI magically solves every single compliance headache forever guaranteed.",
            is_active=True,
            created_at=now - timedelta(days=10),
            updated_at=now - timedelta(days=2)
        )
        v2 = VoiceToneGuideline(
            title="Developer & API Communication Tone",
            audience="Software Engineers, Platform Architects, and DevOps Teams",
            tone_attributes="Direct, Technically Accurate, Pragmatic, Unpretentious",
            dos_principles="• Focus on latency metrics, schemas, and integration patterns.\n• Provide copy-pasteable code and clear error schemas.\n• Be explicit about rate limits and concurrency capabilities.",
            donts_principles="• Avoid marketing fluff and superlatives in technical docs.\n• Never omit error conditions or edge cases.",
            example_positive="The API responds in sub-150ms over REST with structured JSON schema validation.",
            example_negative="Hook into the world's most infinitely powerful AI pipeline with zero effort.",
            is_active=True,
            created_at=now - timedelta(days=20),
            updated_at=now - timedelta(days=5)
        )
        session.add(v1)
        session.add(v2)

    # 3. Terminology Rules
    if not session.exec(select(TerminologyRule)).first():
        terms = [
            TerminologyRule(
                term="100% unbreakable",
                term_type=TerminologyType.PROHIBITED,
                replacement_term="military-grade multi-layer defense",
                category="Legal / Security",
                reason="Absolute security guarantees are legally indefensible under Section 2.1 Claims Policy.",
                severity=Severity.CRITICAL,
                created_at=now - timedelta(days=15)
            ),
            TerminologyRule(
                term="cuts all costs in half guaranteed",
                term_type=TerminologyType.PROHIBITED,
                replacement_term="delivers verified operational savings up to 42%",
                category="Financial Impact",
                reason="Violates marketing accuracy guidelines. Financial promises must reference benchmark #2026-42.",
                severity=Severity.WARNING,
                created_at=now - timedelta(days=12)
            ),
            TerminologyRule(
                term="magic AI",
                term_type=TerminologyType.PROHIBITED,
                replacement_term="deterministic neural validation pipeline",
                category="Brand Voice",
                reason="Superficial buzzword that undermines enterprise trust and scientific precision.",
                severity=Severity.WARNING,
                created_at=now - timedelta(days=10)
            ),
            TerminologyRule(
                term="zero-retention architecture",
                term_type=TerminologyType.APPROVED,
                replacement_term=None,
                category="Data Privacy",
                reason="Approved corporate positioning for zero-training data handling agreements.",
                severity=Severity.INFO,
                created_at=now - timedelta(days=8)
            ),
            TerminologyRule(
                term="human-in-the-loop governance",
                term_type=TerminologyType.APPROVED,
                replacement_term=None,
                category="AI Safety",
                reason="Mandatory standard phrasing when describing approval and review workflows.",
                severity=Severity.INFO,
                created_at=now - timedelta(days=8)
            )
        ]
        for t in terms:
            session.add(t)

    # 4. Product Facts
    if not session.exec(select(ProductFact)).first():
        facts = [
            ProductFact(
                product_name="BrandShield Core Engine",
                category="Security & Encryption",
                feature_name="AES-256-GCM Envelope Encryption",
                specification_detail="All customer guidelines, vectors, and evaluation sessions are encrypted with customer-managed KMS keys with hourly key rotation.",
                verified_source="SecOps Audit Report Q1-2026 (Ref: SEC-AES-09)",
                confidentiality=ConfidentialityLevel.INTERNAL,
                created_at=now - timedelta(days=25)
            ),
            ProductFact(
                product_name="BrandShield Core Engine",
                category="Performance & Latency",
                feature_name="Sub-150ms Semantic Rule Search",
                specification_detail="Evaluates up to 5,000 words against 250 active brand policy clauses in under 150ms using optimized vector index caches.",
                verified_source="Performance Benchmarks Lab #882-P",
                confidentiality=ConfidentialityLevel.INTERNAL,
                created_at=now - timedelta(days=18)
            ),
            ProductFact(
                product_name="BrandShield Enterprise Cloud",
                category="Availability",
                feature_name="Multi-Region Active-Active Clustered SLA",
                specification_detail="Geographically dispersed across US-East, EU-Central, and AP-South with automatic sub-second failover and 99.99% availability.",
                verified_source="Cloud Architecture SLA v3.4 (Public Exhibit A)",
                confidentiality=ConfidentialityLevel.PUBLIC,
                created_at=now - timedelta(days=30)
            ),
            ProductFact(
                product_name="BrandShield Compliance Assistant",
                category="Model Privacy",
                feature_name="Zero Foundation Model Training",
                specification_detail="Strict enterprise API opt-outs guarantee that no customer document or brand copy is logged or utilized in training foundation weights.",
                verified_source="Data Privacy Agreement §8.1 (DPA-2026-E)",
                confidentiality=ConfidentialityLevel.CONFIDENTIAL,
                created_at=now - timedelta(days=14)
            )
        ]
        for f in facts:
            session.add(f)

    # 5. Approved Claims
    if not session.exec(select(ApprovedClaim)).first():
        claims = [
            ApprovedClaim(
                topic="High Availability",
                claim_statement="Delivers 99.99% verified uptime across global multi-region clusters.",
                evidence_type="Audited SOC2 Type II Report",
                source_reference="Ernst & Young SOC2 Type II Audit, Section 4.2 (Oct 2026)",
                verified_by="Morgan Vance (Compliance Lead)",
                verification_status=VerificationStatus.VERIFIED,
                review_date=date(2026, 10, 1),
                expiration_date=date(2027, 10, 1),
                notes="Requires explicit asterisk pointing to SOC2 audited report in marketing collateral.",
                is_confidential=False,
                created_at=now - timedelta(days=26)
            ),
            ApprovedClaim(
                topic="Operational Efficiency",
                claim_statement="Reduces governance review latency by up to 42% on average.",
                evidence_type="Independent Partner Study",
                source_reference="Gartner Partner Assessment Q3 2026 (Doc ID: GTR-42-GOV)",
                verified_by="Morgan Vance (Compliance Lead)",
                verification_status=VerificationStatus.VERIFIED,
                review_date=date(2026, 9, 15),
                expiration_date=date(2027, 9, 15),
                notes="Only permissible when qualified with 'on average' or 'up to'.",
                is_confidential=False,
                created_at=now - timedelta(days=40)
            ),
            ApprovedClaim(
                topic="Data Privacy & Model Safety",
                claim_statement="Customer documents are evaluated in isolated ephemeral memory without model training retention.",
                evidence_type="Legal Regulatory Compliance Review",
                source_reference="Corporate Legal Counsel Opinion #DP-2026-A",
                verified_by="Legal & Compliance Board",
                verification_status=VerificationStatus.VERIFIED,
                review_date=date(2026, 8, 20),
                expiration_date=date(2027, 8, 20),
                notes="Approved for all public web pages and security whitepapers.",
                is_confidential=False,
                created_at=now - timedelta(days=60)
            ),
            ApprovedClaim(
                topic="Energy Efficiency / Carbon Offsets",
                claim_statement="Operates on 100% carbon-neutral server infrastructure.",
                evidence_type="Provider Renewable Certificate",
                source_reference="Cloud Provider ESG Certificate 2026",
                verified_by="Pending Legal Sign-off",
                verification_status=VerificationStatus.PENDING_REVIEW,
                review_date=date(2026, 10, 20),
                expiration_date=None,
                notes="Under audit by external ESG firm. Do NOT use in external press releases until certified.",
                is_confidential=True,
                created_at=now - timedelta(days=5)
            )
        ]
        for c in claims:
            session.add(c)

    # 6. Brand Asset References
    if not session.exec(select(BrandAssetRef)).first():
        asset_refs = [
            BrandAssetRef(
                name="BrandShield Primary Wordmark & Shield",
                category="Logo",
                usage_guidelines="Use white wordmark with violet/indigo gradient shield on dark backgrounds (#020617). Minimum clear space equals height of shield icon.",
                attribution_text="BrandShield is a registered trademark of Codex 48 Technologies.",
                file_reference="/static/brand/brandshield_logo_primary.svg",
                is_deprecated=False,
                created_at=now - timedelta(days=30)
            ),
            BrandAssetRef(
                name="SOC2 Type II Compliance Badge",
                category="Seal & Trust Mark",
                usage_guidelines="Display strictly on pricing, enterprise trust, and security landing pages. Never modify dimensions or aspect ratio.",
                attribution_text="SOC2 Type II Certified by Ernst & Young.",
                file_reference="/static/brand/soc2_certified_badge.svg",
                is_deprecated=False,
                created_at=now - timedelta(days=20)
            ),
            BrandAssetRef(
                name="Standard Corporate Legal Boilerplate (2026)",
                category="Boilerplate",
                usage_guidelines="Must appear verbatim at the footer of all press releases, formal earnings releases, and partnership announcements.",
                attribution_text="About BrandShield AI: BrandShield is the leading AI brand governance platform...",
                file_reference="/static/brand/corporate_boilerplate_2026.txt",
                is_deprecated=False,
                created_at=now - timedelta(days=45)
            )
        ]
        for a in asset_refs:
            session.add(a)

    # 7. Ensure submissions have baseline revisions & decisions
    submissions = session.exec(select(ContentSubmission)).all()
    for sub in submissions:
        existing_rev = session.exec(select(ContentRevision).where(ContentRevision.submission_id == sub.id)).first()
        if not existing_rev:
            rev = ContentRevision(
                submission_id=sub.id,
                version_number=1,
                content_text=sub.content_text,
                change_summary="Initial copy submission",
                submitted_by=sub.author_name,
                submitted_at=sub.created_at,
                compliance_score=sub.compliance_score,
                engine_used=sub.engine_used or "DETERMINISTIC_DEV",
                status_at_submission=sub.status.value
            )
            session.add(rev)

        if sub.status == ContentStatus.APPROVED:
            sub.approved_by = sub.approved_by or "Morgan Vance (Governance Lead)"
            sub.approved_at = sub.approved_at or sub.updated_at
            session.add(sub)
            
            existing_dec = session.exec(select(ReviewDecision).where(ReviewDecision.submission_id == sub.id)).first()
            if not existing_dec:
                dec = ReviewDecision(
                    submission_id=sub.id,
                    revision_version=1,
                    reviewer_name="Morgan Vance",
                    reviewer_email="morgan.vance@brandshield.internal",
                    reviewer_role=Role.REVIEWER,
                    decision="approved",
                    comments="Verified against SOC2 Type II benchmark records. Approved for publishing.",
                    decided_at=sub.updated_at
                )
                session.add(dec)

    session.commit()
