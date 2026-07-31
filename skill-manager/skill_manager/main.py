from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field

from skill_manager.config import get_settings
from skill_manager.installer import SkillInstallError, remove_skill, scan_and_install
from skill_manager.security import verify_shared_secret


class InstallRequest(BaseModel):
    url: str = Field(min_length=19, max_length=2048)


app = FastAPI(title="MiniSwarm Skill Manager", docs_url=None, redoc_url=None, openapi_url=None)


@app.get("/health")
def health():
    return {"status": "ok", "scanner": "NVIDIA/SkillSpector", "version": "2.4.4"}


@app.post("/v1/skills/scan-install", dependencies=[Depends(verify_shared_secret)])
def install_skill(payload: InstallRequest):
    try:
        return scan_and_install(payload.url, get_settings())
    except SkillInstallError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.delete("/v1/skills/{name}", dependencies=[Depends(verify_shared_secret)])
def delete_skill(name: str):
    try:
        return remove_skill(name, get_settings())
    except SkillInstallError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
