import json
import unittest
import importlib
import urllib.error
from unittest import mock


class _Resp:
    def __init__(self, payload):
        self._payload = payload
    def __enter__(self):
        return self
    def __exit__(self, exc_type, exc, tb):
        return False
    def read(self):
        return self._payload


class TestGitlabFetchAndDetect(unittest.TestCase):
    def _server(self):
        import mcp_server as s
        return importlib.reload(s)

    def test_fetch_gitlab_group_repos_branches(self):
        s = self._server()

        # token missing
        s.GITLAB_TOKEN = ""
        out = s.fetch_gitlab_group_repos("g")
        self.assertEqual(out, [])

        s.GITLAB_TOKEN = "t"
        data_page = json.dumps([
            {"id": 1, "name": "n", "path": "p", "ssh_url_to_repo": "ssh", "http_url_to_repo": "http", "default_branch": "main"}
        ]).encode()
        with mock.patch("urllib.request.urlopen", return_value=_Resp(data_page)):
            repos = s.fetch_gitlab_group_repos("g")
        self.assertEqual(len(repos), 1)
        self.assertEqual(repos[0]["ssh_url"], "ssh")

        many = [
            {"id": i, "name": f"n{i}", "path": f"p{i}", "ssh_url_to_repo": "ssh", "http_url_to_repo": "http", "default_branch": "main"}
            for i in range(100)
        ]
        with mock.patch("urllib.request.urlopen", side_effect=[_Resp(json.dumps(many).encode()), _Resp(b"[]")]):
            repos2 = s.fetch_gitlab_group_repos("g")
        self.assertEqual(len(repos2), 100)

        http_err = urllib.error.HTTPError(url="u", code=500, msg="x", hdrs=None, fp=None)
        with mock.patch("urllib.request.urlopen", side_effect=http_err):
            self.assertEqual(s.fetch_gitlab_group_repos("g"), [])

        with mock.patch("urllib.request.urlopen", side_effect=RuntimeError("boom")):
            self.assertEqual(s.fetch_gitlab_group_repos("g"), [])

    def test_check_repo_is_base_component_branches(self):
        s = self._server()
        s.GITLAB_URL = "https://gitlab.example.com"

        # list files error
        with mock.patch("urllib.request.urlopen", side_effect=RuntimeError("listfail")):
            ok, pod, reason = s.check_repo_is_base_component("git@gitlab.com:ios/A.git", "main", "")
            self.assertFalse(ok)
            self.assertIn("无法获取文件列表", reason)

        # no podspec
        files = json.dumps([{"name": "README.md", "type": "blob"}]).encode()
        with mock.patch("urllib.request.urlopen", return_value=_Resp(files)):
            ok, pod, reason = s.check_repo_is_base_component("https://gitlab.com/ios/A.git", "main", "")
            self.assertFalse(ok)
            self.assertIsNone(pod)
            self.assertIn("无 podspec", reason)

        # podspec read error
        files2 = json.dumps([{"name": "A.podspec", "type": "blob"}]).encode()
        with mock.patch("urllib.request.urlopen", side_effect=[_Resp(files2), RuntimeError("readfail")]):
            ok, pod, reason = s.check_repo_is_base_component("https://gitlab.com/ios/A.git", "main", "")
            self.assertFalse(ok)
            self.assertEqual(pod, "A.podspec")
            self.assertIn("无法读取 podspec", reason)

        # non-base due to mixup
        podspec_non_base = b"SUPPORT_MIXUP = ['VO']\n"
        with mock.patch("urllib.request.urlopen", side_effect=[_Resp(files2), _Resp(podspec_non_base)]):
            ok, pod, reason = s.check_repo_is_base_component("https://gitlab.com/ios/A.git", "main", "")
            self.assertFalse(ok)
            self.assertIn("非基础组件", reason)

        # base component
        podspec_base = b"SUPPORT_MIXUP = []\n"
        with mock.patch("urllib.request.urlopen", side_effect=[_Resp(files2), _Resp(podspec_base)]):
            ok, pod, reason = s.check_repo_is_base_component("https://gitlab.com/ios/A.git", "main", "")
            self.assertTrue(ok)
            self.assertEqual(reason, "基础组件")


if __name__ == "__main__":
    unittest.main()
