import os
import tempfile
import unittest
import importlib


class TestParsersAndFiles(unittest.TestCase):
    def _server(self):
        import mcp_server as s
        return importlib.reload(s)

    def test_walk_dir_and_source_file(self):
        s = self._server()
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "A", "Example"), exist_ok=True)
            os.makedirs(os.path.join(d, ".hidden"), exist_ok=True)
            with open(os.path.join(d, "A", "f.swift"), "w", encoding="utf-8") as f:
                f.write("x")
            with open(os.path.join(d, "A", "Example", "skip.h"), "w", encoding="utf-8") as f:
                f.write("x")
            files = s.walk_dir(d)
            self.assertTrue(any("f.swift" in x for x in files))
            self.assertFalse(any("skip.h" in x for x in files))
            self.assertTrue(s.is_source_file("a.mm"))
            self.assertFalse(s.is_source_file("a.txt"))

    def test_parse_podspec_fallback_empty(self):
        s = self._server()
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "X"), exist_ok=True)
            spec = s.parse_podspec(os.path.join(d, "X"), "X")
            self.assertEqual(spec["pod_name"], "X")

            with open(os.path.join(d, "X", "Other.podspec"), "w", encoding="utf-8") as f:
                f.write("Pod::Spec.new do |s|\n  s.summary = 'sum'\n  s.description = <<-DESC\nabc\nDESC\nend\n")
            spec2 = s.parse_podspec(os.path.join(d, "X"), "X")
            self.assertEqual(spec2["pod_name"], "X")
            self.assertEqual(spec2["summary"], "sum")
            self.assertIn("abc", spec2["description"])

    def test_extract_apis_swift_objc_and_missing(self):
        s = self._server()
        with tempfile.TemporaryDirectory() as d:
            swift = os.path.join(d, "A.swift")
            with open(swift, "w", encoding="utf-8") as f:
                f.write(
                    "/// doc\n"
                    "public class A {}\n"
                    "public func foo() {}\n"
                    "public init() {}\n"
                    "public var vv: Int = 0\n"
                    "public typealias T = Int\n"
                )
            apis_swift = s.extract_apis(swift, "A.swift")
            kinds = {a["kind"] for a in apis_swift}
            self.assertIn("class", kinds)
            self.assertIn("func", kinds)
            self.assertIn("init", kinds)
            self.assertIn("var", kinds)
            self.assertIn("typealias", kinds)

            hdr = os.path.join(d, "B.h")
            with open(hdr, "w", encoding="utf-8") as f:
                f.write(
                    "/** block */\n"
                    "@interface B : NSObject\n"
                    "@property (nonatomic, strong) NSString *name;\n"
                    "CG_INLINE int f1(int x){return x;}\n"
                    "FOUNDATION_EXTERN void f2(void);\n"
                    "- (void)m1;\n"
                    "@end\n"
                )
            apis_h = s.extract_apis(hdr, "B.h")
            kinds_h = [a["kind"] for a in apis_h]
            self.assertIn("interface", kinds_h)
            self.assertIn("property", kinds_h)
            self.assertIn("func", kinds_h)
            self.assertIn("method", kinds_h)

            self.assertEqual(s.extract_apis(os.path.join(d, "none.swift"), "none.swift"), [])


if __name__ == "__main__":
    unittest.main()
