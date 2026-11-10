# 医疗教学 Agent：LangGraph vs CrewAI 对照实现

同一个业务——**为内科住院医师设计教学活动**——用两个框架各写一遍。
目的不是比谁强，而是亲手体会两者把复杂度放在了不同的地方：

- **LangGraph** 让你画流程：状态、节点、条件边、回环。
- **CrewAI** 让你写角色：人设、任务卡、上下文传递。

| | 例 1 · 临床教学案例生成 | 例 2 · 教学查房设计 |
|---|---|---|
| 框架 | LangGraph 1.2 | CrewAI 1.15 |
| 文件 | [langgraph_case_agent.py](langgraph_case_agent.py) | [crewai_teaching_activity.py](crewai_teaching_activity.py) |
| 业务 | 生成教学病例 + 分层问题，专家评审不过就返工 | 4 个角色协作，产出一份 60 分钟 Teaching Round 教案 |
| 核心机制 | `StateGraph` + `add_conditional_edges` + 回环 | `Agent`(role/goal/backstory) + `Task(context=…)` + `Process.sequential` |
| 输出 | `out/langgraph_teaching_case.md` | `out/crewai_teaching_activity.md` |
| 适合的活 | 流程固定但需要重试/审判/断点续跑 | 职责分工清晰、产出可流水线串起来 |

## 快速开始

```bash
# 1. 装依赖（仓库根目录，一次性）
cd /Users/jsjchai/agent-lab
export UV_CACHE_DIR="$PWD/.uv-cache"          # 沙箱环境用；普通终端可省
uv venv .venv --python 3.11
uv pip install --python .venv/bin/python -r code/07-frameworks/medical-education/requirements.txt

# 2. 跑两个例子（默认离线 mock，不需要 API key）
cd code/07-frameworks/medical-education
AGENT_LLM=mock ../../../.venv/bin/python langgraph_case_agent.py
AGENT_LLM=mock ../../../.venv/bin/python crewai_teaching_activity.py

# 3. 换个主题，确认没有写死
AGENT_LLM=mock ../../../.venv/bin/python langgraph_case_agent.py --topic "急性胸痛"
AGENT_LLM=mock ../../../.venv/bin/python crewai_teaching_activity.py --topic "急性腹痛"
```

## 为什么要做 mock 模式

两个例子的**流程**（状态机、回环、任务编排）与模型能力无关，但**内容质量**强烈依赖模型。
把 LLM 抽到 [common/llm.py](common/llm.py) 后：

- `AGENT_LLM=mock`（默认）：确定性输出，30 秒内跑完，**不需要任何 key**，方便读代码、跑测试、理解流程；
- `AGENT_LLM=openai`：任何 OpenAI 兼容接口（OpenAI / DeepSeek / Qwen / vLLM / Ollama），产出真实内容。

mock 不是"假数据糊弄"，它特意模拟了**真实的失败路径**：LangGraph 例子里第一轮评审只给 78 分
（不通过），触发一次修订，第二轮 88 分才通过。这样你不用 API key 也能看到条件边和回环真的在工作。

## 例 1 · LangGraph：一条带审判回环的生产线

```
plan ──▶ draft_case ──▶ design_questions ──▶ review ──┬──(score<80 且修订<2)──▶ revise ──┐
                                                       │                                   │
                                                       └──(通过 / 次数用尽)──▶ finalize ◀──┘
```

值得停下来看的三处代码：

1. **`TeachingState`**（约第 48 行）：整张图共享的状态。`reviews` 和 `notes` 用
   `Annotated[list, operator.add]` 声明成"追加"，节点只要返回增量，合并由框架做。
2. **`route_after_review`**（约第 175 行）：整个例子的"决策中心"——**回不回退、最多回几次，是代码不是 prompt**。
   改 `PASS_SCORE` 或 `MAX_REVISIONS` 就能看到行为变化。
3. **`add_conditional_edges` + `revise → review`**：条件边和回环。这也正是 LangGraph
   和"一条链式 Prompt"最重要的差别：**失败路径是一等公民**。

试一下：

```bash
# 看图的定义（Mermaid，粘到支持 Mermaid 的 Markdown 里就能渲染）
AGENT_LLM=mock ../../../.venv/bin/python langgraph_case_agent.py --show-graph

# 把及格线调高，观察修订次数如何被封顶
sed -i '' 's/PASS_SCORE = 80/PASS_SCORE = 95/' langgraph_case_agent.py
AGENT_LLM=mock ../../../.venv/bin/python langgraph_case_agent.py
```

