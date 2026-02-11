#!/usr/bin/env python3
"""Compatibility entrypoint for mcp-ios-components.

- Import mode: expose legacy `mcp_server` module surface from `mcp_app.bootstrap`.
- CLI mode: keep `python mcp_server.py ...` behavior unchanged.
"""

from __future__ import annotations

import os
import sys

os.environ.setdefault("IOS_PODS_APP_BASE_DIR", os.path.dirname(os.path.abspath(__file__)))

from mcp_app import bootstrap as _bootstrap

# Keep old path-based behavior (tests and default config resolution rely on this).
_bootstrap.__file__ = __file__

if __name__ == "__main__":
    _bootstrap.main()
else:
    sys.modules[__name__] = _bootstrap
