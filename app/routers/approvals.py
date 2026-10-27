"""
Approvals Router — Human-controlled content approval workflow.

Roles (simulated via ?role= query/form param for Codex 48 demo):
  creator  → Can view findings and resubmit; CANNOT approve or reject.
  reviewer → Can approve, reject, or request changes.
  admin    → Same decision rights as reviewer; also controls guideline management.

Workflow state machine:
  SUBMITTED → AI_REVIEW → HUMAN_REVIEW → APPROVED
                                       → CHANGES_REQUESTED
                                       → REJECTED

Key guards:
  • Creators are forbidden from approving their own (or any) content.
  • Approval requires an explicit human action — never automated.
  • Any edit after approval clears approved_by / approved_at and resets to AI_REVIEW.
  • Every decision is persisted in ReviewDecision for a full audit trail.
"""

from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import Session, select
from datetime import datetime, timezone
from typing import Optional

from app.core.database import get_session
from app.core.models import (
    ContentSubmission, ContentStatus, ActivityLog, Role,
    ReviewDecision, ContentRevision
)
from app.config import settings

router = APIRouter(prefix="/approvals", tags=["Approvals"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve_user(role: str) -> dict:
    """Simulate the current logged-in user from the ?role= param."""
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


def _can_decide(user: dict) -> bool:
    """Reviewers and Admins may make approval decisions; Creators cannot."""
    return user["role"] in (Role.REVIEWER, Role.ADMIN)


# ---------------------------------------------------------------------------
# Queue view
# ---------------------------------------------------------------------------

@router.get("/", response_class=HTMLResponse)
async def approvals_view(
    request: Request,
    role: str = "reviewer",
    action: Optional[str] = None,
    session: Session = Depends(get_session),
):
    """Display the reviewer queue — all submissions awaiting human review."""
    current_user = _resolve_user(role)

    # Items the reviewer needs to act on
    reviewable_statuses = [
        ContentStatus.HUMAN_REVIEW,
        ContentStatus.CHANGES_REQUESTED,
    ]
    pending_items = session.exec(
        select(ContentSubmission)
        .where(ContentSubmission.status.in_(reviewable_statuses))
        .order_by(ContentSubmission.created_at.desc())
    ).all()

    # Also surface recently decided items for context
    recently_decided = session.exec(
        select(ContentSubmission)
        .where(ContentSubmission.status.in_([ContentStatus.APPROVED, ContentStatus.REJECTED]))
        .order_by(ContentSubmission.updated_at.desc())
        .limit(5)
    ).all()

    # Load latest ReviewDecision for each pending item (for display)
    decision_map: dict[int, ReviewDecision] = {}
    for item in pending_items + recently_decided:
        latest = session.exec(
            select(ReviewDecision)
            .where(ReviewDecision.submission_id == item.id)
            .order_by(ReviewDecision.decided_at.desc())
        ).first()
        if latest:
            decision_map[item.id] = latest

    templates = request.app.state.templates
    return templates.TemplateResponse(
        request=request,
        name="approvals.html",
        context={
            "project_name": settings.PROJECT_NAME,
            "current_user": current_user,
            "active_tab": "approvals",
            "pending_items": pending_items,
            "recently_decided": recently_decided,
            "decision_map": decision_map,
            "can_decide": _can_decide(current_user),
            "flash_action": action,
        },
    )


# ---------------------------------------------------------------------------
# Approve
# ---------------------------------------------------------------------------

@router.post("/{submission_id}/approve")
async def approve_submission(
    submission_id: int,
    role: str = Form("reviewer"),
    reviewer_name: str = Form(""),
    comments: str = Form(""),
    session: Session = Depends(get_session),
):
    """
    Approve a submission for publication.
    ONLY reviewers and admins may call this endpoint.
    """
    now = datetime.now(timezone.utc)
    current_user = _resolve_user(role)

    if not _can_decide(current_user):
        # Creator attempted to approve — redirect with error flag
        return RedirectResponse(
            url=f"/approvals?action=forbidden&role={role}", status_code=303
        )

    sub = session.get(ContentSubmission, submission_id)
    if not sub:
        return RedirectResponse(url=f"/approvals?action=not_found&role={role}", status_code=303)

    # Record the human decision
    dec = ReviewDecision(
        submission_id=sub.id,
        revision_version=sub.current_version or 1,
        reviewer_name=reviewer_name.strip() or current_user["name"],
        reviewer_email=current_user["email"],
        reviewer_role=current_user["role"],
        decision="approved",
        comments=comments.strip() or "Approved for publication without additional comments.",
        decided_at=now,
    )
    session.add(dec)

    # Update the submission — explicit human approval required
    sub.status = ContentStatus.APPROVED
    sub.approved_by = reviewer_name.strip() or current_user["name"]
    sub.approved_at = now
    sub.updated_at = now
    session.add(sub)

    log = ActivityLog(
        user_name=current_user["name"],
        action=f"Approved for publication (v{sub.current_version or 1})",
        target_title=sub.title,
        icon="check-circle",
        badge_color="text-emerald-400 bg-emerald-500/10",
        timestamp=now,
    )
    session.add(log)
    session.commit()

    return RedirectResponse(url=f"/approvals?action=approved&role={role}", status_code=303)


# ---------------------------------------------------------------------------
# Request Changes
# ---------------------------------------------------------------------------

@router.post("/{submission_id}/request_changes")
async def request_changes(
    submission_id: int,
    role: str = Form("reviewer"),
    reviewer_name: str = Form(""),
    comments: str = Form(""),
    session: Session = Depends(get_session),
):
    """Request the creator revise and resubmit."""
    now = datetime.now(timezone.utc)
    current_user = _resolve_user(role)

    if not _can_decide(current_user):
        return RedirectResponse(
            url=f"/approvals?action=forbidden&role={role}", status_code=303
        )

    sub = session.get(ContentSubmission, submission_id)
    if not sub:
        return RedirectResponse(url=f"/approvals?action=not_found&role={role}", status_code=303)

    dec = ReviewDecision(
        submission_id=sub.id,
        revision_version=sub.current_version or 1,
        reviewer_name=reviewer_name.strip() or current_user["name"],
        reviewer_email=current_user["email"],
        reviewer_role=current_user["role"],
        decision="changes_requested",
        comments=comments.strip() or "Please revise before resubmitting.",
        decided_at=now,
    )
    session.add(dec)

    sub.status = ContentStatus.CHANGES_REQUESTED
    sub.updated_at = now
    # Invalidate any prior approval
    sub.approved_by = None
    sub.approved_at = None
    session.add(sub)

    log = ActivityLog(
        user_name=current_user["name"],
        action=f"Requested changes on v{sub.current_version or 1}",
        target_title=sub.title,
        icon="rotate-ccw",
        badge_color="text-amber-400 bg-amber-500/10",
        timestamp=now,
    )
    session.add(log)
    session.commit()

    return RedirectResponse(url=f"/approvals?action=changes_requested&role={role}", status_code=303)


# ---------------------------------------------------------------------------
# Reject
# ---------------------------------------------------------------------------

@router.post("/{submission_id}/reject")
async def reject_submission(
    submission_id: int,
    role: str = Form("reviewer"),
    reviewer_name: str = Form(""),
    comments: str = Form(""),
    session: Session = Depends(get_session),
):
    """Permanently reject a submission."""
    now = datetime.now(timezone.utc)
    current_user = _resolve_user(role)

    if not _can_decide(current_user):
        return RedirectResponse(
            url=f"/approvals?action=forbidden&role={role}", status_code=303
        )

    sub = session.get(ContentSubmission, submission_id)
    if not sub:
        return RedirectResponse(url=f"/approvals?action=not_found&role={role}", status_code=303)

    dec = ReviewDecision(
        submission_id=sub.id,
        revision_version=sub.current_version or 1,
        reviewer_name=reviewer_name.strip() or current_user["name"],
        reviewer_email=current_user["email"],
        reviewer_role=current_user["role"],
        decision="rejected",
        comments=comments.strip() or "Submission rejected.",
        decided_at=now,
    )
    session.add(dec)

    sub.status = ContentStatus.REJECTED
    sub.approved_by = None
    sub.approved_at = None
    sub.updated_at = now
    session.add(sub)

    log = ActivityLog(
        user_name=current_user["name"],
        action=f"Rejected submission (v{sub.current_version or 1})",
        target_title=sub.title,
        icon="x-circle",
        badge_color="text-rose-400 bg-rose-500/10",
        timestamp=now,
    )
    session.add(log)
    session.commit()

    return RedirectResponse(url=f"/approvals?action=rejected&role={role}", status_code=303)
