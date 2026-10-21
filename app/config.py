import os
from pathlib import Path
from pydantic_settings import BaseSettings
from typing import Optional

BASE_DIR = Path(__file__).resolve().parent.parent

class Settings(BaseSettings):
    PROJECT_NAME: str = "Smart attendance"
    APP_ENV: str = "development"
    SECRET_KEY: str = "smart-attendance-super-secure-jwt-secret-key-hackathon-2026"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480
    
    # SQLite Database - robust absolute path
    DATABASE_URL: str = f"sqlite:///{BASE_DIR / 'smart_attendance.db'}"
    
    # Attendance Verification Policies
    ROTATING_CODE_INTERVAL_SECONDS: int = 30
    DEFAULT_SESSION_RADIUS_METERS: float = 50.0
    LOCATION_TOLERANCE_METERS: float = 15.0 # Allowed buffer before instant rejection
    
    # Anti-Proxy Face Similarity Percentages (0 - 100)
    FACE_SIMILARITY_THRESHOLD: float = 75.0  # >= 75% -> Auto Present if liveness passes
    FACE_BORDERLINE_THRESHOLD: float = 60.0  # 60% - 74.9% -> Pending Review / Flagged
    
    # External API Keys
    API_KEY: Optional[str] = "AQ.Ab8RN6KXupKRP9G2Xs3q7jeEmGivcV2HfU5P1QhO-gc0xjzftg"
    GEMINI_API_KEY: Optional[str] = "AQ.Ab8RN6KXupKRP9G2Xs3q7jeEmGivcV2HfU5P1QhO-gc0xjzftg"

    class Config:
        env_file = str(BASE_DIR / ".env")
        extra = "ignore"

settings = Settings()

