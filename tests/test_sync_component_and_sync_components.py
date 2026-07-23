import os
import tempfile
import unittest
import importlib
import subprocess
from unittest import mock


class TestSyncComponentAndSyncComponents(unittest.TestCase):
    def _server(self):
        import mcp_server as s
        return importlib.reload(s)

    def _cp(self, code=0, out="", err=""):
        return subprocess.CompletedProcess(args=[], returncode=code, stdout=out, stderr=err)

    def test_sync_component_skip_and_clone_paths(self):
        s = self._server()
        with tempfile.TemporaryDirectory() as d:
            skip = s.sync_component("A", {}, d)
            self.assertEqual(skip["status"], "skip")

            with mock.patch.object(s.subprocess, "run", return_value=self._cp(0, "ok", "")):
                cloned = s.sync_component("A", {"repo": "git@x:y.git", "branch": "main"}, d)
            self.assertEqual(cloned["status"], "cloned")

            with mock.patch.object(s.subprocess, "run", return_value=self._cp(1, "", "boom")):
                err = s.sync_component("B", {"repo": "git@x:y.git", "branch": "main"}, d)
            self.assertEqual(err["status"], "error")

    def test_sync_component_existing_git_and_nongit_and_errors(self):
        s = self._server()
        with tempfile.TemporaryDirectory() as d:
            comp = os.path.join(d, "A")
            os.makedirs(comp, exist_ok=True)

            # existing non-git
            out = s.sync_component("A", {"repo": "git@x:y.git"}, d)
            self.assertEqual(out["status"], "skip")

            # existing git, pull success
            os.makedirs(os.path.join(comp, ".git"), exist_ok=True)
            with mock.patch.object(
                s.subprocess,
                "run",
                side_effect=[self._cp(0, "", ""), self._cp(0, "Already up to date", "")],
            ):
                ok = s.sync_component("A", {"repo": "git@x:y.git", "branch": "main"}, d)
            self.assertEqual(ok["status"], "unchanged")

            with mock.patch.object(
                s.subprocess,
                "run",
                side_effect=[self._cp(0, "", ""), self._cp(0, "Updating 1..2", "")],
            ):
                updated = s.sync_component("A", {"repo": "git@x:y.git", "branch": "main"}, d)
            self.assertEqual(updated["status"], "updated")

            with mock.patch.object(s.subprocess, "run", return_value=self._cp(1, "", "checkout failed")):
                checkout_failed = s.sync_component("A", {"repo": "git@x:y.git", "branch": "main"}, d)
            self.assertEqual(checkout_failed["status"], "error")

            # pull failed
            with mock.patch.object(
                s.subprocess,
                "run",
                side_effect=[self._cp(0, "", ""), self._cp(1, "", "pull failed")],
            ):
                bad = s.sync_component("A", {"repo": "git@x:y.git", "branch": "main"}, d)
            self.assertEqual(bad["status"], "error")

            with mock.patch.object(s.subprocess, "run", side_effect=subprocess.TimeoutExpired(cmd="x", timeout=1)):
                tout = s.sync_component("A", {"repo": "git@x:y.git", "branch": "main"}, d)
            self.assertEqual(tout["status"], "error")

            with mock.patch.object(s.subprocess, "run", side_effect=RuntimeError("x")):
                ex = s.sync_component("A", {"repo": "git@x:y.git", "branch": "main"}, d)
            self.assertEqual(ex["status"], "error")

    def test_sync_components_empty_and_normal(self):
        s = self._server()
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(s, "load_components_config", return_value={}):
                self.assertEqual(s.sync_components("x", d), [])

            with mock.patch.object(s, "load_components_config", return_value={"components": {}}):
                self.assertEqual(s.sync_components("x", d), [])

            cfg = {
                "components": {
                    "A": "git@x:a.git",
                    "B": {"repo": "git@x:b.git", "branch": "dev"},
                }
            }
            with mock.patch.object(s, "load_components_config", return_value=cfg), mock.patch.object(
                s, "sync_component", side_effect=[{"name": "A", "status": "cloned", "message": "ok"}, {"name": "B", "status": "error", "message": "bad"}]
            ):
                res = s.sync_components("x", d)
            self.assertEqual(len(res), 2)
            self.assertEqual(res[0]["status"], "cloned")


if __name__ == "__main__":
    unittest.main()
