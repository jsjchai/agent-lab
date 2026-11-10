#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CrewAI 多智能体示例：为内科住院医师设计一次 60 分钟教学查房。

这个脚本和同目录下的 `langgraph_case_agent.py` 是一对对照实验：
同一个业务（医疗教学活动设计），用两种框架各写一遍。

    LangGraph 版本：重点是「状态机 + 条件边 + 回环」——流程由你来画，
                    节点之间传一个共享 state，什么时候重试由代码决定。
    CrewAI 版本：  重点是「多角色协作」——每个 Agent 有人设（role/goal/backstory），
                    每个 Task 有交付物，框架负责按顺序把它们串起来。

## CrewAI 在这里到底做了什么？

初学的时候容易把 CrewAI 当成"更高级的 prompt 模板"，其实它替你做的是这几件事：

1. **组装 prompt**：你把 role / goal / backstory / description / expected_output
   填进去，CrewAI 负责拼成一段符合它内部 ReAct 格式的系统提示词。
   你写的是「带人设的任务卡」，不是「一整段 prompt」。
2. **管理执行顺序**：`Process.sequential` 表示"上一个 Task 结束才跑下一个"，
   每个 Task 指定一个 agent，CrewAI 逐个调度。
3. **传递上下文**：Task 的 `context=[前一个任务]` 会让框架把前一个任务的产出
   注入到当前任务的 prompt 里——这就是本示例里"后一个角色能读到前一个角色产出"
   的实现方式，不用你手写字符串拼接。
4. **解析输出**：CrewAI 会解析 LLM 返回的 `Thought: ... / Final Answer: ...`，
   只把 Final Answer 作为任务产出；输出不符合格式时会重试或报错。

反过来，CrewAI 也「藏」了两件事（初学要心里有数）：
- 它没有显式的全局状态对象，Task 之间的数据只靠 `context=` 单向流动，
  想实现"评审不通过就回退重做"这类回环，得自己写或换 LangGraph。
- 每次 Agent 执行的具体 prompt 是框架拼的，不打开 verbose/日志你是看不到的，
  出问题时排查成本比手写 prompt 高。

## 运行方式

    # 离线模式（默认，不需要 API key）
    AGENT_LLM=mock python crewai_teaching_activity.py

    # 覆盖主题（证明没有写死业务内容）
    AGENT_LLM=mock python crewai_teaching_activity.py --topic "急性腹痛"

    # 接真实模型（任何 OpenAI 兼容接口）
    export AGENT_LLM=openai OPENAI_API_KEY=sk-... AGENT_MODEL=gpt-4o-mini
    python crewai_teaching_activity.py --verbose

产出：`out/crewai_teaching_activity.md`（含完整教案 + 附录里各环节的原始产出）。
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# 以下环境准备必须在 `from crewai import ...` 之前完成。
#
# 背景：CrewAI 1.x 在 **import 阶段** 就会初始化自己的本地存储目录
# （SQLite、凭证、缓存等），默认位置在用户家目录下：
#     macOS   ~/Library/Application Support/...
#     Linux   ~/.local/share/...
# 在容器、CI、以及本机这种「只允许写工作区」的沙箱里，家目录不可写，
# import 会直接抛 PermissionError。教学示例不应该卡在这种环境问题上，
# 所以这里做两件事：
#   1. 把 CrewAI 的数据目录指到仓库内的 .crewai-home/（不污染家目录）；
#   2. 如果家目录不可写，再把 HOME 临时重定向到同一个目录。
# 普通终端运行时家目录可写，第 2 步不会触发，也不会多出任何目录。
# ---------------------------------------------------------------------------
_HERE = Path(__file__).resolve().parent

os.environ.setdefault("CREWAI_STORAGE_DIR", str(_HERE / ".crewai-home"))

# 家目录被重定向时记一条提示，等 main() 开始时再打印；
# 这样 `--help` 这类不真正跑 Crew 的命令不会被环境日志干扰。
_HOME_REDIRECT_MSG: str | None = None


