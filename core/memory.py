"""
Multi-Agent Platform - Shared Memory Module
Agent 间共享上下文和记忆库
"""

import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, asdict
import threading


@dataclass
class Message:
    """消息结构"""
    id: str
    from_agent: str
    to_agent: Optional[str]  # None 表示广播
    content: str
    type: str  # "text", "code", "result", "error"
    timestamp: str
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class SharedMemory:
    """共享记忆库 - Agent 间共享上下文"""

    def __init__(self, project_id: str = "default"):
        self.project_id = project_id
        self.lock = threading.Lock()
        
        # 存储结构
        self.messages: List[Message] = []  # 消息历史
        self.context: Dict[str, Any] = {}  # 共享上下文
        self.agent_states: Dict[str, Dict] = {}  # 各 Agent 状态
        self.shared_knowledge: Dict[str, Any] = {}  # 共享知识库
        self.task_results: Dict[str, Any] = {}  # 任务结果
        
        self.message_counter = 0

    def add_message(self, from_agent: str, content: str, 
                    to_agent: Optional[str] = None,
                    msg_type: str = "text",
                    metadata: Dict = None) -> Message:
        """添加一条消息"""
        with self.lock:
            self.message_counter += 1
            msg = Message(
                id=f"msg_{self.message_counter}",
                from_agent=from_agent,
                to_agent=to_agent,
                content=content,
                type=msg_type,
                timestamp=datetime.now().isoformat(),
                metadata=metadata or {}
            )
            self.messages.append(msg)
            return msg

    def get_messages(self, agent_id: Optional[str] = None, 
                     limit: int = 50) -> List[Message]:
        """获取消息历史"""
        with self.lock:
            msgs = self.messages
            if agent_id:
                msgs = [m for m in msgs if m.from_agent == agent_id or m.to_agent == agent_id or m.to_agent is None]
            return msgs[-limit:]

    def update_context(self, key: str, value: Any):
        """更新共享上下文"""
        with self.lock:
            self.context[key] = value

    def get_context(self, key: str, default: Any = None) -> Any:
        """获取上下文值"""
        return self.context.get(key, default)

    def update_agent_state(self, agent_id: str, state: Dict):
        """更新 Agent 状态"""
        with self.lock:
            if agent_id not in self.agent_states:
                self.agent_states[agent_id] = {}
            self.agent_states[agent_id].update(state)

    def get_agent_state(self, agent_id: str) -> Dict:
        """获取 Agent 状态"""
        return self.agent_states.get(agent_id, {})

    def add_knowledge(self, key: str, value: Any):
        """添加共享知识"""
        with self.lock:
            self.shared_knowledge[key] = value

    def get_knowledge(self, key: str, default: Any = None) -> Any:
        """获取共享知识"""
        return self.shared_knowledge.get(key, default)

    def save_task_result(self, task_id: str, result: Any):
        """保存任务结果"""
        with self.lock:
            self.task_results[task_id] = {
                "result": result,
                "timestamp": datetime.now().isoformat()
            }

    def get_task_result(self, task_id: str) -> Optional[Any]:
        """获取任务结果"""
        data = self.task_results.get(task_id)
        return data["result"] if data else None

    def get_conversation_history(self) -> str:
        """获取对话历史（格式化字符串）"""
        history = []
        for msg in self.messages[-20:]:  # 最近 20 条
            target = msg.to_agent or "所有人"
            history.append(f"[{msg.from_agent} → {target}]: {msg.content[:100]}")
        return "\n".join(history)

    def clear(self):
        """清空记忆"""
        with self.lock:
            self.messages.clear()
            self.context.clear()
            self.agent_states.clear()
            self.task_results.clear()
            self.shared_knowledge.clear()

    def to_dict(self) -> Dict:
        """导出为字典"""
        return {
            "project_id": self.project_id,
            "context": self.context,
            "agent_states": self.agent_states,
            "shared_knowledge": self.shared_knowledge,
            "message_count": len(self.messages),
            "task_count": len(self.task_results)
        }
