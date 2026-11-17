# DeepSeek Harness 扩展示例

本目录包含三个 DeepSeek Harness (DSH) 扩展示例，演示如何通过插件机制定制和增强 DSH 的能力。

## 示例概览

| 示例 | 类型 | 说明 | 难度 |
|------|------|------|------|
| [review-preset](./review-preset/) | Agent Preset | 自定义只读代码审查 Agent | ⭐ 入门 |
| [medical-tool-plugin](./medical-tool-plugin/) | Host Plugin | 为 Agent 添加医疗教学工具 | ⭐⭐ 进阶 |
| [mcp-bundle-example](./mcp-bundle-example/) | MCP Bundle | 连接外部 MCP 服务器 | ⭐⭐ 进阶 |

## 什么是 DeepSeek Harness？

DeepSeek Harness 是一个可扩展的 AI Agent 框架，核心特点：

- **插件化架构**：通过 Cordis 插件系统扩展功能
- **多种扩展点**：Agent Preset、Host Plugin、MCP Bundle、UI Plugin 等
- **配置驱动**：大部分定制通过 YAML 配置完成，无需编写复杂代码

## 三种扩展方式对比

```
┌─────────────────────────────────────────────────────────────────┐
│                    DeepSeek Harness 扩展体系                      │
├─────────────────┬─────────────────┬─────────────────────────────┤
│  Agent Preset   │  Host Plugin    │      MCP Bundle             │
├─────────────────┼─────────────────┼─────────────────────────────┤
│ 定义 Agent 的   │ 为 Agent 添加   │ 连接外部 MCP 服务器          │
│ 能力组合        │ 新工具/服务     │ 获取外部工具                 │
├─────────────────┼─────────────────┼─────────────────────────────┤
│ • persona       │ • ctx.tools     │ • streamable-http           │
│ • tools 选择    │   .register()   │ • stdio                     │
│ • 插件列表      │ • ctx.effect()  │ • 自动发现工具               │
├─────────────────┼─────────────────┼─────────────────────────────┤
│ 纯配置 (YAML)   │ 需要 JS 代码    │ 纯配置 (YAML)               │
│ 无运行时依赖    │ 运行在 Host 进程 │ 依赖外部服务器               │
└─────────────────┴─────────────────┴─────────────────────────────┘
```

## 快速开始

### 前置条件

1. 安装 DeepSeek Harness Desktop 或 Web 版本
2. 确保可以访问 Plugins 管理界面

### 安装示例插件

每个示例都是一个独立的 bundle，安装方式相同：

**方式 1：Web GUI（推荐）**
1. 打开 DSH Web GUI → 左侧栏 Plugins
2. 点击 "Add plugin" → 选择示例目录
3. 等待安装完成，在插件列表中启用

**方式 2：plugin_manager 工具**
```javascript
// 在 Agent 对话中使用
plugin_manager({
  action: 'install_bundle',
  target: '/absolute/path/to/review-preset'
})
```

## 示例详解

### 1. review-preset：自定义 Agent Preset

**场景**：创建一个只能审查代码、不能修改代码的 Agent。

**核心概念**：
- Agent Preset 是 Agent 能力的「配方」
- 通过组合不同的插件（persona、tools 等）定义 Agent 行为
- 纯 YAML 配置，无需编写代码

**文件结构**：
```
review-preset/
├── package.json      # Bundle 清单
└── cordis.patch.yml  # 插件配置（核心）
```

**关键配置**：
```yaml
plugins:
  - id: persona
    config:
      prefix: "你是代码审查专家..."  # 系统提示词
  - id: tool-bash
    # 只给 bash，不给 fs（read/write/edit）
    # 这样 Agent 只能查看文件，不能修改
```

**使用场景**：
- 代码审查流程
- 安全审计（防止 Agent 误操作）
- 教学演示（展示最小权限原则）

---

### 2. medical-tool-plugin：Host Plugin 开发

**场景**：为 Agent 添加医疗教育专用工具。

**核心概念**：
- Host Plugin 运行在 DSH Host 进程中
- 通过 `ctx.tools.register()` 注册新工具
- 工具可以被任何使用该插件的 Agent 调用

