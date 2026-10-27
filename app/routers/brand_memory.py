from fastapi import APIRouter, Depends, Request, Form, Query, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import Session, select
from datetime import datetime, timezone, date
from typing import Optional
from app.core.database import get_session
from app.core.models import (
    VoiceToneGuideline, TerminologyRule, TerminologyType,
    ProductFact, ConfidentialityLevel,
    ApprovedClaim, VerificationStatus,
    BrandAssetRef, ActivityLog, Role, Severity
)
from app.config import settings

router = APIRouter(prefix="/brand-memory", tags=["Brand Memory"])

def check_reviewer_permission(role: str) -> bool:
    """Helper to verify if active user has governance management rights."""
    return role.lower() in ["reviewer", "admin"]

@router.get("/", response_class=HTMLResponse)
async def brand_memory_view(
    request: Request,
    tab: str = "voice",  # voice, terms, facts, claims, assets
    role: str = "reviewer",
    q: Optional[str] = None,
    msg: Optional[str] = None,
    msg_type: Optional[str] = None,
    session: Session = Depends(get_session)
):
    is_reviewer = check_reviewer_permission(role)
    
    current_user = {
        "name": "Morgan Vance" if is_reviewer else "Alex Chen",
        "email": "morgan.vance@brandshield.internal" if is_reviewer else "alex.chen@brandshield.internal",
        "role": Role.REVIEWER if is_reviewer else Role.CREATOR,
        "role_label": "Reviewer & Governance Lead" if is_reviewer else "Content Specialist & Creator",
        "avatar_bg": "bg-emerald-600" if is_reviewer else "bg-sky-600"
    }

    # 1. Fetch Voice & Tone Guidelines
    voice_query = select(VoiceToneGuideline).order_by(VoiceToneGuideline.updated_at.desc())
    if q and tab == "voice":
        voice_query = voice_query.where(VoiceToneGuideline.title.contains(q) | VoiceToneGuideline.tone_attributes.contains(q))
    voice_guidelines = session.exec(voice_query).all()

    # 2. Fetch Terminology Rules
    terms_query = select(TerminologyRule).order_by(TerminologyRule.created_at.desc())
    if q and tab == "terms":
        terms_query = terms_query.where(TerminologyRule.term.contains(q) | TerminologyRule.reason.contains(q))
    terms = session.exec(terms_query).all()

    # 3. Fetch Product Facts & Specs
    facts_query = select(ProductFact).order_by(ProductFact.product_name, ProductFact.feature_name)
    if q and tab == "facts":
        facts_query = facts_query.where(ProductFact.product_name.contains(q) | ProductFact.feature_name.contains(q) | ProductFact.specification_detail.contains(q))
    facts = session.exec(facts_query).all()

    # 4. Fetch Approved Claims
    claims_query = select(ApprovedClaim).order_by(ApprovedClaim.updated_at.desc())
    if q and tab == "claims":
        claims_query = claims_query.where(ApprovedClaim.topic.contains(q) | ApprovedClaim.claim_statement.contains(q) | ApprovedClaim.source_reference.contains(q))
    claims = session.exec(claims_query).all()

    # 5. Fetch Brand Asset References
    assets_query = select(BrandAssetRef).order_by(BrandAssetRef.category, BrandAssetRef.name)
    if q and tab == "assets":
        assets_query = assets_query.where(BrandAssetRef.name.contains(q) | BrandAssetRef.usage_guidelines.contains(q))
    asset_refs = session.exec(assets_query).all()

    # Summary metrics for tabs
    counts = {
        "voice": len(voice_guidelines),
        "terms": len(terms),
        "facts": len(facts),
        "claims": len(claims),
        "assets": len(asset_refs)
    }

    templates = request.app.state.templates
    return templates.TemplateResponse(
        request=request,
        name="brand_memory.html",
        context={
            "project_name": settings.PROJECT_NAME,
            "current_user": current_user,
            "active_tab": "brand_memory",
            "current_memory_tab": tab,
            "search_query": q or "",
            "counts": counts,
            "voice_guidelines": voice_guidelines,
            "terms": terms,
            "facts": facts,
            "claims": claims,
            "asset_refs": asset_refs,
            "is_reviewer": is_reviewer,
            "msg": msg,
            "msg_type": msg_type or "info"
        }
    )

# -------------------------------------------------------------
# 1. VOICE & TONE GUIDELINES CRUD
# -------------------------------------------------------------

