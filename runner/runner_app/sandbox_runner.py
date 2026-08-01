from __future__ import annotations

import argparse
import json
import os
import runpy
import sys
from pathlib import Path
from typing import Any


class SandboxViolation(PermissionError):
    pass


def _inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _path_value(raw: Any, cwd: Path) -> Path | None:
    if isinstance(raw, int) or raw is None:
        return None
    try:
        value = os.fspath(raw)
    except TypeError:
        return None
    path = Path(value)
    if not path.is_absolute():
        path = cwd / path
    return path.resolve(strict=False)


def install_audit_guard(
    *,
    task_root: Path,
    readable_roots: tuple[Path, ...],
    writable_roots: tuple[Path, ...],
    role: str = "",
    output_root: Path | None = None,
) -> None:
    task_root = task_root.resolve(strict=False)
    data_root = task_root.parents[3] if len(task_root.parents) >= 4 else task_root.parent
    cwd = Path.cwd().resolve(strict=False)
    def check_path(raw: Any, *, write: bool) -> None:
        path = _path_value(raw, cwd)
        if path is None:
            return
        if _inside(path, task_root):
            roots = writable_roots if write else readable_roots
            if not any(_inside(path, root) for root in roots):
                operation = "写入" if write else "读取"
                raise SandboxViolation(f"Python 沙箱拒绝跨 Agent {operation}：{path}")
            if (
                write
                and role == "data_analyst"
                and output_root is not None
                and _inside(path, output_root)
                and path.suffix.lower() in {".ppt", ".pptx", ".odp"}
            ):
                raise SandboxViolation(
                    "Python 沙箱拒绝角色越界：data_analyst 不得生成演示文稿交付物"
                )
            return
        if _inside(path, data_root):
            raise SandboxViolation(f"Python 沙箱拒绝访问其他任务或 Agent 数据：{path}")
        if write:
            raise SandboxViolation(f"Python 沙箱只允许写入当前 Agent 私有目录：{path}")

    def audit(event: str, args: tuple[Any, ...]) -> None:
        if event == "open" and args:
            mode = args[1] if len(args) > 1 else "r"
            write = False
            if isinstance(mode, str):
                write = any(flag in mode for flag in "wax+")
            elif isinstance(mode, int):
                write = bool(mode & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
            check_path(args[0], write=write)
        elif event in {"os.listdir", "os.scandir", "os.chdir"} and args:
            check_path(args[0], write=False)
        elif event in {"os.remove", "os.rmdir", "os.mkdir", "os.chmod", "os.chown", "os.utime", "os.truncate"} and args:
            check_path(args[0], write=True)
        elif event in {"os.rename", "os.replace", "os.link", "os.symlink"} and len(args) >= 2:
            check_path(args[0], write=True)
            check_path(args[1], write=True)
        elif event in {"subprocess.Popen", "os.system", "socket.__new__", "socket.connect"}:
            raise SandboxViolation(f"Python 沙箱禁止外部进程或网络操作：{event}")

    sys.addaudithook(audit)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task-root", required=True)
    parser.add_argument("--script")
    parser.add_argument("--pytest-target")
    parser.add_argument("--read-roots", required=True)
    parser.add_argument("--write-roots", required=True)
    parser.add_argument("--role", default="")
    parser.add_argument("--output-root", default="")
    options = parser.parse_args()

    task_root = Path(options.task_root).resolve(strict=False)
    read_roots = tuple(
        (task_root / value).resolve(strict=False)
        for value in json.loads(options.read_roots)
    )
    write_roots = tuple(
        (task_root / value).resolve(strict=False)
        for value in json.loads(options.write_roots)
    )
    install_audit_guard(
        task_root=task_root,
        readable_roots=read_roots,
        writable_roots=write_roots,
        role=options.role,
        output_root=(
            (task_root / options.output_root).resolve(strict=False)
            if options.output_root
            else None
        ),
    )

    if bool(options.script) == bool(options.pytest_target):
        parser.error("exactly one of --script or --pytest-target is required")
    if options.script:
        runpy.run_path(str(Path(options.script).resolve(strict=False)), run_name="__main__")
        return 0

    import pytest

    return int(pytest.main(["-q", str(Path(options.pytest_target).resolve(strict=False))]))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SandboxViolation as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(126)
