from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
import re
from typing import Any

from runner_app.schemas import ToolRequest


class RunnerScopeError(ValueError):
    """The signed Agent scope is invalid or a request crosses its boundary."""


ROLE_BLOCKED_OUTPUT_SUFFIXES: dict[str, frozenset[str]] = {
    "data_analyst": frozenset({".ppt", ".pptx", ".odp"}),
}


def _normalize(raw: Any) -> str:
    if not isinstance(raw, str) or not raw.strip():
        raise RunnerScopeError("路径不能为空")
    value = raw.strip()
    if "\\" in value:
        raise RunnerScopeError("路径必须使用正斜杠")
    pure = PurePosixPath(value)
    if pure.is_absolute() or ".." in pure.parts:
        raise RunnerScopeError("路径不能是绝对路径，也不能包含 ..")
    normalized = pure.as_posix().removeprefix("./")
    if normalized in {"", "."}:
        raise RunnerScopeError("路径必须明确位于 Agent 允许目录")
    return normalized


def _within(path: str, root: str) -> bool:
    root = root.rstrip("/")
    return path == root or path.startswith(root + "/")


@dataclass(frozen=True)
class SignedAgentScope:
    node_key: str
    role: str
    workspace: str
    output: str
    readable_roots: tuple[str, ...]
    writable_roots: tuple[str, ...]

    def require_read(self, raw: Any) -> str:
        path = _normalize(raw)
        if not any(_within(path, root) for root in self.readable_roots):
            raise RunnerScopeError(f"Runner 拒绝跨 Agent 读取：{path}")
        return path

    def require_write(self, raw: Any) -> str:
        path = _normalize(raw)
        if not any(_within(path, root) for root in self.writable_roots):
            raise RunnerScopeError(f"Runner 拒绝跨 Agent 写入：{path}")
        blocked = ROLE_BLOCKED_OUTPUT_SUFFIXES.get(self.role, frozenset())
        if _within(path, self.output) and PurePosixPath(path).suffix.lower() in blocked:
            raise RunnerScopeError(
                f"Runner 拒绝角色越界：{self.role} 不得生成演示文稿交付物"
            )
        return path


def _scope_from_request(request: ToolRequest) -> SignedAgentScope | None:
    raw = request.agent_scope
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise RunnerScopeError("Agent scope 格式无效")
    node_key = str(raw.get("node_key") or "")
    if not re.fullmatch(r"[a-z][a-z0-9_]{0,47}", node_key):
        raise RunnerScopeError("Agent scope 节点标识无效")
    role = str(raw.get("role") or "")
    if role not in {
        "researcher", "reader", "data_analyst", "coder", "document",
        "file_worker", "reviewer",
    }:
        raise RunnerScopeError("Agent scope 角色无效")
    workspace = _normalize(raw.get("workspace"))
    output = _normalize(raw.get("output"))
    readable = raw.get("readable_roots")
    writable = raw.get("writable_roots")
    if not isinstance(readable, list) or not readable:
        raise RunnerScopeError("Agent scope 缺少可读目录")
    if not isinstance(writable, list) or not writable:
        raise RunnerScopeError("Agent scope 缺少可写目录")
    readable_roots = tuple(dict.fromkeys(_normalize(item) for item in readable))
    writable_roots = tuple(dict.fromkeys(_normalize(item) for item in writable))
    if workspace not in readable_roots or workspace not in writable_roots:
        raise RunnerScopeError("Agent 私有 workspace 未包含在读写范围")
    if any(root.split("/", 1)[0] not in {"input", "workspace", "shared", "output"} for root in readable_roots + writable_roots):
        raise RunnerScopeError("Agent scope 包含非法顶层目录")
    return SignedAgentScope(
        node_key=node_key,
        role=role,
        workspace=workspace,
        output=output,
        readable_roots=readable_roots,
        writable_roots=writable_roots,
    )


def enforce_request_scope(request: ToolRequest) -> tuple[dict[str, Any], SignedAgentScope | None]:
    """Re-check all task paths inside Runner, independent of backend checks."""

    scope = _scope_from_request(request)
    args = dict(request.arguments)
    if scope is None:
        return args, None

    if request.tool == "list_files":
        args["path"] = scope.require_read(args.get("path") or scope.workspace)
    elif request.tool in {"read_text", "inspect_document", "validate_swiss_deck"}:
        args["path"] = scope.require_read(args.get("path"))
    elif request.tool in {"write_text", "create_directory", "move_to_trash"}:
        args["path"] = scope.require_write(args.get("path"))
    elif request.tool == "copy_skill_file":
        args["target"] = scope.require_write(args.get("target"))
    elif request.tool in {"convert_document", "convert_to_markdown", "copy_file"}:
        args["source"] = scope.require_read(args.get("source"))
        args["target"] = scope.require_write(args.get("target"))
    elif request.tool == "move_file":
        args["source"] = scope.require_write(args.get("source"))
        args["target"] = scope.require_write(args.get("target"))
    elif request.tool == "create_zip":
        sources = args.get("sources")
        if not isinstance(sources, list) or not sources:
            raise RunnerScopeError("压缩来源必须是非空路径列表")
        args["sources"] = [scope.require_read(item) for item in sources]
        args["target"] = scope.require_write(args.get("target"))
    elif request.tool == "run_python":
        script = scope.require_read(args.get("script"))
        if not _within(script, scope.workspace):
            raise RunnerScopeError("Python 脚本必须位于当前 Agent 私有 workspace")
        args["script"] = script
    elif request.tool == "run_tests":
        path = scope.require_read(args.get("path") or scope.workspace)
        if not _within(path, scope.workspace):
            raise RunnerScopeError("测试只能在当前 Agent 私有 workspace 中运行")
        args["path"] = path
    elif request.tool not in {
        "read_skill_file",
        "anysearch",
    } and any(key in args for key in {"path", "source", "target", "script", "sources"}):
        raise RunnerScopeError(f"Runner 不允许未声明的路径型工具绕过隔离：{request.tool}")
    return args, scope
