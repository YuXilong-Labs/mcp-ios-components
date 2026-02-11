import os
import tempfile
import unittest
import importlib
import threading
from unittest import mock


class TestReindexAndWatchLoop(unittest.TestCase):
    def _server(self):
        import mcp_server as s
        return importlib.reload(s)

    def test_reindex_lock_and_normal_flow(self):
        s = self._server()

        class BusyLock:
            def acquire(self, blocking=False):
                return False
            def release(self):
                pass

        old_lock = s.REINDEX_LOCK
        try:
            s.REINDEX_LOCK = BusyLock()
            s.reindex()  # just ensure no crash on busy
        finally:
            s.REINDEX_LOCK = old_lock

        with tempfile.TemporaryDirectory() as d:
            s.PODS_DIR = d
            os.makedirs(os.path.join(d, ".git"), exist_ok=True)
            cache_path = os.path.join(s.CACHE_DIR, "index.json")
            os.makedirs(s.CACHE_DIR, exist_ok=True)
            with open(cache_path, "w", encoding="utf-8") as f:
                f.write("x")

            cp = mock.Mock(returncode=0, stdout="ok", stderr="")
            with mock.patch.object(s.subprocess, "run", return_value=cp), \
                mock.patch.object(s, "build_index", return_value={"A": {}}), \
                mock.patch.object(s, "discover_components", return_value={"A"}), \
                mock.patch.object(s, "compute_hash", return_value="h"):
                s.reindex()

            self.assertEqual(s.LAST_HASH, "h")
            self.assertFalse(os.path.exists(cache_path))

            # git pull exception path
            with mock.patch.object(s.subprocess, "run", side_effect=RuntimeError("x")), \
                mock.patch.object(s, "build_index", return_value={}), \
                mock.patch.object(s, "discover_components", return_value=set()), \
                mock.patch.object(s, "compute_hash", return_value="z"):
                s.reindex()

    def test_watch_loop_handles_exceptions(self):
        s = self._server()

        calls = {"n": 0}

        def fake_sleep(_):
            calls["n"] += 1
            if calls["n"] >= 2:
                raise KeyboardInterrupt()

        with mock.patch("time.sleep", side_effect=fake_sleep), \
            mock.patch.object(s, "check_for_updates", side_effect=RuntimeError("boom")):
            with self.assertRaises(KeyboardInterrupt):
                s.watch_loop(1)


if __name__ == "__main__":
    unittest.main()