def _redirect_home_if_unwritable() -> None:
    """家目录不可写时，把 HOME 重定向到仓库内目录（仅当前进程生效）。"""
    global _HOME_REDIRECT_MSG

    try:
        probe = Path.home() / ".crewai-write-probe"
        probe.mkdir(parents=True, exist_ok=True)
        probe.rmdir()  # 只是探测，用完立即清理
        return
    except OSError:
        pass

    fallback = _HERE / ".crewai-home"
    fallback.mkdir(parents=True, exist_ok=True)
    os.environ["HOME"] = str(fallback)
    os.environ["USERPROFILE"] = str(fallback)  # Windows 兜底
    _HOME_REDIRECT_MSG = f"[环境] 家目录不可写，已把 CrewAI 的 HOME 重定向到：{fallback}"


_redirect_home_if_unwritable()

# ---------------------------------------------------------------------------
# 离线/遥测开关：让 CrewAI 在无网环境里不去做遥测上报、不去检查版本更新，
# 否则跑到一半可能因为网络超时卡住（mock 模式下我们只想验证流程）。
# ---------------------------------------------------------------------------
os.environ.setdefault("CREWAI_DISABLE_TELEMETRY", "true")
os.environ.setdefault("CREWAI_TELEMETRY_OPT_OUT", "true")
os.environ.setdefault("CREWAI_TRACING_ENABLED", "false")
os.environ.setdefault("OTEL_SDK_DISABLED", "true")

from crewai import Agent, Crew, Process, Task  # noqa: E402

from common.events import emit, enable_json_events  # noqa: E402
from common.llm import current_mode, describe, make_crewai_llm, model_name  # noqa: E402

# --------------------------------------------------------------------------- 常量
DEFAULT_TOPIC = "急性胸痛（STEMI 鉴别）"
DEFAULT_LEVEL = "内科住院医师 R1-R2"
DEFAULT_GROUP_SIZE = "6-8 人"

# 每个任务的短名，用于控制台进度打印和 Markdown 附录标题。
STAGE_NAMES = ["教学设计", "临床要点", "考核评价", "汇总整合"]

# 脚本目录下的 out/，作为 --out 缺省值（从任何 cwd 运行都输出到本目录）。
SCRIPT_DIR = _HERE
DEFAULT_OUT = SCRIPT_DIR / "out" / "crewai_teaching_activity.md"


# --------------------------------------------------------------------------- 角色
def build_agents(llm, verbose: bool) -> dict[str, Agent]:
    """创建 4 个 Agent。

    这里是 CrewAI 最核心的一步：**每个 Agent 是一张角色卡**。
    - role：一句话身份，框架会把它放进系统提示词的第一句；
    - goal：这个角色要对什么结果负责（越可衡量越好）；
    - backstory：给模型"经验背景"，直接影响它输出的专业深度与口吻。

    注意 `allow_delegation=False`：教学演示里不要让 Agent 自己去"找人帮忙"，
    否则它可能把活推给别的角色，顺序就乱了。真实生产里也建议先关掉。
    """
    # 所有角色共用的参数，避免重复写。
    common = dict(
        llm=llm,                # 关键：把 mock / 真实 LLM 对象注入每个 Agent
        verbose=verbose,        # --verbose 时才打印 ReAct 过程
        allow_delegation=False, # 关闭"把任务转交别人"
        max_iter=3,             # 防止真模型陷入空转的最新次数上限
    )

    designer = Agent(
        role="教学设计专家",
        goal="把一次 60 分钟教学查房拆成目标可测量、时间可执行、每个环节都有产出的课",
        backstory=(
            "你在三甲医院教学部做了 10 年住院医师规范化培训课程设计，"
            "熟悉 Bloom 认知分层、ADDIE 与翻转课堂。你最讨厌空泛的教学目标——"
            "写不出「学员课后能做什么」的目标，你会直接打回重写。"
            "你也非常在意时间表：每个环节必须写清楚教师做什么、学员做什么。"
        ),
        **common,
    )

    cardiologist = Agent(
        role="心内科带教老师",
        goal="把本主题真正决定患者结局的临床要点、以及学员最容易犯的具体错误讲清楚",
        backstory=(
            "你是心内科主治医师，带了 6 年住院医师，做过 300 多台急诊 PCI。"
            "你上课从不念指南，而是用「如果你是值班医生，此刻怎么办」逼学员做决策。"
            "你记得住每一届学员犯过的错，也能一句话点出错误背后的思维漏洞。"
        ),
        **common,
    )

    assessor = Agent(
        role="考核评价专家",
        goal="设计能真正区分「会背」和「会用」的评价工具，并给出可操作的反馈机制",
        backstory=(
            "你在医学院考试中心负责 Mini-CEX 与 DOPS 的本地化落地，"
            "主张评价要嵌在教学过程里，而不是最后考一张卷子。"
            "你设计的评分表每一条都能在床旁被直接观察到，不用猜。"
        ),
        **common,
    )

    lead_teacher = Agent(
        role="教研组长（教案整合者）",
        goal="把教学、临床、评价三份产出整合成一份可以直接拿去上课的完整教案",
        backstory=(
            "你是内科教研组长，每次查房前都要签发教案。你的标准是："
            "一个新来的规培生拿到这份教案，不看别的资料也能把这 60 分钟上下来；"
            "时间表要能对上，目标、活动、评价三者要互相对齐（建构性对齐）。"
        ),
        **common,
    )

    return {
        "designer": designer,
        "cardiologist": cardiologist,
        "assessor": assessor,
        "lead": lead_teacher,
    }


