"""Shared models and constants for mcp-ios-components."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field

ACCESS_MODE_FULL = "full"
ACCESS_MODE_API_ONLY = "api_only"
API_ONLY_DENY_MESSAGE = "该组件已配置为 API 可见模式，禁止读取实现细节"

DEFAULT_EXCLUDE_COMPONENTS = {"btrtcengine"}
VALID_KINDS = {
    "interface",
    "protocol",
    "method",
    "property",
    "func",
    "class",
    "struct",
    "enum",
    "var",
    "let",
    "typealias",
    "init",
    "subscript",
}
VALID_FORMATS = {"text", "json"}

MAX_KEYWORD_LEN = 500
MAX_READ_LINES = 500
MAX_API_OUTPUT = 200


@dataclass
class AppState:
    pods_dir: str
    cache_dir: str
    keys_file: str
    mixup_marker: str
    webhook_secret: str
    watch_interval: int
    components_config_file: str
    gitlab_url: str
    gitlab_token: str
    index: dict = field(default_factory=dict)
    index_lock: threading.Lock = field(default_factory=threading.Lock)
    last_hash: str = ""
    watch_log: list = field(default_factory=list)
    watch_log_max: int = 50
    reindex_lock: threading.Lock = field(default_factory=threading.Lock)
