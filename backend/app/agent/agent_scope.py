from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any


class AgentScopeError(ValueError):
    """A tool attempted to cross the current Agent's context boundary."""


ROLE_BLOCKED_OUTPUT_SUFFIXES: dict[str, frozenset[str]] = {
    # Data agents may prepare JSON/CSV/XLSX and chart assets, while presentation
    # production belongs to the downstream document/coder node.
    "data_analyst": frozenset({".ppt", ".pptx", ".odp"}),
}


def _normalize_path(raw: Any) -> str:
    if not isinstance(raw, str) or not raw.strip():
        raise AgentScopeError("路径不能为空")
    value = raw.strip()
    if "\\" in value:
        raise AgentScopeError("路径必须使用正斜杠")
    pure = PurePosixPath(value)
    if pure.is_absolute() or ".." in pure.parts:
        raise AgentScopeError("路径不能是绝对路径，也不能包含 ..")
    normalized = pure.as_posix()
    if normalized in {"", "."}:
        raise AgentScopeError("请明确指定 input、当前 Agent 的 workspace/shared/output 路径")
    return normalized.removeprefix("./")


def _within(path: str, root: str) -> bool:
    root = root.rstrip("/")
    return path == root or path.startswith(root + "/")


@dataclass(frozen=True)
class AgentPathScope:
    node_key: str
    role: str
    workspace: str
    shared: str
    output: str
    readable_roots: tuple[str, ...]
    writable_roots: tuple[str, ...]

    @property
    def reviewer(self) -> bool:
        return self.role == "reviewer"

    def can_read(self, path: str) -> bool:
        return any(_within(path, root) for root in self.readable_roots)

    def can_write(self, path: str) -> bool:
        return any(_within(path, root) for root in self.writable_roots)

    def require_read(self, raw: Any, *, label: str = "路径") -> str:
        path = _normalize_path(raw)
        if not self.can_read(path):
            raise AgentScopeError(
                f"{label}超出当前 Agent 可读范围：{path}。"
                f"允许读取：{'、'.join(self.readable_roots)}"
            )
        return path

    def require_write(self, raw: Any, *, label: str = "路径") -> str:
        path = _normalize_path(raw)
        if not self.can_write(path):
            raise AgentScopeError(
                f"{label}超出当前 Agent 可写范围：{path}。"
                f"允许写入：{'、'.join(self.writable_roots)}"
            )
        blocked = ROLE_BLOCKED_OUTPUT_SUFFIXES.get(self.role, frozenset())
        if _within(path, self.output) and PurePosixPath(path).suffix.lower() in blocked:
            raise AgentScopeError(
                f"{label}违反角色边界：{self.role} 不得生成演示文稿交付物；"
                "请把结构化分析写入 shared，由 document 节点制作 PPT。"
            )
        return path

    def guidance(self) -> str:
        return (
            f"当前 Agent 私有工作目录为 {self.workspace}，私有协作目录为 {self.shared}，"
            f"私有输出目录为 {self.output}。只能读取 input、自己目录以及明确依赖节点的 shared/output；"
            "不得读取或修改其他并行 Agent 的 workspace。"
        )

    def to_payload(self) -> dict[str, Any]:
        """Serialize the signed scope sent to Runner for defense in depth."""

        return {
            "node_key": self.node_key,
            "role": self.role,
            "workspace": self.workspace,
            "shared": self.shared,
            "output": self.output,
            "readable_roots": list(self.readable_roots),
            "writable_roots": list(self.writable_roots),
        }