# --------------------------------------------------------------------------- 任务
def build_tasks(
    agents: dict[str, Agent],
    topic: str,
    level: str,
    group_size: str,
) -> list[Task]:
    """创建 4 个 Task，并用 context= 把前序产出串给后续任务。

    Task 的三个关键字段：
    - description：要做什么（写给模型看，越具体越稳）；
    - expected_output：交付物的验收标准（CrewAI 会据此判断任务是否完成）；
    - context：把哪些任务的产出作为本任务的输入。

    本示例的数据流：

        教学设计 ──┐
        临床要点 ──┼──> 汇总整合
        考核评价 ──┘

    所以最后一个 Task 的 context 同时指向前面三个 Task。
    这就是"后一个任务能读到前一个任务产出"的实现方式——不用手写拼接。
    """
    # ---- Task 1：教学设计专家 ------------------------------------------------
    task_design = Task(
        description=(
            f"【环节】设计\n"
            f"教学主题：{topic}\n"
            f"学习者：{level}\n"
            f"分组人数：一次约 {group_size}\n"
            "场景：一次 60 分钟的临床教学查房（不是大讲课，也不是出科考试），"
            "学员需要在床旁/病例讨论中完成真实的临床判断。\n"
            "请产出三部分：\n"
            "1. 教学目标：按 Bloom 认知分层写，至少 4 条，覆盖「记忆/理解 → 应用 → 分析」"
            "至少三层。每条目标都用可观察的行为动词（如「能列出」「能排序」「能说明理由」），"
            "不要写「掌握」「了解」这种无法测量的词。\n"
            "2. 60 分钟时间分配表：Markdown 表格，列固定为"
            "「时间 | 环节 | 教师动作 | 学员动作 | 本环节产出」，五段左右。\n"
            "3. 设计原则：3~5 条，并说明每一条为什么能解决本主题的教学难点。\n"
            "内容要具体到「教师说什么、学员写什么」，不要只写环节名称。"
        ),
        expected_output=(
            "Markdown 文档，包含三个小节：Bloom 分层教学目标、60 分钟时间分配表、"
            "设计原则。时间表必须是表格，且五列齐全。"
        ),
        agent=agents["designer"],
    )

    # ---- Task 2：心内科带教老师（读 Task 1 的产出） --------------------------
    task_clinic = Task(
        description=(
            f"【环节】临床\n"
            f"教学主题：{topic}\n"
            f"学习者：{level}\n"
            f"分组人数：一次约 {group_size}\n"
            "前一环节（教学设计）确定的教学目标和时间安排已经在上下文中，"
            "请让本环节的内容与那些目标一一对应，不要另起一套。\n"
            "请从心内科带教老师的角度产出三部分：\n"
            "1. 临床要点：按「时间线 / 危险分层 / 鉴别诊断 / 处置优先级」组织，"
            "每一条都写清楚「为什么这一条决定结局」。\n"
            "2. 学员常见误区：至少 5 个，必须写成具体行为（例如「只做一次心电图就说排除」），"
            "不要写「知识不扎实」这种空话；每个误区后附一句纠正话术。\n"
            "3. 教学追问设计：至少 5 个层层递进的问题，每个问题附带"
            "「学员答对了怎么继续追问、答错了怎么引导」，形成追问链。"
        ),
        expected_output=(
            "Markdown 文档，包含三部分：临床要点（按时间线/分层/鉴别/处置组织）、"
            "至少 5 条具体行为化的学员误区、至少 5 个带追问链的教学问题。"
        ),
        agent=agents["cardiologist"],
        context=[task_design],  # ← 关键：把教学设计的产出喂给心内科老师
    )

    # ---- Task 3：考核评价专家（读 Task 1、Task 2 的产出） --------------------
    task_assess = Task(
        description=(
            f"【环节】考核\n"
            f"教学主题：{topic}\n"
            f"学习者：{level}\n"
            f"分组人数：一次约 {group_size}\n"
            "前两环节的目标、时间安排和临床要点都在上下文中。你的评价必须对准它们，"
            "凡是没有被教学目标覆盖的内容，不要考。\n"
            "请产出三部分：\n"
            "1. Mini-CEX 评分表：恰好 7 项维度，每项 1~9 分，并给出三档行为描述"
            "（1-3 分不达标 / 4-6 分达标 / 7-9 分优秀）。每一档都要写成「看得到的行为」，"
            "不能只写「良好」「一般」。\n"
            "2. 3 道病例题：分别对应「应用」「分析」「评价」三个层次，"
            "每题给出参考答案要点和评分点（答到哪几条给几分）。\n"
            "3. 反馈机制：说明什么时候反馈、由谁反馈、反馈什么、记录到哪里。"
        ),
        expected_output=(
            "Markdown 文档，包含：7 项 Mini-CEX 评分表（每项三档行为描述）、"
            "3 道带评分要点的病例题、可执行的反馈机制。"
        ),
        agent=agents["assessor"],
        context=[task_design, task_clinic],  # ← 同时读取前两个任务的产出
    )

    # ---- Task 4：教研组长整合（读前三份产出） --------------------------------
    task_summary = Task(
        description=(
            f"【环节】汇总\n"
            f"教学主题：{topic}\n"
            f"学习者：{level}\n"
            f"分组人数：一次约 {group_size}\n"
            "上面三个环节的产出（教学目标/时间表、临床要点与误区、考核与反馈）"
            "都在上下文中，请把它们整合成一份**可以直接拿去上课的完整教案**。\n"
            "要求：\n"
            "1. 开头写活动概览：名称、对象、时长、形式、场地与教具准备。\n"
            "2. 完整 60 分钟流程表：把教学目标、临床要点、考核活动都落到具体时间点，"
            "并注明每个时点对应哪个教学目标。\n"
            "3. 逐环节教学脚本：每个环节写「教师做什么、学员做什么、可能出现的问题、"
            "应对方式」。\n"
            "4. 评价与反馈安排、学员课后作业、风险与伦理提示"
            "（真实病例去标识化、模拟演练需声明非真实抢救等）。\n"
            "5. 最后检查一遍：目标—活动—评价是否互相对齐，不一致的地方直接修正。\n"
            "不要简单复制前三个环节的原文，要做取舍、对齐和补充。"
        ),
        expected_output=(
            "一份完整的 Markdown 教案：活动概览、60 分钟流程表、逐环节教学脚本、"
            "评价与反馈、课后作业、风险与伦理提示，且目标-活动-评价互相对齐。"
        ),
        agent=agents["lead"],
        context=[task_design, task_clinic, task_assess],  # ← 汇总前三个任务的产出
    )

    return [task_design, task_clinic, task_assess, task_summary]


