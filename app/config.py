import os
from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    PROJECT_NAME: str = "BrandShield AI"
    VERSION: str = "1.0.0"
    ENVIRONMENT: str = "production"
    SECRET_KEY: str = os.environ.get(
        "SECRET_KEY", "development-only-key"
    )

    BASE_DIR: Path = Path(__file__).resolve().parent.parent

    if os.environ.get("VERCEL"):
        DATABASE_URL: str = "sqlite:////tmp/brandshield.db"
        UPLOAD_DIR: Path = Path("/tmp/uploads")
    else:
        DATABASE_URL: str = f"sqlite:///{BASE_DIR}/brandshield.db"
        UPLOAD_DIR: Path = BASE_DIR / "uploads"

    ENABLE_PII_REDACTION: bool = True
    DEMO_MODE: bool = True

    class Config:
        env_file = ".env"
        extra = "allow"


settings = Settings()
settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)