@router.post("/voice/add")
async def add_voice_guideline(
    title: str = Form(...),
    audience: str = Form("General Enterprise Audience"),
    tone_attributes: str = Form(...),
    dos_principles: str = Form(...),
    donts_principles: str = Form(...),
    example_positive: Optional[str] = Form(None),
    example_negative: Optional[str] = Form(None),
    role: str = Form("reviewer"),
    session: Session = Depends(get_session)
):
    if not check_reviewer_permission(role):
        return RedirectResponse(
            url="/brand-memory?tab=voice&role=creator&msg=Permission+Denied:+Only+Reviewers+can+add+guidelines&msg_type=error",
            status_code=303
        )

    now = datetime.now(timezone.utc)
    guideline = VoiceToneGuideline(
        title=title.strip(),
        audience=audience.strip(),
        tone_attributes=tone_attributes.strip(),
        dos_principles=dos_principles.strip(),
        donts_principles=donts_principles.strip(),
        example_positive=example_positive.strip() if example_positive else None,
        example_negative=example_negative.strip() if example_negative else None,
        is_active=True,
        created_at=now,
        updated_at=now
    )
    session.add(guideline)
    
    log = ActivityLog(
        user_name="Morgan Vance",
        action="Created brand voice guideline",
        target_title=title.strip(),
        icon="book-open",
        badge_color="text-indigo-400 bg-indigo-500/10",
        timestamp=now
    )
    session.add(log)
    session.commit()

    return RedirectResponse(
        url=f"/brand-memory?tab=voice&role={role}&msg=Voice+guideline+created+successfully&msg_type=success",
        status_code=303
    )

@router.post("/voice/{item_id}/edit")
async def edit_voice_guideline(
    item_id: int,
    title: str = Form(...),
    audience: str = Form(...),
    tone_attributes: str = Form(...),
    dos_principles: str = Form(...),
    donts_principles: str = Form(...),
    example_positive: Optional[str] = Form(None),
    example_negative: Optional[str] = Form(None),
    role: str = Form("reviewer"),
    session: Session = Depends(get_session)
):
    if not check_reviewer_permission(role):
        return RedirectResponse(
            url=f"/brand-memory?tab=voice&role={role}&msg=Permission+Denied:+Reviewer+role+required&msg_type=error",
            status_code=303
        )

    guideline = session.get(VoiceToneGuideline, item_id)
    if guideline:
        guideline.title = title.strip()
        guideline.audience = audience.strip()
        guideline.tone_attributes = tone_attributes.strip()
        guideline.dos_principles = dos_principles.strip()
        guideline.donts_principles = donts_principles.strip()
        guideline.example_positive = example_positive.strip() if example_positive else None
        guideline.example_negative = example_negative.strip() if example_negative else None
        guideline.updated_at = datetime.now(timezone.utc)
        session.add(guideline)
        session.commit()

    return RedirectResponse(
        url=f"/brand-memory?tab=voice&role={role}&msg=Voice+guideline+updated&msg_type=success",
        status_code=303
    )

@router.post("/voice/{item_id}/delete")
async def delete_voice_guideline(
    item_id: int,
    role: str = Form("reviewer"),
    session: Session = Depends(get_session)
):
    if not check_reviewer_permission(role):
        return RedirectResponse(
            url=f"/brand-memory?tab=voice&role={role}&msg=Permission+Denied:+Reviewer+role+required&msg_type=error",
            status_code=303
        )

    guideline = session.get(VoiceToneGuideline, item_id)
    if guideline:
        session.delete(guideline)
        session.commit()

    return RedirectResponse(
        url=f"/brand-memory?tab=voice&role={role}&msg=Voice+guideline+removed&msg_type=info",
        status_code=303
    )

# -------------------------------------------------------------
# 2. TERMINOLOGY RULES CRUD
# -------------------------------------------------------------

