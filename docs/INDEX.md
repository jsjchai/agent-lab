# 文档总索引

> 本页是全仓库文档的**唯一总入口**：按主题列出每章的状态、篇幅与对应代码，避免「找不到/以为没有」。
> 更新规则见文末「文档规范」。最后核对：2026-11-23。

状态：**☐ 提纲**（只有 README）｜**◐ 进行中**｜**☑ 已成章**（有完整章节 + 代码/验证）

---

## 一、知识章节（`docs/`）

### 02 · 提示与上下文工程（5 章 ☑）

| 章节 | 主题 | 行数 | 代码实验 |
|---|---|---|---|
| [01-意图识别](02-prompt-context/01-intent-recognition.md) | 意图/槽位/多意图/置信度；调接口 vs 问答路由 | 540 | [intent_recognition.py](../code/02-prompt-context/intent_recognition.py) |
| [02-接口 40 参策略](02-prompt-context/02-api-param-strategy.md) | 参数六层分层、40→5 换算、草稿优先 | 555 | [large_api_params.py](../code/02-prompt-context/large_api_params.py) |
| [03-Agent 意图路由设计](02-prompt-context/03-agent-intent-routing.md) | 路由表/打分/阈值边距/四类判据/置信度校准 | 409 | [intent_router.py](../code/02-prompt-context/intent_router.py) · [confidence_calibration.py](../code/02-prompt-context/confidence_calibration.py) |
| [04-小模型意图优化](02-prompt-context/04-small-model-intent-optimization.md) | 失败模式、七层优化阶梯、7B/8B 实测 | 221 | [small_model_optimization.py](../code/02-prompt-context/small_model_optimization.py) |
| [05-JEV 与 System One](02-prompt-context/05-jev-system-one-decision-models.md) | 非生成式决策接口、校验、风险 | 224 | [jev_decision_demo.py](../code/02-prompt-context/jev_decision_demo.py) |

### 05 · 规划与推理（2 章 ☑）

| 章节 | 主题 | 行数 | 代码实验 |
|---|---|---|---|
| [01-模型做规划](05-planning/01-planning-with-models.md) | Plan-and-Execute vs ReAct、计划=步骤依赖 | 197 | [planning_demo.py](../code/05-planning/planning_demo.py) |
| [02-计划校验与重规划](05-planning/02-plan-validation-and-replan.md) | 四类校验、局部重规划、终止条件 | 181 | 同上 |

### 11 · Harness Engineering（11 章 ☑，质量标杆）

| 章节 | 主题 | 行数 |
|---|---|---|
| [01-为什么需要 Harness](11-harness-engineering/01-introduction.md) | 四堵墙、五职责、日志即真相 | 212 |
| [02-核心概念](11-harness-engineering/02-core-concepts.md) | 四层次、五对易混概念 | 93 |
| [03-架构](11-harness-engineering/03-architecture.md) | Cordis/profile/bundle/patch | 129 |
| [04-执行循环](11-harness-engineering/04-execution-loop.md) | step/turn、取消、重试 | 196 |
| [05-上下文工程](11-harness-engineering/05-context-engineering.md) | 组装/压缩/注入 | 142 |
| [06-工具工程](11-harness-engineering/06-tool-engineering.md) | 流水线/单调守卫/fail-closed | 176 |
| [07-执行环境](11-harness-engineering/07-execution-environment.md) | seam/共享世界/沙箱 | 155 |
| [08-错误恢复](11-harness-engineering/08-error-recovery.md) | checkpoint/悬空修复 | 141 |
| [09-安全边界](11-harness-engineering/09-security.md) | 纵深防御/最小权限 | 130 |
| [10-生产实践](11-harness-engineering/10-production-practice.md) | 长任务/可观测/评测 | 128 |
| [11-总结](11-harness-engineering/11-summary.md) | 知识图谱/学习路径 | 106 |

配套实验（7 个，全离线可跑）：`minimal_harness` / `execution_loop` / `tool_pipeline` /
`context_window` / `sandbox_env` / `checkpoint_recovery` / `injection_defense`，见 [code/11-harness-experiments](../code/11-harness-experiments/)。

### 其余主题（仅 README 提纲 ◐/☐）

| 主题 | 状态 | 已有内容 |
|---|---|---|
| [01-foundations](01-foundations/README.md) | ◐ | LLM 基础、Agent vs Workflow、ReAct（配套 teaching m01/m05） |
| [03-tool-use](03-tool-use/README.md) | ◐ | Function Calling、工具设计、MCP（配套 m04） |
| [04-memory-rag](04-memory-rag/README.md) | ◐ | 记忆/检索/知识库（配套 m06） |
| [06-multi-agent](06-multi-agent/README.md) | ☐ | 只有提纲（多智能体何时值得） |
| [07-frameworks](07-frameworks/README.md) | ◐ | LangGraph/CrewAI/DSH 选型（配套 medical-education） |
| [08-eval-observability](08-eval-observability/README.md) | ◐ | 评测集/LLM-as-judge/tracing（配套 m08） |
| [09-safety-guardrails](09-safety-guardrails/README.md) | ◐ | 注入/权限/确认（配套 m07） |
| [10-production](10-production/README.md) | ◐ | 成本/延迟/部署（配套 m09/m10） |

