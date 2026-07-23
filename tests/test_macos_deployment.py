import importlib.util
import json
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestMacosDeployment(unittest.TestCase):
    def test_launchd_plist_is_isolated_and_localhost_safe(self):
        module = _load_module("install_launchd", os.path.join(ROOT, "deploy", "macos", "install_launchd.py"))
        payload = module.build_launchd_plist(
            label="com.baitu.mcp-ios-components",
            service_root="/srv/mcp",
            data_root="/data/mcp",
            log_root="/logs/mcp",
        )

        self.assertEqual(payload["Label"], "com.baitu.mcp-ios-components")
        self.assertEqual(payload["ProgramArguments"], ["/srv/mcp/deploy/macos/run-mcp.sh"])
        self.assertEqual(payload["EnvironmentVariables"]["MCP_DATA_ROOT"], "/data/mcp")
        self.assertIn("127.0.0.1", payload["EnvironmentVariables"]["NO_PROXY"])
        self.assertTrue(payload["KeepAlive"])

    def test_mcp_response_parser_supports_json_and_sse(self):
        module = _load_module("mcp_http_client", os.path.join(ROOT, "scripts", "mcp_http_client.py"))
        payload = {"jsonrpc": "2.0", "id": 1, "result": {"ok": True}}
        encoded = json.dumps(payload).encode("utf-8")

        self.assertEqual(module.parse_response(encoded, "application/json"), payload)
        self.assertEqual(module.parse_response(b"event: message\ndata: " + encoded + b"\n\n", "text/event-stream"), payload)


if __name__ == "__main__":
    unittest.main()