@router.post("/terms/add")
async def add_terminology_rule(
    term: str = Form(...),
    term_type: TerminologyType = Form(...),
    replacement_term: Optional[str] = Form(None),
    category: str = Form("General"),
    reason: str = Form(...),
    severity: Severity = Form(Severity.WARNING),
    role: str = Form("reviewer"),
    session: Session = Depends(get_session)
):
    if not check_reviewer_permission(role):
        return RedirectResponse(
            url=f"/brand-memory?tab=terms&role={role}&msg=Permission+Denied:+Reviewer+role+required&msg_type=error",
            status_code=303
        )

    now = datetime.now(timezone.utc)
    new_term = TerminologyRule(
        term=term.strip().lower(),
        term_type=term_type,
        replacement_term=replacement_term.strip() if replacement_term else None,
        category=category.strip(),
        reason=reason.strip(),
        severity=severity,
        created_at=now,
        updated_at=now
    )
    session.add(new_term)
    
    log = ActivityLog(
        user_name="Morgan Vance",
        action=f"Added terminology rule for '{term}'",
        target_title=f"Category: {category}",
        icon="tag",
        badge_color="text-amber-400 bg-amber-500/10",
        timestamp=now
    )
    session.add(log)
    session.commit()

    return RedirectResponse(
        url=f"/brand-memory?tab=terms&role={role}&msg=Terminology+rule+registered&msg_type=success",
        status_code=303
    )

@router.post("/terms/{item_id}/edit")
async def edit_terminology_rule(
    item_id: int,
    term: str = Form(...),
    term_type: TerminologyType = Form(...),
    replacement_term: Optional[str] = Form(None),
    category: str = Form("General"),
    reason: str = Form(...),
    severity: Severity = Form(Severity.WARNING),
    role: str = Form("reviewer"),
    session: Session = Depends(get_session)
):
    if not check_reviewer_permission(role):
        return RedirectResponse(
            url=f"/brand-memory?tab=terms&role={role}&msg=Permission+Denied&msg_type=error",
            status_code=303
        )

    t = session.get(TerminologyRule, item_id)
    if t:
        t.term = term.strip().lower()
        t.term_type = term_type
        t.replacement_term = replacement_term.strip() if replacement_term else None
        t.category = category.strip()
        t.reason = reason.strip()
        t.severity = severity
        t.updated_at = datetime.now(timezone.utc)
        session.add(t)
        session.commit()

    return RedirectResponse(
        url=f"/brand-memory?tab=terms&role={role}&msg=Terminology+rule+updated&msg_type=success",
        status_code=303
    )

@router.post("/terms/{item_id}/delete")
async def delete_terminology_rule(
    item_id: int,
    role: str = Form("reviewer"),
    session: Session = Depends(get_session)
):
    if not check_reviewer_permission(role):
        return RedirectResponse(
            url=f"/brand-memory?tab=terms&role={role}&msg=Permission+Denied&msg_type=error",
            status_code=303
        )

    t = session.get(TerminologyRule, item_id)
    if t:
        session.delete(t)
        session.commit()

    return RedirectResponse(
        url=f"/brand-memory?tab=terms&role={role}&msg=Terminology+rule+deleted&msg_type=info",
        status_code=303
    )

# -------------------------------------------------------------
# 3. PRODUCT FACTS & SPECS CRUD
# -------------------------------------------------------------

@router.post("/facts/add")
async def add_product_fact(
    product_name: str = Form(...),
    category: str = Form("Specifications"),
    feature_name: str = Form(...),
    specification_detail: str = Form(...),
    verified_source: str = Form(...),
    confidentiality: ConfidentialityLevel = Form(ConfidentialityLevel.INTERNAL),
    role: str = Form("reviewer"),
    session: Session = Depends(get_session)
):
    if not check_reviewer_permission(role):
        return RedirectResponse(
            url=f"/brand-memory?tab=facts&role={role}&msg=Permission+Denied:+Reviewer+role+required&msg_type=error",
            status_code=303
        )

    now = datetime.now(timezone.utc)
    fact = ProductFact(
        product_name=product_name.strip(),
        category=category.strip(),
        feature_name=feature_name.strip(),
        specification_detail=specification_detail.strip(),
        verified_source=verified_source.strip(),
        confidentiality=confidentiality,
        created_at=now,
        updated_at=now
    )
    session.add(fact)
    session.commit()

    return RedirectResponse(
        url=f"/brand-memory?tab=facts&role={role}&msg=Product+fact+added+with+source+citation&msg_type=success",
        status_code=303
    )

