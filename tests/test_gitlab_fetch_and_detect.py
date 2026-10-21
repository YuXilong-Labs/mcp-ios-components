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

    def test_nested_group_path_is_encoded_and_subgroups_included(self):
        from mcp_app.integrations.gitlab_client import fetch_gitlab_group_repos

        for group, encoded in [("42", "42"), ("ios_component/Dora/Common", "ios_component%2FDora%2FCommon")]:
            with self.subTest(group=group), mock.patch("urllib.request.urlopen", return_value=_Resp(b"[]")) as request:
                fetch_gitlab_group_repos(group, "https://gitlab.example.com/", "token")
                self.assertEqual(request.call_args.args[0].full_url,
                                 f"https://gitlab.example.com/api/v4/groups/{encoded}/projects?per_page=100&page=1&include_subgroups=true")

    def test_nested_repo_paths_preserved_for_all_transports(self):
        from mcp_app.integrations.gitlab_client import check_repo_is_base_component

        path = "ios_component/Dora/Common/BTHttpClient"
        urls = [f"https://gitlab.example.com/{path}.git", f"https://gitlab.example.com/{path}/",
                f"git@gitlab.example.com:{path}.git", f"ssh://git@gitlab.example.com:2222/{path}.git"]
        files = json.dumps([{"name": "BTHttpClient.podspec", "type": "blob"}]).encode()
        for url in urls:
            with self.subTest(url=url), mock.patch("urllib.request.urlopen", side_effect=[_Resp(files), _Resp(b"SUPPORT_MIXUP = []")]) as request:
                self.assertEqual(check_repo_is_base_component(url, "https://gitlab.example.com/", "feature/http&client", "token"),
                                 (True, "BTHttpClient.podspec", "基础组件"))
                requests = [call.args[0] for call in request.call_args_list]
                for req in requests:
                    self.assertIn("/projects/ios_component%2FDora%2FCommon%2FBTHttpClient/repository/", req.full_url)
                    self.assertIn("ref=feature%2Fhttp%26client", req.full_url)
                    self.assertEqual(req.get_header("Private-token"), "token")

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
