#!/usr/bin/env python3
"""sandbox_env · 执行环境与能力 seam —— docs/11-harness-engineering/07-execution-environment.md 代码锚点。

镜像真实 DSH 的执行环境设计（capability-seams.zh.md）：
- **ctx.fs**（文件系统 seam）：fs-local / fs-sandbox / fs-ssh 可替换。
- **ctx.shell**（bash 执行 seam）：bash-local / bash-sandbox。
- **ctx.sandbox**（进程沙箱 seam）+ sandbox-policy（策略）。
- **关键设计**：fs 与进程提供方共享同一个「执行世界」——把它们指向沙箱，
  Bash/文件操作一并受限，无需为每个工具单独改代码。

本实验用纯 Python 演示「提供方替换」：LocalWorld（无限制）vs SandboxWorld（workspace-write 围栏）。
不执行真实 shell（教学骨架，安全第一）；真实 DSH 用 sandbox-local/seatbelt/landlock 等后端。

运行（离线）：../../.venv/bin/python sandbox_env.py
"""

from __future__ import annotations

from dataclasses import dataclass, field


class Denied(Exception):
    """沙箱拒绝（越界写入）。"""


@dataclass
class LocalFS:
    """fs-local 类比：无限制读写。"""
    files: dict = field(default_factory=dict)

    def write(self, path: str, content: str) -> None:
        self.files[path] = content

    def read(self, path: str) -> str:
        return self.files.get(path, "")


@dataclass
class SandboxFS:
    """fs-sandbox 类比：写入限制在 workspace 根内，读取放行。"""
    workspace: str
    files: dict = field(default_factory=dict)

    def write(self, path: str, content: str) -> None:
        if not path.startswith(self.workspace.rstrip("/") + "/"):
            raise Denied(f"写入越界：{path} 不在 {self.workspace} 内")
        self.files[path] = content

    def read(self, path: str) -> str:
        return self.files.get(path, "")        # 读取放行（DSH fs-sandbox 读通过）


@dataclass
class Shell:
    """ctx.shell 类比：执行命令，cwd 受执行世界约束。"""
    world: "ExecutionWorld"

    def run(self, cmd: str) -> str:
        # 沙箱世界里，命令的工作目录被限定在 workspace
        cwd = self.world.cwd()
        return f"[cwd={cwd}] $ {cmd}"


@dataclass
class ExecutionWorld:
    """一个「执行世界」= fs 提供方 + shell 共享的环境。

    DSH 关键：fs 与进程共享执行世界，替换世界即同时替换两者。
    """
    fs: object
    workspace: str | None = None

    def cwd(self) -> str:
        return self.workspace or "/"

    def shell(self) -> Shell:
        return Shell(self)


def demo() -> None:
    print("【sandbox_env】执行世界：本地 vs 沙箱")
    local = ExecutionWorld(LocalFS(), workspace=None)
    sandbox = ExecutionWorld(SandboxFS(workspace="/repo"), workspace="/repo")

    print("  本地世界写 /etc/passwd：", end=" ")
    local.fs.write("/etc/passwd", "x"); print("允许")

    print("  沙箱世界写 /repo/a.py：", end=" ")
    sandbox.fs.write("/repo/a.py", "x"); print("允许")

    print("  沙箱世界写 /etc/passwd：", end=" ")
    try:
        sandbox.fs.write("/etc/passwd", "x"); print("允许（错误！）")
    except Denied as e:
        print("拒绝 ->", e)

    print("  同一 shell 在两个世界的 cwd：")
    print("   ", local.shell().run("ls"))
    print("   ", sandbox.shell().run("ls"))


def selftest() -> None:
    sandbox = ExecutionWorld(SandboxFS(workspace="/repo"), workspace="/repo")
    sandbox.fs.write("/repo/a.py", "ok")
    assert sandbox.fs.read("/repo/a.py") == "ok"
    try:
        sandbox.fs.write("/etc/passwd", "x"); raise AssertionError("应拒绝")
    except Denied:
        pass
    assert sandbox.fs.read("/etc/passwd") == ""        # 越界写入未生效
    # shell 与 fs 共享执行世界（cwd 受限）
    assert sandbox.shell().run("ls").startswith("[cwd=/repo]")
    # 替换世界：local 无限制
    local = ExecutionWorld(LocalFS())
    local.fs.write("/anywhere", "x")
    assert local.fs.read("/anywhere") == "x"
    assert local.shell().run("ls").startswith("[cwd=/]")


if __name__ == "__main__":
    demo()
