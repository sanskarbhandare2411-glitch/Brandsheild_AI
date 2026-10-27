from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlmodel import Session, select
from collections import Counter
from app.core.database import get_session
from app.core.models import ContentSubmission, ComplianceIssue, ContentStatus, Role, Severity
from app.config import settings

router = APIRouter(prefix="/analytics", tags=["Analytics"])

@router.get("/", response_class=HTMLResponse)
async def analytics_view(
    request: Request,
    role: str = "reviewer",
    session: Session = Depends(get_session)
):
    submissions = session.exec(select(ContentSubmission)).all()
    issues = session.exec(select(ComplianceIssue)).all()
    
    total_submissions = len(submissions)
    approved_count = sum(1 for s in submissions if s.status == ContentStatus.APPROVED)
    pending_approvals = sum(1 for s in submissions if s.status in [
        ContentStatus.HUMAN_REVIEW, 
        ContentStatus.CHANGES_REQUESTED, 
        ContentStatus.PENDING_REVIEW, 
        ContentStatus.FLAGGED
    ])
    rejected_count = sum(1 for s in submissions if s.status == ContentStatus.REJECTED)
    
    compliance_rate = round((approved_count / total_submissions * 100)) if total_submissions > 0 else 100
    
    # Calculate average compliance score across evaluated submissions
    evaluated = [s.compliance_score for s in submissions if s.compliance_score is not None]
    avg_score = round(sum(evaluated) / len(evaluated)) if evaluated else 0

    # Severity distribution
    severity_counts = {
        "critical": sum(1 for i in issues if i.severity == Severity.CRITICAL),
        "warning": sum(1 for i in issues if i.severity == Severity.WARNING),
        "info": sum(1 for i in issues if i.severity == Severity.INFO),
    }

    # Issue categories breakdown
    categories = {}
    for issue in issues:
        categories[issue.rule_category] = categories.get(issue.rule_category, 0) + 1

    # Top recurring brand violations (exact flagged texts)
    recurring_texts = Counter(i.claim_text.strip() for i in issues if i.claim_text).most_common(5)

    templates = request.app.state.templates
    
    current_user = {
        "name": "Morgan Vance" if role == "reviewer" else "Alex Chen",
        "email": "morgan.vance@brandshield.internal" if role == "reviewer" else "alex.chen@brandshield.internal",
        "role": Role.REVIEWER if role == "reviewer" else Role.CREATOR,
        "role_label": "Reviewer & Governance Lead" if role == "reviewer" else "Content Specialist & Creator",
        "avatar_bg": "bg-emerald-600" if role == "reviewer" else "bg-sky-600"
    }

    return templates.TemplateResponse(
        request=request,
        name="analytics.html",
        context={
            "project_name": settings.PROJECT_NAME,
            "current_user": current_user,
            "active_tab": "analytics",
            "total_submissions": total_submissions,
            "approved_count": approved_count,
            "pending_approvals": pending_approvals,
            "rejected_count": rejected_count,
            "compliance_rate": compliance_rate,
            "avg_score": avg_score,
            "total_issues": len(issues),
            "severity_counts": severity_counts,
            "categories": categories,
            "recurring_texts": recurring_texts,
            "has_demo_data": any(s.is_demo for s in submissions)
        }
    )
