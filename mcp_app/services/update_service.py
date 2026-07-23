"""Update and watch services."""

from __future__ import annotations

import datetime
import os
import subprocess
import sys
import time
from typing import Callable



def reindex(
    *,
    pods_dir: str,
    cache_dir: str,
    reindex_lock,
    set_index: Callable[[dict], None],
    set_last_hash: Callable[[str], None],
    build_index: Callable[[str], dict],
    discover_components: Callable[[str], set],
    compute_hash: Callable[[str, set], str],
) -> None:
    if not reindex_lock.acquire(blocking=False):
        print("[mcp-ios] ⚠️ reindex 已在运行，跳过本次请求", file=sys.stderr)
        return

    try:
        print("[mcp-ios] 🔄 webhook 触发重建索引...", file=sys.stderr)

        git_dir = os.path.join(pods_dir, ".git")
        if os.path.isdir(git_dir):
            try:
                result = subprocess.run(
                    ["git", "pull", "--ff-only"],
                    cwd=pods_dir,
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                print(f"[mcp-ios] git pull: {result.stdout.strip()}", file=sys.stderr)
                if result.returncode != 0:
                    print(f"[mcp-ios] git pull stderr: {result.stderr.strip()}", file=sys.stderr)
            except Exception as e:
                print(f"[mcp-ios] git pull 失败: {e}", file=sys.stderr)

        cache_path = os.path.join(cache_dir, "index.json")
        if os.path.exists(cache_path):
            os.remove(cache_path)

        new_index = build_index(pods_dir)
        set_index(new_index)

        components = discover_components(pods_dir)
        set_last_hash(compute_hash(pods_dir, components))

        print(f"[mcp-ios] ✅ 索引已更新 ({len(new_index)} 个组件)", file=sys.stderr)
    finally:
        reindex_lock.release()


def check_for_updates(
    *,
    pods_dir: str,
    cache_dir: str,
    last_hash: str,
    watch_log: list,
    watch_log_max: int,
    set_index: Callable[[dict], None],
    set_last_hash: Callable[[str], None],
    discover_git_repos: Callable[[str], list],
    git_pull_repo: Callable[[str], dict],
    discover_components: Callable[[str], set],
    compute_hash: Callable[[str, set], str],
    build_index: Callable[[str], dict],
    reindex_lock=None,
) -> dict:
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = {"time": timestamp, "repos": [], "reindexed": False, "skipped": False}

    acquired = False
    if reindex_lock is not None:
        acquired = reindex_lock.acquire(blocking=False)
        if not acquired:
            log_entry["skipped"] = True
            watch_log.append(log_entry)
            if len(watch_log) > watch_log_max:
                watch_log.pop(0)
            print("[mcp-ios] ⏭️ 组件同步或索引刷新正在运行，跳过本轮检查", file=sys.stderr)
            return log_entry

    try:
        repos = discover_git_repos(pods_dir)
        any_updated = False

        for repo in repos:
            result = git_pull_repo(repo)
            repo_name = os.path.basename(result["path"]) or "root"
            if result["error"]:
                print(f"[mcp-ios] ⚠️ {repo_name}: {result['error']}", file=sys.stderr)
            if result["updated"]:
                any_updated = True
            log_entry["repos"].append(
                {
                    "name": repo_name,
                    "updated": result["updated"],
                    "changes": len(result["changes"]),
                    "error": result["error"],
                }
            )

        if not any_updated:
            components = discover_components(pods_dir)
            current_hash = compute_hash(pods_dir, components)
            if current_hash != last_hash and last_hash:
                any_updated = True
                print("[mcp-ios] 🔍 检测到文件系统变更", file=sys.stderr)

        if any_updated:
            cache_path = os.path.join(cache_dir, "index.json")
            if os.path.exists(cache_path):
                os.remove(cache_path)

            new_index = build_index(pods_dir)
            set_index(new_index)
            components = discover_components(pods_dir)
            set_last_hash(compute_hash(pods_dir, components))

            log_entry["reindexed"] = True
            print(f"[mcp-ios] ✅ 索引已更新 ({len(new_index)} 个组件)", file=sys.stderr)
        else:
            print("[mcp-ios] ℹ️ 无更新", file=sys.stderr)

        watch_log.append(log_entry)
        if len(watch_log) > watch_log_max:
            watch_log.pop(0)

        return log_entry
    finally:
        if acquired:
            reindex_lock.release()


def watch_loop(interval: int, *, check_for_updates: Callable[[], dict]) -> None:
    print(f"[mcp-ios] 🔄 定时检查已启动，间隔 {interval} 秒", file=sys.stderr)
    while True:
        time.sleep(interval)
        try:
            check_for_updates()
        except Exception as e:
            print(f"[mcp-ios] ❌ 定时检查异常: {e}", file=sys.stderr)
