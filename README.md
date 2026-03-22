# 🤖 Multi-Agent 代码协作平台

> 多 Agent 协作编排系统，支持角色定义、任务分发、实时协作、结果输出

## 📁 项目结构

```
multi-agent-platform/
├── README.md              # 项目说明
├── requirements.txt      # Python 依赖
├── app.py                 # FastAPI 主程序
├── config/
│   └── agents.json        # Agent 角色配置
├── agents/
│   ├── __init__.py
│   ├── base.py            # Agent 基类
│   ├── engineer.py        # 代码工程师 Agent
│   ├── reviewer.py        # 代码审查员 Agent
│   └── tester.py          # 测试工程师 Agent
├── core/
│   ├── __init__.py
│   ├── orchestrator.py    # 任务编排器
│   ├── memory.py           # 共享记忆库
│   └── message_bus.py      # 消息总线
├── web/
│   ├── index.html         # Web 界面
│   └── app.js             # 前端交互逻辑
└── output/                # 输出目录
```

## 🚀 快速启动

```bash
pip install fastapi uvicorn langchain openai python-multipart
python app.py
```

然后打开浏览器访问：`http://localhost:8000`

## 🎯 核心功能

- [x] Agent 角色系统（可扩展）
- [x] 任务创建和分发
- [x] Agent 协作流程编排
- [x] Web 可视化界面
- [x] 实时消息流
- [ ] 代码输出和导出
- [ ] 协作历史记录
