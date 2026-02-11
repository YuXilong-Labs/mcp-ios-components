import unittest
import importlib


class TestWebhookSignature(unittest.TestCase):
    def _server(self):
        import mcp_server as s
        return importlib.reload(s)

    def test_verify_gitlab_signature(self):
        s = self._server()
        s.WEBHOOK_SECRET = ""
        self.assertFalse(s.verify_gitlab_signature(b"", "x"))

        s.WEBHOOK_SECRET = "tok"
        self.assertTrue(s.verify_gitlab_signature(b"", "tok"))
        self.assertFalse(s.verify_gitlab_signature(b"", "bad"))


if __name__ == "__main__":
    unittest.main()
