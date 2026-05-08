import os
from typing import Optional
from pydantic import field_validator, ValidationInfo
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    host: str = "0.0.0.0"
    port: int = 8000
    environment: str = "development"
    
    # Security - No defaults to force explicit configuration
    jwt_secret_key: str = "CHANGE_ME"
    admin_cleanup_token: str = "CHANGE_ME"
    allowed_origins: str = "http://localhost:5173,http://localhost:5174,http://127.0.0.1:5173,http://127.0.0.1:5174"
    
    # ── Infrastructure ────────────────────────────────
    database_path: str = "printers.db"
    db_type: str = "sqlite" # or "postgresql"
    db_host: str = "localhost"
    db_port: int = 5432
    db_user: str = "postgres"
    db_password: str = "password"
    db_name: str = "printhub"
    database_backup_path: str = "./backups/"
    stale_threshold_seconds: int = 45

    # ── Alerting (Optional) ───────────────────────────
    alert_webhook_url: Optional[str] = None
    smtp_host: Optional[str] = None
    smtp_port: int = 587
    alert_email_from: str = "printhub@hospital.internal"
    alert_email_to: str = "it-support@hospital.internal"
    
    # Intervals & Timeouts
    max_retry_count: int = 3
    job_lock_timeout_seconds: int = 300
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False
    )

    @field_validator("jwt_secret_key", "admin_cleanup_token")
    @classmethod
    def validate_secrets(cls, v: str, info: ValidationInfo):
        if info.data.get("environment") == "production":
            if not v or v == "CHANGE_ME" or len(v) < 32:
                raise ValueError("Secrets must be set to a strong random value (min 32 chars) in production")
        return v

# Instantiate settings singleton
settings = Settings()
