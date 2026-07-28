import hmac

from fastapi import Header, HTTPException, status

from skill_manager.config import get_settings


def verify_shared_secret(
    x_skill_manager_secret: str = Header(default="", alias="X-Skill-Manager-Secret"),
) -> None:
    expected = get_settings().shared_secret
    if not hmac.compare_digest(x_skill_manager_secret, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Skill Manager authentication failed",
        )
