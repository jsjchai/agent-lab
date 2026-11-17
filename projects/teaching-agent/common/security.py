"""安全上下文与人工确认凭证 —— 对应文档 §11 安全治理与人工确认。

核心原则（文档原文的 Python 落地）：
1. 安全上下文来自可信认证链路，**不能采信模型生成的身份字段**。
2. 确认凭证绑定 用户 + 租户 + 草稿哈希 + 有效期，且**一次性使用**。
3. 关键工具调用可审计。

这里用内存字典模拟认证服务与凭证存储；生产应换成
认证网关签发的 token + Redis/DB 存储（带 TTL 与原子消费）。
"""

from __future__ import annotations

import hashlib
import json
import secrets
import time
from dataclasses import dataclass, field


# --------------------------------------------------------------------------- 可信用户库
# 模拟 Teaching 既有用户/组织数据。认证链路从这里取身份，而不是从模型输出。
_USERS = {
    "u1": {"tenant": "t1", "orgs": ["o1", "o2"], "role": "teacher", "name": "陈老师"},
    "u2": {"tenant": "t1", "orgs": ["o2"], "role": "teacher", "name": "林老师"},
    "u3": {"tenant": "t2", "orgs": ["o3"], "role": "teacher", "name": "王老师"},
}


@dataclass(frozen=True)
class SecurityContext:
    user_id: str
    tenant_id: str
    org_ids: tuple[str, ...]
    role: str

    def can_access_org(self, org_id: str) -> bool:
        return org_id in self.org_ids


class AuthError(Exception):
    """认证/授权失败。工具层抛出后由上层映射为统一错误码，不泄漏内部细节。"""


def authenticate(user_id: str) -> SecurityContext:
    """模拟可信认证链路：只接受已知用户，身份字段全部来自服务端数据。"""
    record = _USERS.get(user_id)
    if record is None:
        raise AuthError(f"未知用户：{user_id}")
    return SecurityContext(
        user_id=user_id,
        tenant_id=record["tenant"],
        org_ids=tuple(record["orgs"]),
        role=record["role"],
    )


# --------------------------------------------------------------------------- 审计
@dataclass
class AuditLog:
    entries: list[dict] = field(default_factory=list)

    def record(self, action: str, ctx: SecurityContext | None, detail: dict, allowed: bool) -> None:
        self.entries.append({
            "ts": round(time.time(), 3),
            "action": action,
            "user": ctx.user_id if ctx else None,
            "tenant": ctx.tenant_id if ctx else None,
            "allowed": allowed,
            "detail": detail,
        })

    def denied(self) -> list[dict]:
        return [e for e in self.entries if not e["allowed"]]


# --------------------------------------------------------------------------- 确认凭证
def draft_hash(draft: dict) -> str:
    """草稿规范化哈希：确认凭证绑定它，草稿被篡改则凭证失效。"""
    canonical = json.dumps(draft, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(canonical.encode()).hexdigest()


class ConfirmTokenStore:
    """一次性确认凭证存储。

    issue() 绑定 (user, tenant, draft_hash, expiry)；
    consume() 校验全部绑定 + 有效期 + 一次性，任何一项不符即拒绝。
    """

    def __init__(self) -> None:
        self._tokens: dict[str, dict] = {}

    def issue(self, ctx: SecurityContext, draft: dict, ttl_seconds: float = 300) -> str:
        token = secrets.token_urlsafe(24)
        self._tokens[token] = {
            "user": ctx.user_id,
            "tenant": ctx.tenant_id,
            "hash": draft_hash(draft),
            "expires": time.time() + ttl_seconds,
            "used": False,
        }
        return token

    def consume(self, token: str, ctx: SecurityContext, draft: dict) -> None:
        rec = self._tokens.get(token)
        if rec is None:
            raise AuthError("确认凭证不存在")
        if rec["used"]:
            raise AuthError("确认凭证已被使用（不可重放）")
        if time.time() > rec["expires"]:
            raise AuthError("确认凭证已过期")
        if rec["user"] != ctx.user_id or rec["tenant"] != ctx.tenant_id:
            raise AuthError("确认凭证与当前用户/租户不匹配")
        if rec["hash"] != draft_hash(draft):
            raise AuthError("草稿已被篡改，与凭证绑定的哈希不一致")
        rec["used"] = True  # 一次性

    def expire_for_test(self, token: str) -> None:
        if token in self._tokens:
            self._tokens[token]["expires"] = time.time() - 1


class PersistentConfirmTokenStore:
    """SQLite 持久化的一次性确认凭证存储。

    与 ConfirmTokenStore 接口一致，但凭证落盘，支持跨进程/重启恢复。
    consume 用原子 UPDATE（used=0 -> 1）保证一次性，天然防重放。
    生产环境对应 Redis（SETNX + TTL）或 DB 唯一约束。
    """

    def __init__(self, db_path: str):
        import sqlite3

        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS confirm_tokens "
            "(token TEXT PRIMARY KEY, user TEXT, tenant TEXT, hash TEXT, expires REAL, used INTEGER)"
        )
        self._conn.commit()

    def issue(self, ctx: SecurityContext, draft: dict, ttl_seconds: float = 300) -> str:
        token = secrets.token_urlsafe(24)
        self._conn.execute(
            "INSERT INTO confirm_tokens VALUES (?,?,?,?,?,0)",
            (token, ctx.user_id, ctx.tenant_id, draft_hash(draft), time.time() + ttl_seconds),
        )
        self._conn.commit()
        return token

    def consume(self, token: str, ctx: SecurityContext, draft: dict) -> None:
        row = self._conn.execute(
            "SELECT user, tenant, hash, expires, used FROM confirm_tokens WHERE token=?", (token,)
        ).fetchone()
        if row is None:
            raise AuthError("确认凭证不存在")
        user, tenant, h, expires, used = row
        if used:
            raise AuthError("确认凭证已被使用（不可重放）")
        if time.time() > expires:
            raise AuthError("确认凭证已过期")
        if user != ctx.user_id or tenant != ctx.tenant_id:
            raise AuthError("确认凭证与当前用户/租户不匹配")
        if h != draft_hash(draft):
            raise AuthError("草稿已被篡改，与凭证绑定的哈希不一致")
        cur = self._conn.execute("UPDATE confirm_tokens SET used=1 WHERE token=? AND used=0", (token,))
        self._conn.commit()
        if cur.rowcount != 1:
            raise AuthError("确认凭证已被使用（不可重放）")

    def expire_for_test(self, token: str) -> None:
        self._conn.execute("UPDATE confirm_tokens SET expires=? WHERE token=?", (time.time() - 1, token))
        self._conn.commit()
