import os
import tempfile
import unittest
import importlib
import subprocess
from unittest import mock


class TestTargetedBranchBoost(unittest.TestCase):
    def _server(self):
        import mcp_server as s
        return importlib.reload(s)

    def _write_comp(self, root, dname, pod_name, body=""):
        comp = os.path.join(root, dname)
        os.makedirs(comp, exist_ok=True)
        with open(os.path.join(comp, f"{pod_name}.podspec"), "w", encoding="utf-8") as f:
            f.write(f"Pod::Spec.new do |s|\n  s.name = '{pod_name}'\n{body}\nend\n")
        return comp

    def test_discover_walk_parse_and_extract_extra_branches(self):
        s = self._server()
        with tempfile.TemporaryDirectory() as d:
            # non-dir entry
            with open(os.path.join(d, "not_dir.txt"), "w", encoding="utf-8") as f:
                f.write("x")
            # dir without podspec
            os.makedirs(os.path.join(d, "empty_dir"), exist_ok=True)
            # dir with comment lines in podspec
            self._write_comp(d, "c1", "C1", body="  # comment\n  // comment")

            comps = s.discover_components(d)
            self.assertIn("c1", comps)

            self.assertEqual(s.walk_dir("/path/not/exist"), [])

            with mock.patch.object(s.os, "listdir", side_effect=RuntimeError("x")):
                spec = s.parse_podspec("/bad", "name")
                self.assertEqual(spec["pod_name"], "name")

            src = os.path.join(d, "A.h")
            with open(src, "w", encoding="utf-8") as f:
                f.write("/**\nline\n*/\n@interface A : NSObject\n@end\n")
            apis = s.extract_apis(src, "A.h")
            self.assertTrue(len(apis) >= 1)

    def test_compute_hash_and_build_index_error_paths(self):
        s = self._server()
        with tempfile.TemporaryDirectory() as d:
            self._write_comp(d, "ok", "OK")
            os.makedirs(os.path.join(d, "ok", "Sources"), exist_ok=True)
            with open(os.path.join(d, "ok", "Sources", "A.h"), "w", encoding="utf-8") as f:
                f.write("@interface A : NSObject\n@end\n")

            # compute_hash: missing comp and stat exception
            with mock.patch.object(s, "walk_dir", return_value=["missing.h"]):
                h = s.compute_hash(d, {"missing", "ok"}, {"exclude_from_index": set(), "api_only": set()})
                self.assertTrue(isinstance(h, str) and h)

            # build_index: print filtered mixup/excluded + cache parse fail + per-component exception
            self._write_comp(d, "mix", "MIX", body="  SUPPORT_MIXUP = ['VO']")
            self._write_comp(d, "rtc", "BTRtcEngine")

            cache_path = os.path.join(s.CACHE_DIR, "index.json")
            os.makedirs(s.CACHE_DIR, exist_ok=True)
            with open(cache_path, "w", encoding="utf-8") as f:
                f.write("not-json")

            ac = {"exclude_from_index": {"btrtcengine"}, "api_only": set(), "config_path": "x"}
            original_parse = s.parse_podspec

            def bad_parse(comp_dir, name):
                if name == "ok":
                    raise RuntimeError("parse fail")
                return original_parse(comp_dir, name)

            with mock.patch.object(s, "load_access_control", return_value=ac), mock.patch.object(s, "parse_podspec", side_effect=bad_parse):
                idx = s.build_index(d)
            self.assertEqual(idx, {})

    def test_list_keys_search_audit_and_suspicious_generic(self):
        s = self._server()
        with tempfile.TemporaryDirectory() as d:
            key_file = os.path.join(d, ".api-keys")
            with open(key_file, "w", encoding="utf-8") as f:
                f.write("# c\n\n")
                f.write("hash_without_name\n")
            s.KEYS_FILE = key_file
            out = s.list_api_keys()
            self.assertEqual(out[0]["name"], "(unnamed)")

        self.assertEqual(s._looks_suspicious_name("run"), "too_generic")
        self.assertIn("关键词过长", s.search_component("x" * (s.MAX_KEYWORD_LEN + 1)))

        with s.INDEX_LOCK:
            s.INDEX = {
                "A": {
                    "name": "A",
                    "dir": "A",
                    "summary": "",
                    "description": "",
                    "podspec": "",
                    "files": [],
                    "source_count": 0,
                    "apis": [{"kind": "method", "name": "run", "declaration": "- (void)run;", "file": "A.h", "line": 1, "comment": ""}],
                },
                "B": {
                    "name": "B",
                    "dir": "B",
                    "summary": "",
                    "description": "",
                    "podspec": "",
                    "files": [],
                    "source_count": 0,
                    "apis": [],
                },
            }
        # top-of-loop break branch for second component when limit reached
        s.search_component("A", format="text", limit=1)

        raw = s.audit_component_api_quality(component_name="", format="json", limit=1)
        self.assertIn('"ok":true', raw)

    def test_read_source_remaining_branches(self):
        s = self._server()
        self.assertIn("组件名不能为空", s.read_source("", "x"))
        self.assertIn("文件路径不能为空", s.read_source("A", ""))
        self.assertEqual(s.read_source("A", "x"), "组件不存在")

        with tempfile.TemporaryDirectory() as d:
            comp_dir = os.path.join(d, "A")
            os.makedirs(comp_dir, exist_ok=True)
            with open(os.path.join(comp_dir, "A.h"), "w", encoding="utf-8") as f:
                f.write("line1\nline2\n")

            with s.INDEX_LOCK:
                s.PODS_DIR = d
                s.INDEX = {
                    "A": {
                        "name": "A",
                        "dir": "A",
                        "podspec": "",
                        "summary": "",
                        "description": "",
                        "files": ["A.h", "ghost.h", "../evil.h"],
                        "source_count": 1,
                        "apis": [],
                        "access_mode": s.ACCESS_MODE_FULL,
                    }
                }

            # exact match 1201-1202
            self.assertIn("A.h", s.read_source("A", "A.h", start=1, end=1))
            # not found 1215-1216
            self.assertIn("文件未找到", s.read_source("A", "none.h", start=1, end=1))
            # path forbidden 1224 via matched ../evil.h
            self.assertIn("禁止访问", s.read_source("A", "evil.h", start=1, end=1))
            # file missing 1227
            self.assertIn("文件不存在", s.read_source("A", "ghost.h", start=1, end=1))
            # end <=0 1230
            self.assertIn("L1-", s.read_source("A", "A.h", start=1, end=0))
            # start>end 1238
            self.assertIn("起始行号不能大于结束行号", s.read_source("A", "A.h", start=2, end=1))

    def test_sync_gitlab_tool_truncation_and_cache_remove(self):
        s = self._server()
        s.GITLAB_TOKEN = "tok"
        skipped = [{"name": f"S{i}", "status": "skip", "message": "x"} for i in range(12)]
        results = skipped + [{"name": "C", "status": "cloned", "message": "ok"}]

        cache_path = os.path.join(s.CACHE_DIR, "index.json")
        os.makedirs(s.CACHE_DIR, exist_ok=True)
        with open(cache_path, "w", encoding="utf-8") as f:
            f.write("x")

        with mock.patch.object(s, "sync_gitlab_group", return_value=results), mock.patch.object(
            s, "build_index", return_value={"C": {}}
        ), mock.patch.object(s, "discover_components", return_value={"C"}), mock.patch.object(s, "compute_hash", return_value="h"):
            out = s.sync_gitlab_group_tool("g", gitlab_token="tok")

        self.assertIn("还有 2 个", out)
        self.assertFalse(os.path.exists(cache_path))

    def test_find_usage_example_remaining_branches(self):
        s = self._server()
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "B"), exist_ok=True)
            with open(os.path.join(d, "B", "nohit.m"), "w", encoding="utf-8") as f:
                f.write("int x = 1;\n")
            # many hits for truncation and line cap
            os.makedirs(os.path.join(d, "C"), exist_ok=True)
            with open(os.path.join(d, "C", "hit.m"), "w", encoding="utf-8") as f:
                lines = ["#import <BTBaseKit/A.h>\n"] + [f"BTBaseKit_call_{i}\n" for i in range(30)]
                f.writelines(lines)

            with s.INDEX_LOCK:
                s.PODS_DIR = d
                s.INDEX = {
                    "BTBaseKit": {"name": "BTBaseKit", "dir": "A", "files": [], "apis": [], "source_count": 0, "summary": "", "description": "", "podspec": "", "access_mode": s.ACCESS_MODE_FULL},
                    "B": {"name": "B", "dir": "B", "files": ["missing.m", "nohit.m"], "apis": [], "source_count": 0, "summary": "", "description": "", "podspec": "", "access_mode": s.ACCESS_MODE_FULL},
                    "C": {"name": "C", "dir": "C", "files": ["hit.m"], "apis": [], "source_count": 0, "summary": "", "description": "", "podspec": "", "access_mode": s.ACCESS_MODE_FULL},
                }

            out = s.find_usage_example("BTBaseKit")
            self.assertIn("C/hit.m", out)

            # >20 results truncation 1494
            with s.INDEX_LOCK:
                for i in range(25):
                    dn = f"D{i}"
                    os.makedirs(os.path.join(d, dn), exist_ok=True)
                    with open(os.path.join(d, dn, "u.m"), "w", encoding="utf-8") as f:
                        f.write("#import <BTBaseKit/A.h>\n")
                    s.INDEX[dn] = {"name": dn, "dir": dn, "files": ["u.m"], "apis": [], "source_count": 0, "summary": "", "description": "", "podspec": "", "access_mode": s.ACCESS_MODE_FULL}
            out2 = s.find_usage_example("BTBaseKit")
            self.assertIn("仅显示前 20 处", out2)

    def test_reindex_and_check_for_updates_remaining_branches(self):
        s = self._server()
        with tempfile.TemporaryDirectory() as d:
            s.PODS_DIR = d
            os.makedirs(os.path.join(d, ".git"), exist_ok=True)
            cp = subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="err")
            with mock.patch.object(s.subprocess, "run", return_value=cp), mock.patch.object(s, "build_index", return_value={}), mock.patch.object(
                s, "discover_components", return_value=set()
            ), mock.patch.object(s, "compute_hash", return_value="x"):
                s.reindex()

            with mock.patch.object(s, "discover_git_repos", return_value=["/repo"]), mock.patch.object(
                s, "git_pull_repo", return_value={"path": "/repo", "updated": False, "changes": [], "error": "boom"}
            ), mock.patch.object(s, "discover_components", return_value=set()), mock.patch.object(s, "compute_hash", return_value="same"):
                s.LAST_HASH = "same"
                s.WATCH_LOG = [
                    {"time": "old", "repos": [], "reindexed": False},
                ]
                s.WATCH_LOG_MAX = 1
                out = s.check_for_updates()
            self.assertFalse(out["reindexed"])
            self.assertEqual(len(s.WATCH_LOG), 1)

    def test_check_repo_and_main_remaining_branches(self):
        s = self._server()

        class Resp:
            def __init__(self, b):
                self.b = b
            def __enter__(self):
                return self
            def __exit__(self, *a):
                return False
            def read(self):
                return self.b

        files = b'[{"name":"A.podspec","type":"blob"}]'
        pod = b"# comment\nSUPPORT_MIXUP = []\n"
        with mock.patch("urllib.request.urlopen", side_effect=[Resp(files), Resp(pod)]):
            ok, _, _ = s.check_repo_is_base_component("https://gitlab.com/ios/A.git", gitlab_token="tok")
            self.assertTrue(ok)

        with tempfile.TemporaryDirectory() as d:
            rel_cfg = os.path.join(os.path.dirname(os.path.abspath(s.__file__)), "rel_tmp_components.yaml")
            try:
                with open(rel_cfg, "w", encoding="utf-8") as f:
                    f.write("components:\n  A: git@x:a.git\n")
                with mock.patch.object(
                    s.sys, "argv", ["prog", "--sync", "rel_tmp_components.yaml", "--sync-only", d]
                ), mock.patch.object(s, "sync_components", return_value=[{"status": "updated"}]):
                    with self.assertRaises(SystemExit):
                        s.main()

                with mock.patch.object(
                    s.sys,
                    "argv",
                    ["prog", "--gitlab-group", "g", "--gitlab-url", "https://x", "--gitlab-token", "tt", "--sync-only", d],
                ), mock.patch.object(s, "sync_gitlab_group", return_value=[{"status": "updated"}]):
                    with self.assertRaises(SystemExit):
                        s.main()
                self.assertEqual(s.GITLAB_URL, "https://x")
                self.assertEqual(s.GITLAB_TOKEN, "tt")

                with mock.patch.object(
                    s.sys,
                    "argv",
                    ["prog", "--api-keys", "k1,k2", "--webhook-secret", "sec", d],
                ), mock.patch.object(s, "build_index", return_value={}), mock.patch.object(s, "discover_components", return_value=set()), mock.patch.object(
                    s, "compute_hash", return_value="h"
                ), mock.patch.object(s.mcp, "run"):
                    s.main()
                self.assertEqual(os.environ.get("MCP_API_KEYS"), "k1,k2")
                self.assertEqual(s.WEBHOOK_SECRET, "sec")
            finally:
                if os.path.exists(rel_cfg):
                    os.remove(rel_cfg)


if __name__ == "__main__":
    unittest.main()