## 例 2 · CrewAI：四个角色开一次教研会

| 角色 | 职责 | 产出 |
|---|---|---|
| 教学设计专家 | 目标（Bloom 分层）、60 分钟流程表 | 教学目标 + 时间分配 |
| 心内科带教老师 | 临床主线、学员五大常见误区、追问设计 | 临床要点 |
| 考核评价专家 | Mini-CEX 七项评分表、3 道病例题、反馈机制 | 评价方案 |
| 教研组长 | 汇总前三份产出 | 可直接上课的完整教案 |

四个 `Task` 用 `context=[...]` 串成一条链：后一个任务能读到前一个任务的产出，
不用手写字符串拼接——这是 CrewAI 最省事的地方。

值得注意的两点：

1. **`Agent` 写的是"人设"，不是 prompt**。`role/goal/backstory` 会被框架拼进系统提示词。
   好处是意图清晰、可复用；代价是**你看不到最终 prompt**，出问题排查成本更高（打开 `--verbose` 能看到）。
2. **CrewAI 没有显式全局状态**。所有数据靠 `context=` 单向流动，所以"评审不通过就回退重做"
   这类回环，用 CrewAI 写会很别扭——这正是例 1 用 LangGraph 的原因。

## 接真实模型

```bash
export AGENT_LLM=openai
export OPENAI_API_KEY=sk-...
export AGENT_MODEL=gpt-4o-mini          # 或 deepseek-chat / qwen-plus
# export OPENAI_BASE_URL=https://api.deepseek.com/v1   # 非 OpenAI 官方时

../../../.venv/bin/python langgraph_case_agent.py --topic "急性胸痛"
../../../.venv/bin/python crewai_teaching_activity.py --topic "急性腹痛" --verbose
```

切到真实模型后建议观察：`review` 节点的 JSON 是否稳定、分数是否合理、
`route_after_review` 是否真的会被触发（这是检验"评测是否可信"的起点）。

## 小模型（本地 7B/8B）怎么跑

