from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class RunnerSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="RUNNER_", extra="ignore")

    data_root: Path = Path("/data")
    skills_root: Path = Path("/skills")
    shared_secret: str = Field(min_length=32)
    max_timeout_seconds: int = Field(default=300, ge=1, le=900)
    max_output_bytes: int = Field(default=65_536, ge=1024, le=1_048_576)
    max_text_bytes: int = Field(default=2_097_152, ge=1024, le=20_971_520)
    office_visual_qa_required: bool = False
    office_visual_max_pages: int = Field(default=60, ge=1, le=200)
    max_office_bytes: int = Field(default=104_857_600, ge=1_048_576, le=524_288_000)
    concurrency: int = Field(default=2, ge=1, le=16)


@lru_cache
def get_settings() -> RunnerSettings:
    return RunnerSettings()