# --------------------------------------------------------------------------- 执行
def make_crew(agents: dict[str, Agent], tasks: list[Task], verbose: bool) -> Crew:
    """组装 Crew 并返回。

    这里体现 CrewAI 的第二个核心概念：**Crew = 班组 + 流程**。
    - process=Process.sequential：按 tasks 列表顺序执行，前一个完成才做下一个；
    - cache=False：教学示例里关闭 CrewAI 的 LLM 结果缓存，
      否则同一进程内重复调用会拿到旧输出，不利于观察每个环节的真实产出；
    - verbose：控制台是否打印每个 Agent 的思考过程。
    """
    kwargs = dict(
        agents=list(agents.values()),
        tasks=tasks,
        process=Process.sequential,
        verbose=verbose,
    )
    # cache / memory 这两个参数在不同 CrewAI 小版本里存在性不同，
    # 用 try/except 做兼容，避免因为一个可选参数让示例直接崩掉。
    try:
        return Crew(**kwargs, cache=False, memory=False)
    except TypeError:
        return Crew(**kwargs)


def _output_text(obj) -> str:
    """从 CrewAI 的各类输出对象里取出纯文本（兼容不同版本的字段名）。"""
    if obj is None:
        return ""
    for attr in ("raw", "output", "result"):
        value = getattr(obj, attr, None)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return str(obj).strip()


