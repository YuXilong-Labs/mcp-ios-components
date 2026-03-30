"""飞书 API 封装（lark_client.py）的测试。

覆盖认证流程、请求封装、Wiki 节点创建、block 追加分批。

Created by yuxilong on 2026/03/25
"""

import json
import unittest
from unittest.mock import MagicMock, patch

from mcp_app.integrations.lark_client import LANG_MAP, LarkAPIError, LarkClient


class TestLarkClientInit(unittest.TestCase):
    """初始化与配置。"""

    def test_default_domain(self):
        client = LarkClient(app_id="id", app_secret="secret")
        self.assertEqual(client.domain, "https://open.larksuite.com")

    def test_feishu_domain_auto_detect(self):
        client = LarkClient(app_id="cli_a686486c8578d02f", app_secret="secret")
        self.assertEqual(client.domain, "https://open.feishu.cn")

    def test_custom_domain(self):
        client = LarkClient(app_id="id", app_secret="secret", domain="https://open.feishu.cn")
        self.assertEqual(client.domain, "https://open.feishu.cn")

    def test_domain_trailing_slash_stripped(self):
        client = LarkClient(domain="https://open.feishu.cn/")
        self.assertEqual(client.domain, "https://open.feishu.cn")

    @patch.dict("os.environ", {"LARK_APP_ID": "env_id", "LARK_APP_SECRET": "env_secret"})
    def test_env_vars(self):
        client = LarkClient()
        self.assertEqual(client.app_id, "env_id")
        self.assertEqual(client.app_secret, "env_secret")


class TestLarkClientAuth(unittest.TestCase):
    """认证流程。"""

    def test_missing_credentials_raises(self):
        client = LarkClient(app_id="", app_secret="")
        with self.assertRaises(LarkAPIError) as ctx:
            client._get_token()
        self.assertIn("LARK_APP_ID", str(ctx.exception))

    @patch("urllib.request.urlopen")
    def test_get_token_success(self, mock_urlopen):
        resp_body = json.dumps({
            "code": 0,
            "tenant_access_token": "t-test-token",
            "expire": 7200,
        }).encode()
        mock_resp = MagicMock()
        mock_resp.read.return_value = resp_body
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        client = LarkClient(app_id="id", app_secret="secret")
        token = client._get_token()
        self.assertEqual(token, "t-test-token")

    @patch("urllib.request.urlopen")
    def test_get_token_cached(self, mock_urlopen):
        resp_body = json.dumps({
            "code": 0,
            "tenant_access_token": "t-cached",
            "expire": 7200,
        }).encode()
        mock_resp = MagicMock()
        mock_resp.read.return_value = resp_body
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        client = LarkClient(app_id="id", app_secret="secret")
        client._get_token()
        client._get_token()  # 第二次应走缓存
        self.assertEqual(mock_urlopen.call_count, 1)

    @patch("urllib.request.urlopen")
    def test_get_token_api_error(self, mock_urlopen):
        resp_body = json.dumps({"code": 10003, "msg": "invalid app_id"}).encode()
        mock_resp = MagicMock()
        mock_resp.read.return_value = resp_body
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        client = LarkClient(app_id="bad", app_secret="bad")
        with self.assertRaises(LarkAPIError) as ctx:
            client._get_token()
        self.assertEqual(ctx.exception.code, 10003)


