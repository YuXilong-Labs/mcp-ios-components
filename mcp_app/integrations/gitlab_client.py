"""GitLab API operations."""

from __future__ import annotations

import json
import re
import sys



def fetch_gitlab_group_repos(group_id: str, gitlab_url: str, gitlab_token: str) -> list:
    import urllib.error
    import urllib.request

    if not gitlab_token:
        print("[mcp-ios] ⚠️ 未配置 GITLAB_TOKEN", file=sys.stderr)
        return []

    repos = []
    page = 1
    per_page = 100

    while True:
        url = f"{gitlab_url}/api/v4/groups/{group_id}/projects?per_page={per_page}&page={page}&include_subgroups=true"

        req = urllib.request.Request(url)
        req.add_header("PRIVATE-TOKEN", gitlab_token)

        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                data = json.loads(response.read().decode())
                if not data:
                    break

                for project in data:
                    repos.append(
                        {
                            "id": project["id"],
                            "name": project["name"],
                            "path": project["path"],
                            "ssh_url": project.get("ssh_url_to_repo", ""),
                            "http_url": project.get("http_url_to_repo", ""),
                            "default_branch": project.get("default_branch", "main"),
                        }
                    )

                page += 1
                if len(data) < per_page:
                    break

        except urllib.error.HTTPError as e:
            print(f"[mcp-ios] ❌ GitLab API 错误: {e.code} {e.reason}", file=sys.stderr)
            break
        except Exception as e:
            print(f"[mcp-ios] ❌ 请求失败: {e}", file=sys.stderr)
            break

    return repos


def check_repo_is_base_component(repo_url: str, gitlab_url: str, branch: str = "main", gitlab_token: str = "") -> tuple:
    import urllib.request

    if repo_url.startswith("git@"):
        path = repo_url.split(":")[-1].replace(".git", "")
    else:
        path = "/".join(repo_url.split("/")[-2:]).replace(".git", "")

    project_encoded = path.replace("/", "%2F")

    url = f"{gitlab_url}/api/v4/projects/{project_encoded}/repository/tree?ref={branch}&per_page=100"
    req = urllib.request.Request(url)
    if gitlab_token:
        req.add_header("PRIVATE-TOKEN", gitlab_token)

    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            files = json.loads(response.read().decode())
    except Exception as e:
        return (False, None, f"无法获取文件列表: {e}")

    podspec_file = None
    for f in files:
        if f["name"].endswith(".podspec") and f["type"] == "blob":
            podspec_file = f["name"]
            break

    if not podspec_file:
        return (False, None, "无 podspec 文件")

    file_encoded = podspec_file.replace("/", "%2F")
    url = f"{gitlab_url}/api/v4/projects/{project_encoded}/repository/files/{file_encoded}/raw?ref={branch}"

    req = urllib.request.Request(url)
    if gitlab_token:
        req.add_header("PRIVATE-TOKEN", gitlab_token)

    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            content = response.read().decode("utf-8", errors="ignore")
    except Exception as e:
        return (False, podspec_file, f"无法读取 podspec: {e}")

    has_nonempty_mixup = False
    mixup_values = []

    for line in content.split("\n"):
        stripped = line.strip()
        if stripped.startswith("#") or stripped.startswith("//"):
            continue

        mixup_match = re.search(r"((?:SUPPORT_MIXUP|BETA_SUPPORT_MIXUP)\s*=\s*\[[^\]]*\])", stripped)
        if mixup_match:
            mixup_values.append(mixup_match.group(1))
            array_match = re.search(r"=\s*\[([^\]]*)\]", mixup_match.group(1))
            if array_match:
                array_content = array_match.group(1).strip()
                if array_content:
                    has_nonempty_mixup = True

    if has_nonempty_mixup:
        return (False, podspec_file, f"非基础组件: {', '.join(mixup_values)}")

    return (True, podspec_file, "基础组件")
