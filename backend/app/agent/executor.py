import json
import mimetypes
import time
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agent.deepseek import DeepSeekClient, DeepSeekError, resolve_task_model
from app.agent.risk import approval_reason, yolo_auto_approvable
from app.agent.runner_client import RunnerClient, RunnerError
from app.agent.skill_manager_client import SkillManagerClient, SkillManagerError
from app.agent.skill_registry import load_task_skill_prompt
from app.agent.tools import tool_definitions_for_skills
from app.agent.web_tools import WebToolError, search_news
from app.core.config import Settings, get_settings
from app.models import (
    ApiUsage,
    AgentRun,
    Approval,
    ApprovalStatus,
    Artifact,
    NodeStatus,
    Task,
    TaskBriefVersion,
    TaskNode,
    TaskStatus,
    ToolCall,
    ToolCallStatus,
    User,
    UserRole,
)
from app.sources import capture_search_results
from app.services import add_event, request_approval, task_execution_prompt
from app.storage import task_root
from app.project_files import preview_kind


@dataclass(frozen=True)
class ExecutionOutcome:
    status: Literal["succeeded", "waiting", "failed"]
    summary: str


SYSTEM_PROMPT = """你是 MiniSwarm 的受限执行 Agent。完成分配给你的节点，不要创建子 Agent。
只能使用提供的工具；所有路径必须相对于任务根目录。输入在 input，工作文件在 workspace，协作结果在 shared，最终结果必须放在 output。
Runner 已预装 python-docx、openpyxl、python-pptx、reportlab、pypdf、Pillow 和 defusedxml。制作 Word、Excel、PPT、PDF、HTML、CSV、文本、ZIP 或图片时，先用 write_text 把脚本写到 workspace/create_output.py，再调用 run_python，script 参数必须直接填写刚才 write_text 成功返回的同一路径 workspace/create_output.py，绝不能填写 Python 代码、exec/open 表达式或绝对路径。脚本运行目录是 workspace，最终文件写到 ../output/；随后必须对每个最终文件调用 inspect_document 验证。
办公交付以原生、可继续编辑的 DOCX/XLSX/PPTX 为优先；用户要求 PDF 时再单独生成 PDF。不得用 HTML、图片或 Markdown 冒充 Office 文件。
DOCX 新建文档必须先按用途选择统一的商务样式，使用真实标题样式和真实编号，显式设置页边距、正文/标题字号、段落间距、页眉页脚；表格必须按内容设置列宽、单元格边距和重复表头，不得用表格包装普通长段落，不得用手工圆点或手工数字伪造列表。来源附录包含长 URL 时避免使用五列以上的窄表格，优先采用一条来源一段或横向页面，保证标题、机构、日期和完整可点击 URL 均可读。修改既有 DOCX 时保留原样式并做局部修改。
XLSX 必须区分输入、计算和输出区域；派生值使用可审计公式，不得在计算区硬编码结果；正确设置日期、百分比、货币和数字格式，合理列宽、冻结窗格、筛选和数据验证。公式引用中文或含空格工作表时始终写成 '工作表名'!A1，并先建立明确的参数单元格映射，避免引用错行；例如先定义 `PARAM={"base":"'参数表'!$B$3","growth":"'参数表'!$B$4"}`，再用 `f"={PARAM['base']}*(1+{PARAM['growth']})"`，绝不能使用未加引号的 `参数表!B1`，也不能把标题行或表头行误当参数。列表数据验证使用英文逗号分隔。重要汇总放在明显位置，只有能帮助判断时才制作图表。使用 openpyxl 时 chart.add_data(...) 返回 None，不得把返回值当作 Series；需要修改系列时从 chart.series[-1] 取得，优先把系列标题写入源数据表头并使用 titles_from_data=True。公式必须处理除零和缺失值。PageSetupProperties 的正确导入是 `from openpyxl.worksheet.properties import PageSetupProperties`，绝不能从 `openpyxl.worksheet.page` 导入。为每个工作表显式设置 print_area、orientation、`sheet_properties.pageSetUpPr=PageSetupProperties(fitToPage=True)`、fitToWidth=1；普通明细 fitToHeight=0，单页仪表板 fitToHeight=1，并把图表尺寸与锚点控制在打印区域内。金额/日期列必须足够宽，渲染结果中不得出现 ### 或只有图表残片的重复分页；交付前由 inspect_document 重新计算、扫描错误并逐页渲染检查。
PDF 必须逐页保持统一页边距、字号、标题层级、页码和清晰表格。中文 PDF 的首选流程是：先用 python-docx 在 workspace 创建排版完整、可编辑的 DOCX 原稿，再调用 convert_document 转换到 output 中的 PDF；不要自己反复探测字体或安装库。若确实要用 ReportLab 直接生成，中文字体必须嵌入文件，严禁使用未嵌入的 `UnicodeCIDFont("STSong-Light")`、`STSong-Light` 或仅依赖阅读器替代字体，使用 `TTFont("WQYZenHei", "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc", subfontIndex=0)` 并把正文、标题、表格和页眉页脚全部显式设置为该字体。交付前由 inspect_document 逐页渲染；文本层存在但肉眼不可见同样视为失败，不得交付空白页、异常黑页或损坏页面。
需要网络调研时优先使用 AnySearch。行业、学术、金融、法律、健康、代码等垂直领域先调用 get_sub_domains，再按返回要求检索；深度调研应先用一次 batch_search 同时提出 3 至 5 个互补问题，避免连续进行高度相似的单次搜索。用户要求 N 条来源时，实际采用并记录至少 N 个不同 URL；优先官方机构、标准组织、产品官方文档和第一方资料。关键结论不能只依赖搜索摘要，必须对至少两个主要来源调用 extract 阅读正文；至少交叉核对两个独立来源，并在交付文件中保留标题、来源机构、日期和完整可点击 URL。不得把检索结果或模型记忆当成未经标注的事实。
处理当天新闻时必须先调用 search_news，并在交付文档中保留每条新闻的来源链接和发布时间；不得依靠模型记忆编造实时信息。
除非用户明确要求“今天、当前、最新、实时”信息，否则不要调用 search_news。
重新进入节点时会提供已有工具记录。已经成功的步骤不得重复；优先复用 workspace 和 output 中已有文件继续执行。
角色为 researcher 时只负责检索、提取和把结构化证据写入 shared，不得生成最终 Office 文件；角色为 reader 时只负责读取、转换和整理 shared 笔记，不得接管最终交付。document、data_analyst 或 coder 节点负责制作文件。
当最终文件已经满足要求且 inspect_document 检查通过后，立即停止调用工具并返回可验证的完成摘要；不得为了“继续优化”反复重写已通过的文件。修复已有生成脚本时优先进行最小修改，避免无变化地整份重写。
不得请求 sudo、宿主机目录、Docker Socket、服务配置或绕过审批。
不要声称未实际创建的文件已经生成。遇到工具错误时先调整方法；完成后给出简短、可验证的结果摘要，不输出内部思考。
"""

