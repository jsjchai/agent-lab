"""事件通道：CLI 照常人读打印，加 --emit-json 时把结构化事件写给 Web 端。

为什么用"事件 + 子进程"而不是在 Web 服务里直接 import 这两个脚本：
- LangGraph / CrewAI 都可能在 import 阶段做重活（CrewAI 会初始化本地存储），
  放进 Web 进程会把服务启动时间和故障面一起放大；
- 子进程可以被杀掉（超时、用户关页面），不会把服务拖死；
- 脚本既能独立运行，也能被 Web 端驱动，两种用法共享同一份业务代码。
"""

from __future__ import annotations

import json
import sys

_events_on = False
# 保存"真正的 stdout"：开启事件模式后 sys.stdout 会被改到 stderr
_real_stdout = sys.stdout


def enable_json_events() -> None:
    """开启后：stdout 只输出 JSON 事件，人类可读日志全部改走 stderr。"""
    global _events_on
    _events_on = True
    sys.stdout = sys.stderr


def emit(**event) -> None:
    """发一个事件。未开启事件模式时是空操作，CLI 用法完全不受影响。"""
    if not _events_on:
        return
    _real_stdout.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")
    _real_stdout.flush()
