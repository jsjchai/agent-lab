#!/usr/bin/env python3
"""总验收：依次运行 m01~m10 的 selftest，输出 PASS/FAIL 汇总。

运行（离线，无需 API key）：
    ../../.venv/bin/python run_all.py
全部通过退出码 0，任一失败退出码 1。
"""

from __future__ import annotations

import importlib
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

MODULES = [
    ("m01_structured_output", "§3 结构化输出 + DTO 校验"),
    ("m02_intent_slots", "§4 意图识别 / 槽位 / 澄清"),
    ("m03_client_sse", "§5 模型接入 / SSE 流式"),
    ("m04_tools", "§7 工具白名单 / 权限 / 审计"),
    ("m05_workflow", "§6 工作流 / Checkpoint / HITL"),
    ("m06_rag", "§8 RAG / 混合检索 / ACL / 引用"),
    ("m07_security", "§11 安全治理测试套件"),
    ("m08_eval", "§12 Golden Set 评测门禁"),
    ("m09_router", "§9 模型路由 / 合规回退"),
    ("m10_reliability", "§10 Outbox / 幂等 / 租约 / 重试"),
    ("m11_model_bench", "§9/§12 模型横向对比（mock 基线）"),
]


def main() -> int:
    print("=" * 60)
    print("Teaching Agent · 全模块验收（离线 mock）")
    print("=" * 60)
    failed = []
    for mod_name, label in MODULES:
        t0 = time.time()
        try:
            mod = importlib.import_module(mod_name)
            mod.selftest()
            print(f"  ✅ {mod_name:24s} {label}  ({time.time() - t0:.2f}s)")
        except Exception as exc:
            failed.append(mod_name)
            print(f"  ❌ {mod_name:24s} {label}  -> {type(exc).__name__}: {exc}")
    print("=" * 60)
    print(f"结果：{len(MODULES) - len(failed)}/{len(MODULES)} 通过")
    if failed:
        print("失败模块：", ", ".join(failed))
        return 1
    print("全部通过 🎉")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
