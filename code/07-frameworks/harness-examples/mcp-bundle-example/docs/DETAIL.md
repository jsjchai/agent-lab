# 天气 MCP 服务

这个 bundle 演示了如何通过 DeepSeek Harness 连接到外部 MCP (Model Context Protocol) 服务器。

## 什么是 MCP？

MCP 是一种标准化协议，让 AI Agent 能够发现和调用外部工具。通过 MCP，Agent 可以：
- 访问外部 API（天气、地图、数据库等）
- 调用本地命令行工具
- 与第三方服务集成

## 本示例的架构

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   DSH Agent     │────▶│  MCP Client     │────▶│  Weather Server │
│  (对话界面)      │     │  (dsh-mcp-client)│     │  (外部服务)      │
└─────────────────┘     └─────────────────┘     └─────────────────┘
        │                       │                       │
        │  调用工具              │  HTTP/SSE             │  返回数据
        │  mcp__weather__*      │  streamable-http      │
        └───────────────────────┴───────────────────────┘
```

## 启动 MCP 服务器

本示例需要一个运行在 `http://127.0.0.1:3001/mcp` 的天气 MCP 服务器。

### 选项 1：使用官方示例服务器

```bash
# 安装并运行官方 weather MCP 示例
npx @modelcontextprotocol/server-weather
```

### 选项 2：自己实现一个简单的 MCP 服务器

```javascript
// weather-server.js
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/streamableHttp.js";
import express from "express";

const server = new McpServer({
  name: "weather",
  version: "1.0.0"
});

// 注册工具
server.tool(
  "get_weather",
  "获取指定城市的天气信息",
  { city: { type: "string", description: "城市名称" } },
  async ({ city }) => {
    // 实际项目中调用真实天气 API
    return {
      content: [{
        type: "text",
        text: `${city} 今天天气晴朗，气温 25°C，湿度 60%。`
      }]
    };
  }
);

const app = express();
app.use(express.json());

app.post("/mcp", async (req, res) => {
  const transport = new StreamableHTTPServerTransport({
    sessionIdGenerator: undefined
  });
  await server.connect(transport);
  await transport.handleRequest(req, res, req.body);
});

app.listen(3001, () => {
  console.log("Weather MCP server running on http://127.0.0.1:3001/mcp");
});
```

运行：
```bash
node weather-server.js
```

## 安装 Bundle

1. 确保 MCP 服务器已启动
2. 在 DSH Web GUI 中：Plugins → Add plugin → 选择此目录
3. 或使用 `plugin_manager` 工具安装

## 验证连接

安装成功后，在对话中询问天气相关问题，Agent 会自动调用 `mcp__weather__get_weather` 工具。

示例对话：
```
用户：北京今天天气怎么样？
Agent：[调用 mcp__weather__get_weather] 北京今天天气晴朗，气温 25°C...
```

## 配置说明

`cordis.patch.yml` 中的关键配置：

| 字段 | 说明 |
|------|------|
| `serverName` | 服务器标识符，工具名前缀为 `mcp__<serverName>__` |
| `transport` | 传输方式：`streamable-http` 或 `stdio` |
| `url` | MCP 服务器地址 |
| `failOnStartupError` | 服务器不可用时是否阻止插件加载 |

## stdio 传输示例

如果要连接本地命令行 MCP 服务器：

```yaml
- insert:
    - id: local-tools-mcp
      name: '@deepseek-ai/dsh-mcp-client'
      config:
        serverName: local-tools
        transport: stdio
        command: npx
        args: ["-y", "@modelcontextprotocol/server-filesystem", "/path/to/workspace"]
```

## 故障排查

- **工具未出现**：检查 MCP 服务器是否正常运行
- **连接超时**：确认 URL 和端口正确
- **认证失败**：某些 MCP 服务器需要 API key，通过 `env` 配置传递
