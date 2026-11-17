# evals · 评测集与脚本

本目录存放**跨项目共享**的评测集与评分脚本。当前教学场景的评测实现集中在
[projects/teaching-agent/](../projects/teaching-agent/README.md)，此处做索引与约定。

## 现有评测资产

| 资产 | 位置 | 说明 |
|---|---|---|
| Golden Set（30 条种子） | [golden_set.jsonl](../projects/teaching-agent/golden_set.jsonl) | 7 类：正常/缺项/非法/可答/无答案/注入/越权 |
| 评测门禁脚本 | [m08_eval.py](../projects/teaching-agent/m08_eval.py) | 6 项指标对照门槛，确定性断言 |
| 模型横向对比 | [m11_model_bench.py](../projects/teaching-agent/m11_model_bench.py) | 准确率/漂移/重试/延迟 + RAG 引用/拒答 |
| 安全测试套件 | [m07_security.py](../projects/teaching-agent/m07_security.py) | 12 项对抗用例 |

## 约定

- **业务规则 / 权限 / 数据一致性用确定性断言**；表达质量才用 LLM-as-Judge。
- 每条用例一个 JSON：`{id, category, input/draft, user, expect_*}`。
- 线上 bad case 持续回流进 Golden Set，形成回归闭环。
- 目标 ≥100 条（源文档 §12）；扩展方法见 [项目 README 第六节](../projects/teaching-agent/README.md)。

## 跑评测

```bash
cd projects/teaching-agent
../../.venv/bin/python m08_eval.py        # 门禁指标 + out/eval_report.md
../../.venv/bin/python m11_model_bench.py # 模型对比（需 Ollama）
```
