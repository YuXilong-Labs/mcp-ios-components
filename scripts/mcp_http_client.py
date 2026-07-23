#!/usr/bin/env python3
"""Small stdlib MCP HTTP client used by deployment smoke checks."""

from __future__ import annotations

import argparse
import json
import os
import re
import urllib.error
import urllib.request


def parse_response(body: bytes, content_type: str) -> dict:
    text = body.decode("utf-8")
    if "text/event-stream" not in content_type:
        return json.loads(text) if text.strip() else {}

    for event in text.split("\n\n"):
        data = "\n".join(line[5:].lstrip() for line in event.splitlines() if line.startswith("data:"))
        if data and data != "[DONE]":
            return json.loads(data)
    return {}


class MCPHttpClient:
    def __init__(self, url: str, timeout: int = 120, api_key: str = ""):
        self.url = url
        self.timeout = timeout
        self.api_key = api_key
        self.session_id = ""
        self._request_id = 0
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def _send(self, payload: dict) -> dict:
        headers = {
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
        }
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        request = urllib.request.Request(
            self.url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with self._opener.open(request, timeout=self.timeout) as response:
                self.session_id = response.headers.get("Mcp-Session-Id", self.session_id)
                return parse_response(response.read(), response.headers.get("Content-Type", ""))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"MCP HTTP {exc.code}: {body[:500]}") from exc

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    def initialize(self) -> None:
        response = self._send(
            {
                "jsonrpc": "2.0",
                "id": self._next_id(),
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {},
                    "clientInfo": {"name": "mcp-deploy-check", "version": "1.0"},
                },
            }
        )
        if response.get("error"):
            raise RuntimeError(str(response["error"]))
        self._send({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})

    def call_tool(self, name: str, arguments: dict) -> str:
        response = self._send(
            {
                "jsonrpc": "2.0",
                "id": self._next_id(),
                "method": "tools/call",
                "params": {"name": name, "arguments": arguments},
            }
        )
        if response.get("error"):
            raise RuntimeError(str(response["error"]))
        result = response.get("result", {})
        if result.get("isError"):
            raise RuntimeError(str(result))
        return "\n".join(item.get("text", "") for item in result.get("content", []) if item.get("type") == "text")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8900/mcp")
    parser.add_argument("--tool", required=True)
    parser.add_argument("--arguments", default="{}")
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--api-key", default=os.environ.get("MCP_API_KEY", ""))
    parser.add_argument("--contains", default="")
    parser.add_argument("--fail-sync-errors", action="store_true")
    args = parser.parse_args()

    arguments = json.loads(args.arguments)
    client = MCPHttpClient(args.url, timeout=args.timeout, api_key=args.api_key)
    client.initialize()
    output = client.call_tool(args.tool, arguments)
    print(output)

    if args.contains and args.contains not in output:
        raise RuntimeError(f"MCP response does not contain expected text: {args.contains}")
    if args.fail_sync_errors:
        match = re.search(r"统计:\s*\d+ 克隆,\s*\d+ 更新,\s*(\d+) 错误", output)
        if not match:
            raise RuntimeError("MCP sync result did not contain a recognizable summary")
        if int(match.group(1)) > 0:
            raise RuntimeError(f"MCP component sync reported {match.group(1)} errors")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
