from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Database ──────────────────────────────────────────────────────────────
    DATABASE_URL: str = "sqlite:///./vigilyx.db"

    # ── API server ────────────────────────────────────────────────────────────
    API_HOST: str = "127.0.0.1"
    API_PORT: int = 8000

    # ── Scheduler ─────────────────────────────────────────────────────────────
    SCHEDULER_INTERVAL_HOURS: int = 24

    # ── Anomaly detection thresholds ──────────────────────────────────────────
    MAD_THRESHOLD: float = 3.5
    ZSCORE_THRESHOLD: float = 2.5
    ROLLING_WINDOW_DAYS: int = 30

    # ── Auth ──────────────────────────────────────────────────────────────────
    SECRET_KEY: str = "changeme-use-a-long-random-string-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 8  # 8 hours

    # ── Ingestion ─────────────────────────────────────────────────────────────
    # How many days back to pull from Stripe on first-time ingestion
    INGESTION_LOOKBACK_DAYS: int = 90
    # Base currency for cross-currency aggregation
    BASE_CURRENCY: str = "usd"


settings = Settings()
