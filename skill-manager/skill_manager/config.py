from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class SkillManagerSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SKILL_MANAGER_", extra="ignore")

    shared_secret: str = Field(min_length=32)
    skills_root: Path = Path("/skills")
    scan_timeout_seconds: int = Field(default=240, ge=30, le=600)
    max_archive_bytes: int = Field(default=52_428_800, ge=1_048_576, le=104_857_600)
    max_extracted_bytes: int = Field(default=104_857_600, ge=1_048_576, le=209_715_200)
    max_files: int = Field(default=2500, ge=10, le=10000)


@lru_cache
def get_settings() -> SkillManagerSettings:
    return SkillManagerSettings()
