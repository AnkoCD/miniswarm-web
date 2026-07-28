from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


ToolName = Literal[
    "list_files",
    "read_text",
    "read_skill_file",
    "copy_skill_file",
    "validate_swiss_deck",
    "anysearch",
    "convert_document",
    "convert_to_markdown",
    "write_text",
    "copy_file",
    "move_file",
    "move_to_trash",
    "create_directory",
    "create_zip",
    "run_python",
    "run_tests",
    "inspect_document",
]


class ToolRequest(BaseModel):
    request_id: UUID
    user_id: UUID
    task_id: UUID
    tool: ToolName
    arguments: dict[str, Any] = Field(default_factory=dict)
    approval_granted: bool = False


class ToolResponse(BaseModel):
    ok: bool
    summary: str
    data: dict[str, Any] = Field(default_factory=dict)
