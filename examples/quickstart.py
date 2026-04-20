"""最小跑通示例：创建 Soul -> 聊一句 -> 触发一次 digest。

运行方式（在 FuFuAgent 根目录下）::

    pip install -r requirements.txt
    cp .env.example .env        # 填入至少一个 LLM API Key
    python examples/quickstart.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# 如果没有 ``pip install -e .``，把包根放进 sys.path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fufu_agent import (  # noqa: E402
    BiasType,
    CompanionAgent,
    SoulAlreadyExists,
    SoulCreateRequest,
)


async def main() -> None:
    async with CompanionAgent() as agent:
        # 订阅事件（可选）
        agent.on("state_change", lambda d: print("[state_change]", d))
        agent.on("personality_update", lambda d: print("[personality]", d))

        # 如果已经创建过 Soul 就跳过
        try:
            agent.create_soul(
                SoulCreateRequest(
                    current_state_word="迷茫",
                    struggle="不知道要不要换工作",
                    bias=BiasType.ADVENTUROUS,
                )
            )
            print("Soul 已创建")
        except SoulAlreadyExists:
            print("Soul 已存在，复用")

        # 模拟硬件事件
        await agent.person_arrive()
        await agent.person_sit()

        # 对话一句（需要 LLM key；没配置会报 RuntimeError）
        if agent.llm_adapter.available:
            reply = await agent.chat("今天工作有点烦。")
            print("Agent:", reply)

            # 主动触发一次关系整理（manual=True 降低阈值）
            digest = await agent.run_digest(manual=True)
            print("Digest:", digest.get("ok"), digest.get("skipped"))
        else:
            print("LLM 未配置，跳过对话和 digest。")

        # 导出当前多级上下文
        print(agent.export_context_markdown())


if __name__ == "__main__":
    asyncio.run(main())