@router.post("/facts/{item_id}/edit")
async def edit_product_fact(
    item_id: int,
    product_name: str = Form(...),
    category: str = Form("Specifications"),
    feature_name: str = Form(...),
    specification_detail: str = Form(...),
    verified_source: str = Form(...),
    confidentiality: ConfidentialityLevel = Form(ConfidentialityLevel.INTERNAL),
    role: str = Form("reviewer"),
    session: Session = Depends(get_session)
):
    if not check_reviewer_permission(role):
        return RedirectResponse(
            url=f"/brand-memory?tab=facts&role={role}&msg=Permission+Denied&msg_type=error",
            status_code=303
        )

    fact = session.get(ProductFact, item_id)
    if fact:
        fact.product_name = product_name.strip()
        fact.category = category.strip()
        fact.feature_name = feature_name.strip()
        fact.specification_detail = specification_detail.strip()
        fact.verified_source = verified_source.strip()
        fact.confidentiality = confidentiality
        fact.updated_at = datetime.now(timezone.utc)
        session.add(fact)
        session.commit()

    return RedirectResponse(
        url=f"/brand-memory?tab=facts&role={role}&msg=Product+fact+updated&msg_type=success",
        status_code=303
    )

@router.post("/facts/{item_id}/delete")
async def delete_product_fact(
    item_id: int,
    role: str = Form("reviewer"),
    session: Session = Depends(get_session)
):
    if not check_reviewer_permission(role):
        return RedirectResponse(
            url=f"/brand-memory?tab=facts&role={role}&msg=Permission+Denied&msg_type=error",
            status_code=303
        )

    fact = session.get(ProductFact, item_id)
    if fact:
        session.delete(fact)
        session.commit()

    return RedirectResponse(
        url=f"/brand-memory?tab=facts&role={role}&msg=Product+fact+deleted&msg_type=info",
        status_code=303
    )

# -------------------------------------------------------------
# 4. APPROVED CLAIMS LIBRARY CRUD & VERIFICATION WORKFLOW
# -------------------------------------------------------------

@router.post("/claims/add")
async def add_approved_claim(
    topic: str = Form(...),
    claim_statement: str = Form(...),
    evidence_type: str = Form(...),
    source_reference: str = Form(...),
    review_date: Optional[str] = Form(None),
    expiration_date: Optional[str] = Form(None),
    notes: Optional[str] = Form(None),
    is_confidential: bool = Form(False),
    role: str = Form("reviewer"),
    session: Session = Depends(get_session)
):
    # Enforce Governance Principle: Arbitrary user text is NEVER automatically verified
    is_rev = check_reviewer_permission(role)
    status = VerificationStatus.VERIFIED if is_rev else VerificationStatus.PENDING_REVIEW
    verifier = "Morgan Vance (Governance Lead)" if is_rev else "Pending Legal Verification"

    parsed_review_date = None
    if review_date:
        try:
            parsed_review_date = date.fromisoformat(review_date)
        except ValueError:
            pass

    parsed_expiration_date = None
    if expiration_date:
        try:
            parsed_expiration_date = date.fromisoformat(expiration_date)
        except ValueError:
            pass

    now = datetime.now(timezone.utc)
    claim = ApprovedClaim(
        topic=topic.strip(),
        claim_statement=claim_statement.strip(),
        evidence_type=evidence_type.strip(),
        source_reference=source_reference.strip(),
        verified_by=verifier,
        verification_status=status,
        review_date=parsed_review_date or date.today(),
        expiration_date=parsed_expiration_date,
        notes=notes.strip() if notes else None,
        is_confidential=is_confidential,
        created_at=now,
        updated_at=now
    )
    session.add(claim)

    log = ActivityLog(
        user_name="Morgan Vance" if is_rev else "Alex Chen",
        action="Added verified claim" if is_rev else "Submitted claim for legal verification",
        target_title=topic.strip(),
        icon="award",
        badge_color="text-emerald-400 bg-emerald-500/10" if is_rev else "text-amber-400 bg-amber-500/10",
        timestamp=now
    )
    session.add(log)
    session.commit()

    feedback = "Verified claim added with source attribution" if is_rev else "Claim submitted and marked PENDING VERIFICATION"
    return RedirectResponse(
        url=f"/brand-memory?tab=claims&role={role}&msg={feedback.replace(' ', '+')}&msg_type=success",
        status_code=303
    )

@router.post("/claims/{item_id}/verify")
async def verify_claim_status(
    item_id: int,
    status: VerificationStatus = Form(...),
    notes: Optional[str] = Form(None),
    role: str = Form("reviewer"),
    session: Session = Depends(get_session)
):
    if not check_reviewer_permission(role):
        return RedirectResponse(
            url=f"/brand-memory?tab=claims&role={role}&msg=Permission+Denied:+Only+Reviewers+can+verify+claims&msg_type=error",
            status_code=303
        )

    claim = session.get(ApprovedClaim, item_id)
    if claim:
        claim.verification_status = status
        claim.verified_by = "Morgan Vance (Governance Lead)" if status == VerificationStatus.VERIFIED else claim.verified_by
        claim.review_date = date.today()
        if notes:
            claim.notes = notes.strip()
        claim.updated_at = datetime.now(timezone.utc)
        session.add(claim)
        session.commit()

    return RedirectResponse(
        url=f"/brand-memory?tab=claims&role={role}&msg=Claim+status+updated+to+{status.value}&msg_type=success",
        status_code=303
    )

