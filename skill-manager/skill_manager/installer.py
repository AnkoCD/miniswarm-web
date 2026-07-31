from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import uuid
import zipfile
from datetime import datetime, timezone
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse

import httpx

from skill_manager.config import SkillManagerSettings


SKILL_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
GITHUB_PART_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")


class SkillInstallError(RuntimeError):
    pass


@dataclass(frozen=True)
class GitHubTarget:
    owner: str
    repo: str
    ref: str | None
    subpath: str


def parse_github_url(raw: str) -> GitHubTarget:
    parsed = urlparse(raw.strip())
    if parsed.scheme != "https" or parsed.hostname not in {"github.com", "www.github.com"}:
        raise SkillInstallError("仅支持 https://github.com 上的公开 Skill 仓库")
    if parsed.username or parsed.password or parsed.port or parsed.query or parsed.fragment:
        raise SkillInstallError("GitHub 地址不能包含凭据、端口、查询参数或片段")
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 2 or not all(GITHUB_PART_RE.fullmatch(part) for part in parts[:2]):
        raise SkillInstallError("GitHub 仓库地址格式无效")
    owner, repo = parts[0], parts[1].removesuffix(".git")
    ref = None
    subpath = ""
    if len(parts) > 2:
        if len(parts) < 4 or parts[2] != "tree":
            raise SkillInstallError("子目录必须使用 GitHub 的 /tree/<ref>/<path> 地址")
        ref = parts[3]
        subpath = "/".join(parts[4:])
    if any(part in {"", ".", ".."} for part in PurePosixPath(subpath).parts):
        raise SkillInstallError("Skill 子目录无效")
    return GitHubTarget(owner=owner, repo=repo, ref=ref, subpath=subpath)


