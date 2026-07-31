import json
import re

from pydantic import BaseModel, Field

from app.agent.deepseek import ChatResult, DeepSeekClient, DeepSeekError
from app.core.config import Settings, get_settings


class SupervisorDecision(BaseModel):
    kind: str = Field(pattern="^(chat|directive|clarify)$")
    summary: str = Field(min_length=1, max_length=2000)
    affected_node_keys: list[str] = Field(default_factory=list, max_length=12)
    requires_replan: bool = False
    reply: str = Field(default="", max_length=2000)


SYSTEM_PROMPT = """你是 MiniSwarm 的 Supervisor Agent，只负责运行中消息的分类和影响分析，不执行工具、不修改文件。
chat：询问进度、解释结果或普通讨论；directive：新增、删除、修改任务要求；clarify：要求互相冲突或缺少关键选择。
任务必须继续运行，不得要求取消正在进行的模型或工具调用。只选择真正受影响的节点；结构性目标变化才 requires_replan=true。
只输出 JSON：{"kind":"chat|directive|clarify","summary":"简洁结论","affected_node_keys":[],"requires_replan":false,"reply":"需要澄清时的问题"}。"""


class Supervisor:
    def __init__(self, client: DeepSeekClient | None = None, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self.client = client or DeepSeekClient(self.settings)

    def analyze(
        self,
        *,
        content: str,
        brief: str,
        nodes: list[dict],
        deep: bool,
    ) -> tuple[SupervisorDecision, ChatResult | None]:
        node_keys = {str(item.get("key")) for item in nodes}
        try:
            result = self.client.chat(
                model=self.settings.model_orchestrator,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": (
                            f"当前任务简报：\n{brief[:8000]}\n\n"
                            f"节点：{json.dumps(nodes, ensure_ascii=False)[:6000]}\n\n"
                            f"用户新消息：\n{content[:4000]}"
                        ),
                    },
                ],
                thinking=deep,
                response_format={"type": "json_object"},
                max_tokens=None,
            )
            decision = SupervisorDecision.model_validate_json(str(result.message.get("content") or "{}"))
            decision.affected_node_keys = [key for key in decision.affected_node_keys if key in node_keys]
            return decision, result
        except (DeepSeekError, ValueError, TypeError):
            return self._fallback(content, nodes), None

    @staticmethod
    def _fallback(content: str, nodes: list[dict]) -> SupervisorDecision:
        change = re.search(
            r"(?:修改|调整|增加|添加|删掉|删除|改成|改为|不要|必须|需要|请把|重新|补充|同时|另外|改一下|修复)",
            content,
            re.IGNORECASE,
        )
        if not change:
            return SupervisorDecision(kind="chat", summary="作为普通任务对话处理")
        keys = [str(item.get("key")) for item in nodes if item.get("role") != "reviewer"]
        return SupervisorDecision(
            kind="directive",
            summary=content.strip()[:1000],
            affected_node_keys=keys,
            requires_replan=False,
        )
