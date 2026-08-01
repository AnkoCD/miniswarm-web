import json
import re
from collections import deque
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.agent.deepseek import ChatResult, DeepSeekClient, DeepSeekError
from app.agent.deliverables import detect_multi_deliverable_request
from app.core.config import Settings, get_settings


AgentRole = Literal[
    "researcher", "reader", "data_analyst", "coder", "document", "file_worker", "reviewer"
]


class PlanNode(BaseModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,47}$")
    role: AgentRole
    title: str = Field(min_length=2, max_length=120)
    instructions: str = Field(min_length=3, max_length=4000)
    depends_on: list[str] = Field(default_factory=list, max_length=8)
    weight: int = Field(ge=1, le=100)


class TaskPlan(BaseModel):
    mode: Literal["single", "swarm"]
    goal: str = Field(min_length=3, max_length=1000)
    acceptance_criteria: list[str] = Field(default_factory=list, max_length=12)
    nodes: list[PlanNode] = Field(min_length=2, max_length=13)

    @model_validator(mode="after")
    def validate_graph(self):
        keys = [node.id for node in self.nodes]
        if len(keys) != len(set(keys)):
            raise ValueError("node ids must be unique")
        known = set(keys)
        if any(dep not in known for node in self.nodes for dep in node.depends_on):
            raise ValueError("node dependency does not exist")
        if any(node.id in node.depends_on for node in self.nodes):
            raise ValueError("node cannot depend on itself")
        indegree = {key: 0 for key in keys}
        outgoing = {key: [] for key in keys}
        for node in self.nodes:
            for dep in node.depends_on:
                indegree[node.id] += 1
                outgoing[dep].append(node.id)
        queue = deque(key for key, degree in indegree.items() if degree == 0)
        visited = 0
        while queue:
            key = queue.popleft()
            visited += 1
            for target in outgoing[key]:
                indegree[target] -= 1
                if indegree[target] == 0:
                    queue.append(target)
        if visited != len(keys):
            raise ValueError("plan graph contains a cycle")
        reviewers = [node for node in self.nodes if node.role == "reviewer"]
        if len(reviewers) != 1 or self.nodes[-1].role != "reviewer":
            raise ValueError("plan requires exactly one final reviewer")
        reviewer = reviewers[0]
        worker_keys = {node.id for node in self.nodes if node.role != "reviewer"}
        worker_dependencies = {
            dep for node in self.nodes if node.role != "reviewer" for dep in node.depends_on
        }
        terminal_workers = worker_keys - worker_dependencies
        if not terminal_workers.issubset(set(reviewer.depends_on)):
            raise ValueError("reviewer must depend on every terminal worker")
        if any(reviewer.id in node.depends_on for node in self.nodes if node.role != "reviewer"):
            raise ValueError("worker cannot depend on reviewer")
        worker_count = sum(node.role != "reviewer" for node in self.nodes)
        if self.mode == "single" and worker_count < 1:
            raise ValueError("single mode requires at least one worker node")
        if self.mode == "swarm" and worker_count < 2:
            raise ValueError("swarm mode requires at least two worker nodes")
        return self


