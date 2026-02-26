import os
import sys
import tempfile
import types
import asyncio
import unittest
import importlib
from contextlib import contextmanager, asynccontextmanager
from unittest import mock


class _DummyRouter:
    @asynccontextmanager
    async def lifespan_context(self, app):
        yield


class _DummyMcpApp:
    def __init__(self):
        self.router = _DummyRouter()

    async def __call__(self, scope, receive, send):
        return None


class _DummyRoute:
    def __init__(self, path, endpoint, methods=None):
        self.path = path
        self.endpoint = endpoint
        self.methods = methods or []


class _DummyMount:
    def __init__(self, path, app=None):
        self.path = path
        self.app = app


class _DummyStarlette:
    def __init__(self, routes=None, lifespan=None):
        self.routes = routes or []
        self.lifespan = lifespan


class _DummyJSONResponse:
    def __init__(self, body, status_code=200):
        self.body = body
        self.status_code = status_code

    async def __call__(self, scope, receive, send):
        return None


class _DummyRequest:
    pass


class TestMainCli(unittest.TestCase):
    def _server(self):
        import mcp_server as s
        return importlib.reload(s)

    def test_main_gen_key_and_list_keys(self):
        s = self._server()

        with mock.patch.object(sys, "argv", ["prog", "--gen-key", "alice"]), \
            mock.patch.object(s, "generate_api_key", return_value="sk-test"):
            s.main()

        with mock.patch.object(sys, "argv", ["prog", "--list-keys"]), \
            mock.patch.object(s, "list_api_keys", return_value=[{"id": 1, "name": "alice"}]):
            s.main()

        with mock.patch.object(sys, "argv", ["prog", "--list-keys"]), \
            mock.patch.object(s, "list_api_keys", return_value=[]):
            s.main()

    def test_main_sync_only_and_gitlab_sync_only_exit_codes(self):
        s = self._server()
        with tempfile.TemporaryDirectory() as d:
            cfg = os.path.join(d, "components.yaml")
            with open(cfg, "w", encoding="utf-8") as f:
                f.write("components:\n  A: git@x:a.git\n")

            with mock.patch.object(sys, "argv", ["prog", "--sync", cfg, "--sync-only", d]), \
                mock.patch.object(s, "sync_components", return_value=[{"status": "error"}]):
                with self.assertRaises(SystemExit) as e:
                    s.main()
                self.assertEqual(e.exception.code, 1)

            with mock.patch.object(sys, "argv", ["prog", "--sync", cfg, "--sync-only", d]), \
                mock.patch.object(s, "sync_components", return_value=[{"status": "updated"}]):
                with self.assertRaises(SystemExit) as e2:
                    s.main()
                self.assertEqual(e2.exception.code, 0)

            with mock.patch.object(sys, "argv", ["prog", "--gitlab-group", "ios", "--sync-only", d]), \
                mock.patch.object(s, "sync_gitlab_group", return_value=[{"status": "error"}]):
                with self.assertRaises(SystemExit) as e3:
                    s.main()
                self.assertEqual(e3.exception.code, 1)

    def test_main_stdio_branch_and_watch(self):
        s = self._server()
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(sys, "argv", ["prog", "--watch", "1", d]), \
                mock.patch.object(s, "build_index", return_value={"A": {}}), \
                mock.patch.object(s, "discover_components", return_value={"A"}), \
                mock.patch.object(s, "compute_hash", return_value="h"), \
                mock.patch.object(s.mcp, "run") as mcp_run, \
                mock.patch.object(s.threading, "Thread") as th:
                inst = mock.Mock()
                th.return_value = inst
                s.main()

            mcp_run.assert_called_once()
            inst.start.assert_called_once()

    def test_align_mcp_http_runtime_settings_disables_localhost_only_security_for_lan_host(self):
        s = self._server()
        fake_transport_security = types.SimpleNamespace(
            enable_dns_rebinding_protection=True,
            allowed_hosts=["127.0.0.1:*", "localhost:*", "[::1]:*"],
            allowed_origins=["http://127.0.0.1:*", "http://localhost:*", "http://[::1]:*"],
        )
        fake_settings = types.SimpleNamespace(host="127.0.0.1", port=8000, transport_security=fake_transport_security)
        fake_mcp = types.SimpleNamespace(settings=fake_settings)

        with mock.patch.object(s, "mcp", fake_mcp):
            s._align_mcp_http_runtime_settings("0.0.0.0", 8900)

        self.assertEqual(fake_settings.host, "0.0.0.0")
        self.assertEqual(fake_settings.port, 8900)
        self.assertFalse(fake_settings.transport_security.enable_dns_rebinding_protection)

    def test_align_mcp_http_runtime_settings_keeps_loopback_security(self):
        s = self._server()
        fake_transport_security = types.SimpleNamespace(
            enable_dns_rebinding_protection=True,
            allowed_hosts=["127.0.0.1:*", "localhost:*", "[::1]:*"],
            allowed_origins=["http://127.0.0.1:*", "http://localhost:*", "http://[::1]:*"],
        )
        fake_settings = types.SimpleNamespace(host="127.0.0.1", port=8000, transport_security=fake_transport_security)
        fake_mcp = types.SimpleNamespace(settings=fake_settings)

        with mock.patch.object(s, "mcp", fake_mcp):
            s._align_mcp_http_runtime_settings("127.0.0.1", 8900)

        self.assertEqual(fake_settings.host, "127.0.0.1")
        self.assertEqual(fake_settings.port, 8900)
        self.assertTrue(fake_settings.transport_security.enable_dns_rebinding_protection)

    def test_main_http_branch_with_fake_modules(self):
        s = self._server()

        uvicorn_mod = types.SimpleNamespace(run=mock.Mock())
        starlette_apps = types.SimpleNamespace(Starlette=_DummyStarlette)
        starlette_responses = types.SimpleNamespace(JSONResponse=_DummyJSONResponse)
        starlette_routing = types.SimpleNamespace(Route=_DummyRoute, Mount=_DummyMount)
        starlette_requests = types.SimpleNamespace(Request=_DummyRequest)

        module_overrides = {
            "uvicorn": uvicorn_mod,
            "starlette.applications": starlette_apps,
            "starlette.responses": starlette_responses,
            "starlette.routing": starlette_routing,
            "starlette.requests": starlette_requests,
        }

        fake_mcp_app = _DummyMcpApp()
        with tempfile.TemporaryDirectory() as d, \
            mock.patch.dict(sys.modules, module_overrides, clear=False), \
            mock.patch.object(sys, "argv", ["prog", "--http", "--port", "9999", d]), \
            mock.patch.object(s, "build_index", return_value={"A": {}}), \
            mock.patch.object(s, "discover_components", return_value={"A"}), \
            mock.patch.object(s, "compute_hash", return_value="h"), \
            mock.patch.object(s, "discover_git_repos", return_value=["/repo"]), \
            mock.patch.object(s, "load_api_keys", return_value={"hash": "u"}), \
            mock.patch.object(s.mcp, "streamable_http_app", return_value=fake_mcp_app), \
            mock.patch.object(s, "validate_api_key", side_effect=[False, True]), \
            mock.patch.object(s.threading, "Thread") as th:
            th.return_value = mock.Mock(start=mock.Mock())
            s.main()

        uvicorn_mod.run.assert_called_once()
        self.assertEqual(getattr(s.mcp.settings, "host", None), "0.0.0.0")
        self.assertEqual(getattr(s.mcp.settings, "port", None), 9999)
        if getattr(s.mcp.settings, "transport_security", None) is not None:
            self.assertFalse(s.mcp.settings.transport_security.enable_dns_rebinding_protection)
        app = uvicorn_mod.run.call_args.args[0]
        self.assertIsInstance(app, _DummyStarlette)
        self.assertEqual(len(app.routes), 3)

        class Req:
            def __init__(self, headers, body=None, raise_json=False):
                self.headers = headers
                self._body = body
                self._raise_json = raise_json

            async def json(self):
                if self._raise_json:
                    raise RuntimeError("bad")
                return self._body or {}

        route_gitlab = app.routes[0]
        route_health = app.routes[1]
        mount = app.routes[2]
        s.WEBHOOK_SECRET = "ok"

        # webhook forbidden
        resp = asyncio.run(route_gitlab.endpoint(Req({"X-Gitlab-Token": ""}, {})))
        self.assertEqual(resp.status_code, 403)
        # webhook invalid json
        resp2 = asyncio.run(route_gitlab.endpoint(Req({"X-Gitlab-Token": "ok"}, raise_json=True)))
        self.assertEqual(resp2.status_code, 400)
        # webhook non-push
        resp3 = asyncio.run(route_gitlab.endpoint(Req({"X-Gitlab-Token": "ok", "X-Gitlab-Event": "Tag Hook"}, {"object_kind": "tag_push"})))
        self.assertEqual(resp3.status_code, 200)
        # webhook push
        resp4 = asyncio.run(route_gitlab.endpoint(Req({"X-Gitlab-Token": "ok", "X-Gitlab-Event": "Push Hook"}, {"object_kind": "push", "project": {"name": "p"}, "commits": [1]})))
        self.assertEqual(resp4.status_code, 200)

        # health
        with s.INDEX_LOCK:
            s.INDEX = {"A": {}}
        resp5 = asyncio.run(route_health.endpoint(Req({})))
        self.assertEqual(resp5.status_code, 200)

        async def receive():
            return {"type": "http.request"}

        async def send(_msg):
            return None

        # auth path unauthorized then authorized
        s.load_api_keys = lambda: {"x": "u"}  # noqa: E731
        decisions = iter([False, True])
        s.validate_api_key = lambda _k, _v: next(decisions)  # noqa: E731
        scope_bad = {"type": "http", "headers": [(b"authorization", b"Bearer bad")]}
        asyncio.run(mount.app(scope_bad, receive, send))
        scope_ok = {"type": "http", "headers": [(b"authorization", b"Bearer ok")]}
        asyncio.run(mount.app(scope_ok, receive, send))

        # lifespan context branch
        async def _run_lifespan():
            async with app.lifespan(app):
                return None

        asyncio.run(_run_lifespan())


if __name__ == "__main__":
    unittest.main()
