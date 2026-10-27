"""
Content Router — Submission, AI analysis, recheck, and creator resubmit.

Workflow transitions managed here:
  Submit new   → AI_REVIEW → HUMAN_REVIEW (clean) | CHANGES_REQUESTED (issues found)
  Resubmit     → invalidates prior approval → AI_REVIEW → HUMAN_REVIEW | CHANGES_REQUESTED
  Recheck      → re-evaluates existing copy against latest Brand Memory

Auto-approval is NEVER triggered regardless of compliance score.
Every revision is persisted in ContentRevision for full audit history.
"""

from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import Session, select
from datetime import datetime, timezone
from typing import Optional

from app.core.database import get_session
from app.core.models import (
    ContentSubmission, ContentStatus, ContentRevision, ReviewDecision,
    ComplianceIssue, ActivityLog, Role, Severity, ConfidenceLevel
)
from app.services.compliance_engine import ComplianceEngine
from app.config import settings

router = APIRouter(prefix="/content", tags=["Content"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve_user(role: str) -> dict:
    role_lc = role.lower()
    if role_lc == "admin":
        return {
            "name": "Jordan Cross",
            "email": "jordan.cross@brandshield.internal",
            "role": Role.ADMIN,
            "role_label": "Platform Administrator",
            "avatar_bg": "bg-violet-600",
        }
    if role_lc == "reviewer":
        return {
            "name": "Morgan Vance",
            "email": "morgan.vance@brandshield.internal",
            "role": Role.REVIEWER,
            "role_label": "Reviewer & Governance Lead",
            "avatar_bg": "bg-emerald-600",
        }
    return {
        "name": "Alex Chen",
        "email": "alex.chen@brandshield.internal",
        "role": Role.CREATOR,
        "role_label": "Content Specialist & Creator",
        "avatar_bg": "bg-sky-600",
    }


def _status_after_analysis(findings) -> ContentStatus:
    """
    Determine next status after AI scan.
    NEVER returns APPROVED — always requires explicit human decision.
    """
    if findings:
        return ContentStatus.CHANGES_REQUESTED
    return ContentStatus.HUMAN_REVIEW


def _run_analysis_and_store(session, submission_id: int, content_text: str, channel: str):
    """Run compliance engine and persist findings. Returns (analysis_result, engine_mode)."""
    engine = ComplianceEngine(session)
    analysis_result, engine_mode = engine.evaluate(content_text, channel)

    for finding in analysis_result.findings:
        # ConfidenceEnum values are now uppercase ("HIGH","MEDIUM","LOW") matching ConfidenceLevel
        issue = ComplianceIssue(
            submission_id=submission_id,
            rule_category=finding.issue_category,
            severity=Severity(finding.severity.value),
            confidence=ConfidenceLevel(finding.confidence.value),
            claim_text=finding.problematic_text,
            explanation=finding.explanation,
            suggested_fix=finding.suggested_correction,
            rule_citation=finding.applicable_rule_or_source or "Brand Memory Policy",
            requires_human_verification=finding.requires_human_verification,
        )
        session.add(issue)

    return analysis_result, engine_mode


# ---------------------------------------------------------------------------
# List view
# ---------------------------------------------------------------------------

@router.get("/", response_class=HTMLResponse)
async def content_list_view(
    request: Request,
    role: str = "creator",
    session: Session = Depends(get_session),
):
    submissions = session.exec(
        select(ContentSubmission).order_by(ContentSubmission.created_at.desc())
    ).all()
    templates = request.app.state.templates
    current_user = _resolve_user(role)

    return templates.TemplateResponse(
        request=request,
        name="content_review.html",
        context={
            "project_name": settings.PROJECT_NAME,
            "current_user": current_user,
            "active_tab": "content",
            "submissions": submissions,
        },
    )


# ---------------------------------------------------------------------------
# Detail / Inspection view
# ---------------------------------------------------------------------------

@router.get("/{submission_id}", response_class=HTMLResponse)
async def content_detail_view(
    submission_id: int,
    request: Request,
    role: str = "creator",
    analyzed: Optional[str] = None,
    rechecked: Optional[str] = None,
    resubmitted: Optional[str] = None,
    session: Session = Depends(get_session),
):
    sub = session.get(ContentSubmission, submission_id)
    if not sub:
        raise HTTPException(status_code=404, detail="Content submission not found")

    issues = session.exec(
        select(ComplianceIssue).where(ComplianceIssue.submission_id == submission_id)
    ).all()

    revisions = session.exec(
        select(ContentRevision)
        .where(ContentRevision.submission_id == submission_id)
        .order_by(ContentRevision.version_number.desc())
    ).all()

    decisions = session.exec(
        select(ReviewDecision)
        .where(ReviewDecision.submission_id == submission_id)
        .order_by(ReviewDecision.decided_at.desc())
    ).all()

    current_user = _resolve_user(role)
    is_reviewer = current_user["role"] in (Role.REVIEWER, Role.ADMIN)

    templates = request.app.state.templates
    return templates.TemplateResponse(
        request=request,
        name="content_detail.html",
        context={
            "project_name": settings.PROJECT_NAME,
            "current_user": current_user,
            "active_tab": "content",
            "submission": sub,
            "issues": issues,
            "revisions": revisions,
            "decisions": decisions,
            "is_reviewer": is_reviewer,
            "flash_analyzed": analyzed == "true",
            "flash_rechecked": rechecked == "true",
            "flash_resubmitted": resubmitted == "true",
        },
    )


# ---------------------------------------------------------------------------
# Submit new content
# ---------------------------------------------------------------------------

@router.post("/submit")
async def submit_content(
    request: Request,
    title: str = Form(...),
    campaign: str = Form("General Marketing"),
    channel: str = Form("Multi-Channel"),
    content_text: str = Form(...),
    author_name: str = Form("Alex Chen"),
    role: str = Form("creator"),
    session: Session = Depends(get_session),
):
    now = datetime.now(timezone.utc)

    # Validate input length and non-empty content
    clean_title = title.strip()
    clean_text = content_text.strip()
    if not clean_title:
        raise HTTPException(status_code=400, detail="Document title cannot be empty.")
    if len(clean_text) < 10:
        raise HTTPException(status_code=400, detail="Content text must be at least 10 characters long.")
    if len(clean_text) > 100_000:
        raise HTTPException(status_code=400, detail="Content exceeds maximum allowed size (100,000 characters).")

    # 1. Persist new submission in SUBMITTED state
    new_submission = ContentSubmission(
        title=clean_title,
        campaign=campaign.strip(),
        channel=channel.strip(),
        content_text=clean_text,
        status=ContentStatus.AI_REVIEW,      # starts here, transitions below
        compliance_score=None,
        author_name=author_name,
        author_role=Role.CREATOR if role == "creator" else Role.REVIEWER,
        current_version=1,
        is_demo=False,
        created_at=now,
        updated_at=now,
    )
    session.add(new_submission)
    session.commit()
    session.refresh(new_submission)

    # 2. Run AI compliance scan
    analysis_result, engine_mode = _run_analysis_and_store(
        session, new_submission.id, content_text.strip(), channel.strip()
    )

    # 3. Save initial revision record
    rev = ContentRevision(
        submission_id=new_submission.id,
        version_number=1,
        content_text=content_text.strip(),
        change_summary="Initial submission",
        submitted_by=author_name,
        submitted_at=now,
        compliance_score=analysis_result.overall_score,
        engine_used=engine_mode,
        status_at_submission=ContentStatus.AI_REVIEW.value,
    )
    session.add(rev)

    # 4. Update submission — NEVER auto-approve
    new_submission.compliance_score = analysis_result.overall_score
    new_submission.engine_used = engine_mode
    new_submission.status = _status_after_analysis(analysis_result.findings)
    new_submission.updated_at = now
    session.add(new_submission)

    # 5. Audit log
    activity = ActivityLog(
        user_name=author_name,
        action=f"Submitted for AI review ({engine_mode.split()[0]} score: {analysis_result.overall_score}%)",
        target_title=title.strip(),
        icon="scan-line",
        badge_color=(
            "text-emerald-400 bg-emerald-500/10"
            if analysis_result.overall_score >= 80
            else "text-rose-400 bg-rose-500/10"
        ),
        timestamp=now,
    )
    session.add(activity)
    session.commit()

    return RedirectResponse(
        url=f"/content/{new_submission.id}?role={role}&analyzed=true", status_code=303
    )


# ---------------------------------------------------------------------------
# Resubmit (creator revises after changes requested)
# ---------------------------------------------------------------------------

@router.post("/{submission_id}/resubmit")
async def resubmit_content(
    submission_id: int,
    role: str = Form("creator"),
    content_text: str = Form(...),
    change_summary: str = Form("Revised per reviewer feedback"),
    session: Session = Depends(get_session),
):
    """
    Creator revises and resubmits content.
    • Increments version number.
    • Saves the new revision to history.
    • Clears prior approval (approved_by / approved_at).
    • Re-runs AI compliance scan.
    • Transitions back through AI_REVIEW → HUMAN_REVIEW | CHANGES_REQUESTED.
    """
    now = datetime.now(timezone.utc)
    current_user = _resolve_user(role)

    sub = session.get(ContentSubmission, submission_id)
    if not sub:
        raise HTTPException(status_code=404, detail="Submission not found")

    # Only allow resubmit if changes were requested or submission was rejected
    allowed_resubmit_statuses = [
        ContentStatus.CHANGES_REQUESTED,
        ContentStatus.REJECTED,
        ContentStatus.HUMAN_REVIEW,  # also allow resubmit from HUMAN_REVIEW
    ]
    if sub.status not in allowed_resubmit_statuses:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot resubmit content in status '{sub.status.value}'. "
                   f"Only allowed when changes have been requested or content was rejected.",
        )

    new_version = (sub.current_version or 1) + 1

    # Invalidate any prior approval
    sub.content_text = content_text.strip()
    sub.current_version = new_version
    sub.approved_by = None
    sub.approved_at = None
    sub.status = ContentStatus.AI_REVIEW
    sub.updated_at = now

    # Clear old issues before re-evaluation
    old_issues = session.exec(
        select(ComplianceIssue).where(ComplianceIssue.submission_id == submission_id)
    ).all()
    for oi in old_issues:
        session.delete(oi)
    session.flush()

    # Run fresh AI scan
    analysis_result, engine_mode = _run_analysis_and_store(
        session, submission_id, content_text.strip(), sub.channel
    )

    # Save revision record
    rev = ContentRevision(
        submission_id=submission_id,
        version_number=new_version,
        content_text=content_text.strip(),
        change_summary=change_summary.strip(),
        submitted_by=current_user["name"],
        submitted_at=now,
        compliance_score=analysis_result.overall_score,
        engine_used=engine_mode,
        status_at_submission=ContentStatus.AI_REVIEW.value,
    )
    session.add(rev)

    # Update submission status — NEVER auto-approve
    sub.compliance_score = analysis_result.overall_score
    sub.engine_used = engine_mode
    sub.status = _status_after_analysis(analysis_result.findings)
    sub.updated_at = now
    session.add(sub)

    # Audit log
    activity = ActivityLog(
        user_name=current_user["name"],
        action=f"Resubmitted v{new_version} for re-review (score: {analysis_result.overall_score}%)",
        target_title=sub.title,
        icon="refresh-cw",
        badge_color="text-sky-400 bg-sky-500/10",
        timestamp=now,
    )
    session.add(activity)
    session.commit()

    return RedirectResponse(
        url=f"/content/{submission_id}?role={role}&resubmitted=true", status_code=303
    )


# ---------------------------------------------------------------------------
# Recheck (re-evaluate existing text against latest Brand Memory)
# ---------------------------------------------------------------------------

@router.post("/{submission_id}/recheck")
async def recheck_submission(
    submission_id: int,
    role: str = Form("reviewer"),
    session: Session = Depends(get_session),
):
    sub = session.get(ContentSubmission, submission_id)
    if not sub:
        raise HTTPException(status_code=404, detail="Submission not found")

    # Clear old issues
    old_issues = session.exec(
        select(ComplianceIssue).where(ComplianceIssue.submission_id == submission_id)
    ).all()
    for oi in old_issues:
        session.delete(oi)
    session.flush()

    # Re-evaluate against latest Brand Memory
    analysis_result, engine_mode = _run_analysis_and_store(
        session, submission_id, sub.content_text, sub.channel
    )

    sub.compliance_score = analysis_result.overall_score
    sub.engine_used = engine_mode
    # Only transition non-final statuses — don't reopen APPROVED/REJECTED without explicit action
    if sub.status not in (ContentStatus.APPROVED, ContentStatus.REJECTED):
        sub.status = _status_after_analysis(analysis_result.findings)
    sub.updated_at = datetime.now(timezone.utc)
    session.add(sub)
    session.commit()

    return RedirectResponse(
        url=f"/content/{sub.id}?role={role}&rechecked=true", status_code=303
    )