REVIEWER_SYSTEM_PROMPT = """你是 MiniSwarm 的只读 Reviewer。必须先调用 list_files 检查 output，再对清单中的每个最终文件逐一调用 inspect_document；DOCX、XLSX 和 PDF 会执行结构与逐页渲染质检，XLSX 还会重新计算并扫描公式错误，PPTX 会检查文本越界与显著重叠。不得用 read_text 读取 DOCX、XLSX、PPTX 或 PDF 二进制文件；需要核对正文时先用 convert_to_markdown 转换到 workspace，再读取转换结果。不得猜测不存在的 Skill 脚本路径。
必须逐项核对用户要求与节点中的验收条件。不得仅根据生产 Agent 的文字摘要判定通过，也不得对目录调用 inspect_document。
检查 DOCX 时关注内容层级、真实标题/列表、表格可读性、页眉页脚、空白页和渲染结果；检查 XLSX 时关注公式是否可追溯、数字格式、冻结/筛选、汇总区、图表有效性、公式错误、### 列宽截断和图表/表格溢出的重复分页；检查 PDF 时关注每页可读性、中文字体是否实际可见、空白页、异常黑页和引用，文本层可提取但渲染页看不到文字不能通过。
若任务使用网络检索，必须核对来源数量、独立域名、发布时间和 URL，确保交付文件中能找到来源；深度调研不能只使用搜索摘要，必须有网页正文提取记录。
不得修改文件。最终只输出 JSON 对象：{"verdict":"pass|rework|fail","summary":"结论和已检查文件","instructions":"需要返工时给出具体修复要求，否则为空字符串"}。
pass 仅用于要求全部满足、所有最终文件真实存在且逐一检查通过；rework 用于可以修复的问题；fail 用于无法安全完成或缺少关键输入。不要输出内部思考。
"""


