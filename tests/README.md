# Tests

This folder contains lightweight tests and smoke checks for MCP server stability.

## Quick run (unit tests)

```bash
cd /Users/yuxilong/clawd/mcp-ios-components
./tests/run_unittest.sh
```

## Optional integration tests (requires local pods repo)

If you have the BaiTuPods workspace locally, set:

```bash
export IOS_PODS_DIR=/Users/yuxilong/Desktop/code/BaiTuPods
export IOS_PODS_INCLUDE=BTBaseKit
./tests/run_unittest.sh
```

Integration tests will be skipped automatically when `IOS_PODS_DIR` is missing.
