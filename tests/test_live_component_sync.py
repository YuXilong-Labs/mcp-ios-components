import importlib
import json
import os
import subprocess
import tempfile
import unittest
from unittest import mock


class TestLiveComponentSync(unittest.TestCase):
    def _run(self, args, cwd=None):
        subprocess.run(args, cwd=cwd, check=True, capture_output=True, text=True)

    def test_remote_push_is_pulled_and_reindexed(self):
        with tempfile.TemporaryDirectory() as d:
            remote = os.path.join(d, "remote.git")
            seed = os.path.join(d, "seed")
            pods = os.path.join(d, "pods")
            app = os.path.join(d, "app")
            cache = os.path.join(d, "cache")
            config = os.path.join(app, "components.yaml")

            self._run(["git", "init", "--bare", remote])
            self._run(["git", "init", "-b", "main", seed])
            self._run(["git", "config", "user.name", "MCP Sync Test"], cwd=seed)
            self._run(["git", "config", "user.email", "mcp-sync@example.invalid"], cwd=seed)

            os.makedirs(os.path.join(seed, "Sources"), exist_ok=True)
            with open(os.path.join(seed, "SyncProbe.podspec"), "w", encoding="utf-8") as f:
                f.write("Pod::Spec.new do |s|\n  s.name = 'SyncProbe'\nend\n")
            header = os.path.join(seed, "Sources", "SyncProbe.h")
            with open(header, "w", encoding="utf-8") as f:
                f.write("@interface SyncProbe : NSObject\n- (void)syncProbeV1;\n@end\n")
            self._run(["git", "add", "."], cwd=seed)
            self._run(["git", "commit", "-m", "initial"], cwd=seed)
            self._run(["git", "remote", "add", "origin", remote], cwd=seed)
            self._run(["git", "push", "-u", "origin", "main"], cwd=seed)

            os.makedirs(app, exist_ok=True)
            with open(config, "w", encoding="utf-8") as f:
                f.write(f"components:\n  SyncProbe:\n    repo: {remote}\n    branch: main\n")

            env = {
                "IOS_PODS_APP_BASE_DIR": app,
                "IOS_PODS_CACHE_DIR": cache,
                "IOS_PODS_CONFIG": config,
            }
            with mock.patch.dict(os.environ, env, clear=False):
                import mcp_server as server

                server = importlib.reload(server)
                server.PODS_DIR = pods
                first = server.sync_from_config(config)
                self.assertIn("索引已更新", first)
                self.assertIn("syncProbeV1", json.dumps(server.INDEX))

                with open(header, "w", encoding="utf-8") as f:
                    f.write("@interface SyncProbe : NSObject\n- (void)syncProbeV2;\n@end\n")
                self._run(["git", "add", "."], cwd=seed)
                self._run(["git", "commit", "-m", "add v2"], cwd=seed)
                self._run(["git", "push", "origin", "main"], cwd=seed)

                result = server.check_for_updates()

            self.assertTrue(result["reindexed"])
            self.assertIn("syncProbeV2", json.dumps(server.INDEX))


if __name__ == "__main__":
    unittest.main()
