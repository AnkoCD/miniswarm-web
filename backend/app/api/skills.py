from fastapi import APIRouter, Depends, HTTPException

from app.agent.skill_manager_client import SkillManagerClient, SkillManagerError
from app.agent.skill_registry import AUTO_RULES, list_installed_skills
from app.core.config import get_settings
from app.dependencies import get_admin_user, get_current_user
from app.models import User
from app.schemas import SkillInstallRead, SkillInstallRequest, SkillRead


router = APIRouter(prefix="/skills", tags=["skills"])


@router.get("", response_model=list[SkillRead])
def list_skills(_: User = Depends(get_current_user)):
    return [
        SkillRead(
            name=item.name,
            display_name=item.display_name,
            description=item.description,
            source=item.source,
            source_ref=item.source_ref,
            supports_auto=item.name in AUTO_RULES,
        )
        for item in list_installed_skills(get_settings())
    ]


@router.post("/install", response_model=SkillInstallRead)
def install_skill(
    payload: SkillInstallRequest,
    _: User = Depends(get_admin_user),
):
    try:
        return SkillManagerClient().scan_install(payload.url)
    except SkillManagerError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
