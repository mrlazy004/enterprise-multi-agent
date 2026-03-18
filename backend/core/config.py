"""
Enterprise Multi-Agent AI System — Core Configuration
"""
from pydantic_settings import BaseSettings
from typing import Optional
import os


class Settings(BaseSettings):
    # ── App ─────────────────────────────────────────────────────────────────
    APP_NAME: str = "Enterprise Multi-Agent AI"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"

    # ── Azure OpenAI ────────────────────────────────────────────────────────
    AZURE_OPENAI_API_KEY: str = os.getenv("AZURE_OPENAI_API_KEY", "")
    AZURE_OPENAI_ENDPOINT: str = os.getenv("AZURE_OPENAI_ENDPOINT", "")
    AZURE_OPENAI_API_VERSION: str = "2024-02-01"
    AZURE_OPENAI_DEPLOYMENT_NAME: str = "gpt-4o"
    AZURE_OPENAI_EMBEDDING_DEPLOYMENT: str = "text-embedding-ada-002"

    # ── Azure Storage & Search ───────────────────────────────────────────────
    AZURE_STORAGE_CONNECTION_STRING: str = os.getenv("AZURE_STORAGE_CONNECTION_STRING", "")
    AZURE_SEARCH_ENDPOINT: str = os.getenv("AZURE_SEARCH_ENDPOINT", "")
    AZURE_SEARCH_API_KEY: str = os.getenv("AZURE_SEARCH_API_KEY", "")
    AZURE_SEARCH_INDEX_NAME: str = "enterprise-docs"

    # ── Database ────────────────────────────────────────────────────────────
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./enterprise_agents.db")
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379")

    # ── Security ────────────────────────────────────────────────────────────
    SECRET_KEY: str = os.getenv("SECRET_KEY", "change-me-in-production")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # ── Agent Config ────────────────────────────────────────────────────────
    AGENT_MAX_ITERATIONS: int = 10
    AGENT_TIMEOUT_SECONDS: int = 120
    MEMORY_WINDOW_SIZE: int = 20

    # ── Human-in-the-Loop ───────────────────────────────────────────────────
    HITL_APPROVAL_TIMEOUT: int = 3600          # 1 hour
    HITL_HIGH_RISK_THRESHOLD: float = 0.85
    FINANCE_APPROVAL_THRESHOLD: float = 5000.0  # USD — amounts above require HITL

    # ── Monitoring ──────────────────────────────────────────────────────────
    AZURE_APP_INSIGHTS_KEY: str = os.getenv("AZURE_APP_INSIGHTS_KEY", "")
    ENABLE_TELEMETRY: bool = True

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
