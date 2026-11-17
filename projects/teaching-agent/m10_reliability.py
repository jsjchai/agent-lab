#!/usr/bin/env python3
"""m10 · 分布式可靠性 —— 对应文档 §10（RocketMQ+MySQL 的 SQLite 替代）。

文档 §10 的可靠性机制在这里用 SQLite 完整模拟：
- Outbox：任务状态与待发消息在**同一事务**写入，避免「库改了消息没发」。
- 幂等键：业务效果用唯一约束去重，重复投递不产生重复业务操作。
- 租约 + 心跳：识别异常退出的 Worker，租约过期任务被回收重跑。
- 指数退避：控制重试节奏。
- 死信/转人工：超过最大重试转 NEEDS_HUMAN。
- 取消：定义可取消边界（PENDING/QUEUED/RETRY_WAIT 可取消，RUNNING 拒绝）。

任务状态机（文档 §10）：
    PENDING -> QUEUED -> RUNNING -> SUCCEEDED / RETRY_WAIT / FAILED / NEEDS_HUMAN / CANCELLED

运行（离线）：
    ../../.venv/bin/python m10_reliability.py
"""

from __future__ import annotations

import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

MAX_ATTEMPTS = 3
BACKOFF_BASE = 0.05
LEASE_SECONDS = 0.2


class TransientError(Exception):
    """可重试错误（如模型超时）。"""


class PermanentError(Exception):
    """不可重试错误。"""


