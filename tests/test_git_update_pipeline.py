import os
import tempfile
import unittest
import importlib
import subprocess
from unittest import mock


class TestGitUpdatePipeline(unittest.TestCase):
    def _server(self):
        import mcp_server as s
        return importlib.reload(s)

    def _cp(self, code=0, out="", err=""):
        return subprocess.CompletedProcess(args=[], returncode=code, stdout=out, stderr=err)

    def test_discover_git_repos(self):
        s = self._server()
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, ".git"), exist_ok=True)
            os.makedirs(os.path.join(d, "A", ".git"), exist_ok=True)
            os.makedirs(os.path.join(d, "B"), exist_ok=True)
            repos = s.discover_git_repos(d)
            self.assertIn(d, repos)
            self.assertTrue(any(r.endswith("/A") for r in repos))

        repos = s.discover_git_repos("/not/exist")
        self.assertEqual(repos, [])

    def test_git_pull_repo_branches(self):
        s = self._server()
        with tempfile.TemporaryDirectory() as d:
            # fetch fail
            with mock.patch.object(s.subprocess, "run", return_value=self._cp(1, "", "f")):
                r = s.git_pull_repo(d)
                self.assertIn("fetch failed", r["error"])

            # no diff
            with mock.patch.object(
                s.subprocess,
                "run",
                side_effect=[self._cp(0, "", ""), self._cp(0, "main\n", ""), self._cp(0, "", "")],
            ):
                r = s.git_pull_repo(d)
                self.assertFalse(r["updated"])

            # pull fail
            with mock.patch.object(
                s.subprocess,
                "run",
                side_effect=[self._cp(0, "", ""), self._cp(0, "main\n", ""), self._cp(0, "a | 1 +\n", ""), self._cp(1, "", "x")],
            ):
                r = s.git_pull_repo(d)
                self.assertIn("pull failed", r["error"])

            # updated success
            with mock.patch.object(
                s.subprocess,
                "run",
                side_effect=[self._cp(0, "", ""), self._cp(0, "\n", ""), self._cp(0, "a | 1 +\n", ""), self._cp(0, "ok", "")],
            ):
                r = s.git_pull_repo(d)
                self.assertTrue(r["updated"])
                self.assertEqual(r["changes"], ["a"])

            with mock.patch.object(s.subprocess, "run", side_effect=subprocess.TimeoutExpired(cmd="x", timeout=1)):
                r = s.git_pull_repo(d)
                self.assertEqual(r["error"], "timeout")

            with mock.patch.object(s.subprocess, "run", side_effect=RuntimeError("boom")):
                r = s.git_pull_repo(d)
                self.assertIn("boom", r["error"])

    def test_check_for_updates_paths(self):
        s = self._server()
        with tempfile.TemporaryDirectory() as d:
            s.PODS_DIR = d
            s.WATCH_LOG = []
            s.LAST_HASH = "old"

            cache_path = os.path.join(s.CACHE_DIR, "index.json")
            os.makedirs(s.CACHE_DIR, exist_ok=True)
            with open(cache_path, "w", encoding="utf-8") as f:
                f.write("x")

            with mock.patch.object(s, "discover_git_repos", return_value=["/repo"]), \
                mock.patch.object(s, "git_pull_repo", return_value={"path": "/repo", "updated": True, "changes": ["x"], "error": None}), \
                mock.patch.object(s, "build_index", return_value={"A": {}}), \
                mock.patch.object(s, "discover_components", return_value={"A"}), \
                mock.patch.object(s, "compute_hash", return_value="new"):
                out = s.check_for_updates()
            self.assertTrue(out["reindexed"])
            self.assertEqual(s.LAST_HASH, "new")
            self.assertFalse(os.path.exists(cache_path))

            # no git update, fs hash changed
            with mock.patch.object(s, "discover_git_repos", return_value=[]), \
                mock.patch.object(s, "discover_components", return_value={"A"}), \
                mock.patch.object(s, "compute_hash", side_effect=["changed", "changed2"]), \
                mock.patch.object(s, "build_index", return_value={"A": {}}):
                s.LAST_HASH = "old2"
                out2 = s.check_for_updates()
            self.assertTrue(out2["reindexed"])

            # no update at all
            with mock.patch.object(s, "discover_git_repos", return_value=[]), \
                mock.patch.object(s, "discover_components", return_value={"A"}), \
                mock.patch.object(s, "compute_hash", return_value="same"):
                s.LAST_HASH = "same"
                out3 = s.check_for_updates()
            self.assertFalse(out3["reindexed"])

    def test_check_for_updates_skips_when_sync_is_running(self):
        s = self._server()

        class BusyLock:
            def acquire(self, blocking=False):
                return False

            def release(self):
                raise AssertionError("busy lock must not be released")

        s.REINDEX_LOCK = BusyLock()
        with mock.patch.object(s, "discover_git_repos") as discover:
            result = s.check_for_updates()

        self.assertTrue(result["skipped"])
        self.assertFalse(result["reindexed"])
        discover.assert_not_called()


if __name__ == "__main__":
    unittest.main()
