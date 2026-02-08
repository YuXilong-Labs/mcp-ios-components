import os
import tempfile
import unittest
import importlib


class TestBuildIndexMinimal(unittest.TestCase):
    def _server(self):
        import mcp_server as s
        return importlib.reload(s)

    def test_build_index_keys_by_pod_name_and_keeps_dir(self):
        s = self._server()

        with tempfile.TemporaryDirectory() as d:
            # Directory name doesn't match pod name
            os.makedirs(os.path.join(d, "btbasekit"), exist_ok=True)
            with open(os.path.join(d, "btbasekit", "BTBaseKit.podspec"), "w", encoding="utf-8") as f:
                f.write("Pod::Spec.new do |s|\n  s.name = 'BTBaseKit'\n  s.summary = 'base'\nend\n")
            # A minimal header file to be indexed
            os.makedirs(os.path.join(d, "btbasekit", "Sources"), exist_ok=True)
            with open(os.path.join(d, "btbasekit", "Sources", "Foo.h"), "w", encoding="utf-8") as f:
                f.write("@interface Foo : NSObject\n@end\n")

            os.environ["IOS_PODS_INCLUDE"] = "btbasekit"
            idx = s.build_index(d)
            self.assertIn("BTBaseKit", idx)
            self.assertEqual(idx["BTBaseKit"].get("dir"), "btbasekit")
            self.assertEqual(idx["BTBaseKit"].get("name"), "BTBaseKit")

        os.environ.pop("IOS_PODS_INCLUDE", None)


if __name__ == "__main__":
    unittest.main()