class AgentExecutor:
    def __init__(
        self,
        model_client: DeepSeekClient | None = None,
        runner_client: RunnerClient | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.model = model_client or DeepSeekClient(self.settings)
        self.runner = runner_client or RunnerClient(self.settings)
        self.skill_manager = SkillManagerClient(self.settings)

    def run_node(self, db: Session, task: Task, node: TaskNode) -> ExecutionOutcome:
        model_name = resolve_task_model(task.model_mode, node.role, self.settings)
        thinking_enabled = task.execution_mode == "deep"
        node.status = NodeStatus.RUNNING
        node.attempt += 1
        node.started_at = datetime.now(UTC)
        agent_run = AgentRun(
            task_id=task.id,
            node_id=node.id,
            attempt=node.attempt,
            role=node.role,
            model=model_name,
        )
        db.add(agent_run)
        add_event(db, task, "agent.started", f"{node.title} 已启动", content=node.role)
        db.commit()

        root = task_root(task.owner_id, task.id, self.settings)
        input_files = [p.relative_to(root).as_posix() for p in (root / "input").rglob("*") if p.is_file()]
        output_files = [
            {"path": p.relative_to(root).as_posix(), "size": p.stat().st_size}
            for p in (root / "output").rglob("*")
            if p.is_file() and not p.is_symlink()
        ]
        dependency_nodes = list(
            db.scalars(
                select(TaskNode).where(
                    TaskNode.task_id == task.id,
                    TaskNode.revision == node.revision,
                    TaskNode.node_key.in_(node.depends_on),
                )
            )
        ) if node.depends_on else []
        dependency_context = "\n".join(
            f"- {item.title}: {item.result_summary or '无结果摘要'}"
            for item in dependency_nodes
        ) or "无"
        prior_tool_context = self._prior_tool_context(db, node)
        skill_text = "\n".join(
            [task_execution_prompt(db, task), node.title, node.instructions]
        )
        skill_prompt, active_skills = load_task_skill_prompt(
            self.settings, task, skill_text, node.role
        )
        if active_skills:
            add_event(
                db,
                task,
                "skill.loaded",
                "已加载任务 Skill",
                content="、".join(active_skills),
            )
        messages: list[dict] = [
            {
                "role": "system",
                "content": (REVIEWER_SYSTEM_PROMPT if node.role == "reviewer" else SYSTEM_PROMPT)
                + skill_prompt,
            },
            {
                "role": "user",
                "content": (
                    f"用户任务与对话上下文：\n{task_execution_prompt(db, task)}\n\n"
                    f"服务器当前 UTC 日期：{datetime.now(UTC).date().isoformat()}\n"
                    f"当前节点：{node.title}\n角色：{node.role}\n"
                    f"具体要求：{node.instructions}\n"
                    f"依赖节点结果：\n{dependency_context}\n"
                    f"可用输入文件：{json.dumps(input_files, ensure_ascii=False)}\n"
                    f"当前 output 文件清单：{json.dumps(output_files, ensure_ascii=False)}\n"
                    f"自主执行模式：{'YOLO（仅自动批准任务目录内可恢复操作）' if task.autonomy_mode == 'yolo' else '安全审批'}\n"
                    f"本节点已有工具记录：\n{prior_tool_context}"
                ),
            },
        ]
        tools = tool_definitions_for_skills(
            active_skills,
            reviewer=node.role == "reviewer",
            allow_skill_install=(
                node.role != "reviewer"
                and (owner := db.get(User, task.owner_id)) is not None
                and owner.role == UserRole.ADMIN
            ),
        )
        role_tool_allowlists = {
            "researcher": {
                "anysearch",
                "search_news",
                "list_files",
                "read_text",
                "read_skill_file",
                "write_text",
            },
            "reader": {
                "anysearch",
                "list_files",
                "read_text",
                "read_skill_file",
                "write_text",
                "convert_to_markdown",
                "inspect_document",
            },
        }
        if node.role in role_tool_allowlists:
            allowed_for_role = role_tool_allowlists[node.role]
            tools = [
                item
                for item in tools
                if item["function"]["name"] in allowed_for_role
            ]
        allowed = {item["function"]["name"] for item in tools}
        failure_counts: Counter[tuple[str, str]] = Counter()
        for previous in db.scalars(
            select(ToolCall).where(
                ToolCall.node_id == node.id,
                ToolCall.status == ToolCallStatus.FAILED,
            )
        ):
            failure_counts[(previous.tool_name, previous.result_summary or "")] += 1

        for _round in range(self.settings.max_agent_rounds):
            db.refresh(task)
            db.refresh(node)
            if task.cancel_requested:
                node.status = NodeStatus.CANCELED
                self._finish_run(agent_run, "CANCELED", "任务已取消")
                db.commit()
                return ExecutionOutcome("failed", "任务已取消")
            self._apply_brief_updates(db, task, node, messages)
            try:
                result = self.model.chat(
                    model=model_name,
                    messages=messages,
                    thinking=thinking_enabled,
                    tools=tools,
                    response_format={"type": "json_object"} if node.role == "reviewer" else None,
                    max_tokens=None,
                )
            except DeepSeekError as exc:
                node.status = NodeStatus.FAILED
                node.result_summary = str(exc)
                node.completed_at = datetime.now(UTC)
                self._finish_run(agent_run, "FAILED", str(exc))
                add_event(db, task, "agent.failed", f"{node.title} 执行失败", content=str(exc))
                db.commit()
                return ExecutionOutcome("failed", str(exc))
            db.add(
                ApiUsage(
                    task_id=task.id,
                    purpose="reviewer" if node.role == "reviewer" else "worker",
                    model=model_name,
                    prompt_tokens=result.usage.prompt_tokens,
                    completion_tokens=result.usage.completion_tokens,
                    cache_hit_tokens=result.usage.cache_hit_tokens,
                    duration_ms=result.usage.duration_ms,
                )
            )
            message = {
                key: value
                for key, value in result.message.items()
                if key in {"role", "content", "tool_calls"}
            }
            message.setdefault("role", "assistant")
            tool_calls = message.get("tool_calls") or []
            content = message.get("content")
            messages.append(message)
            if not tool_calls:
                db.refresh(node)
                if self._apply_brief_updates(db, task, node, messages):
                    continue
                if not isinstance(content, str) or not content.strip():
                    node.status = NodeStatus.FAILED
                    node.result_summary = "模型未返回结果"
                    node.completed_at = datetime.now(UTC)
                    self._finish_run(agent_run, "FAILED", "模型未返回结果")
                    db.commit()
                    return ExecutionOutcome("failed", "模型未返回结果")
                if node.role == "reviewer":
                    try:
                        review = json.loads(content)
                        verdict = review["verdict"]
                        summary = str(review["summary"])
                        instructions = str(review.get("instructions") or "")
                        if verdict not in {"pass", "rework", "fail"}:
                            raise ValueError
                    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                        node.status = NodeStatus.FAILED
                        node.result_summary = "REVIEW_FAILED: Reviewer 返回格式无效"
                        node.completed_at = datetime.now(UTC)
                        self._finish_run(agent_run, "FAILED", node.result_summary)
                        add_event(db, task, "agent.failed", "Reviewer 结论无效")
                        db.commit()
                        return ExecutionOutcome("failed", node.result_summary)
                    if verdict != "pass":
                        prefix = "REWORK_REQUIRED" if verdict == "rework" else "REVIEW_FAILED"
                        detail = instructions or summary
                        node.status = NodeStatus.FAILED
                        node.result_summary = f"{prefix}: {detail}"
                        node.completed_at = datetime.now(UTC)
                        self._finish_run(agent_run, "FAILED", node.result_summary)
                        add_event(
                            db,
                            task,
                            "agent.failed",
                            "Reviewer 要求返工" if verdict == "rework" else "Reviewer 检查失败",
                            content=detail,
                        )
                        db.commit()
                        return ExecutionOutcome("failed", node.result_summary)
                    content = summary
                node.status = NodeStatus.SUCCEEDED
                node.result_summary = content[:4000]
                node.completed_at = datetime.now(UTC)
                self._finish_run(agent_run, "SUCCEEDED", content[:4000])
                add_event(db, task, "agent.completed", f"{node.title} 已完成", content=content[:1000])
                if node.role != "reviewer":
                    self._register_output_artifacts(db, task, node, root)
                db.commit()
                return ExecutionOutcome("succeeded", content[:1000])

            for raw_call in tool_calls:
                try:
                    call_id = str(raw_call["id"])
                    function = raw_call["function"]
                    tool_name = str(function["name"])
                    arguments = json.loads(function.get("arguments") or "{}")
                    if tool_name not in allowed or not isinstance(arguments, dict):
                        raise ValueError
                    if tool_name in {"read_skill_file", "copy_skill_file"}:
                        requested_skill = str(
                            arguments.get("skill_name") or "guizang-ppt-skill"
                        )
                        if requested_skill not in active_skills:
                            raise ValueError
                except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                    messages.append({"role": "tool", "tool_call_id": str(raw_call.get("id", "invalid")), "content": "工具调用格式无效"})
                    continue
                revision_node_ids = select(TaskNode.id).where(
                    TaskNode.task_id == task.id,
                    TaskNode.revision == task.current_revision,
                )
                count = db.scalar(
                    select(func.count())
                    .select_from(ToolCall)
                    .where(
                        ToolCall.task_id == task.id,
                        ToolCall.node_id.in_(revision_node_ids),
                    )
                ) or 0
                if count >= self.settings.max_tool_calls_per_task:
                    node.status = NodeStatus.FAILED
                    node.result_summary = "工具调用次数超过限制"
                    self._finish_run(agent_run, "FAILED", node.result_summary)
                    db.commit()
                    return ExecutionOutcome("failed", "工具调用次数超过限制")
                call = ToolCall(
                    task_id=task.id,
                    node_id=node.id,
                    tool_name=tool_name,
                    arguments=arguments,
                )
                db.add(call)
                db.flush()
                reason = approval_reason(tool_name, arguments, root)
                if (
                    reason
                    and task.autonomy_mode == "yolo"
                    and yolo_auto_approvable(tool_name, arguments, root)
                ):
                    approval_state = "yolo"
                    add_event(
                        db,
                        task,
                        "approval.auto_approved",
                        f"YOLO 已自动批准 {tool_name}",
                        content=reason,
                    )
                else:
                    approval_state = self._approval_state(
                        db, task.id, tool_name, arguments
                    ) if reason else "not_needed"
                if reason and approval_state == "pending":
                    call.status = ToolCallStatus.WAITING_APPROVAL
                    node.status = NodeStatus.WAITING
                    task.status = TaskStatus.WAITING_APPROVAL
                    self._finish_run(agent_run, "WAITING", reason)
                    db.commit()
                    return ExecutionOutcome("waiting", reason)
                if reason and approval_state == "new":
                    request_approval(
                        db,
                        task,
                        call,
                        operation=tool_name,
                        summary=f"{reason}：{tool_name}",
                        arguments=arguments,
                    )
                    node.status = NodeStatus.WAITING
                    self._finish_run(agent_run, "WAITING", reason)
                    db.commit()
                    return ExecutionOutcome("waiting", reason)
                if approval_state == "denied":
                    call.status = ToolCallStatus.REJECTED
                    call.result_summary = "用户拒绝此操作"
                    call.completed_at = datetime.now(UTC)
                    tool_payload = {"ok": False, "error": "用户拒绝此操作，请采用不需要该操作的方案"}
                else:
                    call.status = ToolCallStatus.RUNNING
                    add_event(db, task, "tool.started", f"正在运行 {tool_name}")
                    db.commit()
                    started = time.monotonic()
                    try:
                        if tool_name == "search_news":
                            news = search_news(
                                str(arguments.get("query") or ""),
                                int(arguments.get("limit") or 10),
                            )
                            ok = True
                            summary = f"已检索 {news['count']} 条新闻"
                            data = news
                        elif tool_name == "install_skill_from_github":
                            installed = self.skill_manager.scan_install(
                                str(arguments.get("url") or "")
                            )
                            ok = installed.installed
                            summary = (
                                f"Skill {installed.name} 已通过 SkillSpector 扫描并安装"
                            )
                            data = {
                                "name": installed.name,
                                "source": installed.source,
                                "source_ref": installed.source_ref,
                                "risk_score": installed.risk_score,
                                "risk_severity": installed.risk_severity,
                                "recommendation": installed.recommendation,
                                "finding_count": installed.finding_count,
                                "scan_mode": installed.scan_mode,
                            }
                        else:
                            runner_result = self.runner.execute(
                                user_id=task.owner_id,
                                task_id=task.id,
                                tool=tool_name,
                                arguments=arguments,
                                approval_granted=approval_state in {
                                    "approved_once",
                                    "approved_for_task",
                                    "yolo",
                                },
                            )
                            ok = runner_result.ok
                            summary = runner_result.summary
                            data = runner_result.data
                        call.status = ToolCallStatus.SUCCEEDED if ok else ToolCallStatus.FAILED
                        if ok and tool_name in {"search_news", "anysearch"} and isinstance(data, dict):
                            if (
                                tool_name == "anysearch"
                                and arguments.get("action") == "extract"
                                and arguments.get("url")
                            ):
                                data = {
                                    **data,
                                    "items": [
                                        {
                                            "url": str(arguments["url"]),
                                            "title": str(arguments["url"]),
                                            "summary": str(data.get("content") or "")[:4000],
                                        }
                                    ],
                                }
                            capture_search_results(
                                db,
                                task,
                                node_id=node.id,
                                source_type="news" if tool_name == "search_news" else "anysearch",
                                source_agent=node.role,
                                data=data,
                                parse_text_urls=(
                                    tool_name == "anysearch"
                                    and str(arguments.get("action") or "")
                                    in {"search", "batch_search"}
                                ),
                            )
                        failure_detail = ""
                        if not ok and isinstance(data, dict):
                            failure_detail = str(data.get("stderr") or data.get("stdout") or "").strip()
                        call.result_summary = (
                            f"{summary}：{failure_detail[:500]}" if failure_detail else summary
                        )
                        call.completed_at = datetime.now(UTC)
                        call.duration_ms = int((time.monotonic() - started) * 1000)
                        tool_payload = {
                            "ok": ok,
                            "summary": summary,
                            "data": data,
                        }
                        add_event(
                            db,
                            task,
                            "tool.completed" if ok else "tool.failed",
                            summary,
                            content=tool_name,
                        )
                    except (
                        RunnerError,
                        SkillManagerError,
                        WebToolError,
                        ValueError,
                        TypeError,
                    ) as exc:
                        call.status = ToolCallStatus.FAILED
                        call.result_summary = str(exc)
                        call.completed_at = datetime.now(UTC)
                        call.duration_ms = int((time.monotonic() - started) * 1000)
                        tool_payload = {"ok": False, "error": str(exc)}
                        add_event(db, task, "tool.failed", f"{tool_name} 执行失败", content=str(exc))
                    if call.status == ToolCallStatus.FAILED:
                        signature = (tool_name, call.result_summary or "")
                        failure_counts[signature] += 1
                        if failure_counts[signature] >= 2:
                            tool_payload["correction"] = self._failure_guidance(
                                tool_name, call.result_summary or ""
                            )
                        if failure_counts[signature] >= 4:
                            node.status = NodeStatus.FAILED
                            node.result_summary = f"{tool_name} 连续失败，已停止重复尝试：{call.result_summary}"
                            node.completed_at = datetime.now(UTC)
                            self._finish_run(agent_run, "FAILED", node.result_summary)
                            add_event(
                                db,
                                task,
                                "agent.failed",
                                f"{node.title} 因重复工具错误停止",
                                content=node.result_summary[:1000],
                            )
                            db.commit()
                            return ExecutionOutcome("failed", node.result_summary[:1000])
                db.commit()
                serialized = json.dumps(tool_payload, ensure_ascii=False)
                messages.append({"role": "tool", "tool_call_id": call_id, "content": serialized[:12_000]})

        node.status = NodeStatus.FAILED
        node.result_summary = "Agent 达到最大循环次数"
        node.completed_at = datetime.now(UTC)
        self._finish_run(agent_run, "FAILED", node.result_summary)
        add_event(db, task, "agent.failed", f"{node.title} 超过最大循环次数")
        db.commit()
        return ExecutionOutcome("failed", "Agent 达到最大循环次数")

    @staticmethod
    def _finish_run(agent_run: AgentRun, status: str, summary: str | None) -> None:
        agent_run.status = status
        agent_run.result_summary = summary
        agent_run.completed_at = datetime.now(UTC)

    @staticmethod
    def _apply_brief_updates(
        db: Session,
        task: Task,
        node: TaskNode,
        messages: list[dict],
    ) -> bool:
        if node.target_brief_version <= node.applied_brief_version:
            return False
        briefs = list(
            db.scalars(
                select(TaskBriefVersion)
                .where(
                    TaskBriefVersion.task_id == task.id,
                    TaskBriefVersion.version > node.applied_brief_version,
                    TaskBriefVersion.version <= node.target_brief_version,
                )
                .order_by(TaskBriefVersion.version)
            )
        )
        if not briefs:
            node.applied_brief_version = node.target_brief_version
            db.commit()
            return False
        delta = "\n".join(f"- v{brief.version}: {brief.change_summary}" for brief in briefs)
        messages.append(
            {
                "role": "user",
                "content": (
                    "Supervisor 已在安全检查点合并以下新要求。请保留仍有效的工作，"
                    "只修改受影响部分：\n" + delta
                ),
            }
        )
        node.applied_brief_version = node.target_brief_version
        add_event(
            db,
            task,
            "directive.applied",
            f"{node.title} 已接收最新要求",
            content=f"Brief v{node.applied_brief_version}",
        )
        db.commit()
        return True

    @staticmethod
    def _failure_guidance(tool_name: str, detail: str) -> str:
        if tool_name == "run_python":
            return (
                "不要传入 Python 代码或 exec/open 表达式。先用 write_text 写入 "
                "workspace/<name>.py，再把该相对路径原样作为 run_python 的 script 参数。"
            )
        if "路径" in detail or "目录" in detail:
            return "只使用 input、workspace、shared、output 下的任务相对路径；不要使用 / 或绝对路径。"
        return "不要原样重复失败调用；先检查工具参数和现有文件，再采用不同方法。"

    @staticmethod
    def _prior_tool_context(db: Session, node: TaskNode) -> str:
        calls = list(
            db.scalars(
                select(ToolCall)
                .where(ToolCall.node_id == node.id)
                .order_by(ToolCall.created_at.desc())
                .limit(30)
            )
        )
        if not calls:
            return "无"
        lines = []
        for call in reversed(calls):
            safe_arguments = {
                key: value
                for key, value in (call.arguments or {}).items()
                if key != "content"
            }
            lines.append(
                f"- {call.tool_name} {json.dumps(safe_arguments, ensure_ascii=False)[:500]} "
                f"=> {call.status.value}: {(call.result_summary or '')[:500]}"
            )
        return "\n".join(lines)

    def _approval_state(self, db: Session, task_id: str, operation: str, arguments: dict) -> str:
        approvals = list(
            db.scalars(
                select(Approval)
                .where(Approval.task_id == task_id, Approval.operation == operation)
                .order_by(Approval.requested_at.desc())
            )
        )
        for approval in approvals:
            if approval.status == ApprovalStatus.APPROVED_FOR_TASK:
                return "approved_for_task"
            if approval.arguments != arguments:
                continue
            if approval.status == ApprovalStatus.APPROVED_ONCE and approval.consumed_at is None:
                approval.consumed_at = datetime.now(UTC)
                db.flush()
                return "approved_once"
            if approval.status == ApprovalStatus.DENIED:
                return "denied"
            if approval.status == ApprovalStatus.PENDING:
                return "pending"
        return "new"

    def _register_output_artifacts(
        self, db: Session, task: Task, node: TaskNode, root: Path
    ) -> None:
        known = {
            artifact.relative_path: artifact
            for artifact in db.scalars(select(Artifact).where(Artifact.task_id == task.id))
        }
        for path in (root / "output").rglob("*"):
            if not path.is_file() or path.is_symlink():
                continue
            relative = path.relative_to(root).as_posix()
            mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            if relative in known:
                artifact = known[relative]
                artifact.node_id = node.id
                artifact.mime_type = mime_type
                artifact.size = path.stat().st_size
                artifact.is_final = True
                artifact.preview_kind = preview_kind(path.name, mime_type)
                artifact.inspection_status = "READY"
                artifact.brief_version = node.applied_brief_version
                artifact.created_at = datetime.now(UTC)
                add_event(db, task, "artifact.updated", f"已更新 {path.name}", content=relative)
                continue
            artifact = Artifact(
                task_id=task.id,
                node_id=node.id,
                filename=path.name,
                relative_path=relative,
                mime_type=mime_type,
                size=path.stat().st_size,
                is_final=True,
                preview_kind=preview_kind(path.name, mime_type),
                inspection_status="READY",
                brief_version=node.applied_brief_version,
            )
            db.add(artifact)
            add_event(db, task, "artifact.created", f"已生成 {path.name}", content=relative)
            known[relative] = artifact
