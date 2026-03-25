---
name: verify
description: Run full project verification — tests + MCP tool list consistency check
---

## Steps

1. Run the full test suite:
   ```bash
   cd /Users/yuxilong/clawd/mcp-ios-components && pytest
   ```

2. Verify MCP tool list in README matches actual registered tools:
   - Read `README.md` and extract the documented tool names
   - Read `mcp_app/bootstrap.py` (or wherever tools are registered) and extract actual tool names
   - Report any mismatches (tools in code but not in README, or vice versa)

3. If any tests fail or mismatches are found, report the issues clearly with file paths and suggested fixes.

4. If everything passes, confirm with a brief summary.
