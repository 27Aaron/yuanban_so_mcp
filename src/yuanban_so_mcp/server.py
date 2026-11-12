"""yuanban_so_mcp: 腾讯元宝搜索 MCP server (stdio)。

工具：
- yuanbao_search: AI 问答（多轮 session）
- web_search:     网页搜索（学术/公众号/视频 tab）
- pic_search:     图片搜索（缩略图/原图/来源页）
"""

from __future__ import annotations

from mcp.server import MCPServer

from .client import VALID_TABS, get_client

mcp = MCPServer(
    name="yuanban_so_mcp",
    instructions=(
        "腾讯元宝搜索（so.qq.com）工具集。"
        "AI 问答用 yuanbao_search（传 session_id 可多轮）；"
        "网页结果用 web_search；"
        "图片素材用 pic_search。"
    ),
)


@mcp.tool()
async def yuanbao_search(query: str, session_id: str | None = None) -> str:
    """元宝 AI 搜索问答，回答含 [citation:N] 引用标记。

    传入上次返回的 session_id 可继续追问。

    Args:
        query: 问题。
        session_id: 上次返回的会话 id，留空则新建。
    """
    client = get_client()
    result = await client.ask(query, session_id=session_id)
    return result.answer + f"\n\n---\nsession_id: `{result.session_id}`"


@mcp.tool()
async def web_search(query: str, tab: str = "all", limit: int = 10) -> str:
    """网页搜索，返回标题、链接、摘要。

    Args:
        query: 关键词。
        tab: all(综合) / xueshu(学术) / weixin_article(公众号) / weixin_video(视频)。
        limit: 条数，1-20。
    """
    if tab not in VALID_TABS:
        return f"不支持的 tab: {tab}，可选: {sorted(VALID_TABS)}"
    limit = max(1, min(int(limit), 20))
    client = get_client()
    results = await client.web_search(query, tab=tab, limit=limit)
    if not results:
        return f"未找到结果（query={query!r}, tab={tab}）"
    lines = []
    for i, r in enumerate(results, 1):
        lines.append(f"{i}. [{r.title}]({r.url})")
        if r.summary and r.summary != r.title:
            lines.append(f"   {r.summary}")
    return "\n".join(lines)


@mcp.tool()
async def pic_search(query: str, limit: int = 10) -> str:
    """图片搜索，返回缩略图、原图、来源页及尺寸。

    Args:
        query: 关键词。
        limit: 条数，1-20。
    """
    limit = max(1, min(int(limit), 20))
    client = get_client()
    results = await client.pic_search(query, limit=limit)
    if not results:
        return f"未找到图片（query={query!r}）"
    lines = []
    for i, r in enumerate(results, 1):
        size = f"{r.width}×{r.height}" if r.width and r.height else "尺寸未知"
        site = f" · {r.site}" if r.site else ""
        lines.append(f"{i}. **{r.title or '（无标题）'}**（{size}{site}）")
        lines.append(
            f"   缩略图: {r.thumb_url} | 原图: {r.image_url}"
            + (f" | 来源页: {r.source_url}" if r.source_url else "")
        )
    return "\n".join(lines)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
