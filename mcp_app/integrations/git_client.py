"""Git operations for local repositories."""

from __future__ import annotations

import os
import subprocess
import sys



def discover_git_repos(pods_dir: str) -> list:
    repos = []
    if os.path.isdir(os.path.join(pods_dir, ".git")):
        repos.append(pods_dir)
    try:
        for entry in os.listdir(pods_dir):
            entry_path = os.path.join(pods_dir, entry)
            if os.path.isdir(entry_path) and os.path.isdir(os.path.join(entry_path, ".git")):
                repos.append(entry_path)
    except OSError:
        pass
    return repos


def git_pull_repo(repo_path: str) -> dict:
    result = {"path": repo_path, "updated": False, "changes": [], "error": None}
    repo_name = os.path.basename(repo_path) or "root"

    try:
        fetch = subprocess.run(
            ["git", "fetch", "--quiet"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if fetch.returncode != 0:
            result["error"] = f"fetch failed: {fetch.stderr.strip()}"
            return result

        branch = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=10,
        )
        current_branch = branch.stdout.strip() or "main"

        diff_stat = subprocess.run(
            ["git", "diff", "--stat", f"HEAD..origin/{current_branch}"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=30,
        )
        diff_output = diff_stat.stdout.strip()

        if not diff_output:
            return result

        pull = subprocess.run(
            ["git", "pull", "--ff-only"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if pull.returncode != 0:
            result["error"] = f"pull failed: {pull.stderr.strip()}"
            return result

        result["updated"] = True
        for line in diff_output.split("\n"):
            line = line.strip()
            if line and "|" in line:
                filename = line.split("|")[0].strip()
                result["changes"].append(filename)

        print(f"[mcp-ios] ✅ {repo_name}: {len(result['changes'])} 文件更新", file=sys.stderr)
    except subprocess.TimeoutExpired:
        result["error"] = "timeout"
    except Exception as e:
        result["error"] = str(e)

    return result