@router.post("/claims/{item_id}/delete")
async def delete_approved_claim(
    item_id: int,
    role: str = Form("reviewer"),
    session: Session = Depends(get_session)
):
    if not check_reviewer_permission(role):
        return RedirectResponse(
            url=f"/brand-memory?tab=claims&role={role}&msg=Permission+Denied&msg_type=error",
            status_code=303
        )

    claim = session.get(ApprovedClaim, item_id)
    if claim:
        session.delete(claim)
        session.commit()

    return RedirectResponse(
        url=f"/brand-memory?tab=claims&role={role}&msg=Claim+entry+removed&msg_type=info",
        status_code=303
    )

# -------------------------------------------------------------
# 5. BRAND ASSET REFERENCES CRUD
# -------------------------------------------------------------

@router.post("/assets/add")
async def add_brand_asset_ref(
    name: str = Form(...),
    category: str = Form("Logo"),
    usage_guidelines: str = Form(...),
    attribution_text: Optional[str] = Form(None),
    file_reference: Optional[str] = Form(None),
    is_deprecated: bool = Form(False),
    role: str = Form("reviewer"),
    session: Session = Depends(get_session)
):
    if not check_reviewer_permission(role):
        return RedirectResponse(
            url=f"/brand-memory?tab=assets&role={role}&msg=Permission+Denied:+Reviewer+role+required&msg_type=error",
            status_code=303
        )

    now = datetime.now(timezone.utc)
    asset = BrandAssetRef(
        name=name.strip(),
        category=category.strip(),
        usage_guidelines=usage_guidelines.strip(),
        attribution_text=attribution_text.strip() if attribution_text else None,
        file_reference=file_reference.strip() if file_reference else None,
        is_deprecated=is_deprecated,
        created_at=now,
        updated_at=now
    )
    session.add(asset)
    session.commit()

    return RedirectResponse(
        url=f"/brand-memory?tab=assets&role={role}&msg=Brand+asset+reference+added&msg_type=success",
        status_code=303
    )

@router.post("/assets/{item_id}/edit")
async def edit_brand_asset_ref(
    item_id: int,
    name: str = Form(...),
    category: str = Form("Logo"),
    usage_guidelines: str = Form(...),
    attribution_text: Optional[str] = Form(None),
    file_reference: Optional[str] = Form(None),
    is_deprecated: bool = Form(False),
    role: str = Form("reviewer"),
    session: Session = Depends(get_session)
):
    if not check_reviewer_permission(role):
        return RedirectResponse(
            url=f"/brand-memory?tab=assets&role={role}&msg=Permission+Denied&msg_type=error",
            status_code=303
        )

    asset = session.get(BrandAssetRef, item_id)
    if asset:
        asset.name = name.strip()
        asset.category = category.strip()
        asset.usage_guidelines = usage_guidelines.strip()
        asset.attribution_text = attribution_text.strip() if attribution_text else None
        asset.file_reference = file_reference.strip() if file_reference else None
        asset.is_deprecated = is_deprecated
        asset.updated_at = datetime.now(timezone.utc)
        session.add(asset)
        session.commit()

    return RedirectResponse(
        url=f"/brand-memory?tab=assets&role={role}&msg=Brand+asset+reference+updated&msg_type=success",
        status_code=303
    )

@router.post("/assets/{item_id}/delete")
async def delete_brand_asset_ref(
    item_id: int,
    role: str = Form("reviewer"),
    session: Session = Depends(get_session)
):
    if not check_reviewer_permission(role):
        return RedirectResponse(
            url=f"/brand-memory?tab=assets&role={role}&msg=Permission+Denied&msg_type=error",
            status_code=303
        )

    asset = session.get(BrandAssetRef, item_id)
    if asset:
        session.delete(asset)
        session.commit()

    return RedirectResponse(
        url=f"/brand-memory?tab=assets&role={role}&msg=Brand+asset+reference+deleted&msg_type=info",
        status_code=303
    )
