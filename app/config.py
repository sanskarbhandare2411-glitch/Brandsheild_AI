from pydantic_settings import BaseSettings
from pathlib import Path

class Settings(BaseSettings):
    PROJECT_NAME: str = "BrandShield AI"
    VERSION: str = "1.0.0"
    ENVIRONMENT: str = "development"
    SECRET_KEY: str = "brandshield-dev-secret-codex48"
    
    BASE_DIR: Path = Path(__file__).resolve().parent.parent
    DATABASE_URL: str = f"sqlite:///{BASE_DIR}/brandshield.db"
    UPLOAD_DIR: Path = BASE_DIR / "uploads"
    
    # Feature flags & privacy
    ENABLE_PII_REDACTION: bool = True
    DEMO_MODE: bool = True  # Explicitly demarcates pre-populated mock records

    class Config:
        env_file = ".env"
        extra = "allow"

settings = Settings()
settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
