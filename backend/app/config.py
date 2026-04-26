from pydantic import model_validator, field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Required — must be provided via environment or .env file
    database_url: str | None = None
    valkey_url: str | None = None
    jwt_secret_key: str
    encryption_key: str

    # Optional: if database_url/valkey_url unset, built from these (same as docker-compose)
    postgres_user: str | None = None
    postgres_password: str | None = None
    postgres_db: str | None = None
    postgres_host: str = "localhost"
    valkey_password: str | None = None
    valkey_host: str = "localhost"

    # JWT — non-credential, safe to have defaults
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7

    # CORS — non-credential, safe to have defaults; override via CORS_ORIGINS env
    cors_origins: list[str] = ["http://localhost:3000"]

    log_level: str = "info"

    # When true, log each statistics/overview API request (route, params, result count) to container stdout
    statistics_query_debug: bool = False

    # Skoda OAuth — overridable via env
    skoda_base_url: str = "https://mysmob.api.connect.skoda-auto.cz"
    skoda_auth_client_id: str | None = None
    skoda_auth_redirect_uri: str | None = None
    skoda_auth_scope: str = (
        "address badge birthdate cars driversLicense dealers email "
        "mileage mbb nationalIdentifier openid phone profession profile vin"
    )

    # Polling — non-credential, safe to have defaults; override per-vehicle via API
    default_parked_interval_seconds: int = 1800
    default_active_interval_seconds: int = 300
    collector_debug: bool = False
    collect_raw_data: bool = False
    skoda_client_debug: bool = False

    # Registration mode — non-credential, safe to have default
    service_registration: str = "invite_only"  # open / invite_only

    # SMTP — overridable via env
    smtp_host: str | None = None
    smtp_port: int | None = None
    smtp_user: str | None = None
    smtp_pass: str | None = None
    smtp_from: str | None = None

    # App — overridable via env
    app_base_url: str | None = None

    # Try parent dir so pytest/uvicorn run from backend/ still find iVDrive/.env
    model_config = {"env_file": (".env", "../.env"), "env_file_encoding": "utf-8", "extra": "ignore"}

    @model_validator(mode="after")
    def build_urls_from_components(self) -> "Settings":
        if not self.database_url and all((self.postgres_user, self.postgres_password, self.postgres_db)):
            self.database_url = (
                f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
                f"@{self.postgres_host}:5432/{self.postgres_db}"
            )
        if not self.valkey_url and self.valkey_password:
            self.valkey_url = f"valkey://:{self.valkey_password}@{self.valkey_host}:6379/0"
        return self

    @model_validator(mode="after")
    def validate_required(self) -> "Settings":
        """Validate all required configuration on startup. Fail fast with clear messages."""
        missing: list[str] = []

        # Core secrets
        if not self.jwt_secret_key:
            missing.append("JWT_SECRET_KEY")
        if not self.encryption_key:
            missing.append("ENCRYPTION_KEY")

        # Database & cache
        if not self.database_url:
            missing.append("DATABASE_URL (or POSTGRES_USER + POSTGRES_PASSWORD + POSTGRES_DB)")
        if not self.valkey_url:
            missing.append("VALKEY_URL (or VALKEY_PASSWORD)")

        # Skoda OAuth — required for collector to function
        # Only enforce if COLLECTOR_ENABLED is set to true (default behavior unchanged for existing deployments)
        import os as _os
        collector_enabled = _os.environ.get("COLLECTOR_ENABLED", "true").lower() in ("true", "1", "yes")
        if collector_enabled:
            if not self.skoda_auth_client_id:
                missing.append("SKODA_AUTH_CLIENT_ID")
            if not self.skoda_auth_redirect_uri:
                missing.append("SKODA_AUTH_REDIRECT_URI")

        # SMTP — optional; warn if partially configured
        smtp_fields = {
            "SMTP_HOST": self.smtp_host,
            "SMTP_PORT": self.smtp_port,
            "SMTP_USER": self.smtp_user,
            "SMTP_PASS": self.smtp_pass,
            "SMTP_FROM": self.smtp_from,
        }
        smtp_provided = [k for k, v in smtp_fields.items() if v is not None and v != ""]
        if smtp_provided and len(smtp_provided) < len(smtp_fields):
            smtp_missing = [k for k, v in smtp_fields.items() if v is None or v == ""]
            missing.append(f"SMTP partially configured — missing: {', '.join(smtp_missing)}")

        if missing:
            lines = [
                "",
                "=" * 60,
                "iVDrive startup error — missing required configuration:",
                "",
                *[f"  • {m}" for m in missing],
                "",
                "Set these as environment variables or in your .env file.",
                "=" * 60,
                "",
            ]
            raise ValueError("\n".join(lines))

        return self


settings = Settings()
