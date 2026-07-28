from dataclasses import dataclass
from typing import Any

import httpx

from app.core.config import Settings, get_settings


class SkillManagerError(RuntimeError):
    pass


@dataclass(frozen=True)
class SkillInstallResult:
    name: str
    source: str
    source_ref: str
    risk_score: int
    risk_severity: str
    recommendation: str
    finding_count: int
    scan_mode: str
    installed: bool

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "SkillInstallResult":
        return cls(
            name=str(payload["name"]),
            source=str(payload["source"]),
            source_ref=str(payload["source_ref"]),
            risk_score=int(payload["risk_score"]),
            risk_severity=str(payload["risk_severity"]),
            recommendation=str(payload["recommendation"]),
            finding_count=int(payload["finding_count"]),
            scan_mode=str(payload["scan_mode"]),
            installed=bool(payload["installed"]),
        )


class SkillManagerClient:
    def __init__(
        self,
        settings: Settings | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self._transport = transport

    def scan_install(self, url: str) -> SkillInstallResult:
        try:
            with httpx.Client(
                base_url=self.settings.skill_manager_url.rstrip("/"),
                timeout=self.settings.skill_manager_timeout_seconds,
                transport=self._transport,
            ) as client:
                response = client.post(
                    "/v1/skills/scan-install",
                    json={"url": url},
                    headers={"X-Skill-Manager-Secret": self.settings.skill_manager_shared_secret},
                )
            if response.status_code == 422:
                detail = response.json().get("detail", "SkillSpector 扫描或安装未通过")
                raise SkillManagerError(str(detail))
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise ValueError
            return SkillInstallResult.from_payload(payload)
        except SkillManagerError:
            raise
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            raise SkillManagerError("Skill Manager 服务不可用或响应无效") from exc