**文件结构**：
```
medical-tool-plugin/
├── package.json      # Bundle 清单
├── cordis.patch.yml  # 插件注册
├── index.js          # 插件代码（核心）
├── locale/           # 国际化
│   ├── en.json
│   └── zh.json
└── icon.svg          # 插件图标
```

**提供的工具**：

| 工具名 | 功能 | 参数 |
|--------|------|------|
| `medical_case_generator` | 生成模拟临床病例 | topic, level, complexity |
| `teaching_plan_validator` | 验证教学计划规范性 | plan (Markdown) |

**代码要点**：
```javascript
export function apply(ctx, config) {
  return ctx.effect(() => {
    // 注册工具
    const unregister = ctx.tools.register({
      name: 'my_tool',
      description: '工具描述...',
      parameters: { /* JSON Schema */ },
      async execute(args) {
        // 工具逻辑
        return { content: [{ type: 'text', text: '结果' }] };
      }
    });
    
    // 返回清理函数
    return () => unregister();
  });
}
```

**使用场景**：
- 领域专用工具（医疗、法律、金融等）
- 内部 API 封装
- 复杂业务逻辑

---

### 3. mcp-bundle-example：MCP Bundle

**场景**：连接外部 MCP 服务器，获取天气查询等工具。

**核心概念**：
- MCP (Model Context Protocol) 是标准化的工具协议
- MCP Bundle 是配置型插件，无需编写代码
- 自动发现并注册 MCP 服务器提供的所有工具

**文件结构**：
```
mcp-bundle-example/
├── package.json      # Bundle 清单
├── cordis.patch.yml  # MCP 连接配置
├── locale/           # 国际化
├── docs/DETAIL.md    # 详细说明
└── icon.svg          # 插件图标
```

**配置示例**：
```yaml
- insert:
    - id: weather-mcp
      name: '@deepseek-ai/dsh-mcp-client'
      config:
        serverName: weather
        transport: streamable-http
        url: http://127.0.0.1:3001/mcp
```

**工具命名规则**：
MCP 工具自动命名为 `mcp__<serverName>__<toolName>`，例如：
- `mcp__weather__get_weather`
- `mcp__weather__get_forecast`

**使用场景**：
- 集成第三方 API（天气、地图、支付等）
- 连接企业内部服务
- 复用已有的 MCP 服务器生态

---

## 开发自己的插件

### 选择扩展方式

| 需求 | 推荐方式 |
|------|----------|
| 只想调整 Agent 的行为/工具组合 | Agent Preset |
| 需要添加新的工具或服务 | Host Plugin |
| 想连接已有的外部服务 | MCP Bundle |
| 需要自定义 UI 组件 | UI Plugin（本目录未包含） |

### 开发流程

1. **复制模板**：从本目录复制最接近的示例
2. **修改配置**：编辑 `package.json` 和 `cordis.patch.yml`
3. **实现逻辑**（Host Plugin）：编写 `index.js`
4. **本地测试**：通过 Web GUI 安装并测试
5. **迭代优化**：根据反馈调整

### 调试技巧

- **查看插件状态**：Plugins 页面可以看到插件是否激活、有无错误
- **查看工具列表**：在对话中输入 `/` 可以看到可用工具
- **查看日志**：DSH 的终端输出会显示插件加载信息

## 参考资料

- [DSH 官方文档](https://github.com/deepseek-ai/dsh)
- [Cordis 插件系统](https://github.com/nicedoc/cordis)
- [MCP 协议规范](https://modelcontextprotocol.io/)

## 目录结构

```
harness-examples/
├── README.md                 # 本文件
├── review-preset/            # 示例 1：Agent Preset
│   ├── package.json
│   └── cordis.patch.yml
├── medical-tool-plugin/      # 示例 2：Host Plugin
│   ├── package.json
│   ├── cordis.patch.yml
│   ├── index.js
│   ├── locale/
│   │   ├── en.json
│   │   └── zh.json
│   └── icon.svg
└── mcp-bundle-example/       # 示例 3：MCP Bundle
    ├── package.json
    ├── cordis.patch.yml
    ├── locale/
    │   ├── en.json
    │   └── zh.json
    ├── docs/
    │   └── DETAIL.md
    └── icon.svg
```
