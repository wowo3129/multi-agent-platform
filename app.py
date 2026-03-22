"""
Multi-Agent Platform - Main Application
FastAPI 后端服务
"""

import json
import os
import asyncio
from pathlib import Path
from typing import Optional
from datetime import datetime

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from core.memory import SharedMemory
from core.orchestrator import TaskOrchestrator, WorkflowStep
from agents.base import BaseAgent, LLMAgent, AgentConfig


# ============ 初始化 ============

app = FastAPI(title="🤖 Multi-Agent 协作平台", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

memory = SharedMemory("multi-agent-platform")
orchestrator = TaskOrchestrator(memory)


class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except:
                pass

manager = ConnectionManager()


def load_agents():
    """从配置文件加载 Agent"""
    config_path = Path(__file__).parent / "config" / "agents.json"
    if not config_path.exists():
        return []
    
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    
    agents = []
    for agent_config in config.get("agents", []):
        config_obj = AgentConfig(**agent_config)
        agent = LLMAgent(config_obj)
        agents.append(agent)
        orchestrator.register_agent(agent.id, agent)
    
    return agents

AGENTS = load_agents()


# ============ API Models ============

class TaskCreate(BaseModel):
    name: str
    description: str
    assigned_agent: Optional[str] = None

class ChatMessage(BaseModel):
    message: str
    agent_id: Optional[str] = None


# ============ API Routes ============

@app.get("/")
async def root():
    """返回 Web 界面"""
    html_path = Path(__file__).parent / "web" / "index.html"
    return HTMLResponse(content=open(html_path, "r", encoding="utf-8").read())

@app.get("/api/status")
async def get_status():
    return orchestrator.get_system_status()

@app.get("/api/agents")
async def list_agents():
    return [
        {
            "id": agent.id,
            "name": agent.name,
            "role": agent.role,
            "description": agent.description,
            "icon": agent.icon,
            "capabilities": agent.capabilities,
            "state": memory.get_agent_state(agent.id)
        }
        for agent in AGENTS
    ]

@app.get("/api/tasks")
async def list_tasks():
    return orchestrator.get_all_tasks()

@app.post("/api/tasks")
async def create_task(task: TaskCreate):
    task_obj = orchestrator.create_task(
        name=task.name,
        description=task.description,
        assigned_agent=task.assigned_agent
    )
    asyncio.create_task(execute_and_broadcast(task_obj.id))
    return {"task_id": task_obj.id, "status": "created"}

async def execute_and_broadcast(task_id: str):
    try:
        result = await orchestrator.execute_task(task_id)
        await manager.broadcast({
            "type": "task_complete",
            "task_id": task_id,
            "result": result
        })
    except Exception as e:
        await manager.broadcast({
            "type": "task_error",
            "task_id": task_id,
            "error": str(e)
        })

@app.get("/api/tasks/{task_id}")
async def get_task(task_id: str):
    task = orchestrator.get_task_status(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return {
        "id": task.id,
        "name": task.name,
        "description": task.description,
        "status": task.status,
        "assigned_agent": task.assigned_agent,
        "result": task.result,
        "error": task.error,
        "created_at": task.created_at,
        "completed_at": task.completed_at
    }

@app.get("/api/memory")
async def get_memory():
    return {
        "messages": [
            {
                "id": m.id,
                "from": m.from_agent,
                "to": m.to_agent,
                "content": m.content,
                "type": m.type,
                "timestamp": m.timestamp
            }
            for m in memory.get_messages(limit=50)
        ],
        "context": memory.context
    }

@app.post("/api/memory/context")
async def update_context(key: str, value: str):
    try:
        val = json.loads(value)
    except:
        val = value
    memory.update_context(key, val)
    return {"success": True}

@app.delete("/api/memory")
async def clear_memory():
    memory.clear()
    return {"success": True}

@app.post("/api/chat")
async def chat(message: ChatMessage):
    if message.agent_id:
        agent = next((a for a in AGENTS if a.id == message.agent_id), None)
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")
        result = await agent.execute(message.message, {"mode": "chat"})
    else:
        results = {}
        for agent in AGENTS:
            try:
                result = await agent.execute(message.message, {"mode": "chat"})
                results[agent.id] = result
            except Exception as e:
                results[agent.id] = f"Error: {str(e)}"
        result = results
    return {"response": result}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                if msg.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
            except:
                pass
    except WebSocketDisconnect:
        manager.disconnect(websocket)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8088)
