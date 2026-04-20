# FuFuAgent

> 陪伴型 AI Agent 核心库 —— 状态感知、性格演化、多轮对话，零框架依赖。

[![Python](https://img.shields.io/badge/python-3.10%2B-blue?style=flat-square)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green?style=flat-square)](LICENSE)
[![Status](https://img.shields.io/badge/status-alpha-orange?style=flat-square)]()

---

## 它是什么

FuFuAgent 是一个**纯 Python 陪伴型 Agent 核心库**。

它不依赖任何 Web 框架（无 FastAPI / WebSocket），可以被 Mac app、FastAPI 服务、CLI 工具或任意 Python 脚本直接嵌入使用。

**核心能力：**

- **6 态状态机** — 感知"人"的存在，在 `IDLE → PASSERBY → COMPANION / DEEP_NIGHT → FOCUS → LEAVING → IDLE` 之间自动流转
- **性格演化引擎** — 每次相处之后，性格参数会随对话内容悄悄偏移
- **多级上下文（L0～L3）** — 从实时状态到灵魂底色，分层组装 Prompt
- **对话整理（Digest）** — 定期把聊天记录提炼成关系快照和用户事实
- **多云 LLM 适配** — 支持 SiliconFlow / DeepSeek / OpenAI，无缝切换
- **离线语料兜底** — 没有 API Key 时自动降级到内置语料，始终能说话

---

## 状态机一览

```
         ┌─────────┐
    ┌───►│  IDLE   │◄───────────────────────────────┐
    │    └────┬────┘                                 │
    │         │ person_arrive                        │ (延时自动)
    │    ┌────▼──────┐                               │
    │    │ PASSERBY  │──────────────────►────────────┘
    │    └────┬──────┘  person_leave      IDLE
    │         │ person_sit
    │    ┌────▼──────┐   start_focus   ┌───────────┐
    │    │ COMPANION │────────────────►│   FOCUS   │
    │    └────┬──────┘                 └─────┬─────┘
    │         │ (深夜)                        │ stop_focus
    │    ┌────▼──────┐                       │
    │    │ DEEP_NIGHT│◄──────────────────────┘
    │    └────┬──────┘
    │         │ person_leave
    │    ┌────▼──────┐
    └────│  LEAVING  │
         └───────────┘
```

每次状态变化时，Agent 会自动生成一句陪伴短语，并通过 `EventBus` 广播出去。

---

## 快速上手

### 安装

```bash
git clone https://github.com/Remaker-A/FuFuAgent.git
cd FuFuAgent
python -m venv .venv
# macOS / Linux
source .venv/bin/activate
# Windows
.venv\Scripts\activate

pip install -e .
cp .env.example .env   # 填入你的 LLM API Key
```

### 最简示例

```python
import asyncio
from fufu_agent import BiasType, CompanionAgent, SoulCreateRequest

async def main():
    async with CompanionAgent() as agent:
        # 监听状态变化
        agent.on("state_change", lambda d: print("[状态]", d["to"], "→", d.get("say_line", "")))

        # 初始化灵魂（首次运行）
        agent.create_soul(SoulCreateRequest(
            current_state_word="迷茫",
            struggle="要不要换工作",
            bias=BiasType.ADVENTUROUS,
        ))

        # 模拟传感器事件
        await agent.person_sit()

        # 多轮对话
        reply = await agent.chat("今天好累，什么都不想做")
        print("[FuFu]", reply)

        # 手动触发一次关系整理
        await agent.run_digest(manual=True)

asyncio.run(main())
```

运行 `examples/quickstart.py` 可以看到完整演示。

---

## 项目结构

```
FuFuAgent/
├── fufu_agent/
│   ├── agent.py                 # CompanionAgent 门面类（从这里开始）
│   ├── config.py                # AgentConfig（可注入，也可走环境变量默认值）
│   ├── events.py                # EventBus（解耦状态变化与外层应用）
│   ├── models.py                # 所有数据模型（Soul / Personality / Rhythm…）
│   ├── storage/
│   │   └── file_store.py        # 本地 JSON / JSONL 持久层
│   ├── llm/
│   │   ├── adapter.py           # 多云 LLM 适配（SiliconFlow / DeepSeek / OpenAI）
│   │   ├── prompts.py           # Prompt 模板
│   │   ├── corpus.py            # 离线语料兜底
│   │   └── presets.py           # 6 种性格预设
│   ├── context/
│   │   ├── manager.py           # L0～L3 多级上下文组装
│   │   └── digest.py            # 对话 → 关系快照 整理器
│   └── core/
│       ├── state_machine.py     # 6 态状态机
│       ├── personality_engine.py  # 性格演化引擎
│       └── scheduler.py         # 周期触发 digest / evolve
├── data/
│   └── corpus/                  # 6 种状态对应的默认离线语料
└── examples/
    └── quickstart.py            # 可直接运行的最小示例
```

---

## 配置

所有配置可以通过 `AgentConfig` 注入，也可以通过 `.env` 环境变量覆盖：

```python
from pathlib import Path
from fufu_agent import AgentConfig, CompanionAgent

cfg = AgentConfig(
    data_dir=Path("/tmp/fufu-test"),
    llm_provider="deepseek",       # "siliconflow" | "deepseek" | "openai"
    night_start_hour=23,
    digest_msg_threshold=10,
)
agent = CompanionAgent(config=cfg)
```

| 环境变量 | 说明 |
|---|---|
| `SILICONFLOW_API_KEY` | SiliconFlow API Key |
| `DEEPSEEK_API_KEY` | DeepSeek API Key |
| `OPENAI_API_KEY` | OpenAI API Key |
| `FUFU_LLM_PROVIDER` | 默认 provider（`siliconflow` / `deepseek` / `openai`） |
| `FUFU_DATA_DIR` | 覆盖数据目录（默认 `FuFuAgent/data`） |
| `SILICONFLOW_BASE_URL` | 自定义 SiliconFlow 接入点 |
| `SILICONFLOW_MODEL` | 覆盖 SiliconFlow 模型名 |

> 未配置任何 LLM Key 时，`say_one_line` 自动降级到离线语料；`chat` 与 `run_digest` 会明确报错。

---

## 事件系统

`EventBus` 是 Agent 与上层应用解耦的核心桥梁。内置三种事件：

| `event_type` | `data` 字段 | 触发时机 |
|---|---|---|
| `state_change` | `from`, `to`, `status`, `say_line` | 每次状态流转 |
| `personality_update` | `version`, `params`, `natural_description`, `voice_style` | 性格演化完成 |
| `soul_update` | `soul`（完整 dump） | Soul 数据更新 |

把事件转发到 WebSocket / Swift Bridge：

```python
@agent.subscribe
async def broadcast(event_type: str, data: dict):
    await my_ws_manager.broadcast(event_type, data)
```

---

## 性格预设

创建 Soul 时选择一种 `BiasType`，Agent 的说话风格和性格参数将以此为起点演化：

| 预设 | 特点 |
|---|---|
| `ADVENTUROUS` | 充满好奇，喜欢探索新事物 |
| `DECISIVE` | 果断干脆，不拖泥带水 |
| `SLOW_DOWN` | 沉稳温和，喜欢慢慢来 |
| `CUSTOM` | 自定义说话风格（需填写 `custom_voice_style`） |

---

## 集成到其他项目

FuFuAgent 设计为零框架依赖，可以嵌入任何 Python 项目：

```bash
# 作为可编辑包安装
pip install -e /path/to/FuFuAgent
```

```python
# FastAPI 中使用
from fufu_agent import CompanionAgent

agent = CompanionAgent()

@app.on_event("startup")
async def startup():
    await agent.start()

@app.post("/chat")
async def chat(msg: str):
    return {"reply": await agent.chat(msg)}
```

---

## 依赖

| 包 | 用途 |
|---|---|
| `pydantic >= 2.7` | 所有数据模型 |
| `pydantic-settings` | 环境变量配置 |
| `httpx` | 异步 HTTP / LLM 调用 |
| `aiofiles` | 异步文件 I/O |
| `python-dotenv` | `.env` 加载 |

Python 3.10+，无其他强依赖。

---

## License

MIT