SYSTEM_PROMPT = """你是 MiniSwarm 的任务规划器。只输出一个 JSON 对象，不要输出 Markdown。
你要选择 single 或 swarm。只有至少两个真正独立、不会同时写同一文件的子任务才选择 swarm。
用户明确要求 N 套、N 份、N 个版本等多个独立交付物时，必须选择 swarm，并按交付物数量创建 N 个并列生产节点；例如“三套不同试卷”应创建 3 个 document 节点，而不是让一个节点循环生成三套。共享资料整理、统一规范或调研可以作为这些生产节点共同依赖的前置节点。
每个并行生产节点必须负责且只负责一个交付物，并在 instructions 中指定互不冲突的 output/<node_id>/ 输出目录；最终 reviewer 同时依赖所有生产节点，并检查数量、差异性和每个文件。
章节、步骤、阶段、页面、模块等同一作品的连续组成部分不要仅因数量而拆成多个独立交付 Agent。
子 Agent 不能再创建 Agent。最后一个节点必须是 reviewer，且依赖所有最终产出节点。
最多创建 12 个工作 Agent，另加 1 个 reviewer；简单任务仍只创建 1 个工作 Agent。
必须输出 acceptance_criteria，列出 2 到 8 条可客观验证的验收条件；包含用户明确要求的文件格式、数量、语言、来源和质量要求。
允许的角色：researcher, reader, data_analyst, coder, document, file_worker, reviewer。
办公任务优先使用 document、data_analyst、reader 和 researcher；除非确实需要软件项目或自动化脚本，不要为 Word、Excel、PPT、PDF 任务创建 coder 节点。
用户要求报告、方案、合同、通知、纪要、简历、说明书或手册但未指定格式时，默认规划真实 DOCX；用户要求预算表、清单、台账、统计表、数据报表或跟踪表但未指定格式时，默认规划真实 XLSX。明确只要聊天答复时不要创建文件。
DOCX、XLSX、PPTX、PDF 的 acceptance_criteria 必须包含：真实目标格式、内容完整性、可打开性，以及相应的渲染/公式/布局质检。Excel 任务还要写明公式可审计和零公式错误；Word/PDF 要写明逐页无空白、裁切或异常字体。
需要联网调研时，把检索和文档制作拆成有依赖关系的节点；researcher 必须记录可追溯来源，深度调研至少交叉核对两个独立来源并提取主要网页正文，document 节点必须把来源标题、机构、日期和 URL 写入交付文件。
涉及当天新闻时，researcher 可以使用 search_news 获取带来源链接和发布时间的实时结果；不得凭空编造新闻。
只有用户明确要求今天、当前、最新或实时信息时才规划 search_news；历史文化、常识和普通文档任务不要联网。
涉及 PPT、幻灯片、slides 或 deck 时，优先分配 document 或 coder 节点，并在节点要求中明确使用已安装的 guizang-ppt-skill；用户明确要求 PPTX 时必须生成真实 .pptx 文件。
不要把内部推理写进 JSON。指令必须具体、可验证，不得要求 sudo、宿主机访问或绕过审批。
示例 JSON：
{"mode":"single","goal":"生成文本摘要","acceptance_criteria":["摘要覆盖全部输入文件","最终文件非空且可打开"],"nodes":[{"id":"work","role":"reader","title":"整理内容","instructions":"读取输入并生成摘要","depends_on":[],"weight":80},{"id":"review","role":"reviewer","title":"检查结果","instructions":"只读检查摘要是否完整","depends_on":["work"],"weight":20}]}
"""


