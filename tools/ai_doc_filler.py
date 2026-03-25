#!/usr/bin/env python3
"""AI 文档补全模块 — 对缺注释的 API 用 LLM 生成说明。

Created by yuxilong on 2026/03/25
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-haiku-4-5-20241022"


def read_source_context(pods_dir: str, comp_dir: str, rel_file: str, line: int, radius: int = 30) -> str | None:
    """读取 API 声明所在源文件的上下文（前后 radius 行）。"""
    filepath = os.path.join(pods_dir, comp_dir, rel_file)
    if not os.path.exists(filepath):
        return None
    try:
        with open(filepath, encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
    except OSError:
        return None

    total = len(lines)
    start = max(0, line - 1 - radius)
    end = min(total, line + radius)
    return "".join(lines[start:end])


def build_prompt(declaration: str, source_context: str, component_name: str) -> str:
    """构建 LLM 补全 prompt。"""
    return f"""你是一位资深 iOS 开发工程师。请根据以下 Objective-C/Swift 方法声明和源码上下文，生成简洁的中文 API 文档。

## 组件：{component_name}

## 方法声明
```
{declaration}
```

## 源码上下文
```
{source_context}
```

## 要求
1. 用 1-2 句话描述方法的功能和用途
2. 如果有参数，列出每个参数的含义（格式：`参数名` — 说明）
3. 如果有返回值，说明返回值含义
4. 语言简洁，不要废话

## 输出格式（严格遵循）
功能说明

**参数：**
- `参数名` — 说明

**返回值：** 说明
"""


def fill_missing_comments(
    index: dict,
    pods_dir: str,
    *,
    component_name: str = "",
    dry_run: bool = False,
    api_key: str = "",
    model: str = DEFAULT_MODEL,
) -> dict:
    """对缺注释的 API 进行 AI 补全。

    返回 {组件名: {API name: 生成的说明}} 的字典。
    dry_run 模式只统计数量，不调用 LLM。
    """
    targets = {}
    for comp in index.values():
        name = comp["name"]
        if component_name and name != component_name:
            continue
        comp_dir = comp.get("dir") or name
        missing = []
        for api in comp.get("apis", []):
            comment = (api.get("comment") or "").strip()
            if not comment or len(comment) < 6:
                missing.append(api)
        if missing:
            targets[name] = {"comp_dir": comp_dir, "apis": missing}

    if dry_run:
        stats = {name: len(info["apis"]) for name, info in targets.items()}
        total = sum(stats.values())
        return {"dry_run": True, "total": total, "by_component": stats}

    # dry_run=False 时才需要 API key
    if not api_key:
        api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        raise ValueError("需要设置 ANTHROPIC_API_KEY 环境变量或传入 api_key 参数")

    try:
        import anthropic
    except ImportError:
        raise ImportError("需要安装 anthropic 包：pip install anthropic")

    client = anthropic.Anthropic(api_key=api_key)
    results = {}

    for name, info in targets.items():
        comp_results = {}
        for api in info["apis"]:
            context = read_source_context(
                pods_dir, info["comp_dir"], api["file"], api.get("line", 1)
            )
            if not context:
                continue

            prompt = build_prompt(api["declaration"], context, name)
            try:
                response = client.messages.create(
                    model=model,
                    max_tokens=500,
                    messages=[{"role": "user", "content": prompt}],
                )
                generated = response.content[0].text.strip()
                comp_results[api["name"]] = generated
            except Exception as e:
                logger.warning("AI 补全失败 [%s.%s]: %s", name, api["name"], e)
                comp_results[api["name"]] = "*AI 补全暂不可用*"

        if comp_results:
            results[name] = comp_results

    return {"dry_run": False, "results": results}
