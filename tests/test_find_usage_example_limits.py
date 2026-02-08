import os
import tempfile
import unittest
import importlib


class TestFindUsageExampleLimits(unittest.TestCase):
    def _server(self):
        import mcp_server as s
        return importlib.reload(s)

    def test_find_usage_example_no_hits(self):
        s = self._server()

        with tempfile.TemporaryDirectory() as d:
            # Base component
            os.makedirs(os.path.join(d, "btbasekit", "Sources"), exist_ok=True)
            with open(os.path.join(d, "btbasekit", "BTBaseKit.podspec"), "w", encoding="utf-8") as f:
                f.write("Pod::Spec.new do |s|\n  s.name = 'BTBaseKit'\nend\n")
            with open(os.path.join(d, "btbasekit", "Sources", "Foo.h"), "w", encoding="utf-8") as f:
                f.write("@interface Foo : NSObject\n@end\n")

            os.environ["IOS_PODS_INCLUDE"] = "btbasekit"
            idx = s.build_index(d)
            with s.INDEX_LOCK:
                s.PODS_DIR = d
                s.INDEX = idx

            out = s.find_usage_example("BTBaseKit")
            # Should not crash and should mention no example or return some guidance text.
            self.assertTrue(isinstance(out, str) and len(out) > 0)

        os.environ.pop("IOS_PODS_INCLUDE", None)


if __name__ == "__main__":
    unittest.main()
