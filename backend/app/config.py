from pydantic import model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Required -- must be provided via environment or .env file (or built from POSTGRES_* / VALKEY_* below)
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

    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7

    cors_origins: list[str] = ["http://localhost:3000"]

    log_level: str = "info"

    # When true, log each statistics/overview API request (route, params, result count) to container stdout
    statistics_query_debug: bool = False

    skoda_base_url: str = "https://mysmob.api.connect.skoda-auto.cz"
    skoda_auth_client_id: str = "7f045eee-7003-4379-9968-9355ed2adb06@apps_vw-dilab_com"
    skoda_auth_redirect_uri: str = "myskoda://redirect/login/"
    skoda_auth_scope: str = (
        "address badge birthdate cars driversLicense dealers email "
        "mileage mbb nationalIdentifier openid phone profession profile vin"
    )
    default_parked_interval_seconds: int = 1800
    default_active_interval_seconds: int = 300
    collector_debug: bool = False

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
        if not self.database_url or not self.valkey_url:
            missing = []
            if not self.database_url:
                missing.append("database_url (or POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB)")
            if not self.valkey_url:
                missing.append("valkey_url (or VALKEY_PASSWORD)")
            raise ValueError("Settings: missing " + "; ".join(missing))
        return self


settings = Settings()