本机装好 [Ollama](https://ollama.com/) 后，用 OpenAI 兼容接口即可，不用改代码：

```bash
ollama pull qwen2.5:7b            # 一次性，约 4.7 GB

export AGENT_LLM=openai
export OPENAI_BASE_URL=http://localhost:11434/v1
export OPENAI_API_KEY=ollama      # 本地服务不校验，随便填

../../../.venv/bin/python langgraph_case_agent.py --model qwen2.5:7b
AGENT_MODEL=qwen2.5:7b ../../../.venv/bin/python crewai_teaching_activity.py
```

### 小模型会在哪儿翻车（实测，M2 Max 32G）

| 配置 | 耗时 | 表现 |
|---|---|---|
| mock | 1.5 s | 流程正确，用于测代码 |
| qwen2.5:7b **未适配** | 64 s | ① 把「90 分钟教学」写成「4 周、70 小时」；② 评审给 85 分、同时列 6 条问题、`verdict=needs_revision`——而路由只看分数，**直接放行** |
| qwen2.5:7b **适配后** | 5～40 min | 守住 90 分钟（三项目标各 30 分钟、合计 90）；评审 3 轮均为 85 分，修订 2 次后按 `MAX_REVISIONS` 封顶 |
| qwen2.5:7b（CrewAI） | 4 min | 4 个任务全部完成，产出 393 行，结构完整但比 mock 啰嗦 4 倍 |

### 为此做了五件事

1. **硬约束（`small_only`）**：小模型档位才追加「只做一次 90 分钟」「不超过 500 字」这类边界，大模型不加。
2. **结构化输出 + 校验重试（`complete_json`）**：字段缺失/类型不对，就把错误回灌给模型重试，最多 2 次。
3. **一致性纠正 + 路由改为 `verdict && score`**：宁可判不通过，也别被"高分低评"骗过去放行。
4. **输出上限**：小模型默认 `max_tokens=900`，结构化调用温度 0。
5. **客户端超时与重试**：`AGENT_TIMEOUT`（默认 180 秒）、`AGENT_MAX_RETRIES`（默认 1）。
   本地模型抖动极大——同一份代码实测跑过 5 分钟，也跑过 41 分钟，没有超时就会静默挂死。

档位自动判定：模型名里含 `7b`/`8b`/`mini`/`flash` 等即视为小模型，也可用 `AGENT_PROFILE=small|large` 强制。
CrewAI 侧 LiteLLM 需要 `provider/model` 形式，接本地服务时会自动补 `openai/` 前缀。

### 换模型前先体检

```bash
AGENT_LLM=openai OPENAI_BASE_URL=http://localhost:11434/v1 OPENAI_API_KEY=ollama \
  ../../../.venv/bin/python bench_models.py --models qwen2.5:7b qwen3:8b --runs 2
```

它测三件与模型规模强相关、又最容易让 Agent 崩掉的事：

| 检查项 | 为什么重要 |
|---|---|
| JSON 合规率 | 评审/打分节点能不能用 |
| 是否守住 90 分钟 | 指令跟随，跑偏一次整份教案就废了 |
| 平均耗时 / 字数 | 决定迭代速度和 token 成本 |

实测（同一组 prompt，各 2 轮）：

| 模型 | JSON 合规 | 守住 90 分钟 | 平均耗时 | 平均字数 |
|---|---|---|---|---|
| `qwen2.5:7b` | 2/2 | 2/2 | 7.7 s | 402 |
| `qwen3:8b` | 2/2 | 2/2 | 24.9 s | 381 |

注意这个结果**不代表小模型没问题**：单条 prompt 它们都能过，但放进完整流程里就退化了——
上面「未适配」那行的 64 秒里，7B 同时做到了「跑偏成 4 周」和「85 分 + needs_revision」两件事。
原因是多步流程里上下文不断变长、上游产出质量参差，模型在第 3、4 步时已经偏离了第一条指令。

**结论**：7B 级模型在"能说人话"上够用，在"守格式、守边界"上必须靠代码兜底——
这就是把校验、重试、回环上限写成代码而不是 prompt 的原因。


## 两个框架怎么选

| 维度 | LangGraph | CrewAI |
|---|---|---|
| 抽象单位 | 节点 + 状态 + 边 | 角色 + 任务 |
| 流程控制 | 显式（你自己画） | 隐式（按 tasks 顺序） |
| 回退/重试 | 原生支持（条件边 + 回环） | 需要自己包一层 |
| 断点续跑 | 有 checkpointer | 较弱 |
| 上手速度 | 慢一点（要先想清状态） | 快（写好人设就能跑） |
| 调试难度 | 低（流程可见） | 较高（prompt 被框架拼装） |
| 典型场景 | 有明确质量门禁、需要返工的长流程 | 角色分工清晰的内容生产流水线 |

一句话：**流程会打回重做的，用 LangGraph；一顺到底分工协作的，用 CrewAI。**
两者也可以混用——用 LangGraph 管流程，把某个节点内部实现成一个 Crew。

## 目录

```
medical-education/
├── common/llm.py               # 统一 LLM 适配层（mock / openai / 小模型档位）
├── langgraph_case_agent.py     # 例 1
├── crewai_teaching_activity.py # 例 2
├── bench_models.py             # 模型体检：JSON 合规 / 指令边界 / 速度
├── requirements.txt
└── out/                        # 生成的教案
```

## 排错

- **`PermissionError: ... Library/Application Support`**：CrewAI 1.x 在 **import 阶段**就会初始化本地存储
  （SQLite/缓存），默认写在用户家目录。在容器、CI 或"只允许写工作区"的沙箱里会直接失败。
  [crewai_teaching_activity.py](crewai_teaching_activity.py) 顶部已经处理好了：
  把 `CREWAI_STORAGE_DIR` 指到脚本目录下的 `.crewai-home/`，并在**探测到家目录不可写时自动重定向 `HOME`**。
  普通终端下家目录可写，这段逻辑不会触发，也不会多建目录。
- **`ModuleNotFoundError: crewai`**：依赖装在仓库根的 `.venv`，注意从本目录出发要用 `../../../.venv/bin/python`。
- **CrewAI 卡住不动**：检查网络。mock 模式已关闭遥测，真实模式需要能访问模型接口。
- **想清掉运行产物**：`rm -rf out .crewai-home __pycache__`，重新跑即可再生。

## 内容声明

所有病例均为**模拟病例**，不含真实患者信息；教案用于医学教育演练，
不构成诊疗建议。真实教学场景中还需遵守所在机构的病例使用与隐私规范。
