from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from contextlib import asynccontextmanager
from pathlib import Path
from app.config import settings
from app.core.database import init_db
from app.routers import (
    dashboard, content, brand_memory, assets, 
    approvals, analytics, settings as app_settings
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize SQLite database and seed initial demonstration records
    init_db()
    yield

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    lifespan=lifespan
)

# Setup templates directory
templates_path = settings.BASE_DIR / "app" / "templates"
app.state.templates = Jinja2Templates(directory=str(templates_path))

# Setup static files directory if present
static_path = settings.BASE_DIR / "app" / "static"
if static_path.exists():
    app.mount("/static", StaticFiles(directory=str(static_path)), name="static")

# Include Routers
app.include_router(dashboard.router)
app.include_router(content.router)
app.include_router(brand_memory.router)
app.include_router(assets.router)
app.include_router(approvals.router)
app.include_router(analytics.router)
app.include_router(app_settings.router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
