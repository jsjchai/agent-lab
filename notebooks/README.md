# notebooks · 探索性实验

放**还在试错**的东西：数据探索、临时画图、prompt 对比、参数扫描。不追求整洁，不保证可复现。

## 约定

- 命名 `YYYY-MM-DD-主题.ipynb`，顶部写清「想验证什么」。
- 试出稳定结论后，把可复用部分提炼成 `code/` 或 `projects/` 里的脚本，笔记写进 `docs/`。
- 大输出（图、缓存）不进 git；`.ipynb_checkpoints/` 已忽略。
- 不在 notebook 里硬编码 API key，从 `.env` 读。

## 与正式代码的区别

| | notebooks/ | code/ · projects/ |
|---|---|---|
| 目的 | 探索、试错 | 可复现、可验收 |
| 整洁度 | 不要求 | 必须能单独跑通 |
| 是否进验收 | 否 | 是（run_all / selftest） |

当前暂无 notebook；医疗与教学示例的对比实验已直接做成脚本
（[bench_models.py](../code/07-frameworks/medical-education/bench_models.py)、
[m11_model_bench.py](../projects/teaching-agent/m11_model_bench.py)）。