class Planner:
    def __init__(self, client: DeepSeekClient | None = None, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self.client = client or DeepSeekClient(self.settings)

    def create_plan(
        self,
        prompt: str,
        *,
        deep: bool = False,
        model: str | None = None,
    ) -> tuple[TaskPlan, ChatResult]:
        result = self.client.chat(
            model=model or self.settings.model_orchestrator,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"用户任务：\n{prompt}\n\n请输出符合示例结构的 json。"},
            ],
            thinking=deep,
            response_format={"type": "json_object"},
            max_tokens=self.settings.planner_max_tokens,
        )
        content = result.message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise DeepSeekError("规划器返回了空内容")
        try:
            plan = TaskPlan.model_validate(json.loads(content))
        except (json.JSONDecodeError, ValueError) as exc:
            raise DeepSeekError("规划器返回的计划不符合约定") from exc
        self._normalize_office_roles(prompt, plan)
        self._expand_multi_deliverables(prompt, plan)
        # Mutations above intentionally rewrite the model-produced DAG. Re-run
        # Pydantic validation so the same graph invariants still apply.
        try:
            plan = TaskPlan.model_validate(plan.model_dump())
        except ValueError as exc:
            raise DeepSeekError("多交付物拆分后的计划不符合约定") from exc
        worker_count = sum(node.role != "reviewer" for node in plan.nodes)
        if worker_count > self.settings.max_agents_per_task:
            raise DeepSeekError("规划器创建的 Agent 数量超过系统限制")
        if plan.nodes[-1].role != "reviewer":
            raise DeepSeekError("计划必须以 Reviewer 节点结束")
        return plan, result

    @staticmethod
    def _expand_multi_deliverables(prompt: str, plan: TaskPlan) -> None:
        request = detect_multi_deliverable_request(prompt)
        if request is None:
            return

        workers = [node for node in plan.nodes if node.role != "reviewer"]
        reviewer = plan.nodes[-1]

        # The model already produced enough parallel terminal deliverables.
        producer_roles = {"document", "data_analyst", "coder", "file_worker"}
        terminal_producers = [
            node
            for node in workers
            if node.role in producer_roles
            and not any(node.id in other.depends_on for other in workers)
        ]
        if plan.mode == "swarm" and len(terminal_producers) >= request.count:
            return

        noun = request.noun.lower()
        candidates = [
            node
            for node in workers
            if node.role in producer_roles
            and noun in f"{node.title} {node.instructions}".lower()
        ]
        if not candidates and len(terminal_producers) == 1:
            candidates = terminal_producers
        if not candidates and len(workers) == 1:
            candidates = workers
        if len(candidates) != 1:
            # Ambiguous plans are left untouched rather than risking a broken DAG.
            return
        producer = candidates[0]

        # Only split a terminal producer. Downstream worker aggregation should be
        # planned explicitly by the model instead of being guessed here.
        if any(producer.id in node.depends_on for node in workers if node.id != producer.id):
            return
        if producer.id not in reviewer.depends_on:
            return
        new_reviewer_dep_count = len(reviewer.depends_on) - 1 + request.count
        if new_reviewer_dep_count > 8:
            return
        if len(workers) - 1 + request.count > 12:
            return

        existing_ids = {node.id for node in plan.nodes}
        base = re.sub(r"_+", "_", producer.id)[:38].rstrip("_") or "deliverable"
        copies: list[PlanNode] = []
        per_node_weight = max(1, producer.weight // request.count)
        for index in range(1, request.count + 1):
            candidate_id = f"{base}_{index}"
            suffix = 1
            while candidate_id in existing_ids:
                suffix += 1
                candidate_id = f"{base[:34]}_{index}_{suffix}"
            existing_ids.add(candidate_id)
            isolated_output = f"output/{candidate_id}/"
            isolated_workspace = f"workspace/agents/{candidate_id}/"
            copies.append(
                PlanNode(
                    id=candidate_id,
                    role=producer.role,
                    title=f"{producer.title[:104]}（第 {index} 份）",
                    instructions=(
                        f"{producer.instructions}\n\n"
                        f"你只负责第 {index}/{request.count} 份独立的{request.noun}。"
                        "必须与其他版本在内容、题目、结构或表达上形成可辨识差异，"
                        "不得复制同一份内容后仅修改标题。"
                        f"工作脚本和中间文件仅写入 {isolated_workspace}；"
                        f"最终文件仅写入 {isolated_output}，不得修改其他并行节点目录。"
                    )[:4000],
                    depends_on=list(producer.depends_on),
                    weight=per_node_weight,
                )
            )

        rewritten: list[PlanNode] = []
        for node in plan.nodes:
            if node.id == producer.id:
                rewritten.extend(copies)
            elif node.role == "reviewer":
                dependencies: list[str] = []
                for dependency in node.depends_on:
                    if dependency == producer.id:
                        dependencies.extend(copy.id for copy in copies)
                    else:
                        dependencies.append(dependency)
                node.depends_on = dependencies
                node.instructions = (
                    f"{node.instructions}\n\n"
                    f"必须确认共有 {request.count} 份独立{request.noun}，逐份调用检查工具，"
                    "并检查各版本不是简单改名或轻微改写。"
                )[:4000]
                rewritten.append(node)
            else:
                rewritten.append(node)
        plan.nodes = rewritten
        plan.mode = "swarm"

        additions = [
            f"最终交付物数量必须为 {request.count} 份",
            f"{request.count} 份{request.noun}必须具有实质差异，且分别存放在独立输出目录",
        ]
        plan.acceptance_criteria = list(
            dict.fromkeys([*plan.acceptance_criteria, *additions])
        )[:12]

    @staticmethod
    def _normalize_office_roles(prompt: str, plan: TaskPlan) -> None:
        explicit_code = bool(
            re.search(
                r"(?i)(python|javascript|typescript|代码|脚本|程序|软件|api|开发项目)",
                prompt,
            )
        )
        if explicit_code:
            return
        if re.search(r"(?i)(\.xlsx\b|\bexcel\b|工作簿|电子表格|预算表|台账)", prompt):
            preferred_role: AgentRole = "data_analyst"
        elif re.search(r"(?i)(\.docx\b|\bword\b|\.pdf\b|报告|合同|通知|纪要|手册|试卷|卷子)", prompt):
            preferred_role = "document"
        else:
            return
        for node in plan.nodes:
            if node.role == "coder":
                node.role = preferred_role
