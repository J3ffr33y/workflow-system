"""Application settings, read once from the environment.

Every secret and deployment-specific value lives here; nothing else in the
codebase reads os.environ directly.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FLOW_", env_file=".env", extra="ignore")

    env: Literal["dev", "test", "prod"] = "dev"
    database_url: str = "postgresql+psycopg://flow:flow@localhost:5432/flow"

    # Business clock. "Today" for due dates and date-based automations is
    # evaluated here, never in UTC: a rule that fires "on the due date" must
    # fire on the Sydney calendar day, including across DST changes.
    business_timezone: str = "Australia/Sydney"

    session_cookie_name: str = "flow_session"
    session_ttl_hours: int = 24 * 14
    cookie_secure: bool = False  # forced True in prod by validate_for_prod()
    csrf_header_name: str = "X-CSRF-Token"

    # Initial superadmin created by `python -m app.cli bootstrap`.
    bootstrap_admin_email: str = "admin@example.com"
    bootstrap_admin_password: SecretStr = SecretStr("change-me-now")

    login_max_failures: int = 8
    login_lockout_minutes: int = 15

    # Automations: hard cap on command cascades (rule -> change -> rule ...).
    automation_max_depth: int = 3

    upload_dir: str = "./data/uploads"
    max_upload_mb: int = 25

    git_sha: str = Field(default="dev", description="Injected at build time; reported by /api/health")
    log_json: bool = False

    def validate_for_prod(self) -> None:
        if self.env != "prod":
            return
        problems = []
        if not self.cookie_secure:
            problems.append("FLOW_COOKIE_SECURE must be true in prod")
        if self.bootstrap_admin_password.get_secret_value() == "change-me-now":
            problems.append("FLOW_BOOTSTRAP_ADMIN_PASSWORD must be set in prod")
        if problems:
            raise RuntimeError("; ".join(problems))


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.validate_for_prod()
    return s
