import threading

from fastapi import Depends, FastAPI, HTTPException, status

from runner_app.config import get_settings
from runner_app.schemas import ToolRequest, ToolResponse
from runner_app.security import verify_runner_signature
from runner_app.tools import ToolRejected, execute

app = FastAPI(title="MiniSwarm Runner", docs_url=None, redoc_url=None, openapi_url=None)
runner_slots = threading.BoundedSemaphore(get_settings().concurrency)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/v1/tools/execute", response_model=ToolResponse, dependencies=[Depends(verify_runner_signature)])
def execute_tool(payload: ToolRequest):
    try:
        with runner_slots:
            return execute(payload)
    except ToolRejected as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