def _github_json(client: httpx.Client, path: str) -> dict:
    response = client.get(
        f"https://api.github.com{path}",
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "MiniSwarm-SkillManager/1.0",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    if response.status_code == 404:
        raise SkillInstallError("GitHub 仓库、提交或路径不存在")
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise SkillInstallError("GitHub 返回了无效响应")
    return payload


def resolve_commit(client: httpx.Client, target: GitHubTarget) -> tuple[str, str]:
    repo = _github_json(client, f"/repos/{target.owner}/{target.repo}")
    if bool(repo.get("private")):
        raise SkillInstallError("当前仅支持公开 GitHub 仓库")
    ref = target.ref or str(repo.get("default_branch") or "")
    if not ref or not GITHUB_PART_RE.fullmatch(ref):
        raise SkillInstallError("仓库默认分支无效；请提供固定 tree 地址")
    commit = _github_json(client, f"/repos/{target.owner}/{target.repo}/commits/{ref}")
    sha = str(commit.get("sha") or "").lower()
    if not COMMIT_RE.fullmatch(sha):
        raise SkillInstallError("无法锁定 GitHub 提交")
    return sha, str(repo.get("html_url") or f"https://github.com/{target.owner}/{target.repo}")


def _download_archive(
    client: httpx.Client,
    target: GitHubTarget,
    commit: str,
    destination: Path,
    max_bytes: int,
) -> None:
    url = f"https://codeload.github.com/{target.owner}/{target.repo}/zip/{commit}"
    with client.stream("GET", url, headers={"User-Agent": "MiniSwarm-SkillManager/1.0"}) as response:
        response.raise_for_status()
        total = 0
        with destination.open("xb") as output:
            for chunk in response.iter_bytes(1024 * 1024):
                total += len(chunk)
                if total > max_bytes:
                    raise SkillInstallError("仓库压缩包超过安全大小限制")
                output.write(chunk)
    if total == 0:
        raise SkillInstallError("GitHub 返回了空压缩包")


def _extract_archive(
    archive: Path,
    destination: Path,
    *,
    max_files: int,
    max_bytes: int,
) -> Path:
    try:
        with zipfile.ZipFile(archive) as bundle:
            members = bundle.infolist()
            if not members or len(members) > max_files:
                raise SkillInstallError("仓库文件数量超过安全限制")
            total = 0
            roots: set[str] = set()
            for member in members:
                path = PurePosixPath(member.filename)
                if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
                    raise SkillInstallError("仓库包含不安全路径")
                roots.add(path.parts[0])
                mode = (member.external_attr >> 16) & 0o170000
                if mode in {0o120000, 0o060000, 0o020000, 0o010000}:
                    raise SkillInstallError("仓库包含符号链接或特殊设备文件")
                total += member.file_size
                if total > max_bytes:
                    raise SkillInstallError("仓库解压后超过安全大小限制")
            if len(roots) != 1:
                raise SkillInstallError("GitHub 压缩包目录结构异常")
            bundle.extractall(destination)
    except (zipfile.BadZipFile, OSError) as exc:
        raise SkillInstallError("GitHub 压缩包损坏或无法读取") from exc
    return destination / next(iter(roots))


def _find_skill_root(repo_root: Path, subpath: str) -> Path:
    if subpath:
        candidate = (repo_root / PurePosixPath(subpath)).resolve(strict=False)
        try:
            candidate.relative_to(repo_root.resolve())
        except ValueError as exc:
            raise SkillInstallError("Skill 路径越界") from exc
        if not (candidate / "SKILL.md").is_file():
            raise SkillInstallError("指定目录没有 SKILL.md")
        return candidate
    if (repo_root / "SKILL.md").is_file():
        return repo_root
    candidates = [path.parent for path in repo_root.rglob("SKILL.md")]
    if len(candidates) != 1:
        raise SkillInstallError("仓库包含零个或多个 Skill；请提供精确的 /tree/<ref>/<path> 地址")
    return candidates[0]


def _skill_name(skill_root: Path) -> str:
    skill_file = skill_root / "SKILL.md"
    if skill_file.stat().st_size > 512_000:
        raise SkillInstallError("SKILL.md 超过 512KB")
    try:
        head = skill_file.read_text(encoding="utf-8")[:32_000]
    except UnicodeDecodeError as exc:
        raise SkillInstallError("SKILL.md 必须是 UTF-8 文本") from exc
    match = re.search(r"(?m)^name:\s*[\"']?([a-z0-9][a-z0-9-]{0,63})[\"']?\s*$", head)
    if not match or not SKILL_NAME_RE.fullmatch(match.group(1)):
        raise SkillInstallError("SKILL.md 缺少有效的 name 字段")
    return match.group(1)


def _run_scan(skill_root: Path, report_path: Path, timeout: int) -> dict:
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": str(report_path.parent),
        "PYTHONIOENCODING": "utf-8",
        "NO_COLOR": "1",
    }
    try:
        completed = subprocess.run(
            [
                "skillspector",
                "scan",
                str(skill_root),
                "--no-llm",
                "--format",
                "json",
                "--output",
                str(report_path),
            ],
            env=env,
            cwd=report_path.parent,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        raise SkillInstallError("SkillSpector 不可用或扫描超时") from exc
    if not report_path.is_file():
        detail = (completed.stderr or completed.stdout)[-1000:]
        raise SkillInstallError(f"SkillSpector 未生成报告：{detail}")
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SkillInstallError("SkillSpector 报告无法解析") from exc
    if not isinstance(report, dict):
        raise SkillInstallError("SkillSpector 报告格式无效")
    return report


def _scan_verdict(report: dict) -> tuple[int, str, str, int]:
    risk = report.get("risk_assessment") or {}
    score = int(risk.get("score", 100))
    severity = str(risk.get("severity") or "UNKNOWN").upper()
    recommendation = str(risk.get("recommendation") or "BLOCK").upper()
    issues = report.get("issues") if isinstance(report.get("issues"), list) else []
    severe = sum(
        1
        for issue in issues
        if isinstance(issue, dict)
        and str(issue.get("severity") or "").upper() in {"HIGH", "CRITICAL"}
    )
    if score > 50 or severity in {"HIGH", "CRITICAL"} or severe or recommendation in {"BLOCK", "DANGEROUS"}:
        raise SkillInstallError(
            f"SkillSpector 扫描未通过：风险 {score}/100，等级 {severity}，高危发现 {severe}"
        )
    return score, severity, recommendation, len(issues)


def _manifest_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def scan_and_install(url: str, settings: SkillManagerSettings) -> dict:
    target = parse_github_url(url)
    settings.skills_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="miniswarm-skill-scan-") as temporary:
        work = Path(temporary)
        archive = work / "source.zip"
        with httpx.Client(timeout=httpx.Timeout(60, read=180), follow_redirects=False) as client:
            commit, source = resolve_commit(client, target)
            _download_archive(client, target, commit, archive, settings.max_archive_bytes)
        repo_root = _extract_archive(
            archive,
            work / "repo",
            max_files=settings.max_files,
            max_bytes=settings.max_extracted_bytes,
        )
        candidate = _find_skill_root(repo_root, target.subpath)
        name = _skill_name(candidate)
        destination = settings.skills_root / name
        if destination.exists():
            raise SkillInstallError(f"Skill {name} 已存在，系统不会自动覆盖")
        report_path = work / "skillspector-report.json"
        report = _run_scan(candidate, report_path, settings.scan_timeout_seconds)
        score, severity, recommendation, finding_count = _scan_verdict(report)
        content_hash = _manifest_hash(candidate)
        staging = settings.skills_root / f".installing-{name}-{uuid.uuid4().hex}"
        try:
            shutil.copytree(candidate, staging)
            metadata = {
                "source": source,
                "requested_url": url,
                "ref": commit,
                "scanner": "NVIDIA/SkillSpector",
                "scanner_version": "2.4.4",
                "scanner_ref": "fd25398d7aa99353d86237b9c260759351f0e644",
                "scan_mode": "static-only",
                "risk_score": score,
                "risk_severity": severity,
                "risk_recommendation": recommendation,
                "finding_count": finding_count,
                "content_manifest_sha256": content_hash,
            }
            (staging / ".miniswarm-source.json").write_text(
                json.dumps(metadata, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            staging.rename(destination)
        finally:
            if staging.exists():
                shutil.rmtree(staging)
        return {
            "name": name,
            "source": source,
            "source_ref": commit,
            "risk_score": score,
            "risk_severity": severity,
            "recommendation": recommendation,
            "finding_count": finding_count,
            "scan_mode": "static-only",
            "installed": True,
        }


def remove_skill(name: str, settings: SkillManagerSettings) -> dict:
    if not SKILL_NAME_RE.fullmatch(name):
        raise SkillInstallError("Skill 名称无效")

    skills_root = settings.skills_root.resolve(strict=False)
    raw_destination = skills_root / name
    if raw_destination.is_symlink():
        raise SkillInstallError(f"Skill {name} 目录无效")
    destination = raw_destination.resolve(strict=False)
    if destination.parent != skills_root:
        raise SkillInstallError("Skill 路径越界")
    if destination.is_symlink() or not destination.is_dir():
        raise SkillInstallError(f"Skill {name} 不存在")
    if not (destination / "SKILL.md").is_file():
        raise SkillInstallError(f"Skill {name} 目录无效")

    trash_root = skills_root / ".trash"
    if trash_root.exists() and (trash_root.is_symlink() or not trash_root.is_dir()):
        raise SkillInstallError("Skill 回收区无效")
    trash_root.mkdir(parents=True, exist_ok=True)

    removed_at = datetime.now(timezone.utc)
    trash_id = f"{name}-{removed_at.strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
    trash_destination = trash_root / trash_id
    destination.rename(trash_destination)
    return {
        "name": name,
        "removed": True,
        "recoverable": True,
        "trash_id": trash_id,
        "removed_at": removed_at,
    }
