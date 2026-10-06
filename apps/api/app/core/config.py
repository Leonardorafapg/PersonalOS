from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=Path(__file__).resolve().parents[2] / ".env", extra="ignore")

    database_url: str = "sqlite:///./personal_os.db"  # dev default; Railway injects Postgres
    # Used to sign every token. Set a long random value in production.
    jwt_secret: str = "dev-insecure-secret-change-me"
    # The single owner account is created on first boot from these two values.
    admin_email: str = "admin@example.com"
    admin_password: str = ""
    default_timezone: str = "America/Sao_Paulo"
    environment: str = "development"
    # Public base URL of this API (used in OAuth metadata). Falls back to the request URL.
    public_url: str = ""
    # Comma separated list of hosts allowed as OAuth redirect targets for MCP clients.
    oauth_allowed_redirect_hosts: str = "claude.ai,claude.com,localhost,127.0.0.1"
    cors_origins: str = ""
    session_cookie_name: str = "pos_session"

    @property
    def sqlalchemy_url(self) -> str:
        url = self.database_url
        if url.startswith("postgres://"):
            url = "postgresql+psycopg://" + url[len("postgres://"):]
        elif url.startswith("postgresql://"):
            url = "postgresql+psycopg://" + url[len("postgresql://"):]
        return url

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"

    @property
    def redirect_hosts(self) -> set[str]:
        return {h.strip().lower() for h in self.oauth_allowed_redirect_hosts.split(",") if h.strip()}


@lru_cache
def get_settings() -> Settings:
    return Settings()
