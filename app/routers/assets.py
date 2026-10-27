from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlmodel import Session, select
from app.core.database import get_session
from app.core.models import ApprovedClaim, BrandAssetRef, Role
from app.config import settings

router = APIRouter(prefix="/assets", tags=["Assets"])

@router.get("/", response_class=HTMLResponse)
async def assets_view(
    request: Request,
    role: str = "reviewer",
    session: Session = Depends(get_session)
):
    claims = session.exec(select(ApprovedClaim)).all()
    assets = session.exec(select(BrandAssetRef)).all()
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
        name="assets.html",
        context={
            "project_name": settings.PROJECT_NAME,
            "current_user": current_user,
            "active_tab": "assets",
            "claims": claims,
            "assets": assets
        }
    )
