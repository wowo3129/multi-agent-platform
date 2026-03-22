"""
Multi-Agent Platform - Task Orchestrator
任务编排器 - 负责调度和协调多个 Agent
"""

import json
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Callable
from dataclasses import dataclass, field
import threading
import asyncio

from core.memory import SharedMemory, Message


@dataclass
class Task:
    """任务结构"""
    id: str
    name: str
    description: str
    status: str = "pending"  # pending, running, completed, failed
    assigned_agent: Optional[str] = None
    result: Any = None
    error: Optional[str] = None
    created_at: str = ""
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    steps: List[Dict] = field(default_factory=list)
    metadata: Dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()


@dataclass
class WorkflowStep:
    """工作流步骤"""
    agent_id: str
    action: str
    prompt_template: str
    depends_on: List[str] = field(default_factory=list)  # 依赖的步骤 ID


class TaskOrchestrator:
    """任务编排器"""

    def __init__(self, memory: SharedMemory):
        self.memory = memory
        self.tasks: Dict[str, Task] = {}
        self.workflows: Dict[str, List[WorkflowStep]] = {}
        self.lock = threading.Lock()
        self.agents: Dict[str, Any] = {}  # 注册的 Agent 实例
        self.callbacks: List[Callable] = []  # 状态变更回调

    def register_agent(self, agent_id: str, agent_instance: Any):
        """注册一个 Agent"""
        self.agents[agent_id] = agent_instance
        self.memory.update_agent_state(agent_id, {"status": "idle", "ready": True})

    def add_callback(self, callback: Callable):
        """添加状态变更回调"""
        self.callbacks.append(callback)

    async def _notify_callbacks(self, task: Task):
        """通知所有回调"""
        for cb in self.callbacks:
            try:
                if asyncio.iscoroutinefunction(cb):
                    await cb(task)
                else:
                    cb(task)
            except Exception as e:
                print(f"Callback error: {e}")

    def create_task(self, name: str, description: str, 
                   assigned_agent: Optional[str] = None,
                   metadata: Dict = None) -> Task:
        """创建新任务"""
        task = Task(
            id=f"task_{uuid.uuid4().hex[:8]}",
            name=name,
            description=description,
            assigned_agent=assigned_agent,
            metadata=metadata or {}
        )
        with self.lock:
            self.tasks[task.id] = task
        
        self.memory.add_message(
            from_agent="orchestrator",
            content=f"新任务创建: {name}",
            msg_type="system"
        )
        
        return task

    async def execute_task(self, task_id: str, context: Dict = None) -> Any:
        """执行任务"""
        task = self.tasks.get(task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")

        task.status = "running"
        task.started_at = datetime.now().isoformat()
        await self._notify_callbacks(task)

        try:
            if task.assigned_agent and task.assigned_agent in self.agents:
                # 指定 Agent 执行
                agent = self.agents[task.assigned_agent]
                self.memory.update_agent_state(task.assigned_agent, {"status": "working"})
                
                # 构建 prompt
                full_context = {
                    **self.memory.context,
                    **(context or {}),
                    "task_description": task.description,
                    "conversation_history": self.memory.get_conversation_history()
                }
                
                result = await agent.execute(task.description, full_context)
                
                task.result = result
                task.status = "completed"
                task.completed_at = datetime.now().isoformat()
                
                self.memory.save_task_result(task.id, result)
                self.memory.update_agent_state(task.assigned_agent, {"status": "idle"})
                
                self.memory.add_message(
                    from_agent=task.assigned_agent,
                    content=f"任务完成: {task.name}\n结果: {str(result)[:200]}",
                    msg_type="result"
                )
            else:
                # 没有指定 Agent，分发给所有可用 Agent
                result = await self._broadcast_task(task, context)
                task.result = result
                task.status = "completed"
                task.completed_at = datetime.now().isoformat()
                
        except Exception as e:
            task.status = "failed"
            task.error = str(e)
            task.completed_at = datetime.now().isoformat()
            await self._notify_callbacks(task)
            raise

        await self._notify_callbacks(task)
        return task.result

    async def _broadcast_task(self, task: Task, context: Dict = None) -> Dict:
        """广播任务给所有 Agent"""
        results = {}
        full_context = {
            **self.memory.context,
            **(context or {}),
            "task_description": task.description
        }
        
        for agent_id, agent in self.agents.items():
            try:
                self.memory.update_agent_state(agent_id, {"status": "working"})
                result = await agent.execute(task.description, full_context)
                results[agent_id] = result
            except Exception as e:
                results[agent_id] = {"error": str(e)}
            finally:
                self.memory.update_agent_state(agent_id, {"status": "idle"})
        
        return results

    def create_workflow(self, workflow_id: str, steps: List[WorkflowStep]):
        """创建工作流"""
        self.workflows[workflow_id] = steps

    async def execute_workflow(self, workflow_id: str, initial_input: Any = None) -> Dict:
        """执行工作流"""
        workflow = self.workflows.get(workflow_id)
        if not workflow:
            raise ValueError(f"Workflow {workflow_id} not found")

        results = {"workflow_id": workflow_id, "steps": []}
        step_results = {}

        for i, step in enumerate(workflow):
            if step.depends_on:
                for dep_id in step.depends_on:
                    if dep_id not in step_results:
                        raise ValueError(f"Dependency {dep_id} not satisfied for step {i}")

            context = {
                **self.memory.context,
                "previous_results": step_results,
                "workflow_history": results["steps"]
            }

            task = self.create_task(
                name=f"{workflow_id}_step_{i}",
                description=f"执行 {step.action}: {step.prompt_template}",
                assigned_agent=step.agent_id
            )

            try:
                result = await self.execute_task(task.id, context)
                step_results[step.agent_id] = result
                results["steps"].append({
                    "step": i,
                    "agent": step.agent_id,
                    "action": step.action,
                    "status": "completed",
                    "result": result
                })
            except Exception as e:
                results["steps"].append({
                    "step": i,
                    "agent": step.agent_id,
                    "action": step.action,
                    "status": "failed",
                    "error": str(e)
                })
                break

        return results

    def get_task_status(self, task_id: str) -> Optional[Task]:
        """获取任务状态"""
        return self.tasks.get(task_id)

    def get_all_tasks(self) -> List[Dict]:
        """获取所有任务"""
        return [
            {
                "id": t.id,
                "name": t.name,
                "status": t.status,
                "assigned_agent": t.assigned_agent,
                "created_at": t.created_at,
                "completed_at": t.completed_at
            }
            for t in self.tasks.values()
        ]

    def get_system_status(self) -> Dict:
        """获取系统状态"""
        return {
            "total_tasks": len(self.tasks),
            "pending_tasks": len([t for t in self.tasks.values() if t.status == "pending"]),
            "running_tasks": len([t for t in self.tasks.values() if t.status == "running"]),
            "completed_tasks": len([t for t in self.tasks.values() if t.status == "completed"]),
            "agents": [
                {
                    "id": agent_id,
                    **self.memory.get_agent_state(agent_id)
                }
                for agent_id in self.agents.keys()
            ],
            "memory": self.memory.to_dict()
        }