def build_agent_scope(
    *,
    node_key: str,
    role: str,
    dependency_keys: list[str],
    worker_count: int,
) -> AgentPathScope:
    isolated = worker_count > 1 or role == "reviewer"
    if not isolated:
        return AgentPathScope(
            node_key=node_key,
            role=role,
            workspace="workspace",
            shared="shared",
            output="output",
            readable_roots=("input", "workspace", "shared", "output"),
            writable_roots=("workspace", "shared", "output"),
        )

    workspace = f"workspace/agents/{node_key}"
    shared = f"shared/agents/{node_key}"
    output = f"output/{node_key}"
    if role == "reviewer":
        return AgentPathScope(
            node_key=node_key,
            role=role,
            workspace=workspace,
            shared=shared,
            output=output,
            readable_roots=("input", workspace, "shared/agents", "output"),
            # Reviewer may only create temporary Markdown/PDF representations in
            # its own private workspace. It cannot alter shared or final output.
            writable_roots=(workspace,),
        )

    dependencies: list[str] = []
    for key in dependency_keys:
        dependencies.extend((f"shared/agents/{key}", f"output/{key}"))
    return AgentPathScope(
        node_key=node_key,
        role=role,
        workspace=workspace,
        shared=shared,
        output=output,
        readable_roots=("input", workspace, shared, output, *dependencies),
        writable_roots=(workspace, shared, output),
    )


def enforce_tool_scope(
    tool_name: str,
    arguments: dict[str, Any],
    scope: AgentPathScope,
) -> dict[str, Any]:
    """Return normalized arguments after enforcing node-local path boundaries."""

    result = dict(arguments)

    read_path_tools = {
        "read_text",
        "inspect_document",
        "validate_swiss_deck",
    }
    write_path_tools = {
        "write_text",
        "create_directory",
        "move_to_trash",
    }

    if tool_name == "list_files":
        result["path"] = scope.require_read(
            result.get("path") or scope.workspace,
            label="列目录路径",
        )
    elif tool_name in read_path_tools:
        result["path"] = scope.require_read(result.get("path"), label="读取路径")
    elif tool_name in write_path_tools:
        result["path"] = scope.require_write(result.get("path"), label="写入路径")
    elif tool_name == "copy_skill_file":
        result["target"] = scope.require_write(result.get("target"), label="目标路径")
    elif tool_name == "convert_document":
        result["source"] = scope.require_read(result.get("source"), label="转换来源")
        result["target"] = scope.require_write(result.get("target"), label="转换目标")
    elif tool_name == "convert_to_markdown":
        result["source"] = scope.require_read(result.get("source"), label="转换来源")
        result["target"] = scope.require_write(result.get("target"), label="转换目标")
    elif tool_name == "copy_file":
        result["source"] = scope.require_read(result.get("source"), label="复制来源")
        result["target"] = scope.require_write(result.get("target"), label="复制目标")
    elif tool_name == "move_file":
        # Moving is a mutation of both source and target; dependencies are read-only.
        result["source"] = scope.require_write(result.get("source"), label="移动来源")
        result["target"] = scope.require_write(result.get("target"), label="移动目标")
    elif tool_name == "create_zip":
        sources = result.get("sources")
        if not isinstance(sources, list) or not sources:
            raise AgentScopeError("压缩来源必须是非空路径列表")
        result["sources"] = [
            scope.require_read(item, label="压缩来源") for item in sources
        ]
        result["target"] = scope.require_write(result.get("target"), label="压缩目标")
    elif tool_name == "run_python":
        script = scope.require_read(result.get("script"), label="Python 脚本")
        if not _within(script, scope.workspace):
            raise AgentScopeError("Python 脚本必须位于当前 Agent 私有 workspace")
        result["script"] = script
    elif tool_name == "run_tests":
        target = scope.require_read(result.get("path") or scope.workspace, label="测试路径")
        if not _within(target, scope.workspace):
            raise AgentScopeError("测试只能在当前 Agent 私有 workspace 内运行")
        result["path"] = target
    elif tool_name not in {
        "read_skill_file",
        "install_skill_from_github",
        "anysearch",
        "search_news",
    } and any(key in result for key in {"path", "source", "target", "script", "sources"}):
        raise AgentScopeError(f"未声明的路径型工具不能绕过 Agent 隔离：{tool_name}")

    return result
