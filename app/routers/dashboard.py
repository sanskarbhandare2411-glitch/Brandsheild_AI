from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlmodel import Session, select
from app.core.database import get_session
from app.core.models import (
    ContentSubmission, ContentStatus, ComplianceIssue, 
    ActivityLog, BrandGuideline, ApprovedAsset, Role
)
from app.config import settings

router = APIRouter()

@router.get("/", response_class=HTMLResponse)
async def dashboard_view(
    request: Request, 
    role: str = "reviewer",  # Allows demo switching: 'creator' or 'reviewer'
    session: Session = Depends(get_session)
):
    # Query summary metrics
    submissions = session.exec(select(ContentSubmission).order_by(ContentSubmission.created_at.desc())).all()
    
    total_reviewed = len(submissions)
    pending_approvals = sum(1 for s in submissions if s.status in [
        ContentStatus.HUMAN_REVIEW,
        ContentStatus.CHANGES_REQUESTED,
        # legacy aliases still in DB during first migration run
        ContentStatus.PENDING_REVIEW, ContentStatus.FLAGGED, ContentStatus.REVISION_REQUESTED
    ])
    approved_content = sum(1 for s in submissions if s.status == ContentStatus.APPROVED)
    
    issues = session.exec(select(ComplianceIssue)).all()
    detected_issues = len(issues)
    
    recent_activity = session.exec(select(ActivityLog).order_by(ActivityLog.timestamp.desc()).limit(6)).all()
    active_guidelines = session.exec(select(BrandGuideline).where(BrandGuideline.is_active == True)).all()
    approved_assets = session.exec(select(ApprovedAsset).limit(5)).all()
    
    # Active user profile based on role toggle
    current_user = {
        "name": "Morgan Vance" if role == "reviewer" else "Alex Chen",
        "email": "morgan.vance@brandshield.internal" if role == "reviewer" else "alex.chen@brandshield.internal",
        "role": Role.REVIEWER if role == "reviewer" else Role.CREATOR,
        "role_label": "Reviewer & Governance Lead" if role == "reviewer" else "Content Specialist & Creator",
        "avatar_bg": "bg-emerald-600" if role == "reviewer" else "bg-sky-600"
    }

    templates = request.app.state.templates
    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "project_name": settings.PROJECT_NAME,
            "current_user": current_user,
            "active_tab": "dashboard",
            "metrics": {
                "total_reviewed": total_reviewed,
                "pending_approvals": pending_approvals,
                "detected_issues": detected_issues,
                "approved_content": approved_content,
            },
            "submissions": submissions,
            "recent_activity": recent_activity,
            "active_guidelines": active_guidelines,
            "approved_assets": approved_assets,
            "has_demo_data": any(s.is_demo for s in submissions)
        }
    )
