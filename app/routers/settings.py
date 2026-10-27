from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlmodel import Session, select
import os
from app.core.database import get_session
from app.core.models import User, Role
from app.config import settings

router = APIRouter(prefix="/settings", tags=["Settings"])

@router.get("/", response_class=HTMLResponse)
async def settings_view(
    request: Request,
    role: str = "reviewer",
    session: Session = Depends(get_session)
):
    users = session.exec(select(User)).all()
    templates = request.app.state.templates
    
    current_user = {
        "name": "Morgan Vance" if role == "reviewer" else "Alex Chen",
        "email": "morgan.vance@brandshield.internal" if role == "reviewer" else "alex.chen@brandshield.internal",
        "role": Role.REVIEWER if role == "reviewer" else Role.CREATOR,
        "role_label": "Reviewer & Governance Lead" if role == "reviewer" else "Content Specialist & Creator",
        "avatar_bg": "bg-emerald-600" if role == "reviewer" else "bg-sky-600"
    }

    has_gemini_key = bool(os.getenv("GEMINI_API_KEY"))

    return templates.TemplateResponse(
        request=request,
        name="settings.html",
        context={
            "project_name": settings.PROJECT_NAME,
            "current_user": current_user,
            "active_tab": "settings",
            "users": users,
            "has_gemini_key": has_gemini_key,
            "pii_redaction_enabled": settings.ENABLE_PII_REDACTION
        }
    )
