from pydantic_settings import BaseSettings, SettingsConfigDict

_WEAK_SECRET = "changeme-use-a-long-random-string-in-production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # -- Environment -----------------------------------------------------------
    # Set to "production" to enable strict security checks at startup.
    ENVIRONMENT: str = "development"

    # -- Database --------------------------------------------------------------
    DATABASE_URL: str = "sqlite:///./vigilyx.db"

    # -- API server ------------------------------------------------------------
    API_HOST: str = "127.0.0.1"
    API_PORT: int = 8000

    # -- CORS ------------------------------------------------------------------
    # Comma-separated list of allowed origins.
    # Example: ALLOWED_ORIGINS=https://app.vigilyx.com
    ALLOWED_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"

    # -- Scheduler -------------------------------------------------------------
    SCHEDULER_INTERVAL_HOURS: int = 24

    # -- Anomaly detection thresholds ------------------------------------------
    MAD_THRESHOLD: float = 3.5
    ZSCORE_THRESHOLD: float = 2.5
    ROLLING_WINDOW_DAYS: int = 30

    # -- Auth ------------------------------------------------------------------
    # Generate: python -c "import secrets; print(secrets.token_hex(32))"
    SECRET_KEY: str = _WEAK_SECRET
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 8  # 8 hours

    # -- Encryption ------------------------------------------------------------
    # Generate: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    FERNET_KEY: str = ""

    # -- Ingestion -------------------------------------------------------------
    INGESTION_LOOKBACK_DAYS: int = 90
    BASE_CURRENCY: str = "usd"

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]


settings = Settings()