class TestLarkClientRequest(unittest.TestCase):
    """通用请求封装。"""

    def _make_client(self):
        client = LarkClient(app_id="id", app_secret="secret")
        client._token = "t-mock"
        client._token_expires = 9999999999
        client.REQUEST_INTERVAL = 0  # 测试时不限速
        return client

    @patch("urllib.request.urlopen")
    def test_request_success(self, mock_urlopen):
        resp_body = json.dumps({"code": 0, "data": {"result": "ok"}}).encode()
        mock_resp = MagicMock()
        mock_resp.read.return_value = resp_body
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        client = self._make_client()
        data = client._request("POST", "/open-apis/test", {"key": "value"})
        self.assertEqual(data["result"], "ok")

    @patch("urllib.request.urlopen")
    def test_request_api_error(self, mock_urlopen):
        resp_body = json.dumps({"code": 99991400, "msg": "rate limit"}).encode()
        mock_resp = MagicMock()
        mock_resp.read.return_value = resp_body
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        client = self._make_client()
        with self.assertRaises(LarkAPIError) as ctx:
            client._request("POST", "/open-apis/test")
        self.assertEqual(ctx.exception.code, 99991400)


class TestLarkClientWiki(unittest.TestCase):
    """Wiki 节点创建。"""

    @patch("urllib.request.urlopen")
    def test_create_wiki_node(self, mock_urlopen):
        resp_body = json.dumps({
            "code": 0,
            "data": {
                "node": {
                    "node_token": "wikcnABC",
                    "obj_token": "docxDEF",
                },
            },
        }).encode()
        mock_resp = MagicMock()
        mock_resp.read.return_value = resp_body
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        client = LarkClient(app_id="id", app_secret="secret")
        client._token = "t-mock"
        client._token_expires = 9999999999
        client.REQUEST_INTERVAL = 0

        result = client.create_wiki_node("space123", "parent456", "Test Doc")
        self.assertEqual(result["node_token"], "wikcnABC")
        self.assertEqual(result["obj_token"], "docxDEF")

        # 验证请求体包含 parent_node_token
        call_args = mock_urlopen.call_args
        sent_body = json.loads(call_args[0][0].data.decode())
        self.assertEqual(sent_body["parent_node_token"], "parent456")

    @patch("urllib.request.urlopen")
    def test_create_wiki_node_no_parent(self, mock_urlopen):
        """空 parent_node_token 时不发送该字段（创建在根目录）。"""
        resp_body = json.dumps({
            "code": 0,
            "data": {"node": {"node_token": "wikcnRoot", "obj_token": "docxRoot"}},
        }).encode()
        mock_resp = MagicMock()
        mock_resp.read.return_value = resp_body
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        client = LarkClient(app_id="id", app_secret="secret")
        client._token = "t-mock"
        client._token_expires = 9999999999
        client.REQUEST_INTERVAL = 0

        result = client.create_wiki_node("space123", "", "Root Doc")
        self.assertEqual(result["node_token"], "wikcnRoot")

        # 验证请求体不含 parent_node_token
        call_args = mock_urlopen.call_args
        sent_body = json.loads(call_args[0][0].data.decode())
        self.assertNotIn("parent_node_token", sent_body)


class TestLarkClientBatch(unittest.TestCase):
    """Block 追加分批。"""

    @patch("urllib.request.urlopen")
    def test_append_blocks_batched(self, mock_urlopen):
        resp_body = json.dumps({"code": 0, "data": {}}).encode()
        mock_resp = MagicMock()
        mock_resp.read.return_value = resp_body
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        client = LarkClient(app_id="id", app_secret="secret")
        client._token = "t-mock"
        client._token_expires = 9999999999
        client.REQUEST_INTERVAL = 0
        client.BATCH_SIZE = 3  # 小批量便于测试

        blocks = [{"block_type": 2, "text": {"elements": [{"text_run": {"content": f"block{i}"}}]}}
                  for i in range(7)]
        client.append_body_blocks("doc123", "doc123", blocks)

        # 7 个 block，batch_size=3，应分 3 批（3+3+1）
        self.assertEqual(mock_urlopen.call_count, 3)


class TestLangMap(unittest.TestCase):
    """语言映射。"""

    def test_objc_mapped(self):
        self.assertEqual(LANG_MAP["objc"], 28)

    def test_swift_mapped(self):
        self.assertEqual(LANG_MAP["swift"], 43)


if __name__ == "__main__":
    unittest.main()
