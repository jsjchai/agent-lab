# 项目名

一句话：**给谁**解决**什么问题**。

## 运行

```bash
cd projects/<项目名>
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp ../../.env.example .env    # 填 key
python main.py "输入"
```

## 架构

（一张图，或三行文字：输入 → 中间步骤 → 输出。标清模型在哪、工具在哪、状态存在哪。）

## 关键决策

| 决策 | 选了 | 理由 | 备选方案 |
|---|---|---|---|
|  |  |  |  |

## 评测

- 用例：`evals/...`（共 N 条）
- 指标：通过率 / 平均 token / 平均延迟
- 当前分数：
- 与上一版对比：

## 已知限制

- 什么情况下会失败、为什么、打算怎么处理：

## 下一步

- [ ]