---

## 二、项目教材（`projects/teaching-agent/docs`，12 篇 ☑）

| 文档 | 行数 |
|---|---|
| [00-总览](../projects/teaching-agent/docs/00-总览.md) | 84 |
| [01-LLM基础与结构化输出](../projects/teaching-agent/docs/01-LLM基础与结构化输出.md) | 139 |
| [02-Prompt与上下文工程](../projects/teaching-agent/docs/02-Prompt与上下文工程.md) | 140 |
| [03-模型接入与流式接口](../projects/teaching-agent/docs/03-模型接入与流式接口.md) | 138 |
| [04-工具调用与业务工具设计](../projects/teaching-agent/docs/04-工具调用与业务工具设计.md) | 143 |
| [05-Agent工作流编排](../projects/teaching-agent/docs/05-Agent工作流编排.md) | 182 |
| [06-RAG与知识问答](../projects/teaching-agent/docs/06-RAG与知识问答.md) | 150 |
| [07-安全治理与人工确认](../projects/teaching-agent/docs/07-安全治理与人工确认.md) | 144 |
| [08-评测与质量门禁](../projects/teaching-agent/docs/08-评测与质量门禁.md) | 313 |
| [09-模型部署与路由](../projects/teaching-agent/docs/09-模型部署与路由.md) | 294 |
| [10-分布式可靠性](../projects/teaching-agent/docs/10-分布式可靠性.md) | 384 |
| [11-模型横向对比](../projects/teaching-agent/docs/11-模型横向对比.md) | 310 |

---

## 三、审计与规划

| 文档 | 内容 |
|---|---|
| [V2.0 审计报告](audit/v2.0-audit-report.md) | 阶段 A：现状、问题（P0/P1/P2）、变更清单 |
| [V2.0 架构方案](audit/v2.0-architecture-plan.md) | 阶段 B：目录、五目录职责、质量门禁、选型 |

---

## 四、代码实验索引（`code/`）

| 目录 | 实验 | 说明 |
|---|---|---|
| `02-prompt-context` | 6 个 | 意图识别、40 参、路由、置信度校准、小模型优化、JEV 模拟 |
| `05-planning` | 1 个 | 规划/校验/重规划 |
| `07-frameworks` | 3 套 | medical-education（LangGraph+CrewAI）、harness-examples（DSH 插件） |
| `11-harness-experiments` | 7 个 | Harness 核心机制 |
| `01/03/04/06/08/09/10` | 0 | 仅导航 README（待补最小实验） |

---

## 五、文档规范（新增文档请遵守）

1. **命名**：`NN-主题.md`（两位数、连字符），主题目录内 `README.md` 作门面（学习目标/前置/章节地图/代码映射）。
2. **每章结构**：问题背景 → 核心概念 → 工作原理 → Mermaid（图后必须解释）→ 代码实现（可运行 + 讲解）→ 深入分析（取舍）→ 工程实践 → 总结 → 参考。
3. **状态标记**：☐ 提纲 / ◐ 进行中 / ☑ 已成章；**升级 ☑ 必须有代码或验证证据**。
4. **质量优先于数量**：宁缺毋滥；不写空壳章节、不堆概念、不抄袭式翻译。
5. **链接必须可点**：相对路径；提交前跑链接检查（见下）。
6. **代码锚点**：每章标注对应 demo 文件与运行命令；demo 必须离线可跑、带 selftest。
7. **事实标注**：外部数据标明来源与性质（官方/社区/二手/厂商声明），不确定的写「未验证」。

**提交前自检**：

```bash
# 链接检查（剥离代码块后检查所有相对链接）
python3 - <<'PY'
import re, pathlib
bad = []
for p in pathlib.Path('docs').rglob('*.md'):
    t = re.sub(r'```.*?```', '', p.read_text(), flags=re.S)
    t = re.sub(r'`[^`]*`', '', t)
    for m in re.finditer(r'\[[^\]]*\]\(([^)\s]+)\)', t):
        tgt = m.group(1)
        if tgt.startswith(('http', '#')): continue
        if not (p.parent / tgt.split('#')[0]).resolve().exists():
            bad.append(f'{p}: {tgt}')
print('坏链:', bad or '无')
PY
```
