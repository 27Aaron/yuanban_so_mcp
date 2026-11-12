# yuanban_so_mcp

[so.qq.com](https://so.qq.com/)（腾讯元宝搜索）的 MCP server，提供 AI 问答、网页搜索与图片搜索三个工具。无需登录，开箱即用。

## 工具

| 工具 | 说明 |
|---|---|
| `yuanbao_search` | AI 问答，回答含 `[citation:N]` 引用标记；传 `session_id` 可多轮 |
| `web_search` | 网页搜索，返回标题、链接、摘要；`tab` 可选 `xueshu`(学术) / `weixin_article`(公众号) / `weixin_video`(视频) |
| `pic_search` | 图片搜索，返回缩略图、原图、来源页及尺寸 |

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

- 内置 0.3 秒请求间隔。
