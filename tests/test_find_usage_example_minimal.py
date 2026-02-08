import os
import tempfile
import unittest
import importlib


class TestFindUsageExampleMinimal(unittest.TestCase):
    def _server(self):
        import mcp_server as s
        return importlib.reload(s)

    def test_find_usage_example_uses_dir_mapping(self):
        s = self._server()

        with tempfile.TemporaryDirectory() as d:
            # Component A (BTBaseKit) provides a header
            os.makedirs(os.path.join(d, "btbasekit", "Sources"), exist_ok=True)
            with open(os.path.join(d, "btbasekit", "BTBaseKit.podspec"), "w", encoding="utf-8") as f:
                f.write("Pod::Spec.new do |s|\n  s.name = 'BTBaseKit'\nend\n")
            with open(os.path.join(d, "btbasekit", "Sources", "Foo.h"), "w", encoding="utf-8") as f:
                f.write("@interface Foo : NSObject\n@end\n")

            # Component B imports/uses A
            os.makedirs(os.path.join(d, "btrouter", "Sources"), exist_ok=True)
            with open(os.path.join(d, "btrouter", "BTRouter.podspec"), "w", encoding="utf-8") as f:
                f.write("Pod::Spec.new do |s|\n  s.name = 'BTRouter'\nend\n")
            with open(os.path.join(d, "btrouter", "Sources", "Use.m"), "w", encoding="utf-8") as f:
                f.write('#import <BTBaseKit/Foo.h>\nvoid f(){ /* use */ }\n')

            os.environ["IOS_PODS_INCLUDE"] = "btbasekit,btrouter"
            idx = s.build_index(d)
            with s.INDEX_LOCK:
                s.PODS_DIR = d
                s.INDEX = idx

            out = s.find_usage_example("BTBaseKit")
            # Should mention BTRouter and the file path.
            self.assertTrue("BTRouter" in out or "btrouter" in out)
            self.assertIn("Use.m", out)

        os.environ.pop("IOS_PODS_INCLUDE", None)


if __name__ == "__main__":
    unittest.main()
