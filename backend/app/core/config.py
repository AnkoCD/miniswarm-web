from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_env: str = "development"
    app_name: str = "MiniSwarm Web"
    api_prefix: str = "/api"
    frontend_origin: str = "http://localhost:5173"
    jwt_secret: str = Field(default="development-only-change-me", min_length=16)
    jwt_expire_minutes: int = 10_080
    cookie_secure: bool = False

    database_url: str = "sqlite+pysqlite:///./miniswarm.db"
    redis_url: str = "redis://localhost:6379/0"
    data_root: Path = Path("./data")

    bootstrap_admin_username: str = "admin"
    bootstrap_admin_password: str = ""
    deepseek_api_key: str = ""
    anysearch_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    model_orchestrator: str = "deepseek-v4-pro"
    model_reviewer: str = "deepseek-v4-pro"
    model_worker: str = "deepseek-v4-flash"
    model_memory: str = "deepseek-v4-pro"
    deepseek_timeout_seconds: int = 120
    planner_max_tokens: int = 8_000
    runner_url: str = "http://runner:8100"
    runner_shared_secret: str = "development-runner-secret-change-me"
    skill_manager_url: str = "http://skill-manager:8200"
    skill_manager_shared_secret: str = "development-skill-manager-secret-change-me"
    skill_manager_timeout_seconds: int = 300
    skills_root: Path = Path("/skills")

    max_users: int = 3
    max_active_tasks: int = 3
    max_active_tasks_per_user: int = 1
    max_agents_per_task: int = 8
    max_global_agents: int = 12
    max_agent_depth: int = 1
    max_agent_rounds: int = 20
    max_review_retries: int = 2
    max_tool_calls_per_task: int = 100
    max_memories_per_user: int = 500
    max_memory_context_chars: int = 6_000
    max_skills_per_node: int = 3
    max_skill_context_chars: int = 120_000
    max_upload_mb: int = 100
    max_task_storage_mb: int = 1024
    max_project_storage_gb: int = 5
    message_checkpoint_chars: int = 600

    @field_validator("jwt_secret")
    @classmethod
    def reject_weak_production_secret(cls, value: str, info):
        app_env = info.data.get("app_env", "development")
        if app_env == "production" and len(value) < 32:
            raise ValueError("JWT_SECRET must be at least 32 characters in production")
        return value

    @model_validator(mode="after")
    def validate_production_security(self):
        if self.app_env != "production":
            return self
        if not self.cookie_secure:
            raise ValueError("COOKIE_SECURE must be true in production")
        if len(self.runner_shared_secret) < 32 or "change-me" in self.runner_shared_secret:
            raise ValueError("RUNNER_SHARED_SECRET must be a distinct random production secret")
        if (
            len(self.skill_manager_shared_secret) < 32
            or "change-me" in self.skill_manager_shared_secret
        ):
            raise ValueError(
                "SKILL_MANAGER_SHARED_SECRET must be a distinct random production secret"
            )
        if "change-me" in self.database_url or self.database_url.startswith("sqlite"):
            raise ValueError("DATABASE_URL must use a production PostgreSQL password")
        if not self.deepseek_api_key:
            raise ValueError("DEEPSEEK_API_KEY is required in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
