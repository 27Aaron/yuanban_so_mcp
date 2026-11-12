"""so.qq.com（腾讯元宝搜索）客户端：AI 问答 / 网页搜索。

- AI 问答: POST https://lizhiassistant.search.qq.com/browser_aimode/aimode/query_get（SSE 流式）
- 网页搜索: GET https://so.qq.com/isearch（SSR 页面解析）
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import secrets
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

import httpx
from bs4 import BeautifulSoup
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

import os

DEFAULT_AUTH_TOKEN = "aimode_token_1739178536"

QUERY_GET_URL = (
    "https://lizhiassistant.search.qq.com/browser_aimode/aimode/query_get"
)
ISEARCH_URL = "https://so.qq.com/isearch"

DEFAULT_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# 垂直搜索 tab（图片走独立路径 /ipics，暂不支持）
VALID_TABS = {"all", "xueshu", "weixin_article", "weixin_video"}

# 请求间隔，避免请求过于频繁
_MIN_INTERVAL = 0.3


def generate_auth_sign(data: str, token: str) -> dict[str, Any]:
    """构造请求签名：AES-CBC(MD5(data)+salt+ts, key=SHA256(token), iv=salt)。"""
    salt = secrets.token_hex(16)
    ts = int(time.time())
    payload = (hashlib.md5(data.encode()).hexdigest() + salt + str(ts)).encode()
    key = hashlib.sha256(token.encode()).digest()
    cipher = AES.new(key, AES.MODE_CBC, bytes.fromhex(salt))
    return {"salt": salt, "timestamp": ts, "sign": cipher.encrypt(pad(payload, 16)).hex()}


def _random_uid() -> str:
    return "cuid_" + secrets.token_hex(14) + "="


@dataclass
class AIAnswer:
    query: str
    answer: str
    session_id: str
    query_id: int | None
    trace_id: str | None
    raw_events: int = 0
    anti_crawl: str | None = None


@dataclass
class WebResult:
    title: str
    url: str
    summary: str
    site: str


@dataclass
class SoClient:
    """轻量异步客户端。单实例内自动节流。"""

    token: str = field(default_factory=lambda: os.environ.get("SO_AUTH_TOKEN", DEFAULT_AUTH_TOKEN))
    uid: str = field(default_factory=_random_uid)
    timeout_ai: float = 120.0
    timeout_web: float = 15.0
    _last_request: float = field(default=0.0, init=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False)

    def _headers(self, referer: str = "https://so.qq.com/iaimode/search", accept: str = "text/event-stream") -> dict[str, str]:
        return {
            "User-Agent": DEFAULT_UA,
            "Origin": "https://so.qq.com",
            "Referer": referer,
            "Accept": accept,
        }

    async def _throttle(self) -> None:
        async with self._lock:
            now = time.monotonic()
            wait = _MIN_INTERVAL - (now - self._last_request)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_request = time.monotonic()

    # ------------------------------------------------------------------ AI 问答

    async def ask(
        self,
        query: str,
        session_id: str | None = None,
        model: str = "deepseek-v3",
    ) -> AIAnswer:
        """调用元宝 AI 问答（query_get），聚合 SSE 流为完整回答。

        session_id 复用即可多轮追问；不传则新建会话。
        """
        query = query.strip()[:1000]
        if not query:
            raise ValueError("query 不能为空")
        sid = session_id or str(uuid.uuid4())

        body: dict[str, Any] = {
            "session_id": sid,
            "stream": True,
            "uid": self.uid,
            "qinfo": None,
            "query": query,
            "enable_enhancement": True,
            "model": model,
            "ext": {
                "SupportedTypes": "waterproof",
                "request_id": str(uuid.uuid4()),
                "page_uid": sid,
                "ua_platform": "Mac",
                "user_id": self.uid,
                "if_app": 0,
                "qimei36": "",
                "qua2": "",
                "if_cookie": 1,
                "source": "https://so.qq.com/iaimode",
                "entry_time": "",
                "entry_scene": "",
                "regen_query_id": -1,
                "neo_sphere": "outer",
                "need_dsh": False,
            },
            # query_get 按查询内容生成签名
            "verify": generate_auth_sign(query, self.token),
        }

        await self._throttle()
        async with httpx.AsyncClient(timeout=self.timeout_ai, http2=True) as http:
            async with http.stream(
                "POST", QUERY_GET_URL, json=body, headers=self._headers()
            ) as resp:
                if resp.status_code != 200:
                    detail = (await resp.aread())[:300].decode("utf-8", "replace")
                    raise RuntimeError(f"query_get HTTP {resp.status_code}: {detail}")
                return await self._consume_sse(query, sid, resp)

    async def _consume_sse(self, query: str, sid: str, resp: httpx.Response) -> AIAnswer:
        parts: list[str] = []
        query_id: int | None = None
        trace_id: str | None = None
        anti_crawl: str | None = None
        n_events = 0
        err_msg: str | None = None

        async for raw in resp.aiter_lines():
            line = raw.strip()
            if not line:
                continue
            if line.startswith("data:"):
                line = line[5:].strip()
            try:
                evt = json.loads(line)
            except json.JSONDecodeError:
                continue
            n_events += 1

            if "ret_code" in evt and evt["ret_code"] != 0:
                err_msg = evt.get("message") or json.dumps(evt, ensure_ascii=False)
                continue
            dtype = evt.get("data_type")
            if dtype == "anti_crawl":
                status = (evt.get("data") or {}).get("status")
                anti_crawl = str(status)
                if status != "pass":
                    err_msg = f"anti_crawl: {status}"
            elif dtype == "query_info":
                query_id = evt.get("query_id")
                trace_id = evt.get("trace_id")
                # 服务端可能重写 session_id
                if evt.get("session_id"):
                    sid = evt["session_id"]
            choices = evt.get("choices")
            if choices:
                delta = (choices[0] or {}).get("delta") or {}
                content = delta.get("content")
                if content:
                    parts.append(content)

        answer = "".join(parts).strip()
        if err_msg and not answer:
            raise RuntimeError(f"元宝接口错误: {err_msg}")
        if not answer:
            raise RuntimeError("元宝接口返回为空，请稍后重试")
        return AIAnswer(
            query=query,
            answer=answer,
            session_id=sid,
            query_id=query_id,
            trace_id=trace_id,
            raw_events=n_events,
            anti_crawl=anti_crawl,
        )

    # ------------------------------------------------------------------ 网页搜索

    async def web_search(
        self, query: str, tab: str = "all", limit: int = 10
    ) -> list[WebResult]:
        """普通网页搜索（SSR 页面解析）。tab 见 VALID_TABS。"""
        query = query.strip()
        if not query:
            raise ValueError("query 不能为空")
        if tab not in VALID_TABS:
            raise ValueError(f"不支持的 tab: {tab}，可选: {sorted(VALID_TABS)}")

        params: dict[str, str] = {"query": query}
        if tab != "all":
            params["tab"] = tab

        await self._throttle()
        async with httpx.AsyncClient(timeout=self.timeout_web, follow_redirects=True) as http:
            resp = await http.get(
                ISEARCH_URL,
                params=params,
                headers=self._headers("https://so.qq.com/", "text/html"),
            )
            resp.raise_for_status()
            html = resp.text

        return self._parse_isearch(html, limit)

    @staticmethod
    def _parse_isearch(html: str, limit: int) -> list[WebResult]:
        soup = BeautifulSoup(html, "lxml")
        results: list[WebResult] = []
        seen: set[str] = set()
        for card in soup.select("article.result-card"):
            anchors = [
                a
                for a in card.find_all("a", href=True)
                if a["href"].startswith(("http://", "https://"))
                and "so.qq.com" not in a["href"]
            ]
            if len(anchors) < 2:
                continue
            site_a, title_a = anchors[0], anchors[1]
            url = title_a["href"]
            if url in seen:
                continue
            seen.add(url)
            # 摘要取卡片内文本最长的锚点
            snippet_a = max(anchors, key=lambda a: len(a.get_text(strip=True)))
            results.append(
                WebResult(
                    title=title_a.get_text(strip=True),
                    url=url,
                    summary=snippet_a.get_text(" ", strip=True)[:300],
                    site=site_a.get_text(" ", strip=True)[:80],
                )
            )
            if len(results) >= limit:
                break
        return results

_client: SoClient | None = None


def get_client() -> SoClient:
    global _client
    if _client is None:
        _client = SoClient()
    return _client
