"""Component sync services."""

from __future__ import annotations

import os
import subprocess
import sys
from typing import Callable



def sync_component(name: str, config: dict, target_dir: str) -> dict:
    result = {"name": name, "status": "unknown", "message": ""}

    repo = config.get("repo") or config.get("url")
    branch = config.get("branch", "main")

    if not repo:
        result["status"] = "skip"
        result["message"] = "无 repo 配置"
        return result

    comp_dir = os.path.join(target_dir, name)

    try:
        if os.path.exists(comp_dir):
            if os.path.isdir(os.path.join(comp_dir, ".git")):
                subprocess.run(["git", "checkout", branch], cwd=comp_dir, capture_output=True, timeout=30)
                pull = subprocess.run(
                    ["git", "pull", "--ff-only"],
                    cwd=comp_dir,
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                if pull.returncode == 0:
                    result["status"] = "updated"
                    result["message"] = pull.stdout.strip() or "Already up to date"
                else:
                    result["status"] = "error"
                    result["message"] = pull.stderr.strip()
            else:
                result["status"] = "skip"
                result["message"] = "目录存在但非 git 仓库"
        else:
            clone = subprocess.run(
                ["git", "clone", "--branch", branch, "--single-branch", repo, name],
                cwd=target_dir,
                capture_output=True,
                text=True,
                timeout=300,
            )
            if clone.returncode == 0:
                result["status"] = "cloned"
                result["message"] = f"从 {repo} 克隆成功"
            else:
                result["status"] = "error"
                result["message"] = clone.stderr.strip()

    except subprocess.TimeoutExpired:
        result["status"] = "error"
        result["message"] = "操作超时"
    except Exception as e:
        result["status"] = "error"
        result["message"] = str(e)

    return result


def sync_components(
    config_path: str,
    target_dir: str,
    *,
    load_components_config: Callable[[str], dict],
    sync_component_func: Callable[[str, dict, str], dict],
) -> list:
    config = load_components_config(config_path)

    if not config:
        print(f"[mcp-ios] ⚠️ 配置文件为空或不存在: {config_path}", file=sys.stderr)
        return []

    components = config.get("components", {})
    if not components:
        print("[mcp-ios] ⚠️ 配置文件中无 components 定义", file=sys.stderr)
        return []

    os.makedirs(target_dir, exist_ok=True)

    results = []
    print(f"[mcp-ios] 🔄 开始同步 {len(components)} 个组件...", file=sys.stderr)

    for name, comp_config in components.items():
        if isinstance(comp_config, str):
            comp_config = {"repo": comp_config}

        result = sync_component_func(name, comp_config, target_dir)
        results.append(result)

        status_icon = {"cloned": "✅", "updated": "🔄", "skip": "⏭️", "error": "❌"}.get(result["status"], "❓")

        print(f"  {status_icon} {name}: {result['message']}", file=sys.stderr)

    cloned = sum(1 for r in results if r["status"] == "cloned")
    updated = sum(1 for r in results if r["status"] == "updated")
    errors = sum(1 for r in results if r["status"] == "error")

    print(f"[mcp-ios] 📊 同步完成: {cloned} 克隆, {updated} 更新, {errors} 错误", file=sys.stderr)

    return results


def sync_gitlab_group(
    group_id: str,
    target_dir: str,
    *,
    gitlab_url: str,
    gitlab_token: str,
    use_ssh: bool,
    fetch_gitlab_group_repos: Callable[[str, str, str], list],
    check_repo_is_base_component: Callable[[str, str, str, str], tuple],
    sync_component_func: Callable[[str, dict, str], dict],
) -> list:
    print(f"[mcp-ios] 🔍 正在从 GitLab group '{group_id}' 获取仓库列表...", file=sys.stderr)

    repos = fetch_gitlab_group_repos(group_id, gitlab_url, gitlab_token)

    if not repos:
        print("[mcp-ios] ⚠️ 未找到仓库或获取失败", file=sys.stderr)
        return []

    print(f"[mcp-ios] 📦 发现 {len(repos)} 个仓库，正在检查是否为基础组件...", file=sys.stderr)

    os.makedirs(target_dir, exist_ok=True)

    results = []
    base_count = 0
    skip_count = 0

    for repo in repos:
        name = repo["path"]
        repo_url = repo["ssh_url"] if use_ssh else repo["http_url"]
        branch = repo["default_branch"]

        is_base, _, reason = check_repo_is_base_component(repo_url, gitlab_url, branch, gitlab_token)

        if not is_base:
            print(f"  ⏭️ {name}: {reason}", file=sys.stderr)
            results.append({"name": name, "status": "skip", "message": reason})
            skip_count += 1
            continue

        base_count += 1

        result = sync_component_func(name, {"repo": repo_url, "branch": branch}, target_dir)
        results.append(result)

        status_icon = {"cloned": "✅", "updated": "🔄", "skip": "⏭️", "error": "❌"}.get(result["status"], "❓")
        print(f"  {status_icon} {name}: {result['message']}", file=sys.stderr)

    cloned = sum(1 for r in results if r["status"] == "cloned")
    updated = sum(1 for r in results if r["status"] == "updated")
    errors = sum(1 for r in results if r["status"] == "error")

    print(
        f"[mcp-ios] 📊 完成: {base_count} 基础组件 ({cloned} 克隆, {updated} 更新, {errors} 错误), {skip_count} 非基础组件已跳过",
        file=sys.stderr,
    )

    return results