class TaskEngine:
    def __init__(self, db: str = ":memory:"):
        self.conn = sqlite3.connect(db, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.business_writes = 0  # 真实业务写入计数（幂等保护下应只增一次/任务）
        self._init()

    def _init(self):
        self.conn.executescript("""
        CREATE TABLE IF NOT EXISTS tasks(
            id TEXT PRIMARY KEY, status TEXT, payload TEXT, idem_key TEXT,
            attempts INTEGER DEFAULT 0, next_retry_at REAL DEFAULT 0,
            lease_until REAL DEFAULT 0, worker TEXT);
        CREATE TABLE IF NOT EXISTS outbox(
            id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT, published INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS effects(
            idem_key TEXT PRIMARY KEY, result TEXT);
        """)
        self.conn.commit()

    # -- Outbox：同一事务写任务 + 待发消息
    def enqueue(self, task_id: str, payload: str, idem_key: str):
        with self.conn:
            self.conn.execute("INSERT INTO tasks(id,status,payload,idem_key) VALUES(?,?,?,?)",
                              (task_id, "PENDING", payload, idem_key))
            self.conn.execute("INSERT INTO outbox(task_id) VALUES(?)", (task_id,))

    # -- 投递（模拟 MQ，可能重复）
    def dispatch(self):
        rows = self.conn.execute("SELECT id, task_id FROM outbox WHERE published=0").fetchall()
        for r in rows:
            with self.conn:
                self.conn.execute("UPDATE tasks SET status='QUEUED' WHERE id=? AND status='PENDING'", (r["task_id"],))
                self.conn.execute("UPDATE outbox SET published=1 WHERE id=?", (r["id"],))
        return len(rows)

    def redeliver(self, task_id: str):
        """模拟 MQ 重复投递同一条消息。"""
        with self.conn:
            self.conn.execute("INSERT INTO outbox(task_id,published) VALUES(?,0)", (task_id,))
        self.dispatch()

    # -- 租约领取（含过期回收）
    def claim(self, worker: str):
        now = time.time()
        row = self.conn.execute(
            "SELECT * FROM tasks WHERE (status='QUEUED') "
            "OR (status='RETRY_WAIT' AND next_retry_at<=?) "
            "OR (status='RUNNING' AND lease_until<?) LIMIT 1",
            (now, now),
        ).fetchone()
        if row is None:
            return None
        with self.conn:
            self.conn.execute("UPDATE tasks SET status='RUNNING', worker=?, lease_until=? WHERE id=?",
                              (worker, now + LEASE_SECONDS, row["id"]))
        return dict(self.conn.execute("SELECT * FROM tasks WHERE id=?", (row["id"],)).fetchone())

    def heartbeat(self, task_id: str, worker: str):
        with self.conn:
            self.conn.execute("UPDATE tasks SET lease_until=? WHERE id=? AND worker=?",
                              (time.time() + LEASE_SECONDS, task_id, worker))

    def reap_expired(self):
        with self.conn:
            cur = self.conn.execute("UPDATE tasks SET status='QUEUED', worker=NULL WHERE status='RUNNING' AND lease_until<?",
                                    (time.time(),))
        return cur.rowcount

    # -- 执行（幂等 + 退避 + 转人工）
    def execute(self, task: dict, model_fn):
        tid = task["id"]
        try:
            result = model_fn(task["payload"], task["attempts"])
        except TransientError:
            attempts = task["attempts"] + 1
            if attempts >= MAX_ATTEMPTS:
                self._set(tid, "NEEDS_HUMAN", attempts=attempts)
            else:
                self._set(tid, "RETRY_WAIT", attempts=attempts, next_retry_at=time.time() + BACKOFF_BASE * 2 ** (attempts - 1))
            return "retry"
        except PermanentError:
            self._set(tid, "FAILED", attempts=task["attempts"] + 1)
            return "failed"

        # 幂等：唯一约束保证业务效果只写一次
        with self.conn:
            cur = self.conn.execute("INSERT OR IGNORE INTO effects(idem_key,result) VALUES(?,?)", (task["idem_key"], result))
            if cur.rowcount == 1:
                self.business_writes += 1  # 只有首次插入才算真实业务写入
        self._set(tid, "SUCCEEDED")
        return "success"

    def _set(self, tid: str, status: str, **kw):
        sets = ["status=?"] + [f"{k}=?" for k in kw]
        with self.conn:
            self.conn.execute(f"UPDATE tasks SET {','.join(sets)} WHERE id=?", (status, *kw.values(), tid))

    def cancel(self, task_id: str) -> bool:
        row = self.conn.execute("SELECT status FROM tasks WHERE id=?", (task_id,)).fetchone()
        if row and row["status"] in ("PENDING", "QUEUED", "RETRY_WAIT"):
            self._set(task_id, "CANCELLED")
            return True
        return False

    def status(self, task_id: str) -> str:
        row = self.conn.execute("SELECT status FROM tasks WHERE id=?", (task_id,)).fetchone()
        return row["status"] if row else "UNKNOWN"


def drain(eng: TaskEngine, worker: str, model_fn, max_steps: int = 40):
    """反复领取并执行，直到任务进入终态（自动处理退避等待）。"""
    for _ in range(max_steps):
        t = eng.claim(worker)
        if t is None:
            time.sleep(BACKOFF_BASE)
            continue
        eng.execute(t, model_fn)
        if eng.status(t["id"]) in ("SUCCEEDED", "FAILED", "NEEDS_HUMAN", "CANCELLED"):
            return


def demo() -> None:
    print("【m10 可靠性】Outbox + 幂等 + 租约 + 退避 + 取消")
    eng = TaskEngine()

    print("\n  1) 重复投递不重复写入：")
    eng.enqueue("t1", "payload", "idem-1")
    eng.dispatch()
    eng.redeliver("t1")  # 重复消息
    task = eng.claim("w1")
    eng.execute(task, lambda p, a: "ok")
    eng.dispatch(); t = eng.claim("w1")
    if t: eng.execute(t, lambda p, a: "ok")
    print(f"     状态={eng.status('t1')} 业务写入次数={eng.business_writes}（应为1）")

    print("\n  2) Worker 宕机后租约回收重跑：")
    eng.enqueue("t2", "payload", "idem-2")
    eng.dispatch()
    eng.claim("dead-worker")  # 领取后不心跳，模拟宕机
    time.sleep(LEASE_SECONDS + 0.05)
    reaped = eng.reap_expired()
    task = eng.claim("w2")
    eng.execute(task, lambda p, a: "ok")
    print(f"     回收={reaped} 状态={eng.status('t2')}")

    print("\n  3) 模型超时退避重试后成功：")
    eng.enqueue("t3", "payload", "idem-3")
    eng.dispatch()
    calls = {"n": 0}
    def flaky(p, a):
        calls["n"] += 1
        if calls["n"] < 2:
            raise TransientError("timeout")
        return "ok"
    drain(eng, "w3", flaky)
    print(f"     状态={eng.status('t3')} 调用次数={calls['n']}")

    print("\n  4) 持续失败转人工：")
    eng.enqueue("t4", "payload", "idem-4")
    eng.dispatch()
    drain(eng, "w4", lambda p, a: (_ for _ in ()).throw(TransientError("down")))
    print(f"     状态={eng.status('t4')}（应为 NEEDS_HUMAN）")

    print("\n  5) 取消边界：")
    eng.enqueue("t5", "payload", "idem-5")
    print(f"     PENDING 可取消? {eng.cancel('t5')}")
    eng.enqueue("t6", "payload", "idem-6"); eng.dispatch(); eng.claim("w6")
    print(f"     RUNNING 可取消? {eng.cancel('t6')}（应为 False）")


def selftest() -> None:
    eng = TaskEngine()
    # 幂等
    eng.enqueue("t1", "p", "k1"); eng.dispatch(); eng.redeliver("t1")
    t = eng.claim("w"); eng.execute(t, lambda p, a: "ok")
    t = eng.claim("w")
    if t: eng.execute(t, lambda p, a: "ok")
    assert eng.business_writes == 1 and eng.status("t1") == "SUCCEEDED"

    # 宕机回收
    eng.enqueue("t2", "p", "k2"); eng.dispatch(); eng.claim("dead")
    time.sleep(LEASE_SECONDS + 0.05)
    assert eng.reap_expired() >= 1
    t = eng.claim("w2"); eng.execute(t, lambda p, a: "ok")
    assert eng.status("t2") == "SUCCEEDED"

    # 退避重试
    eng.enqueue("t3", "p", "k3"); eng.dispatch()
    n = {"c": 0}
    def flaky(p, a):
        n["c"] += 1
        if n["c"] < 2: raise TransientError("x")
        return "ok"
    drain(eng, "w3", flaky)
    assert eng.status("t3") == "SUCCEEDED"

    # 转人工
    eng.enqueue("t4", "p", "k4"); eng.dispatch()
    drain(eng, "w4", lambda p, a: (_ for _ in ()).throw(TransientError("x")))
    assert eng.status("t4") == "NEEDS_HUMAN"

    # 取消边界
    eng.enqueue("t5", "p", "k5")
    assert eng.cancel("t5") is True
    eng.enqueue("t6", "p", "k6"); eng.dispatch(); eng.claim("w6")
    assert eng.cancel("t6") is False


if __name__ == "__main__":
    demo()