def collect_task_outputs(result, tasks: list[Task]) -> list[str]:
    """收集每个 Task 的最终产出，按任务顺序返回。

    CrewOutput 上通常有 `tasks_output`（TaskOutput 列表），每项 `.raw` 就是文本。
    不同版本字段可能不同，所以优先用 tasks_output，取不到再回退到 task.output。
    """
    raw_list = getattr(result, "tasks_output", None) or []
    texts = [_output_text(item) for item in raw_list]

    if not any(texts):
        texts = [_output_text(getattr(task, "output", None)) for task in tasks]

    # 补齐长度，保证后面按索引取不会越界。
    texts = (texts + [""] * len(tasks))[: len(tasks)]
    return texts


# --------------------------------------------------------------------------- 输出
def _demote_headings(text: str, by: int = 1) -> str:
    """把模型输出里的 Markdown 标题整体降级。

    模型常从 `##` 开始写小标题，直接拼进来会和本脚本的章节标题打架，
    降级后文件目录层级才正确。`by` 控制降几级：
    - 正文（放在 `## 一、...` 下）降 1 级；
    - 附录（放在 `### 附录 X` 下）降 2 级。
    """
    lines: list[str] = []
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("#"):
            level = len(stripped) - len(stripped.lstrip("#"))
            line = "#" * min(level + by, 6) + line[level:]
        lines.append(line)
    return "\n".join(lines)


