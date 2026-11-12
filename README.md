# yuanban_so_mcp

[so.qq.com](https://so.qq.com/)（腾讯元宝搜索）的 MCP server，提供 AI 问答与网页搜索两个工具。无需登录，开箱即用。

## 工具

| 工具 | 说明 |
|---|---|
| `yuanbao_search` | AI 搜索问答，联网检索增强。传入上次返回的 `session_id` 可多轮追问；回答中的 `[citation:N]` 为引用编号 |
| `web_search` | 网页搜索，返回标题、链接、摘要。`tab` 支持 `all`(综合) / `xueshu`(学术) / `weixin_article`(公众号) / `weixin_video`(视频) |

## 快速开始

```bash
uv sync                # 安装依赖（首次）
uv run yuanban_so_mcp  # 启动 stdio server
```

## 接入配置

ZCode / Claude Desktop / Cursor 通用。

```json
{
  "mcpServers": {
    "yuanban_so_mcp": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/27Aaron/yuanban_so_mcp.git", "yuanban_so_mcp"]
    }
  }
}
```

## 说明

- 工具间内置 0.3 秒请求间隔，避免请求过于频繁。
- 网页搜索返回首页结果（约 10 条），暂不支持翻页；图片搜索未提供。
