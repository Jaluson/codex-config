"""发现并执行项目已有质量检查工具。"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ElementTree
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple


SCHEMA_VERSION = 2
FINGERPRINT_VERSION = 1
DEFAULT_TIMEOUT_SECONDS = 600
SUPPORTED_STACKS = {"springboot", "vue"}
MAVEN_PLUGIN_COMMANDS = {
    "maven-checkstyle-plugin": ("checkstyle", "check"),
    "spotless-maven-plugin": ("spotless", "check"),
    "maven-pmd-plugin": ("pmd", "check"),
    "maven-enforcer-plugin": ("enforcer", "enforce"),
}
SCRIPT_KIND_PATTERNS = (
    ("format-check", re.compile(r"(^|[-_:])(format|prettier)([-_:]|$).*check|(^|[-_:])check[-_:].*format")),
    ("lint", re.compile(r"(^|[-_:])lint([-_:]|$)")),
    ("typecheck", re.compile(r"type[-_:]?check|(^|[-_:])tsc([-_:]|$)")),
    ("test", re.compile(r"(^|[-_:])test([-_:]|$)")),
    ("build", re.compile(r"(^|[-_:])(build|verify)([-_:]|$)")),
)
SKIP_SCRIPT_TOKENS = {"watch", "dev", "start", "serve", "fix"}
SENSITIVE_OUTPUT_PATTERN = re.compile(
    r"(?i)(password|passwd|secret|token|authorization|api[_-]?key)(\s*[:=]\s*)[^\s,;]+"
)
SOURCE_EXCLUDED_PARTS = {
    ".git",
    "artifacts",
    "node_modules",
    "target",
    "dist",
    "build",
    "__pycache__",
}
PRETTIER_EXTENSIONS = {
    ".css",
    ".html",
    ".js",
    ".jsx",
    ".json",
    ".md",
    ".mjs",
    ".scss",
    ".ts",
    ".tsx",
    ".vue",
    ".yaml",
    ".yml",
}
ESLINT_EXTENSIONS = {".cjs", ".js", ".jsx", ".mjs", ".ts", ".tsx", ".vue"}


class ToolError(Exception):
    """检查器无法安全完成请求时抛出的错误。"""


def _parse_scalar(value: str) -> Any:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    if value in {"true", "false"}:
        return value == "true"
    return value


def _read_simple_yaml(path: Path) -> Dict[str, Any]:
    """读取本项目使用的简单嵌套键值 YAML，不实现通用 YAML 语法。"""
    result: Dict[str, Any] = {}
    stack: List[Tuple[int, Dict[str, Any]]] = [(-1, result)]
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise ToolError(f"无法读取 {path}: {exc}") from exc

    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        if "\t" in raw_line[:indent]:
            raise ToolError(f"{path}:{line_number}: 不支持 Tab 缩进")
        content = raw_line.strip()
        if ":" not in content:
            raise ToolError(f"{path}:{line_number}: 不支持的配置行")
        key, value = content.split(":", 1)
        key = key.strip()
        if not key:
            raise ToolError(f"{path}:{line_number}: 配置键不能为空")
        while stack and indent <= stack[-1][0]:
            stack.pop()
        if not stack:
            raise ToolError(f"{path}:{line_number}: 缩进层级无效")
        parent = stack[-1][1]
        if value.strip():
            parent[key] = _parse_scalar(value)
        else:
            child: Dict[str, Any] = {}
            parent[key] = child
            stack.append((indent, child))
    return result


def _load_dev_env(root: Path) -> Tuple[Dict[str, Any], List[str]]:
    path = root / ".dev-env.yaml"
    if not path.is_file():
        return {}, ["缺少 .dev-env.yaml，无法确认项目命令环境"]
    try:
        return _read_simple_yaml(path), []
    except ToolError as exc:
        return {}, [str(exc)]


def _relative_display(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path)


def _source(path: Path, root: Path, kind: str, authoritative: bool = True) -> Dict[str, Any]:
    return {
        "path": _relative_display(path, root),
        "kind": kind,
        "authoritative": authoritative,
    }


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _normalize_text_for_hash(text: str) -> bytes:
    return text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")


def _read_text_for_hash(path: Path, description: str) -> Tuple[str, bytes]:
    try:
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ToolError(f"无法按 UTF-8 读取{description}：{path}: {exc}") from exc
    except OSError as exc:
        raise ToolError(f"无法读取{description}：{path}: {exc}") from exc
    normalized = _normalize_text_for_hash(text)
    return text, normalized


def _content_hash_record(path: Path, relative_path: str, kind: str, authoritative: bool) -> Dict[str, Any]:
    _, normalized = _read_text_for_hash(path, "规范来源")
    return {
        "path": relative_path,
        "kind": kind,
        "authoritative": authoritative,
        "sha256": _sha256_bytes(normalized),
        "bytes": len(normalized),
    }


def _user_rules_record(user_rules_file: Optional[Path]) -> Optional[Dict[str, Any]]:
    if user_rules_file is None:
        return None
    path = user_rules_file.expanduser().resolve()
    _, normalized = _read_text_for_hash(path, "用户规则文件")
    return {
        "name": "当前任务用户规则",
        "sha256": _sha256_bytes(normalized),
        "bytes": len(normalized),
    }


def _command_manifest(commands: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [
        {
            "id": command.get("id"),
            "kind": command.get("kind"),
            "argv": list(command.get("argv", [])),
            "scope": command.get("scope"),
            "source": command.get("source"),
        }
        for command in sorted(commands, key=lambda item: str(item.get("id", "")))
    ]


def _compute_fingerprint(
    root: Path,
    stack: str,
    sources: Sequence[Dict[str, Any]],
    commands: Sequence[Dict[str, Any]],
    user_rules_file: Optional[Path],
) -> Dict[str, Any]:
    inputs = [
        _content_hash_record(
            root / source["path"],
            source["path"],
            source["kind"],
            bool(source.get("authoritative", True)),
        )
        for source in sorted(sources, key=lambda item: item["path"])
    ]
    user_rules = _user_rules_record(user_rules_file)
    payload = {
        "fingerprint_version": FINGERPRINT_VERSION,
        "schema_version": SCHEMA_VERSION,
        "stack": stack,
        "inputs": inputs,
        "user_rules": user_rules,
        "commands": _command_manifest(commands),
    }
    value = _sha256_bytes(_canonical_json(payload).encode("utf-8"))
    return {
        "algorithm": "sha256",
        "fingerprint_version": FINGERPRINT_VERSION,
        "stack": stack,
        "value": value,
        "inputs": inputs,
        "user_rules": user_rules,
        "commands": payload["commands"],
    }


def _load_fingerprint(path: Path) -> Dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8-sig") as handle:
            value = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise ToolError(f"无法读取规范指纹：{path}: {exc}") from exc
    if isinstance(value, dict) and isinstance(value.get("fingerprint"), dict):
        value = value["fingerprint"]
    if not isinstance(value, dict) or not isinstance(value.get("value"), str):
        raise ToolError(f"规范指纹格式无效：{path}")
    return value


def _fingerprint_input_map(fingerprint: Dict[str, Any]) -> Dict[str, str]:
    inputs = fingerprint.get("inputs", [])
    if not isinstance(inputs, list):
        raise ToolError("规范指纹的 inputs 必须是列表")
    result: Dict[str, str] = {}
    for item in inputs:
        if not isinstance(item, dict) or not isinstance(item.get("path"), str) or not isinstance(item.get("sha256"), str):
            raise ToolError("规范指纹的 inputs 包含无效项")
        result[item["path"]] = item["sha256"]
    return result


def _compare_fingerprints(
    baseline: Optional[Dict[str, Any]], current: Dict[str, Any]
) -> Dict[str, Any]:
    if baseline is None:
        return {
            "available": False,
            "changed": False,
            "baseline": None,
            "current": current["value"],
            "changed_inputs": [],
        }
    for key in ("algorithm", "fingerprint_version", "stack"):
        if baseline.get(key) != current.get(key):
            raise ToolError(f"规范指纹基线与当前检查不兼容：{key}")
    baseline_inputs = _fingerprint_input_map(baseline)
    current_inputs = _fingerprint_input_map(current)
    changed_inputs: List[Dict[str, Any]] = []
    for path in sorted(set(baseline_inputs) | set(current_inputs)):
        before = baseline_inputs.get(path)
        after = current_inputs.get(path)
        if before == after:
            continue
        changed_inputs.append({
            "path": path,
            "change": "added" if before is None else "removed" if after is None else "modified",
        })
    baseline_user_rules_record = baseline.get("user_rules")
    baseline_user_rules = (
        baseline_user_rules_record.get("sha256")
        if isinstance(baseline_user_rules_record, dict)
        else None
    )
    current_user_rules = current.get("user_rules", {}).get("sha256") if isinstance(current.get("user_rules"), dict) else None
    if baseline_user_rules != current_user_rules:
        changed_inputs.append({"path": "<user-rules>", "change": "modified"})
    commands_changed = baseline.get("commands") != current.get("commands")
    if commands_changed:
        changed_inputs.append({"path": "<discovered-commands>", "change": "modified"})
    changed = baseline.get("value") != current.get("value")
    return {
        "available": True,
        "changed": changed,
        "baseline": baseline.get("value"),
        "current": current["value"],
        "changed_inputs": changed_inputs,
        "commands_changed": commands_changed,
    }


def _safe_project_path(root: Path, relative_path: str) -> Path:
    candidate = (root / relative_path).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError as exc:
        raise ToolError(f"变更文件越出项目根目录：{relative_path}") from exc
    return candidate


def _read_json(path: Path) -> Dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8-sig") as handle:
            value = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise ToolError(f"无法读取 JSON 配置 {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ToolError(f"JSON 配置必须是对象：{path}")
    return value


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _maven_plugins(pom_path: Path) -> List[str]:
    try:
        tree = ElementTree.parse(pom_path)
    except (OSError, ElementTree.ParseError) as exc:
        raise ToolError(f"无法解析 Maven 配置 {pom_path}: {exc}") from exc
    artifact_ids: List[str] = []
    for element in tree.iter():
        if _local_name(element.tag) == "artifactId" and element.text:
            artifact_ids.append(element.text.strip())
    return artifact_ids


def _resolve_maven_launcher(root: Path, dev_env: Dict[str, Any]) -> Tuple[Optional[str], List[str]]:
    warnings: List[str] = []
    if os.name == "nt":
        wrapper_names = ("mvnw.cmd", "mvnw")
        executable_name = "mvn.cmd"
    else:
        wrapper_names = ("mvnw", "mvnw.cmd")
        executable_name = "mvn"

    for wrapper_name in wrapper_names:
        wrapper = root / wrapper_name
        if wrapper.is_file():
            return str(wrapper), warnings

    maven_config = dev_env.get("development", {}).get("maven", {})
    if isinstance(maven_config, dict):
        maven_home = maven_config.get("home")
        if isinstance(maven_home, str) and maven_home:
            maven_executable = Path(maven_home) / "bin" / executable_name
            if maven_executable.is_file():
                return str(maven_executable), warnings
            warnings.append(f".dev-env.yaml 配置的 Maven 路径不存在：{maven_executable}")

    resolved = shutil.which(executable_name)
    if resolved:
        return resolved, warnings
    warnings.append("未找到 Maven Wrapper 或 Maven 可执行文件")
    return None, warnings


def _resolve_pnpm(dev_env: Dict[str, Any]) -> Tuple[Optional[str], List[str]]:
    warnings: List[str] = []
    package_manager = dev_env.get("frontend", {}).get("package_manager")
    if package_manager and package_manager != "pnpm":
        warnings.append(f"项目配置的前端包管理器不是 pnpm：{package_manager}")
        return None, warnings
    executable_name = "pnpm.cmd" if os.name == "nt" else "pnpm"
    resolved = shutil.which(executable_name) or shutil.which("pnpm")
    if resolved:
        return resolved, warnings
    warnings.append("未找到 pnpm 可执行文件")
    return None, warnings


def _detect_sources(root: Path) -> List[Dict[str, Any]]:
    sources: List[Dict[str, Any]] = []
    seen: Set[str] = set()

    def add(path: Path, kind: str, authoritative: bool = True) -> None:
        if not path.is_file():
            return
        relative_path = _relative_display(path, root)
        if relative_path in seen:
            return
        seen.add(relative_path)
        sources.append(_source(path, root, kind, authoritative))

    for path in sorted(root.rglob("AGENTS.md")):
        if not any(part in SOURCE_EXCLUDED_PARTS for part in path.relative_to(root).parts):
            add(path, "AGENTS.md")

    standards_directory = root / "docs" / "开发规范"
    if standards_directory.is_dir():
        for path in sorted(standards_directory.rglob("*")):
            if path.is_file():
                add(path, "项目开发规范")

    for name in (
        ".dev-env.yaml",
        ".editorconfig",
        "pom.xml",
        "package.json",
        "pnpm-workspace.yaml",
        "pnpm-lock.yaml",
        "package-lock.json",
        "yarn.lock",
        "tsconfig.json",
    ):
        add(root / name, ".dev-env.yaml" if name == ".dev-env.yaml" else "项目配置")

    candidate_patterns = (
        "eslint.config.*",
        ".eslintrc*",
        "prettier.config.*",
        ".prettierrc*",
        ".prettierignore",
        ".eslintignore",
        "tsconfig.*.json",
        "vite.config.*",
        "vitest.config.*",
        "jest.config.*",
        "stylelint.config.*",
        ".stylelintrc*",
        "*checkstyle*",
        "*pmd*",
        "*spotless*",
    )
    for pattern in candidate_patterns:
        for path in sorted(root.glob(pattern)):
            add(path, "质量工具配置")

    workflows_directory = root / ".github" / "workflows"
    if workflows_directory.is_dir():
        for path in sorted(workflows_directory.rglob("*")):
            if path.is_file():
                add(path, "CI 配置")
    return sources


def _script_kind(name: str) -> Optional[str]:
    lowered = name.lower()
    parts = set(re.split(r"[-_:]", lowered))
    if lowered in {"format", "format:write", "prettier:write"} or parts.intersection(SKIP_SCRIPT_TOKENS):
        return None
    for kind, pattern in SCRIPT_KIND_PATTERNS:
        if pattern.search(lowered):
            return kind
    return None


def _command(command_id: str, kind: str, argv: Sequence[str], scope: str, source: str) -> Dict[str, Any]:
    return {
        "id": command_id,
        "kind": kind,
        "argv": list(argv),
        "command": " ".join(str(item) for item in argv),
        "scope": scope,
        "source": source,
    }


def _package_has_dependency(package: Dict[str, Any], dependency: str) -> bool:
    for section_name in ("dependencies", "devDependencies", "optionalDependencies", "peerDependencies"):
        section = package.get(section_name, {})
        if isinstance(section, dict) and dependency in section:
            return True
    return False


def _has_root_pattern(root: Path, patterns: Sequence[str]) -> bool:
    return any(path.is_file() for pattern in patterns for path in root.glob(pattern))


def _fixer(
    fixer_id: str,
    tool: str,
    available: bool,
    runner: Sequence[str],
    extensions: Set[str],
    source: str,
) -> Dict[str, Any]:
    return {
        "id": fixer_id,
        "tool": tool,
        "kind": "pnpm",
        "runner": list(runner),
        "extensions": sorted(extensions),
        "scope": "changed-files",
        "source": source,
        "available": available,
    }


def _discover_vue_fixers(
    root: Path,
    package: Dict[str, Any],
    command_pnpm: str,
    pnpm_available: bool,
) -> List[Dict[str, Any]]:
    fixers: List[Dict[str, Any]] = []
    if (
        _has_root_pattern(root, ("prettier.config.*", ".prettierrc*"))
        or _package_has_dependency(package, "prettier")
    ):
        fixers.append(
            _fixer(
                "prettier-fix",
                "prettier",
                pnpm_available,
                [command_pnpm, "--offline", "exec", "prettier", "--write", "--"],
                PRETTIER_EXTENSIONS,
                "Prettier 配置或依赖",
            )
        )
    if (
        _has_root_pattern(root, ("eslint.config.*", ".eslintrc*"))
        or _package_has_dependency(package, "eslint")
    ):
        fixers.append(
            _fixer(
                "eslint-fix",
                "eslint",
                pnpm_available,
                [command_pnpm, "--offline", "exec", "eslint", "--fix", "--"],
                ESLINT_EXTENSIONS,
                "ESLint 配置或依赖",
            )
        )
    return fixers


def _fix_commands(fixers: Sequence[Dict[str, Any]], changed_files: Sequence[str]) -> List[Dict[str, Any]]:
    commands: List[Dict[str, Any]] = []
    for fixer in fixers:
        extensions = set(fixer.get("extensions", []))
        target_files = [
            path for path in changed_files
            if Path(path).suffix.lower() in extensions
        ]
        if not target_files:
            continue
        commands.append({
            "id": fixer["id"],
            "kind": fixer["kind"],
            "argv": list(fixer["runner"]) + target_files,
            "command": " ".join(str(item) for item in list(fixer["runner"]) + target_files),
            "scope": fixer["scope"],
            "source": fixer["source"],
            "tool": fixer["tool"],
        })
    return commands


def discover(root: Path, stack: str, user_rules_file: Optional[Path] = None) -> Dict[str, Any]:
    root = root.resolve()
    if not root.is_dir():
        raise ToolError(f"项目根目录不存在：{root}")
    if stack not in SUPPORTED_STACKS:
        raise ToolError(f"不支持的技术栈：{stack}")

    dev_env, env_warnings = _load_dev_env(root)
    sources = _detect_sources(root)
    warnings = list(env_warnings)
    standards_path = root / "docs" / "开发规范" / "README.md"
    if not standards_path.is_file():
        warnings.append("缺少 docs/开发规范/README.md，将沿用项目现有规则")
    commands: List[Dict[str, Any]] = []
    tools: List[Dict[str, Any]] = []
    fixers: List[Dict[str, Any]] = []

    if stack == "springboot":
        pom_path = root / "pom.xml"
        if not pom_path.is_file():
            warnings.append("未找到 pom.xml，无法发现 Spring Boot/Maven 检查命令")
        else:
            launcher, launcher_warnings = _resolve_maven_launcher(root, dev_env)
            warnings.extend(launcher_warnings)
            command_launcher = launcher or ("mvn.cmd" if os.name == "nt" else "mvn")
            commands.append(_command("maven-test", "maven", [command_launcher, "test"], "changed-fallback", "Maven 生命周期"))
            commands.append(_command("maven-verify", "maven", [command_launcher, "verify"], "full", "Maven 生命周期"))
            if launcher:
                try:
                    plugin_ids = _maven_plugins(pom_path)
                except ToolError as exc:
                    warnings.append(str(exc))
                    plugin_ids = []
                seen_plugins = set()
                for plugin_id in plugin_ids:
                    if plugin_id in MAVEN_PLUGIN_COMMANDS and plugin_id not in seen_plugins:
                        prefix, goal = MAVEN_PLUGIN_COMMANDS[plugin_id]
                        commands.append(
                            _command(
                                f"maven-{prefix}-{goal}",
                                "maven",
                                [command_launcher, f"{prefix}:{goal}"],
                                "full",
                                f"pom.xml:{plugin_id}",
                            )
                        )
                        seen_plugins.add(plugin_id)
            if not launcher:
                try:
                    plugin_ids = _maven_plugins(pom_path)
                except ToolError:
                    plugin_ids = []
                for plugin_id in plugin_ids:
                    if plugin_id in MAVEN_PLUGIN_COMMANDS and not any(
                        item["source"] == f"pom.xml:{plugin_id}" for item in commands
                    ):
                        prefix, goal = MAVEN_PLUGIN_COMMANDS[plugin_id]
                        commands.append(
                            _command(
                                f"maven-{prefix}-{goal}",
                                "maven",
                                [command_launcher, f"{prefix}:{goal}"],
                                "full",
                                f"pom.xml:{plugin_id}",
                            )
                        )
            tools.append({
                "id": "maven",
                "available": bool(launcher),
                "commands": [item["id"] for item in commands if item["kind"] == "maven"],
            })
    else:
        package_path = root / "package.json"
        if not package_path.is_file():
            warnings.append("未找到 package.json，无法发现 Vue/pnpm 检查命令")
        else:
            package = _read_json(package_path)
            scripts = package.get("scripts", {})
            if not isinstance(scripts, dict):
                raise ToolError("package.json 的 scripts 必须是对象")
            pnpm, pnpm_warnings = _resolve_pnpm(dev_env)
            warnings.extend(pnpm_warnings)
            command_pnpm = pnpm or ("pnpm.cmd" if os.name == "nt" else "pnpm")
            for script_name in sorted(scripts):
                if not isinstance(script_name, str):
                    continue
                kind = _script_kind(script_name)
                if not kind:
                    continue
                scope = "full" if kind in {"test", "build"} else "changed-fallback"
                commands.append(
                    _command(
                        f"pnpm-{script_name}",
                        "pnpm",
                        [command_pnpm, "run", script_name],
                        scope,
                        f"package.json:scripts.{script_name}",
                    )
                )
            fixers.extend(_discover_vue_fixers(root, package, command_pnpm, bool(pnpm)))
            tools.append({
                "id": "pnpm",
                "available": bool(pnpm),
                "commands": [item["id"] for item in commands if item["kind"] == "pnpm"],
            })

    fingerprint = _compute_fingerprint(root, stack, sources, commands, user_rules_file)
    status = "pass-with-warning" if warnings else "passed"
    return {
        "schema_version": SCHEMA_VERSION,
        "mode": "discover",
        "root": str(root),
        "stack": stack,
        "status": status,
        "sources": sources,
        "tools": tools,
        "commands": commands,
        "fixers": fixers,
        "fingerprint": fingerprint,
        "warnings": warnings,
    }


def _run_process(argv: Sequence[str], root: Path, env: Optional[Dict[str, str]], timeout_seconds: int) -> Dict[str, Any]:
    started = time.monotonic()
    try:
        completed = subprocess.run(
            list(argv),
            cwd=str(root),
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout_seconds,
            check=False,
        )
        output = completed.stdout.decode("utf-8", errors="replace") if completed.stdout else ""
        return {
            "exit_code": completed.returncode,
            "duration_seconds": round(time.monotonic() - started, 3),
            "output": _sanitize_output(output),
        }
    except FileNotFoundError as exc:
        return {
            "exit_code": None,
            "duration_seconds": round(time.monotonic() - started, 3),
            "error": f"命令不存在：{exc}",
            "output": "",
        }
    except subprocess.TimeoutExpired as exc:
        output = exc.output.decode("utf-8", errors="replace") if isinstance(exc.output, bytes) else str(exc.output or "")
        return {
            "exit_code": None,
            "duration_seconds": round(time.monotonic() - started, 3),
            "error": f"命令超过 {timeout_seconds} 秒超时",
            "output": _sanitize_output(output),
        }
    except OSError as exc:
        return {
            "exit_code": None,
            "duration_seconds": round(time.monotonic() - started, 3),
            "error": f"命令执行失败：{exc}",
            "output": "",
        }


def _sanitize_output(output: str) -> str:
    output = SENSITIVE_OUTPUT_PATTERN.sub(r"\1\2[已脱敏]", output)
    lines = output.splitlines()
    if len(lines) > 80:
        lines = ["[输出过长，仅保留最后 80 行]", *lines[-80:]]
    return "\n".join(lines)


def _git_output(root: Path, arguments: Sequence[str]) -> Tuple[Optional[int], str]:
    try:
        completed = subprocess.run(
            ["git", "-C", str(root), "-c", "core.quotePath=false", *arguments],
            cwd=str(root),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, str(exc)
    stdout = completed.stdout.decode("utf-8", errors="replace") if completed.stdout else ""
    stderr = completed.stderr.decode("utf-8", errors="replace") if completed.stderr else ""
    return completed.returncode, _sanitize_output(stdout if completed.returncode == 0 else stdout + stderr)


def git_changed_files(root: Path) -> Tuple[List[str], List[str]]:
    paths: Set[str] = set()
    warnings: List[str] = []
    for arguments in (
        ("diff", "--name-only", "--diff-filter=ACMR"),
        ("diff", "--cached", "--name-only", "--diff-filter=ACMR"),
        ("ls-files", "--others", "--exclude-standard"),
    ):
        exit_code, output = _git_output(root, arguments)
        if exit_code != 0:
            warnings.append(f"无法读取 git 变更范围：git {' '.join(arguments)}")
            continue
        paths.update(line.strip().replace("\\", "/") for line in output.splitlines() if line.strip())
    return sorted(paths), warnings


def _check_changed_files(root: Path, changed_files: Iterable[str]) -> List[Dict[str, Any]]:
    checks: List[Dict[str, Any]] = []
    for relative_path in sorted(set(changed_files)):
        path = _safe_project_path(root, relative_path)
        if not path.exists() or not path.is_file():
            checks.append({
                "id": "file-exists",
                "status": "blocked",
                "source": "变更范围",
                "scope": relative_path,
                "command": "",
                "exit_code": None,
                "evidence": "变更文件不存在",
            })
            continue
        try:
            data = path.read_bytes()
            if b"\x00" in data[:4096]:
                continue
            data.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            checks.append({
                "id": "utf8",
                "status": "blocked",
                "source": "AGENTS.md",
                "scope": relative_path,
                "command": "UTF-8 解码",
                "exit_code": None,
                "evidence": str(exc),
            })
        except OSError as exc:
            checks.append({
                "id": "file-read",
                "status": "blocked",
                "source": "变更范围",
                "scope": relative_path,
                "command": "读取文件",
                "exit_code": None,
                "evidence": str(exc),
            })
    if not checks:
        checks.append({
            "id": "utf8",
            "status": "passed",
            "source": "AGENTS.md",
            "scope": "变更文件",
            "command": "UTF-8 解码",
            "exit_code": 0,
            "evidence": "变更文本文件均可按 UTF-8 读取，二进制文件已跳过",
        })
    return checks


def _check_git_diff(root: Path) -> List[Dict[str, Any]]:
    checks: List[Dict[str, Any]] = []
    for label, arguments in (
        ("工作区空白检查", ("diff", "--check")),
        ("暂存区空白检查", ("diff", "--cached", "--check")),
    ):
        exit_code, output = _git_output(root, arguments)
        if exit_code == 0:
            status = "passed"
            evidence = "未发现 Git 空白错误"
        elif exit_code == 1:
            status = "blocked"
            evidence = _sanitize_output(output) or "Git 报告空白错误"
        else:
            status = "warning"
            evidence = "当前目录不是可用的 Git 工作区或无法读取 diff"
        checks.append({
            "id": "git-diff-check",
            "status": status,
            "source": "Git",
            "scope": label,
            "command": "git " + " ".join(arguments),
            "exit_code": exit_code,
            "evidence": evidence,
        })
    return checks


def _command_env(root: Path, dev_env: Dict[str, Any]) -> Dict[str, str]:
    environment = os.environ.copy()
    maven_config = dev_env.get("development", {}).get("maven", {})
    java_config = dev_env.get("development", {}).get("java", {})
    if isinstance(maven_config, dict) and isinstance(maven_config.get("home"), str):
        maven_home = Path(maven_config["home"])
        if not maven_home.is_dir():
            raise ToolError(f"MAVEN_HOME 路径不存在：{maven_home}")
        environment["MAVEN_HOME"] = str(maven_home)
        environment["M2_HOME"] = str(maven_home)
        environment["PATH"] = str(maven_home / "bin") + os.pathsep + environment.get("PATH", "")
    if isinstance(java_config, dict) and isinstance(java_config.get("home"), str):
        java_home = Path(java_config["home"])
        if not java_home.is_dir():
            raise ToolError(f"JAVA_HOME 路径不存在：{java_home}")
        environment["JAVA_HOME"] = str(java_home)
        environment["PATH"] = str(java_home / "bin") + os.pathsep + environment.get("PATH", "")
    return environment


def _execute_command_check(
    root: Path,
    command: Dict[str, Any],
    dev_env: Dict[str, Any],
    timeout_seconds: int,
) -> Dict[str, Any]:
    try:
        environment = _command_env(root, dev_env) if command["kind"] == "maven" else os.environ.copy()
    except ToolError as exc:
        return {
            "id": command["id"],
            "status": "blocked",
            "source": command["source"],
            "scope": command["scope"],
            "command": command["command"],
            "exit_code": None,
            "evidence": str(exc),
        }
    execution = _run_process(command["argv"], root, environment, timeout_seconds)
    if execution["exit_code"] == 0:
        status = "passed"
        evidence = execution.get("output", "") or "命令执行成功"
    else:
        status = "blocked"
        evidence = execution.get("error") or execution.get("output", "") or "命令执行失败"
    return {
        "id": command["id"],
        "status": status,
        "source": command["source"],
        "scope": command["scope"],
        "command": command["command"],
        "exit_code": execution.get("exit_code"),
        "evidence": evidence,
        "duration_seconds": execution.get("duration_seconds"),
    }


def _aggregate_status(checks: Sequence[Dict[str, Any]]) -> str:
    statuses = {check.get("status") for check in checks}
    if "blocked" in statuses:
        return "blocked"
    if statuses.intersection({"warning", "not-executed"}):
        return "pass-with-warning"
    return "passed"


def check(
    root: Path,
    stack: str,
    changed_files: Optional[Iterable[str]] = None,
    changed_from_git: bool = False,
    full: bool = False,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    user_rules_file: Optional[Path] = None,
    baseline_fingerprint: Optional[Path] = None,
    fix: bool = False,
) -> Dict[str, Any]:
    root = root.resolve()
    discovery = discover(root, stack, user_rules_file=user_rules_file)
    dev_env, _ = _load_dev_env(root)
    files = list(changed_files or [])
    warnings: List[str] = []
    if changed_from_git:
        git_files, git_warnings = git_changed_files(root)
        files.extend(git_files)
        warnings.extend(git_warnings)
    files = sorted(set(files))
    file_checks = _check_changed_files(root, files) if files else [{
        "id": "changed-files",
        "status": "warning",
        "source": "Git",
        "scope": "变更范围",
        "command": "",
        "exit_code": None,
        "evidence": "未提供变更文件，跳过变更文件级检查",
    }]
    checks = list(file_checks)

    fixes: List[Dict[str, Any]] = []
    if fix:
        if not files:
            fixes.append({
                "id": "fix-scope",
                "status": "blocked",
                "source": "自动纠正安全边界",
                "scope": "变更文件",
                "command": "",
                "exit_code": None,
                "evidence": "--fix 必须提供明确的变更文件，禁止对整个项目执行自动纠正",
            })
        elif any(item.get("status") == "blocked" for item in file_checks):
            fixes.append({
                "id": "fix-scope",
                "status": "blocked",
                "source": "自动纠正安全边界",
                "scope": "变更文件",
                "command": "",
                "exit_code": None,
                "evidence": "存在无法读取或不存在的变更文件，跳过自动纠正",
            })
        else:
            fix_commands = _fix_commands(discovery.get("fixers", []), files)
            if not discovery.get("fixers", []):
                fixes.append({
                    "id": "fix-tools",
                    "status": "warning",
                    "source": "项目质量工具",
                    "scope": "自动纠正",
                    "command": "",
                    "exit_code": None,
                    "evidence": "未发现可安全限定到变更文件的自动纠正工具",
                })
            elif not fix_commands:
                fixes.append({
                    "id": "fix-files",
                    "status": "warning",
                    "source": "自动纠正安全边界",
                    "scope": "变更文件",
                    "command": "",
                    "exit_code": None,
                    "evidence": "变更文件没有匹配已知自动纠正工具的文件类型",
                })
            else:
                fixer_index = {item["id"]: item for item in discovery.get("fixers", [])}
                for command in fix_commands:
                    fixer = fixer_index.get(command["id"], {})
                    if not fixer.get("available"):
                        fixes.append({
                            "id": command["id"],
                            "status": "blocked",
                            "source": command["source"],
                            "scope": command["scope"],
                            "command": command["command"],
                            "exit_code": None,
                            "evidence": "自动纠正工具不可用，未执行修复",
                        })
                    else:
                        fixes.append(_execute_command_check(root, command, dev_env, timeout_seconds))
                discovery = discover(root, stack, user_rules_file=user_rules_file)

    warnings.extend(discovery.get("warnings", []))
    checks.extend(_check_git_diff(root))

    baseline = _load_fingerprint(baseline_fingerprint) if baseline_fingerprint else None
    fingerprint_comparison = _compare_fingerprints(baseline, discovery["fingerprint"])
    if fingerprint_comparison["available"] and fingerprint_comparison["changed"]:
        checks.append({
            "id": "standards-fingerprint",
            "status": "warning",
            "source": "规范指纹",
            "scope": "当前运行规范来源",
            "command": "standards_tool.py fingerprint",
            "exit_code": 0,
            "evidence": "规范来源已变化，已使用最新来源重新发现；变化项："
            + ", ".join(item["path"] for item in fingerprint_comparison["changed_inputs"]),
        })

    commands = discovery.get("commands", [])
    executable_tool_ids = {tool["id"] for tool in discovery.get("tools", []) if tool.get("available")}
    runnable_commands = [
        command
        for command in commands
        if command["scope"] == "changed-fallback" or (full and command["scope"] == "full")
    ]
    if not runnable_commands:
        checks.append({
            "id": "project-quality-tools",
            "status": "warning",
            "source": "项目配置",
            "scope": "项目质量工具",
            "command": "",
            "exit_code": None,
            "evidence": "未发现可执行的项目质量命令",
        })
    else:
        for command in runnable_commands:
            tool_id = "maven" if command["kind"] == "maven" else "pnpm"
            if tool_id not in executable_tool_ids:
                checks.append({
                    "id": command["id"],
                    "status": "blocked" if full else "warning",
                    "source": command["source"],
                    "scope": command["scope"],
                    "command": command["command"],
                    "exit_code": None,
                    "evidence": f"{tool_id} 不可用，无法执行已发现命令",
                })
            else:
                checks.append(_execute_command_check(root, command, dev_env, timeout_seconds))

    checks.extend({
        "id": "standards-source",
        "status": "warning",
        "source": "项目开发规范",
        "scope": "规则来源",
        "command": "",
        "exit_code": None,
        "evidence": warning,
    } for warning in warnings)
    checks.extend(fixes)
    return {
        "schema_version": SCHEMA_VERSION,
        "mode": "check",
        "root": str(root),
        "stack": stack,
        "full": full,
        "fix": fix,
        "changed_files": files,
        "status": _aggregate_status(checks),
        "sources": discovery.get("sources", []),
        "tools": discovery.get("tools", []),
        "commands": commands,
        "fixers": discovery.get("fixers", []),
        "fingerprint": discovery.get("fingerprint"),
        "fingerprint_comparison": fingerprint_comparison,
        "fixes": fixes,
        "checks": checks,
        "warnings": warnings,
    }


def _escape_markdown(value: Any) -> str:
    text = "" if value is None else str(value)
    return text.replace("|", "\\|").replace("\r", "").replace("\n", "<br>")


def _render_markdown(result: Dict[str, Any]) -> str:
    mode = result.get("mode")
    lines = [
        "# 开发规范检查报告" if mode == "check" else "# 开发规范指纹报告" if mode == "fingerprint" else "# 开发规范来源报告",
        "",
        f"- 结论：`{result.get('status', '')}`",
        f"- 技术栈：`{result.get('stack', '')}`",
        f"- 项目根目录：`{result.get('root', '')}`",
    ]
    fingerprint = result.get("fingerprint")
    if mode == "fingerprint" and isinstance(result.get("value"), str):
        fingerprint = result
    if isinstance(fingerprint, dict):
        lines.append(f"- 规范 Hash：`{_escape_markdown(fingerprint.get('value'))}`")
    if mode == "check":
        lines.append(f"- 全量检查：`{'是' if result.get('full') else '否'}`")
        lines.append(f"- 变更文件数：`{len(result.get('changed_files', []))}`")
        comparison = result.get("fingerprint_comparison", {})
        if comparison.get("available"):
            lines.append(f"- 基线 Hash：`{_escape_markdown(comparison.get('baseline'))}`")
            lines.append(f"- 规范是否变化：`{'是' if comparison.get('changed') else '否'}`")
    lines.extend(["", "## 规则来源", "", "| 路径 | 类型 | 权威 |", "| --- | --- | --- |"])
    for source in result.get("sources", []):
        lines.append(
            f"| `{_escape_markdown(source.get('path'))}` | {_escape_markdown(source.get('kind'))} | "
            f"{('是' if source.get('authoritative') else '否')} |"
        )
    lines.extend(["", "## 可用工具", "", "| 工具 | 可用 | 命令 |", "| --- | --- | --- |"])
    for tool in result.get("tools", []):
        lines.append(
            f"| `{_escape_markdown(tool.get('id'))}` | {('是' if tool.get('available') else '否')} | "
            f"{_escape_markdown(', '.join(tool.get('commands', [])))} |"
        )
    if mode == "check":
        lines.extend(["", "## 检查结果", "", "| 状态 | 检查 | 范围 | 来源 | 退出码 |", "| --- | --- | --- | --- | --- |"])
        for item in result.get("checks", []):
            lines.append(
                f"| `{_escape_markdown(item.get('status'))}` | `{_escape_markdown(item.get('id'))}` | "
                f"{_escape_markdown(item.get('scope'))} | {_escape_markdown(item.get('source'))} | "
                f"{_escape_markdown(item.get('exit_code'))} |"
            )
        lines.extend(["", "## 证据", ""])
        for item in result.get("checks", []):
            evidence = item.get("evidence") or "无额外输出"
            lines.append(f"### `{_escape_markdown(item.get('id'))}`")
            lines.append("")
            lines.append(f"- 命令：`{_escape_markdown(item.get('command'))}`")
            lines.append(f"- 证据：{_escape_markdown(evidence)}")
            lines.append("")
        if result.get("fixes"):
            lines.extend(["## 自动纠正", "", "| 状态 | 工具 | 退出码 |", "| --- | --- | --- |"])
            for item in result["fixes"]:
                lines.append(
                    f"| `{_escape_markdown(item.get('status'))}` | `{_escape_markdown(item.get('id'))}` | "
                    f"{_escape_markdown(item.get('exit_code'))} |"
                )
                lines.append(f"- `{_escape_markdown(item.get('command'))}`：{_escape_markdown(item.get('evidence'))}")
            lines.append("")
    if mode == "fingerprint" and isinstance(fingerprint, dict):
        lines.extend(["", "## 指纹输入", "", "| 路径 | 类型 | SHA-256 |", "| --- | --- | --- |"])
        for item in fingerprint.get("inputs", []):
            lines.append(
                f"| `{_escape_markdown(item.get('path'))}` | {_escape_markdown(item.get('kind'))} | "
                f"`{_escape_markdown(item.get('sha256'))}` |"
            )
    if result.get("warnings"):
        lines.extend(["## 告警和未执行项", ""])
        lines.extend(f"- {warning}" for warning in result["warnings"])
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _emit(result: Dict[str, Any], output_format: str) -> None:
    if output_format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(_render_markdown(result), end="")


def _configure_utf8_output() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            reconfigure(encoding="utf-8", errors="replace")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="发现并执行项目已有开发规范检查工具")
    subparsers = parser.add_subparsers(dest="operation", required=True)
    for operation in ("discover", "fingerprint", "check"):
        subparser = subparsers.add_parser(operation)
        subparser.add_argument("--root", default=".", help="项目根目录，默认当前目录")
        subparser.add_argument("--stack", required=True, choices=sorted(SUPPORTED_STACKS))
        subparser.add_argument("--format", dest="output_format", choices=("markdown", "json"), default="markdown")
        subparser.add_argument("--user-rules-file", help="当前任务用户规则文件，按 UTF-8 读取并纳入规范指纹")
        if operation == "check":
            subparser.add_argument("--changed-from-git", action="store_true")
            subparser.add_argument("--changed-file", action="append", default=[])
            subparser.add_argument("--full", action="store_true")
            subparser.add_argument("--timeout-seconds", type=int, default=DEFAULT_TIMEOUT_SECONDS)
            subparser.add_argument("--baseline-fingerprint", help="当前运行的基线规范指纹 JSON")
            subparser.add_argument("--fix", action="store_true", help="显式执行受限的自动纠正")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    _configure_utf8_output()
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        root = Path(args.root)
        user_rules_file = Path(args.user_rules_file) if args.user_rules_file else None
        if args.operation == "discover":
            result = discover(root, args.stack, user_rules_file=user_rules_file)
            exit_code = 0
        elif args.operation == "fingerprint":
            discovery = discover(root, args.stack, user_rules_file=user_rules_file)
            result = {
                "schema_version": SCHEMA_VERSION,
                "mode": "fingerprint",
                "root": discovery["root"],
                "stack": discovery["stack"],
                "status": discovery["status"],
                **discovery["fingerprint"],
                "sources": discovery["sources"],
                "warnings": discovery["warnings"],
            }
            exit_code = 0
        else:
            if args.timeout_seconds <= 0:
                raise ToolError("--timeout-seconds 必须为正数")
            result = check(
                root,
                args.stack,
                changed_files=args.changed_file,
                changed_from_git=args.changed_from_git,
                full=args.full,
                timeout_seconds=args.timeout_seconds,
                user_rules_file=user_rules_file,
                baseline_fingerprint=Path(args.baseline_fingerprint) if args.baseline_fingerprint else None,
                fix=args.fix,
            )
            exit_code = 2 if result["status"] == "blocked" else 0
        _emit(result, args.output_format)
        return exit_code
    except ToolError as exc:
        error = {"schema_version": SCHEMA_VERSION, "status": "blocked", "error": str(exc)}
        _emit(error, args.output_format)
        return 3


if __name__ == "__main__":
    sys.exit(main())
