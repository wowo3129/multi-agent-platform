"""
Multi-Agent Platform - Base Agent
Agent 基类 - 所有 Agent 的父类
支持智谱AI GLM-4 模型 (HTTP API)
"""

import json
import asyncio
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from dataclasses import dataclass
from pathlib import Path
import httpx


@dataclass
class AgentConfig:
    """Agent 配置"""
    id: str
    name: str
    role: str
    description: str
    prompt: str
    icon: str = "🤖"
    capabilities: List[str] = None

    def __post_init__(self):
        if self.capabilities is None:
            self.capabilities = []


class ZhipuLLM:
    """智谱AI LLM 封装 (HTTP API)"""

    def __init__(self, api_key: str, model: str = "glm-4", temperature: float = 0.7, max_tokens: int = 2048):
        self.api_key = api_key
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.base_url = "https://open.bigmodel.cn/api/paas/v4"

    async def agenerate(self, messages: List[Dict], system_prompt: str = None) -> str:
        """异步调用智谱AI API"""
        formatted_messages = []

        if system_prompt:
            formatted_messages.append({"role": "system", "content": system_prompt})

        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", str(msg))
            formatted_messages.append({"role": role, "content": content})

        payload = {
            "model": self.model,
            "messages": formatted_messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    json=payload,
                    headers=headers,
                )
                response.raise_for_status()
                result = response.json()
                return result["choices"][0]["message"]["content"]
        except httpx.HTTPStatusError as e:
            return f"❌ API 调用失败 (HTTP {e.response.status_code}): {e.response.text}"
        except Exception as e:
            return f"❌ API 调用错误: {str(e)}"


class BaseAgent(ABC):
    """Agent 基类"""

    def __init__(self, config: AgentConfig):
        self.config = config
        self.id = config.id
        self.name = config.name
        self.role = config.role
        self.description = config.description
        self.prompt = config.prompt
        self.icon = config.icon
        self.capabilities = config.capabilities
        self.conversation_history: List[Dict] = []
        self.working_memory: Dict[str, Any] = {}

    @abstractmethod
    async def think(self, task: str, context: Dict) -> str:
        """Agent 的核心思考逻辑"""
        pass

    async def execute(self, task: str, context: Dict = None) -> Any:
        """执行任务"""
        context = context or {}
        full_context = {
            "agent_name": self.name,
            "agent_role": self.role,
            "agent_prompt": self.prompt,
            "conversation_history": self.conversation_history,
            **context
        }
        response = await self.think(task, full_context)
        self.conversation_history.append({
            "task": task,
            "response": response,
            "context_keys": list(context.keys())
        })
        return response

    def has_capability(self, capability: str) -> bool:
        return capability in self.capabilities

    def get_history(self, limit: int = 10) -> List[Dict]:
        return self.conversation_history[-limit:]

    def clear_history(self):
        self.conversation_history.clear()

    def __repr__(self):
        return f"<Agent {self.id}: {self.name} ({self.role})>"


# 全局 LLM 实例（延迟加载）
_llm_instance = None

def get_llm() -> Optional[ZhipuLLM]:
    """获取 LLM 实例"""
    global _llm_instance
    if _llm_instance is not None:
        return _llm_instance

    config_path = Path(__file__).parent.parent / "config" / "llm_config.json"
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
        if config.get("api_key"):
            _llm_instance = ZhipuLLM(
                api_key=config["api_key"],
                model=config.get("model", "glm-4"),
                temperature=config.get("temperature", 0.7),
                max_tokens=config.get("max_tokens", 2048)
            )
            print(f"[OK] LLM initialized: model={config.get('model', 'glm-4')}")
            return _llm_instance
    print("[WARN] LLM config not found, using simulation mode")
    return None


class LLMAgent(BaseAgent):
    """基于 LLM 的 Agent"""

    def __init__(self, config: AgentConfig, llm: ZhipuLLM = None):
        super().__init__(config)
        self.llm = llm

    async def think(self, task: str, context: Dict) -> str:
        system_prompt = f"""你是一个 {self.role}，名叫 {self.name}。

{self.prompt}

你的能力包括：{', '.join(self.capabilities)}

请根据你的角色和能力，完成任务。提供详细、专业、有见地的回答。
用中文回复。"""

        # 尝试使用真实 LLM
        llm = self.llm or get_llm()
        if llm:
            messages = [{"role": "user", "content": task}]
            try:
                response = await llm.agenerate(messages, system_prompt)
                return response
            except Exception as e:
                return f"❌ LLM 调用失败: {str(e)}"

        # 回退到模拟响应
        return await self._simulate_response(task, context)

    async def _simulate_response(self, task: str, context: Dict) -> str:
        """模拟响应 - 当没有真实 LLM 时使用"""
        await asyncio.sleep(0.5)

        responses = {
            "Engineer": f"""💻 **{self.name}** 执行中...

**任务分析：** {task}

**代码实现思路：**
1. 理解需求：{task}
2. 技术选型：Python + 最佳实践
3. 代码结构：模块化、可维护

**实现方案：**
```python
# {task}
def solution():
    # TODO: 实现具体逻辑
    pass
```

**完成情况：** ✅ 已实现核心功能
""",
            "Reviewer": f"""🔍 **{self.name}** 审查中...

**代码审查：**
- 整体架构：✅ 良好
- 代码规范：✅ 符合 PEP8
- 安全检查：⚠️ 建议添加输入验证
- 性能考虑：✅ 无明显问题

**改进建议：**
1. 添加异常处理
2. 增加日志记录
3. 补充文档注释

**审查结论：** ✅ 通过
""",
            "Tester": f"""🧪 **{self.name}** 测试中...

**测试计划：**
- 单元测试覆盖率目标：80%+
- 边界条件测试：✅ 已覆盖
- 异常情况测试：✅ 已覆盖

**测试用例：**
```python
def test_正常情况():
    assert solution(1) == 1

def test_边界情况():
    assert solution(0) == 0

def test_异常情况():
    with pytest.raises(ValueError):
        solution(-1)
```

**测试结论：** ✅ 所有测试通过
""",
            "Architect": f"""🏗️ **{self.name}** 架构设计中...

**系统架构：**
```
┌─────────────┐
│   前端层    │
├─────────────┤
│   API 网关  │
├─────────────┤
│  业务逻辑层 │
├─────────────┤
│   数据层   │
└─────────────┘
```

**技术选型：**
- 后端：FastAPI / Django
- 数据库：PostgreSQL + Redis
- 缓存：Redis
- 消息队列：RabbitMQ

**设计原则：**
1. 高内聚低耦合
2. 可扩展性强
3. 易于维护
"""
        }

        return responses.get(self.role, f"🤖 {self.name} 已收到任务：{task}")