def render_markdown(
    topic: str,
    level: str,
    group_size: str,
    stage_outputs: list[str],
) -> str:
    """把「汇总教案」放到正文，前三个任务的原始产出放到附录。"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    design, clinic, assess, summary = stage_outputs

    parts: list[str] = []
    parts.append(f"# 医疗教学活动设计：{topic}\n")
    parts.append(
        "> 由 CrewAI 多智能体协作生成：4 个角色、4 个任务，"
        "`Process.sequential` 顺序执行，任务之间用 `context=` 传递产出。\n"
        f">\n"
        f"> 学习者：{level}（{group_size}） · 时长：60 分钟 · 形式：教学查房\n"
        f"> {describe()}\n"
        f"> 生成时间：{now}\n"
    )

    parts.append("---\n")
    parts.append("## 一、完整教案（教研组长整合）\n")
    if summary:
        parts.append(_demote_headings(summary) + "\n")
    else:
        parts.append("（汇总任务没有产生内容，请查看控制台输出排查。）\n")

    parts.append("---\n")
    parts.append("## 二、附录：各环节原始产出\n")
    parts.append(
        "> 以下是各角色在自己任务里交付的原始内容，"
        "保留下来便于对照「整合版」到底做了哪些取舍。\n"
    )

    appendix = [
        ("附录 A · 教学设计（Agent A：教学设计专家）", design),
        ("附录 B · 临床要点（Agent B：心内科带教老师）", clinic),
        ("附录 C · 考核评价（Agent C：考核评价专家）", assess),
    ]
    for title, content in appendix:
        parts.append(f"### {title}\n")
        parts.append(_demote_headings(content, by=2) if content else "（该环节没有产生内容）")
        parts[-1] += "\n"

    return "\n".join(parts).rstrip() + "\n"


# --------------------------------------------------------------------------- CLI
def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="用 CrewAI 多智能体设计一次 60 分钟医疗教学查房（默认 mock 离线可跑）。",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--topic",
        default=DEFAULT_TOPIC,
        help="教学主题",
    )
    parser.add_argument(
        "--level",
        default=DEFAULT_LEVEL,
        help="学习者层级",
    )
    parser.add_argument(
        "--out",
        default=str(DEFAULT_OUT),
        help="Markdown 输出路径（默认写到脚本目录下的 out/）",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="打印每个 Agent 的思考过程（调试用，输出较长）",
    )
    parser.add_argument(
        "--emit-json",
        action="store_true",
        help="以 NDJSON 输出运行事件（供 Web 界面消费）",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.emit_json:
        enable_json_events()
    emit(
        type="start",
        example="crewai",
        topic=args.topic,
        model="mock" if current_mode() == "mock" else model_name(),
        mode=current_mode(),
    )

    # ---- 环境说明 ----------------------------------------------------------
    if _HOME_REDIRECT_MSG:
        print(_HOME_REDIRECT_MSG)
    print("=" * 64)
    print("CrewAI 多智能体示例：医疗教学活动设计")
    print(f"教学主题：{args.topic}")
    print(f"学习者　：{args.level}（{DEFAULT_GROUP_SIZE}）")
    print(describe())
    if current_mode() == "mock":
        print("提示　　：mock 模式输出是确定性的教学素材替身，用于验证多智能体流程本身。")
    print("=" * 64)

    # ---- 组装 Agent / Task / Crew ------------------------------------------
    llm = make_crewai_llm()
    agents = build_agents(llm, verbose=args.verbose)
    tasks = build_tasks(agents, topic=args.topic, level=args.level, group_size=DEFAULT_GROUP_SIZE)

    print(f"\n共 {len(agents)} 个角色、{len(tasks)} 个任务，按 Process.sequential 顺序执行：")
    for index, (name, task) in enumerate(zip(STAGE_NAMES, tasks), start=1):
        print(f"  {index}. {name:<6} ← 角色：{task.agent.role}")

    crew = make_crew(agents, tasks, verbose=args.verbose)

    # ---- 事件：每个 Task 完成时把产出推给 Web 端 ---------------------------
    STAGE_KEYS = ["design", "clinic", "assess", "summary"]

    def make_callback(index: int):
        def _cb(output) -> None:
            text = getattr(output, "raw", None) or str(output)
            emit(type="task", task=STAGE_KEYS[index], phase="end", output=text)
            if index + 1 < len(STAGE_KEYS):
                emit(type="task", task=STAGE_KEYS[index + 1], phase="start")

        return _cb

    for _i, _task in enumerate(tasks):
        _task.callback = make_callback(_i)

    emit(type="task", task="design", phase="start")
    started = time.perf_counter()

    # ---- 执行 --------------------------------------------------------------
    try:
        result = crew.kickoff()
    except Exception as exc:  # noqa: BLE001 —— 教学示例：把错误说明白比抛栈更有用
        emit(type="error", message=f"{type(exc).__name__}: {exc}")
        print(f"\n[错误] Crew 执行失败：{exc}", file=sys.stderr)
        print(
            "排查建议：1) 确认 AGENT_LLM=mock；2) 对照已安装版本检查 "
            "common/llm.py 里 make_crewai_llm 的 BaseLLM 接口；"
            "3) 加 --verbose 看是哪个任务出错。",
            file=sys.stderr,
        )
        return 1

    # ---- 每个任务的完成情况 ------------------------------------------------
    stage_outputs = collect_task_outputs(result, tasks)
    print("\n任务执行结果：")
    for index, (name, text) in enumerate(zip(STAGE_NAMES, stage_outputs), start=1):
        mark = "✓" if text else "✗"
        print(f"  {mark} 任务 {index}/{len(tasks)} {name}：输出 {len(text)} 字")

    # ---- 写文件 ------------------------------------------------------------
    markdown = render_markdown(
        topic=args.topic,
        level=args.level,
        group_size=DEFAULT_GROUP_SIZE,
        stage_outputs=stage_outputs,
    )
    out_path = Path(args.out).expanduser()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(markdown, encoding="utf-8")

    # ---- 收尾摘要 ----------------------------------------------------------
    lines = markdown.splitlines()
    print(f"\n已生成 Markdown：{out_path.resolve()}")
    print(f"文件共 {len(lines)} 行，预览前 8 行：")
    print("-" * 64)
    for line in lines[:8]:
        print(line)
    print("-" * 64)
    print("完成。CrewAI 负责了：拼 prompt、按 sequential 调度 Task、用 context 传上下文、解析 Final Answer。")
    emit(
        type="done",
        markdown=markdown,
        elapsed=round(time.perf_counter() - started, 2),
        meta={"stages": STAGE_NAMES, "out": str(out_path)},
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
