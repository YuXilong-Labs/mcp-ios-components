#!/usr/bin/env python3
"""Install mcp-ios-components skills to Codex and/or Claude skill directories.

Features:
- Supports targets: codex / claude / all
- Auto-detects common skill directories (can override with flags)
- Shows source/existing versions before overwrite
- Interactive overwrite confirmation (or `--yes`)
- Post-install validation (SKILL.md / frontmatter name / version / agents/openai.yaml)
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[1]
SKILLS_ROOT = REPO_ROOT / "skills"
EXCLUDE_SKILL_DIRS = {"evals"}


@dataclass
class SkillInfo:
    dir_name: str
    path: Path
    frontmatter_name: str
    version: str
    description: str


@dataclass
class InstallResult:
    target: str
    base_dir: Path
    installed: list[tuple[SkillInfo, Path]]
    skipped_existing: list[tuple[SkillInfo, Path]]
    overwritten: list[tuple[SkillInfo, Path, str]]  # old version


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Install bundled skills for Claude/Codex")
    p.add_argument(
        "--target",
        choices=["codex", "claude", "all"],
        default="all",
        help="安装目标（默认 all）",
    )
    p.add_argument("--codex-dir", help="Codex skills 目录（默认自动探测）")
    p.add_argument("--claude-dir", help="Claude skills 目录（默认自动探测）")
    p.add_argument("--yes", action="store_true", help="覆盖时不询问，直接确认")
    p.add_argument("--dry-run", action="store_true", help="仅打印计划，不实际复制")
    p.add_argument(
        "--include",
        action="append",
        default=[],
        help="仅安装指定 skill（可重复，如 --include ios-component-review）",
    )
    p.add_argument(
        "--skip-claude-if-undetected",
        action="store_true",
        help="target=all 时若未探测到 Claude 目录则跳过 Claude 而非报错",
    )
    return p.parse_args()


def _strip_quotes(s: str) -> str:
    s = s.strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in {'"', "'"}:
        return s[1:-1]
    return s


def parse_skill_frontmatter(skill_md: Path) -> tuple[str, str, str]:
    text = skill_md.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not m:
        raise ValueError(f"SKILL.md frontmatter 格式无效: {skill_md}")
    fm = m.group(1)

    name_match = re.search(r"^name:\s*(.+)$", fm, re.M)
    version_match = re.search(r"^\s*version:\s*(.+)$", fm, re.M)
    desc_match = re.search(r"^description:\s*(.+)$", fm, re.M)

    name = _strip_quotes(name_match.group(1)) if name_match else ""
    version = _strip_quotes(version_match.group(1)) if version_match else ""
    desc = _strip_quotes(desc_match.group(1)) if desc_match else ""
    return name, version, desc


def discover_skills(include: set[str] | None = None) -> list[SkillInfo]:
    skills: list[SkillInfo] = []
    for child in sorted(SKILLS_ROOT.iterdir()):
        if not child.is_dir():
            continue
        if child.name in EXCLUDE_SKILL_DIRS:
            continue
        skill_md = child / "SKILL.md"
        if not skill_md.exists():
            continue
        if include and child.name not in include:
            continue
        name, version, desc = parse_skill_frontmatter(skill_md)
        skills.append(
            SkillInfo(
                dir_name=child.name,
                path=child,
                frontmatter_name=name,
                version=version,
                description=desc,
            )
        )
    return skills


def resolve_codex_dir(override: str | None) -> Path:
    if override:
        return Path(os.path.expanduser(override)).resolve()
    codex_home = os.environ.get("CODEX_HOME")
    if codex_home:
        return (Path(codex_home).expanduser() / "skills").resolve()
    return (Path.home() / ".codex" / "skills").resolve()


def resolve_claude_dir(override: str | None) -> Path | None:
    if override:
        return Path(os.path.expanduser(override)).resolve()

    env_dir = os.environ.get("CLAUDE_SKILLS_DIR")
    if env_dir:
        return Path(os.path.expanduser(env_dir)).resolve()

    candidates = [
        Path.home() / ".claude" / "skills",
        Path.home() / ".config" / "claude" / "skills",
        Path.home() / "Library" / "Application Support" / "Claude" / "skills",
    ]

    for c in candidates:
        if c.exists():
            return c.resolve()

    # Fallback: if ~/.claude exists (file/dir/symlink path), prefer ~/.claude/skills for one-click setup.
    claude_root = Path.home() / ".claude"
    if claude_root.exists():
        return (claude_root / "skills").resolve()

    return None


def read_installed_version(dst_skill_dir: Path) -> str:
    skill_md = dst_skill_dir / "SKILL.md"
    if not skill_md.exists():
        return "(缺少 SKILL.md)"
    try:
        _, version, _ = parse_skill_frontmatter(skill_md)
        return version or "(无 version)"
    except Exception as exc:
        return f"(解析失败: {exc})"


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def prompt_yes_no(question: str, default_no: bool = True) -> bool:
    if not sys.stdin.isatty():
        return False if default_no else True
    suffix = "[y/N]" if default_no else "[Y/n]"
    ans = input(f"{question} {suffix} ").strip().lower()
    if not ans:
        return not default_no
    return ans in {"y", "yes"}


def copy_skill(src: Path, dst: Path, dry_run: bool) -> None:
    if dry_run:
        return
    if dst.exists():
        shutil.rmtree(dst)
    ensure_parent(dst)
    shutil.copytree(src, dst)


def validate_install(target: str, base_dir: Path, skills: Iterable[SkillInfo]) -> list[str]:
    errors: list[str] = []
    for skill in skills:
        dst = base_dir / skill.dir_name
        if not dst.exists() or not dst.is_dir():
            errors.append(f"{target}:{skill.dir_name} 未安装到 {dst}")
            continue

        skill_md = dst / "SKILL.md"
        if not skill_md.exists():
            errors.append(f"{target}:{skill.dir_name} 缺少 SKILL.md")
            continue

        try:
            name, version, _ = parse_skill_frontmatter(skill_md)
        except Exception as exc:
            errors.append(f"{target}:{skill.dir_name} frontmatter 解析失败: {exc}")
            continue

        if name and name != skill.dir_name:
            errors.append(
                f"{target}:{skill.dir_name} frontmatter name={name} 与目录名不一致"
            )
        if not version:
            errors.append(f"{target}:{skill.dir_name} 缺少 metadata.version")

        # 双兼容要求：这些技能应包含 agents/openai.yaml
        if not (dst / "agents" / "openai.yaml").exists():
            errors.append(f"{target}:{skill.dir_name} 缺少 agents/openai.yaml")
    return errors


def install_to_target(
    *,
    target: str,
    base_dir: Path,
    skills: list[SkillInfo],
    assume_yes: bool,
    dry_run: bool,
) -> InstallResult:
    conflicts: list[tuple[SkillInfo, Path, str]] = []
    fresh: list[tuple[SkillInfo, Path]] = []
    for skill in skills:
        dst = base_dir / skill.dir_name
        if dst.exists():
            conflicts.append((skill, dst, read_installed_version(dst)))
        else:
            fresh.append((skill, dst))

    print(f"\n=== 安装目标: {target} ===")
    print(f"目录: {base_dir}")
    print(f"技能数: {len(skills)}")
    print("版本清单:")
    for skill in skills:
        dst = base_dir / skill.dir_name
        old = read_installed_version(dst) if dst.exists() else "(未安装)"
        print(f"- {skill.dir_name}: {old} -> {skill.version or '(无 version)'}")

    if conflicts and not assume_yes:
        print(f"\n检测到 {len(conflicts)} 个已存在技能，覆盖将替换其目录内容。")
        if not prompt_yes_no("是否继续覆盖安装？", default_no=True):
            print(f"已取消 {target} 安装。")
            return InstallResult(target, base_dir, [], [(s, d) for s, d, _ in conflicts] + fresh, conflicts)
    elif conflicts and assume_yes:
        print(f"\n检测到 {len(conflicts)} 个已存在技能，按 --yes 自动覆盖。")

    installed: list[tuple[SkillInfo, Path]] = []
    overwritten: list[tuple[SkillInfo, Path, str]] = []

    if not dry_run:
        base_dir.mkdir(parents=True, exist_ok=True)

    for skill, dst in fresh:
        print(f"安装 {skill.dir_name} -> {dst}")
        copy_skill(skill.path, dst, dry_run)
        installed.append((skill, dst))

    for skill, dst, old_ver in conflicts:
        print(f"覆盖 {skill.dir_name} ({old_ver} -> {skill.version}) -> {dst}")
        copy_skill(skill.path, dst, dry_run)
        installed.append((skill, dst))
        overwritten.append((skill, dst, old_ver))

    return InstallResult(target, base_dir, installed, [], overwritten)


def print_validation(target: str, base_dir: Path, skills: list[SkillInfo], dry_run: bool) -> bool:
    if dry_run:
        print(f"[{target}] dry-run 模式，跳过安装校验")
        return True
    errors = validate_install(target, base_dir, skills)
    if errors:
        print(f"[{target}] 安装校验失败：")
        for err in errors:
            print(f"- {err}")
        return False
    print(f"[{target}] 安装校验通过（{len(skills)} 个技能）")
    return True


def main() -> int:
    args = parse_args()

    include = set(args.include) if args.include else None
    skills = discover_skills(include)
    if not skills:
        print("未发现可安装技能（请检查 skills/ 目录或 --include 参数）")
        return 1

    bad = [s for s in skills if s.frontmatter_name and s.frontmatter_name != s.dir_name]
    if bad:
        print("以下技能目录名与 frontmatter name 不一致，停止安装：")
        for s in bad:
            print(f"- {s.dir_name} (name={s.frontmatter_name})")
        return 1

    targets: list[tuple[str, Path]] = []
    if args.target in {"codex", "all"}:
        targets.append(("codex", resolve_codex_dir(args.codex_dir)))
    if args.target in {"claude", "all"}:
        claude_dir = resolve_claude_dir(args.claude_dir)
        if claude_dir is None:
            msg = (
                "未探测到 Claude skills 目录。请使用 --claude-dir 指定，"
                "或设置 CLAUDE_SKILLS_DIR。"
            )
            if args.target == "all" and args.skip_claude_if_undetected:
                print(f"[WARN] {msg} 已按 --skip-claude-if-undetected 跳过 Claude 安装。")
            else:
                print(msg)
                return 1
        else:
            targets.append(("claude", claude_dir))

    if not targets:
        print("没有可执行的安装目标。")
        return 1

    print("源技能（将被安装）:")
    for s in skills:
        print(f"- {s.dir_name} (version={s.version or 'N/A'})")

    ok = True
    for target, base_dir in targets:
        result = install_to_target(
            target=target,
            base_dir=base_dir,
            skills=skills,
            assume_yes=args.yes,
            dry_run=args.dry_run,
        )
        if result.skipped_existing and not result.installed:
            ok = False
            continue
        ok = print_validation(target, base_dir, skills, args.dry_run) and ok

    print("\n安装完成。" if ok else "\n安装未全部成功。")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
