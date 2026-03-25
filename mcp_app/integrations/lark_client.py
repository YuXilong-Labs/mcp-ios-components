"""飞书（Lark）DocX + Wiki API 封装。

使用 tenant_access_token 认证，支持：
- 创建知识库文档节点
- 向文档追加内容块（自动分批）

Created by yuxilong on 2026/03/25
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.request

logger = logging.getLogger(__name__)

# 飞书代码语言枚举（DocX code block style.language）
LANG_MAP: dict[str, int] = {
    "plaintext": 1,
    "bash": 7,
    "c": 8,
    "cpp": 9,
    "java": 16,
    "javascript": 18,
    "json": 19,
    "objc": 28,
    "python": 33,
    "ruby": 36,
    "swift": 43,
    "typescript": 46,
    "yaml": 50,
}


class LarkAPIError(RuntimeError):
    """飞书 API 调用失败。"""

    def __init__(self, code: int, msg: str, url: str = ""):
        self.code = code
        self.msg = msg
        self.url = url
        super().__init__(f"Lark API error {code}: {msg} (url={url})")


class LarkClient:
    """飞书 API 客户端。

    认证方式：app_id + app_secret → tenant_access_token（自动刷新）。
    """

    # 限速：每次请求后等待的最小间隔（秒），确保 < 3次/秒
    REQUEST_INTERVAL = 0.35
    # 每批追加的最大 block 数
    BATCH_SIZE = 50

    def __init__(
        self,
        app_id: str = "",
        app_secret: str = "",
        domain: str = "",
    ):
        self.app_id = app_id or os.environ.get("LARK_APP_ID", "")
        self.app_secret = app_secret or os.environ.get("LARK_APP_SECRET", "")
        self.domain = (domain or os.environ.get("LARK_DOMAIN", "")).rstrip("/")
        if not self.domain:
            self.domain = "https://open.larksuite.com"

        self._token: str = ""
        self._token_expires: float = 0
        self._last_request_time: float = 0

    # ------------------------------------------------------------------
    # 认证
    # ------------------------------------------------------------------

    def _get_token(self) -> str:
        """获取 tenant_access_token（带缓存，过期自动刷新）。"""
        now = time.time()
        if self._token and now < self._token_expires:
            return self._token

        if not self.app_id or not self.app_secret:
            raise LarkAPIError(0, "未配置 LARK_APP_ID 或 LARK_APP_SECRET")

        url = f"{self.domain}/open-apis/auth/v3/tenant_access_token/internal"
        body = json.dumps({
            "app_id": self.app_id,
            "app_secret": self.app_secret,
        }).encode("utf-8")

        req = urllib.request.Request(url, data=body, method="POST")
        req.add_header("Content-Type", "application/json; charset=utf-8")

        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, OSError) as e:
            raise LarkAPIError(0, f"获取 token 网络错误: {e}", url) from e

        if data.get("code", -1) != 0:
            raise LarkAPIError(data.get("code", -1), data.get("msg", "unknown"), url)

        self._token = data["tenant_access_token"]
        # 提前 5 分钟刷新
        self._token_expires = now + data.get("expire", 7200) - 300
        return self._token

    # ------------------------------------------------------------------
    # 通用请求
    # ------------------------------------------------------------------

    def _request(self, method: str, path: str, body: dict | None = None) -> dict:
        """发送请求（带认证头 + 限速）。"""
        # 限速
        elapsed = time.time() - self._last_request_time
        if elapsed < self.REQUEST_INTERVAL:
            time.sleep(self.REQUEST_INTERVAL - elapsed)

        token = self._get_token()
        url = f"{self.domain}{path}"
        data = json.dumps(body).encode("utf-8") if body else None

        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Authorization", f"Bearer {token}")
        req.add_header("Content-Type", "application/json; charset=utf-8")

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body_text = ""
            try:
                body_text = e.read().decode("utf-8", errors="ignore")
            except Exception:
                pass
            raise LarkAPIError(e.code, f"HTTP {e.code}: {body_text[:500]}", url) from e
        except (urllib.error.URLError, OSError) as e:
            raise LarkAPIError(0, f"网络错误: {e}", url) from e
        finally:
            self._last_request_time = time.time()

        if result.get("code", -1) != 0:
            raise LarkAPIError(result.get("code", -1), result.get("msg", "unknown"), url)

        return result.get("data", {})

    # ------------------------------------------------------------------
    # Wiki 知识库
    # ------------------------------------------------------------------

    def create_wiki_node(
        self,
        space_id: str,
        parent_node_token: str,
        title: str,
    ) -> dict:
        """在知识库空间下创建文档节点。

        返回 {"node_token": "...", "obj_token": "..."（= document_id）}
        """
        data = self._request("POST", f"/open-apis/wiki/v2/spaces/{space_id}/nodes", {
            "obj_type": "docx",
            "node_type": "origin",
            "parent_node_token": parent_node_token,
            "title": title,
        })
        node = data.get("node", {})
        return {
            "node_token": node.get("node_token", ""),
            "obj_token": node.get("obj_token", ""),
        }

    # ------------------------------------------------------------------
    # DocX 文档操作
    # ------------------------------------------------------------------

    def append_body_blocks(
        self,
        document_id: str,
        block_id: str,
        children: list[dict],
    ) -> None:
        """向指定 block 追加子块（自动分批）。

        block_id 通常等于 document_id（追加到文档根）。
        """
        for i in range(0, len(children), self.BATCH_SIZE):
            batch = children[i : i + self.BATCH_SIZE]
            self._request(
                "POST",
                f"/open-apis/docx/v1/documents/{document_id}/blocks/{block_id}/children",
                {"children": batch},
            )
            if len(children) > self.BATCH_SIZE:
                logger.info(
                    "  追加 block %d–%d / %d",
                    i + 1,
                    min(i + self.BATCH_SIZE, len(children)),
                    len(children),
                )
