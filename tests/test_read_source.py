import os
import tempfile
import unittest
import importlib


class TestReadSource(unittest.TestCase):
    def _server(self):
        import mcp_server as s
        return importlib.reload(s)

    def test_read_source_basic_and_limits_and_security(self):
        s = self._server()

        with tempfile.TemporaryDirectory() as d:
            # Create a fake pods layout
            comp_dir = os.path.join(d, "BTBaseKit")
            os.makedirs(os.path.join(comp_dir, "Sources"), exist_ok=True)
            fpath = os.path.join(comp_dir, "Sources", "Foo.h")
            with open(fpath, "w", encoding="utf-8") as f:
                for i in range(1, 101):
                    f.write(f"// line {i}\n")

            # Inject index to allow read_source to locate the file.
            with s.INDEX_LOCK:
                s.PODS_DIR = d
                s.INDEX = {
                    "BTBaseKit": {
                        "name": "BTBaseKit",
                        "dir": "BTBaseKit",
                        "podspec": "BTBaseKit.podspec",
                        "summary": "",
                        "description": "",
                        "files": ["Sources/Foo.h"],
                        "source_count": 1,
                        "apis": [],
                    }
                }

            out = s.read_source("BTBaseKit", "Foo.h", start=1, end=3)
            self.assertIn("Foo.h", out)
            self.assertIn("line 1", out)
            self.assertIn("line 3", out)

            # Over-limit reads should be rejected
            too_many = s.read_source("BTBaseKit", "Foo.h", start=1, end=s.MAX_READ_LINES + 10)
            self.assertTrue("最多读取" in too_many or "读取行数" in too_many)

            # Path traversal must be rejected
            trav = s.read_source("BTBaseKit", "../secrets.txt", start=1, end=2)
            self.assertTrue("非法路径" in trav or "禁止访问" in trav or "文件未找到" in trav)

    def test_read_source_fuzzy_match(self):
        s = self._server()

        with tempfile.TemporaryDirectory() as d:
            comp_dir = os.path.join(d, "BTBaseKit")
            os.makedirs(os.path.join(comp_dir, "Sub"), exist_ok=True)
            fpath = os.path.join(comp_dir, "Sub", "UIImage+BTExtension.h")
            with open(fpath, "w", encoding="utf-8") as f:
                f.write("// header\n")

            with s.INDEX_LOCK:
                s.PODS_DIR = d
                s.INDEX = {
                    "BTBaseKit": {
                        "name": "BTBaseKit",
                        "dir": "BTBaseKit",
                        "podspec": "BTBaseKit.podspec",
                        "summary": "",
                        "description": "",
                        "files": ["Sub/UIImage+BTExtension.h"],
                        "source_count": 1,
                        "apis": [],
                    }
                }

            out = s.read_source("BTBaseKit", "BTExtension", start=1, end=1)
            self.assertIn("UIImage+BTExtension.h", out)


if __name__ == "__main__":
    unittest.main()
