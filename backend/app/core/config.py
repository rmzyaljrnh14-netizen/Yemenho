"""Application configuration.

Secrets come from the environment. In development, a local default is used so the
project runs out of the box; production must set YHQ_JWT_SECRET explicitly.
"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="YHQ_", env_file=".env", extra="ignore")

    app_name: str = "النظام الوطني لإدارة مؤشرات الأداء الصحي والجودة وسلامة المرضى"
    environment: str = "development"

    database_url: str = "postgresql+psycopg://yhq_app:yhq_app_dev_pw@127.0.0.1:5432/yhq"
    # Admin connection used only by migrations/seed. It is a superuser and therefore
    # bypasses RLS — the running application must never use it.
    admin_database_url: str = "postgresql+psycopg://yhq:yhq_dev_pw@127.0.0.1:5432/yhq"
    app_db_role: str = "yhq_app"
    app_db_password: str = "yhq_app_dev_pw"

    # Auth
    jwt_secret: str = "dev-only-change-me"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 60
    refresh_token_days: int = 14
    max_failed_logins: int = 5
    lockout_minutes: int = 15

    # CORS (comma-separated origins). Includes the Vite dev/preview ports and the
    # Tauri desktop webview origins (Linux uses tauri://, Windows uses http://tauri.localhost).
    cors_origins: str = (
        "http://localhost:5173,http://127.0.0.1:5173,"
        "http://localhost:4173,http://127.0.0.1:4173,"
        "http://localhost:5174,http://127.0.0.1:5174,"
        "http://localhost:4174,http://127.0.0.1:4174,"
        "tauri://localhost,http://tauri.localhost,https://tauri.localhost"
    )

    # Assistant (v0.8). The analytical core always works; the optional language
    # model only rewrites already-computed findings into prose. It is off unless
    # an operator turns it on and supplies a key. No key is ever committed.
    ai_enabled: bool = False
    ai_base_url: str = "https://api.openai.com/v1"
    ai_model: str = ""
    ai_api_key: str = ""
    ai_timeout_seconds: float = 20.0

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
