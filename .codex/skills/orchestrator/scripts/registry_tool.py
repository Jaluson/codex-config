#!/usr/bin/env python3
"""Registry、Workflow Registry 和 Artifact 的本地管理工具。"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


DEFAULT_ROOT = Path(__file__).resolve().parents[4]
SCHEMA_VERSION = 1
ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
ALLOWED_STAGE_STATUS = {"pending", "running", "succeeded", "failed", "blocked", "skipped"}
ALLOWED_RUN_STATUS = {"created", "running", "succeeded", "failed", "blocked"}
ALLOWED_FAILURE_POLICIES = {"block", "continue-with-warning"}
ALLOWED_SKILL_ROLES = {"leaf", "support"}
ALLOWED_STAGE_OWNERS = {"orchestrator", "leaf", "support"}


class RegistryError(Exception):
    """表示注册表或制品操作失败。"""


YamlLine = Tuple[int, str, int]


def _is_list_line(content: str) -> bool:
    return content == "-" or content.startswith("- ")


def _strip_comment(content: str) -> str:
    quote: Optional[str] = None
    escaped = False
    for index, char in enumerate(content):
        if quote == '"' and escaped:
            escaped = False
            continue
        if quote == '"' and char == "\\":
            escaped = True
            continue
        if char in {"'", '"'}:
            if quote is None:
                quote = char
            elif quote == char:
                quote = None
            continue
        if char == "#" and quote is None and (index == 0 or content[index - 1].isspace()):
            return content[:index].rstrip()
    if quote is not None:
        raise RegistryError("YAML 字符串缺少结束引号")
    return content.rstrip()


def _split_mapping(content: str) -> Tuple[str, str]:
    quote: Optional[str] = None
    escaped = False
    for index, char in enumerate(content):
        if quote == '"' and escaped:
            escaped = False
            continue
        if quote == '"' and char == "\\":
            escaped = True
            continue
        if char in {"'", '"'}:
            if quote is None:
                quote = char
            elif quote == char:
                quote = None
            continue
        if char == ":" and quote is None:
            key = content[:index].strip()
            if not key:
                raise RegistryError("YAML 映射键不能为空")
            return key, content[index + 1 :].strip()
    raise RegistryError(f"YAML 行不是映射：{content}")


def _parse_scalar(value: str) -> Any:
    value = value.strip()
    if value == "":
        return ""
    if value in {"null", "Null", "NULL", "~"}:
        return None
    if value in {"true", "True", "TRUE"}:
        return True
    if value in {"false", "False", "FALSE"}:
        return False
    if value == "[]":
        return []
    if value == "{}":
        return {}
    if value.startswith('"'):
        if not value.endswith('"'):
            raise RegistryError(f"YAML 双引号字符串不完整：{value}")
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise RegistryError(f"YAML 双引号字符串无效：{value}") from exc
        if not isinstance(parsed, str):
            raise RegistryError(f"YAML 双引号值必须是字符串：{value}")
        return parsed
    if value.startswith("'"):
        if not value.endswith("'"):
            raise RegistryError(f"YAML 单引号字符串不完整：{value}")
        return value[1:-1].replace("''", "'")
    if re.fullmatch(r"-?[0-9]+", value):
        return int(value)
    if value.startswith(("&", "*", "!", "|", ">")):
        raise RegistryError(f"YAML 方言不支持该值：{value}")
    if value.startswith("[") or value.startswith("{"):
        raise RegistryError(f"YAML 方言不支持行内集合：{value}")
    return value


def _prepare_yaml_lines(text: str, source: str) -> List[YamlLine]:
    lines: List[YamlLine] = []
    for line_number, raw_line in enumerate(text.lstrip("\ufeff").splitlines(), start=1):
        if raw_line.startswith("\t") or raw_line[: len(raw_line) - len(raw_line.lstrip(" "))].find("\t") >= 0:
            raise RegistryError(f"{source}:{line_number}: 不允许使用 Tab 缩进")
        content = _strip_comment(raw_line).strip(" ")
        if not content:
            continue
        if content in {"---", "..."}:
            raise RegistryError(f"{source}:{line_number}: 不支持多文档 YAML 标记")
        indentation = len(raw_line) - len(raw_line.lstrip(" "))
        if indentation % 2 != 0:
            raise RegistryError(f"{source}:{line_number}: 缩进必须使用两个空格的倍数")
        lines.append((indentation, content, line_number))
    return lines


def _parse_block(lines: List[YamlLine], index: int, indentation: int) -> Tuple[Any, int]:
    if index >= len(lines) or lines[index][0] != indentation:
        raise RegistryError("YAML 嵌套缩进无效")
    if _is_list_line(lines[index][1]):
        return _parse_list(lines, index, indentation)
    return _parse_map(lines, index, indentation)


def _parse_map(lines: List[YamlLine], index: int, indentation: int) -> Tuple[Dict[str, Any], int]:
    result: Dict[str, Any] = {}
    while index < len(lines) and lines[index][0] == indentation:
        _, content, line_number = lines[index]
        if _is_list_line(content):
            raise RegistryError(f"第 {line_number} 行不能在映射中直接使用列表项")
        key, raw_value = _split_mapping(content)
        if key in result:
            raise RegistryError(f"第 {line_number} 行重复定义键：{key}")
        index += 1
        if raw_value:
            value = _parse_scalar(raw_value)
        elif index < len(lines) and lines[index][0] > indentation:
            value, index = _parse_block(lines, index, lines[index][0])
        else:
            value = None
        result[key] = value
    return result, index


def _parse_list(lines: List[YamlLine], index: int, indentation: int) -> Tuple[List[Any], int]:
    result: List[Any] = []
    while index < len(lines) and lines[index][0] == indentation and _is_list_line(lines[index][1]):
        _, content, line_number = lines[index]
        rest = content[1:].strip()
        index += 1
        if not rest:
            if index < len(lines) and lines[index][0] > indentation:
                item, index = _parse_block(lines, index, lines[index][0])
            else:
                item = None
        elif ":" in rest:
            key, raw_value = _split_mapping(rest)
            item = {}
            if raw_value:
                item[key] = _parse_scalar(raw_value)
            elif index < len(lines) and lines[index][0] > indentation:
                item[key], index = _parse_block(lines, index, lines[index][0])
            else:
                item[key] = None
            if index < len(lines) and lines[index][0] > indentation:
                continuation, index = _parse_map(lines, index, lines[index][0])
                for continuation_key, continuation_value in continuation.items():
                    if continuation_key in item:
                        raise RegistryError(
                            f"第 {line_number} 行列表项重复定义键：{continuation_key}"
                        )
                    item[continuation_key] = continuation_value
        else:
            item = _parse_scalar(rest)
            if index < len(lines) and lines[index][0] > indentation:
                raise RegistryError(f"第 {line_number} 行标量列表项不能拥有嵌套内容")
        result.append(item)
    return result, index


def parse_restricted_yaml(text: str, source: str = "<string>") -> Any:
    """解析 Registry 使用的受限 YAML 方言。"""
    lines = _prepare_yaml_lines(text, source)
    if not lines:
        return {}
    value, index = _parse_block(lines, 0, lines[0][0])
    if index != len(lines):
        raise RegistryError(f"{source}:{lines[index][2]}: 顶层结构存在无法解析的内容")
    return value


def _yaml_scalar(value: Any) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    raise RegistryError(f"无法写出 YAML 标量：{type(value).__name__}")


def dump_restricted_yaml(value: Any) -> str:
    """将基础 Python 集合写成可被本工具读取的 YAML。"""
    lines: List[str] = []

    def emit_map(mapping: Dict[str, Any], indentation: int) -> None:
        for key, item in mapping.items():
            prefix = " " * indentation
            if isinstance(item, dict):
                if item:
                    lines.append(f"{prefix}{key}:")
                    emit_map(item, indentation + 2)
                else:
                    lines.append(f"{prefix}{key}: {{}}")
            elif isinstance(item, list):
                if item:
                    lines.append(f"{prefix}{key}:")
                    emit_list(item, indentation + 2)
                else:
                    lines.append(f"{prefix}{key}: []")
            else:
                lines.append(f"{prefix}{key}: {_yaml_scalar(item)}")

    def emit_list(items: List[Any], indentation: int) -> None:
        for item in items:
            prefix = " " * indentation
            if isinstance(item, dict):
                if not item:
                    lines.append(f"{prefix}- {{}}")
                    continue
                first = True
                for key, child in item.items():
                    key_prefix = f"{prefix}- " if first else f"{prefix}  "
                    if isinstance(child, dict):
                        if child:
                            lines.append(f"{key_prefix}{key}:")
                            emit_map(child, indentation + 4)
                        else:
                            lines.append(f"{key_prefix}{key}: {{}}")
                    elif isinstance(child, list):
                        if child:
                            lines.append(f"{key_prefix}{key}:")
                            emit_list(child, indentation + 4)
                        else:
                            lines.append(f"{key_prefix}{key}: []")
                    else:
                        lines.append(f"{key_prefix}{key}: {_yaml_scalar(child)}")
                    first = False
            elif isinstance(item, list):
                if not item:
                    lines.append(f"{prefix}- []")
                else:
                    lines.append(f"{prefix}-")
                    emit_list(item, indentation + 2)
            else:
                lines.append(f"{prefix}- {_yaml_scalar(item)}")

    if isinstance(value, dict):
        emit_map(value, 0)
    elif isinstance(value, list):
        emit_list(value, 0)
    else:
        lines.append(_yaml_scalar(value))
    return "\n".join(lines) + "\n"


def _is_within(path: Path, parent: Path) -> bool:
    path = path.resolve()
    parent = parent.resolve()
    return path == parent or parent in path.parents


def _safe_child(base: Path, relative: str, label: str) -> Path:
    candidate = Path(relative)
    if candidate.is_absolute() or any(part == ".." for part in candidate.parts):
        raise RegistryError(f"{label} 不能是绝对路径或包含路径穿越：{relative}")
    resolved = (base / candidate).resolve()
    if not _is_within(resolved, base):
        raise RegistryError(f"{label} 超出允许目录：{relative}")
    return resolved


def _read_yaml(path: Path) -> Any:
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise RegistryError(f"无法读取 {path}: {exc}") from exc
    return parse_restricted_yaml(text, str(path))


def _write_utf8(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(content)


def _load_registry_files(root: Path) -> Dict[str, Any]:
    registry_dir = root / ".codex" / "registry"
    result: Dict[str, Any] = {}
    for name in ("skills", "artifacts", "workflows"):
        path = registry_dir / f"{name}.yaml"
        if not path.is_file():
            raise RegistryError(f"缺少注册表文件：{path}")
        result[name] = _read_yaml(path)
    return result


def _as_dict(value: Any, location: str, errors: List[str]) -> Dict[str, Any]:
    if not isinstance(value, dict):
        errors.append(f"{location} 必须是映射")
        return {}
    return value


def _as_list(value: Any, location: str, errors: List[str]) -> List[Any]:
    if not isinstance(value, list):
        errors.append(f"{location} 必须是列表")
        return []
    return value


def _required_string(mapping: Dict[str, Any], key: str, location: str, errors: List[str]) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{location}.{key} 必须是非空字符串")
        return ""
    return value.strip()


def _validate_id(value: str, location: str, errors: List[str]) -> None:
    if not ID_PATTERN.fullmatch(value):
        errors.append(f"{location} 使用了非法 ID：{value}")


def _skill_frontmatter_name(skill_path: Path, errors: List[str], location: str) -> str:
    skill_file = skill_path / "SKILL.md"
    if not skill_file.is_file():
        errors.append(f"{location} 缺少 SKILL.md：{skill_file}")
        return ""
    try:
        content = skill_file.read_text(encoding="utf-8-sig")
    except OSError as exc:
        errors.append(f"{location} 无法读取 SKILL.md：{exc}")
        return ""
    if not content.startswith("---"):
        errors.append(f"{location} 的 SKILL.md 缺少 YAML frontmatter")
        return ""
    match = re.match(r"^---\r?\n(.*?)\r?\n---(?:\r?\n|$)", content, re.DOTALL)
    if not match:
        errors.append(f"{location} 的 SKILL.md frontmatter 格式无效")
        return ""
    try:
        frontmatter = parse_restricted_yaml(match.group(1), str(skill_file))
    except RegistryError as exc:
        errors.append(str(exc))
        return ""
    if not isinstance(frontmatter, dict):
        errors.append(f"{location} 的 SKILL.md frontmatter 必须是映射")
        return ""
    name = frontmatter.get("name")
    if not isinstance(name, str) or not name.strip():
        errors.append(f"{location} 的 SKILL.md 缺少 name")
        return ""
    return name.strip()


def validate_registry(root: Path) -> List[str]:
    """返回所有注册表错误；空列表表示有效。"""
    root = root.resolve()
    errors: List[str] = []
    try:
        files = _load_registry_files(root)
    except RegistryError as exc:
        return [str(exc)]

    for name, data in files.items():
        mapping = _as_dict(data, f"{name}.yaml", errors)
        if mapping.get("schema_version") != SCHEMA_VERSION:
            errors.append(f"{name}.yaml.schema_version 必须为 {SCHEMA_VERSION}")

    skill_records = _as_list(files["skills"].get("skills"), "skills.yaml.skills", errors)
    skill_index: Dict[str, Dict[str, Any]] = {}
    for index, raw_record in enumerate(skill_records):
        location = f"skills.yaml.skills[{index}]"
        record = _as_dict(raw_record, location, errors)
        skill_id = _required_string(record, "id", location, errors)
        if skill_id:
            _validate_id(skill_id, f"{location}.id", errors)
            if skill_id in skill_index:
                errors.append(f"重复技能 ID：{skill_id}")
            skill_index[skill_id] = record
        path_value = _required_string(record, "path", location, errors)
        if path_value:
            try:
                skill_path = _safe_child(root, path_value, f"{location}.path")
                if not skill_path.is_dir():
                    errors.append(f"{location}.path 指向的技能目录不存在：{skill_path}")
                elif skill_id:
                    frontmatter_name = _skill_frontmatter_name(skill_path, errors, location)
                    if frontmatter_name and frontmatter_name != skill_id:
                        errors.append(
                            f"{location} 的 frontmatter name 与 Registry 不一致："
                            f"{frontmatter_name} != {skill_id}"
                        )
            except RegistryError as exc:
                errors.append(str(exc))
        stack = _required_string(record, "stack", location, errors)
        work_type = _required_string(record, "work_type", location, errors)
        role = _required_string(record, "role", location, errors)
        if stack and work_type and skill_id:
            if not ID_PATTERN.fullmatch(stack):
                errors.append(f"{location}.stack 使用了非法 ID：{stack}")
            if not ID_PATTERN.fullmatch(work_type):
                errors.append(f"{location}.work_type 使用了非法 ID：{work_type}")
        if role not in ALLOWED_SKILL_ROLES:
            errors.append(f"{location}.role 必须是 leaf 或 support")
        elif role == "support" and stack != "cross-stack":
            errors.append(f"{location}.role 为 support 时 stack 必须是 cross-stack")
        phases = _as_list(record.get("phases"), f"{location}.phases", errors)
        phase_ids = set()
        for phase_index, raw_phase in enumerate(phases):
            phase_location = f"{location}.phases[{phase_index}]"
            phase = _as_dict(raw_phase, phase_location, errors)
            phase_id = _required_string(phase, "id", phase_location, errors)
            if phase_id:
                _validate_id(phase_id, f"{phase_location}.id", errors)
                if phase_id in phase_ids:
                    errors.append(f"{phase_location} 重复阶段 ID：{phase_id}")
                phase_ids.add(phase_id)
            _required_string(phase, "section", phase_location, errors)
        record["_phase_ids"] = phase_ids

    artifact_records = _as_list(
        files["artifacts"].get("artifacts"), "artifacts.yaml.artifacts", errors
    )
    artifact_index: Dict[str, Dict[str, Any]] = {}
    for index, raw_record in enumerate(artifact_records):
        location = f"artifacts.yaml.artifacts[{index}]"
        record = _as_dict(raw_record, location, errors)
        artifact_id = _required_string(record, "id", location, errors)
        if artifact_id:
            _validate_id(artifact_id, f"{location}.id", errors)
            if artifact_id in artifact_index:
                errors.append(f"重复制品 ID：{artifact_id}")
            artifact_index[artifact_id] = record
        filename = _required_string(record, "filename", location, errors)
        if filename:
            try:
                _safe_child(root / ".codex" / "artifacts" / "_template", filename, f"{location}.filename")
            except RegistryError as exc:
                errors.append(str(exc))
        format_name = _required_string(record, "format", location, errors)
        if format_name != "markdown":
            errors.append(f"{location}.format 当前只支持 markdown")
        for boolean_key in ("required", "sensitive"):
            if not isinstance(record.get(boolean_key), bool):
                errors.append(f"{location}.{boolean_key} 必须是布尔值")

    workflow_records = _as_list(
        files["workflows"].get("workflows"), "workflows.yaml.workflows", errors
    )
    workflow_ids = set()
    for index, raw_workflow in enumerate(workflow_records):
        location = f"workflows.yaml.workflows[{index}]"
        workflow = _as_dict(raw_workflow, location, errors)
        workflow_id = _required_string(workflow, "id", location, errors)
        if workflow_id:
            _validate_id(workflow_id, f"{location}.id", errors)
            if workflow_id in workflow_ids:
                errors.append(f"重复工作流 ID：{workflow_id}")
            workflow_ids.add(workflow_id)
        _required_string(workflow, "display_name", location, errors)
        supported_stacks = _as_list(
            workflow.get("supported_stacks"), f"{location}.supported_stacks", errors
        )
        supported_stack_set = set()
        for stack in supported_stacks:
            if not isinstance(stack, str) or not stack:
                errors.append(f"{location}.supported_stacks 包含非法值：{stack}")
            else:
                supported_stack_set.add(stack)
        skill_by_stack = _as_dict(
            workflow.get("skill_by_stack"), f"{location}.skill_by_stack", errors
        )
        if set(skill_by_stack) != supported_stack_set:
            errors.append(f"{location}.skill_by_stack 必须覆盖全部 supported_stacks")
        for stack in supported_stack_set:
            skill_id = skill_by_stack.get(stack)
            if not isinstance(skill_id, str) or skill_id not in skill_index:
                errors.append(f"{location}.skill_by_stack.{stack} 引用了未知技能：{skill_id}")
            else:
                skill = skill_index[skill_id]
                if skill.get("stack") != stack:
                    errors.append(
                        f"{location}.skill_by_stack.{stack} 的技能栈不匹配：{skill.get('stack')}"
                    )
                if skill.get("work_type") != workflow_id:
                    errors.append(
                        f"{location}.skill_by_stack.{stack} 的工作类型不匹配："
                        f"{skill.get('work_type')} != {workflow_id}"
                    )
        initial_artifacts = _as_list(
            workflow.get("initial_artifacts"), f"{location}.initial_artifacts", errors
        )
        available = set()
        for artifact_id in initial_artifacts:
            if not isinstance(artifact_id, str) or artifact_id not in artifact_index:
                errors.append(f"{location}.initial_artifacts 引用了未知制品：{artifact_id}")
            else:
                available.add(artifact_id)
        stages = _as_list(workflow.get("stages"), f"{location}.stages", errors)
        stage_ids = set()
        produced_by: Dict[str, str] = {}
        for stage_index, raw_stage in enumerate(stages):
            stage_location = f"{location}.stages[{stage_index}]"
            stage = _as_dict(raw_stage, stage_location, errors)
            stage_id = _required_string(stage, "id", stage_location, errors)
            if stage_id:
                _validate_id(stage_id, f"{stage_location}.id", errors)
                if stage_id in stage_ids:
                    errors.append(f"{stage_location} 重复阶段 ID：{stage_id}")
                stage_ids.add(stage_id)
            owner = _required_string(stage, "owner", stage_location, errors)
            if owner not in ALLOWED_STAGE_OWNERS:
                errors.append(f"{stage_location}.owner 必须是 orchestrator、leaf 或 support")
            if not isinstance(stage.get("required"), bool):
                errors.append(f"{stage_location}.required 必须是布尔值")
            failure_policy = _required_string(stage, "on_failure", stage_location, errors)
            if failure_policy not in ALLOWED_FAILURE_POLICIES:
                errors.append(f"{stage_location}.on_failure 值无效：{failure_policy}")
            consumes = _as_list(stage.get("consumes"), f"{stage_location}.consumes", errors)
            produces = _as_list(stage.get("produces"), f"{stage_location}.produces", errors)
            for artifact_id in consumes:
                if not isinstance(artifact_id, str) or artifact_id not in artifact_index:
                    errors.append(f"{stage_location}.consumes 引用了未知制品：{artifact_id}")
                elif artifact_id not in available:
                    errors.append(
                        f"{stage_location}.consumes 的制品尚未由前置阶段产生：{artifact_id}"
                    )
            if owner == "leaf":
                phase = _required_string(stage, "phase", stage_location, errors)
                if "skill" in stage:
                    errors.append(f"{stage_location} 的 leaf 阶段不应声明 skill")
                for stack in supported_stack_set:
                    skill_id = skill_by_stack.get(stack)
                    skill = skill_index.get(skill_id, {})
                    phase_ids = skill.get("_phase_ids", set())
                    if phase and phase not in phase_ids:
                        errors.append(
                            f"{stage_location}.phase 在 {skill_id} 中不存在：{phase}"
                        )
            elif owner == "support":
                support_skill_id = _required_string(stage, "skill", stage_location, errors)
                phase = _required_string(stage, "phase", stage_location, errors)
                support_skill = skill_index.get(support_skill_id, {})
                if support_skill_id and not support_skill:
                    errors.append(
                        f"{stage_location}.skill 引用了未知技能：{support_skill_id}"
                    )
                elif support_skill.get("role") != "support":
                    errors.append(
                        f"{stage_location}.skill 必须引用 role=support 的技能：{support_skill_id}"
                    )
                if phase and phase not in support_skill.get("_phase_ids", set()):
                    errors.append(
                        f"{stage_location}.phase 在 {support_skill_id} 中不存在：{phase}"
                    )
            else:
                if "phase" in stage:
                    errors.append(f"{stage_location} 的 orchestrator 阶段不应声明 phase")
                if "skill" in stage:
                    errors.append(f"{stage_location} 的 orchestrator 阶段不应声明 skill")
            for artifact_id in produces:
                if not isinstance(artifact_id, str) or artifact_id not in artifact_index:
                    errors.append(f"{stage_location}.produces 引用了未知制品：{artifact_id}")
                elif artifact_id in produced_by:
                    errors.append(
                        f"制品 {artifact_id} 被多个阶段生产："
                        f"{produced_by[artifact_id]}、{stage_id}"
                    )
                else:
                    produced_by[artifact_id] = stage_id
                    available.add(artifact_id)

    return errors


def _validated_data(root: Path) -> Dict[str, Any]:
    errors = validate_registry(root)
    if errors:
        raise RegistryError("注册表校验失败：\n- " + "\n- ".join(errors))
    return _load_registry_files(root)


def resolve_workflow(root: Path, workflow_id: str, stack: str) -> Dict[str, Any]:
    """解析指定技术栈的线性阶段计划。"""
    files = _validated_data(root.resolve())
    workflows = files["workflows"]["workflows"]
    workflow = next(item for item in workflows if item["id"] == workflow_id)
    skill_id = workflow["skill_by_stack"][stack]
    stages: List[Dict[str, Any]] = []
    for stage in workflow["stages"]:
        if stage["owner"] == "leaf":
            stage_skill_id = skill_id
        elif stage["owner"] == "support":
            stage_skill_id = stage["skill"]
        else:
            stage_skill_id = None
        resolved_stage = {
            "id": stage["id"],
            "owner": stage["owner"],
            "phase": stage.get("phase"),
            "skill_id": stage_skill_id,
            "required": stage["required"],
            "on_failure": stage["on_failure"],
            "consumes": list(stage["consumes"]),
            "produces": list(stage["produces"]),
        }
        stages.append(resolved_stage)
    return {
        "schema_version": SCHEMA_VERSION,
        "workflow_id": workflow_id,
        "stack": stack,
        "skill_id": skill_id,
        "initial_artifacts": list(workflow["initial_artifacts"]),
        "stages": stages,
    }


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _new_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]


def _validate_run_id(run_id: str) -> None:
    if not RUN_ID_PATTERN.fullmatch(run_id):
        raise RegistryError(f"run-id 非法，只能使用安全的单层目录名：{run_id}")


def _artifact_records(files: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {record["id"]: record for record in files["artifacts"]["artifacts"]}


def init_artifact_run(
    root: Path, workflow_id: str, stack: str, request_file: Path, run_id: Optional[str] = None
) -> Dict[str, Any]:
    """创建隔离运行目录和初始 manifest。"""
    root = root.resolve()
    resolved_workflow = resolve_workflow(root, workflow_id, stack)
    request_file = request_file.resolve()
    if not request_file.is_file():
        raise RegistryError(f"请求文件不存在：{request_file}")
    try:
        request_text = request_file.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise RegistryError(f"无法读取请求文件：{exc}") from exc
    if not request_text.strip():
        raise RegistryError("请求文件不能为空")

    actual_run_id = run_id or _new_run_id()
    _validate_run_id(actual_run_id)
    artifacts_root = root / ".codex" / "artifacts"
    run_dir = _safe_child(artifacts_root, actual_run_id, "run-id")
    if run_dir.exists():
        raise RegistryError(f"运行目录已经存在，不覆盖已有制品：{run_dir}")
    run_dir.mkdir(parents=True, exist_ok=False)
    _write_utf8(run_dir / "request.md", request_text)

    timestamp = _utc_now()
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "run_id": actual_run_id,
        "workflow_id": workflow_id,
        "stack": stack,
        "status": "created",
        "current_stage": "intake",
        "created_at": timestamp,
        "updated_at": timestamp,
        "stages": [
            {
                "id": stage["id"],
                "status": "pending",
                "owner": stage["owner"],
                "skill_id": stage["skill_id"],
            }
            for stage in resolved_workflow["stages"]
        ],
        "artifacts": [
            {
                "id": "request-brief",
                "path": "request.md",
                "status": "present",
                "producer_stage": "init",
            }
        ],
    }
    _write_utf8(run_dir / "manifest.yaml", dump_restricted_yaml(manifest))
    return {"run_id": actual_run_id, "run_dir": str(run_dir), "manifest": manifest}


def _load_run_manifest(root: Path, run_dir: Path) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    root = root.resolve()
    artifacts_root = (root / ".codex" / "artifacts").resolve()
    run_dir = run_dir.resolve()
    if not _is_within(run_dir, artifacts_root) or run_dir == artifacts_root:
        raise RegistryError(f"run 目录必须位于 .codex/artifacts 下：{run_dir}")
    manifest_path = run_dir / "manifest.yaml"
    if not manifest_path.is_file():
        raise RegistryError(f"run 目录缺少 manifest.yaml：{run_dir}")
    manifest = _read_yaml(manifest_path)
    if not isinstance(manifest, dict):
        raise RegistryError("manifest.yaml 必须是映射")
    files = _validated_data(root)
    workflow_id = manifest.get("workflow_id")
    stack = manifest.get("stack")
    if not isinstance(workflow_id, str) or not isinstance(stack, str):
        raise RegistryError("manifest 必须包含 workflow_id 和 stack")
    workflow = resolve_workflow(root, workflow_id, stack)
    return manifest, files, workflow


def validate_artifact_run(root: Path, run_dir: Path) -> List[str]:
    """校验某个运行目录，返回错误列表。"""
    try:
        manifest, files, workflow = _load_run_manifest(root, run_dir)
    except RegistryError as exc:
        return [str(exc)]
    errors: List[str] = []
    run_dir = run_dir.resolve()
    if manifest.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"manifest.schema_version 必须为 {SCHEMA_VERSION}")
    run_id = manifest.get("run_id")
    if not isinstance(run_id, str) or run_id != run_dir.name:
        errors.append("manifest.run_id 必须与运行目录名一致")
    if manifest.get("status") not in ALLOWED_RUN_STATUS:
        errors.append(f"manifest.status 无效：{manifest.get('status')}")
    for timestamp_key in ("created_at", "updated_at"):
        if not isinstance(manifest.get(timestamp_key), str) or not manifest[timestamp_key]:
            errors.append(f"manifest.{timestamp_key} 必须是非空字符串")

    stage_records = manifest.get("stages")
    if not isinstance(stage_records, list):
        errors.append("manifest.stages 必须是列表")
        stage_records = []
    expected_stages = {stage["id"]: stage for stage in workflow["stages"]}
    actual_stages: Dict[str, Dict[str, Any]] = {}
    for index, raw_stage in enumerate(stage_records):
        location = f"manifest.stages[{index}]"
        if not isinstance(raw_stage, dict):
            errors.append(f"{location} 必须是映射")
            continue
        stage_id = raw_stage.get("id")
        if not isinstance(stage_id, str) or stage_id not in expected_stages:
            errors.append(f"{location}.id 不是当前工作流阶段：{stage_id}")
            continue
        if stage_id in actual_stages:
            errors.append(f"manifest 重复记录阶段：{stage_id}")
        actual_stages[stage_id] = raw_stage
        if raw_stage.get("status") not in ALLOWED_STAGE_STATUS:
            errors.append(f"{location}.status 无效：{raw_stage.get('status')}")
    missing_stages = set(expected_stages) - set(actual_stages)
    for stage_id in sorted(missing_stages):
        errors.append(f"manifest 缺少阶段：{stage_id}")

    artifact_index = _artifact_records(files)
    raw_artifacts = manifest.get("artifacts")
    if not isinstance(raw_artifacts, list):
        errors.append("manifest.artifacts 必须是列表")
        raw_artifacts = []
    actual_artifacts: Dict[str, Dict[str, Any]] = {}
    for index, raw_artifact in enumerate(raw_artifacts):
        location = f"manifest.artifacts[{index}]"
        if not isinstance(raw_artifact, dict):
            errors.append(f"{location} 必须是映射")
            continue
        artifact_id = raw_artifact.get("id")
        relative_path = raw_artifact.get("path")
        if not isinstance(artifact_id, str) or artifact_id not in artifact_index:
            errors.append(f"{location}.id 不是已注册制品：{artifact_id}")
            continue
        if artifact_id in actual_artifacts:
            errors.append(f"manifest 重复记录制品：{artifact_id}")
        actual_artifacts[artifact_id] = raw_artifact
        if not isinstance(relative_path, str) or not relative_path:
            errors.append(f"{location}.path 必须是非空字符串")
            continue
        try:
            artifact_path = _safe_child(run_dir, relative_path, f"{location}.path")
            if not artifact_path.is_file():
                errors.append(f"{location}.path 文件不存在：{artifact_path}")
            expected_filename = artifact_index[artifact_id]["filename"]
            if relative_path != expected_filename:
                errors.append(
                    f"{location}.path 必须使用注册文件名：{expected_filename}"
                )
        except RegistryError as exc:
            errors.append(str(exc))

    if "request-brief" not in actual_artifacts:
        errors.append("manifest 必须记录 request-brief")
    for stage in workflow["stages"]:
        actual_stage = actual_stages.get(stage["id"], {})
        if actual_stage.get("status") != "succeeded":
            continue
        for artifact_id in stage["produces"]:
            if artifact_id not in actual_artifacts:
                errors.append(
                    f"成功阶段 {stage['id']} 缺少输出制品：{artifact_id}"
                )
    return errors


def export_artifacts(
    root: Path, run_dir: Path, destination: Path, artifact_ids: Optional[Iterable[str]] = None
) -> Dict[str, Any]:
    """导出运行 manifest 和指定制品，默认拒绝覆盖目标目录。"""
    errors = validate_artifact_run(root, run_dir)
    if errors:
        raise RegistryError("Artifact 校验失败：\n- " + "\n- ".join(errors))
    manifest, files, _ = _load_run_manifest(root, run_dir)
    run_dir = run_dir.resolve()
    destination = destination.resolve()
    if destination.exists():
        raise RegistryError(f"导出目标已存在，为避免覆盖而拒绝操作：{destination}")
    if _is_within(destination, run_dir):
        raise RegistryError("导出目标不能位于源运行目录内")
    selected = set(artifact_ids or [])
    available = {record["id"]: record for record in manifest["artifacts"]}
    if selected - set(available):
        unknown = ", ".join(sorted(selected - set(available)))
        raise RegistryError(f"导出了未知或未生成的制品：{unknown}")
    if not selected:
        selected = set(available)

    destination.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(run_dir / "manifest.yaml", destination / "manifest.yaml")
    exported: List[str] = []
    artifact_definitions = _artifact_records(files)
    for artifact_id in sorted(selected):
        relative_path = available[artifact_id]["path"]
        source = _safe_child(run_dir, relative_path, f"制品 {artifact_id}")
        target = _safe_child(destination, artifact_definitions[artifact_id]["filename"], f"制品 {artifact_id}")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        exported.append(artifact_id)
    return {"run_id": manifest["run_id"], "destination": str(destination), "artifacts": exported}


def _print_json(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="管理 Codex Registry、Workflow Registry 和 Artifact")
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT, help="配置仓库根目录")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("validate", help="校验三个注册表和所有叶子技能")
    resolve_parser = subparsers.add_parser("resolve", help="解析指定技术栈的工作流")
    resolve_parser.add_argument("--workflow", required=True)
    resolve_parser.add_argument("--stack", required=True)

    artifact_parser = subparsers.add_parser("artifact", help="管理运行制品")
    artifact_subparsers = artifact_parser.add_subparsers(dest="artifact_command", required=True)

    init_parser = artifact_subparsers.add_parser("init", help="初始化运行制品目录")
    init_parser.add_argument("--workflow", required=True)
    init_parser.add_argument("--stack", required=True)
    init_parser.add_argument("--request-file", type=Path, required=True)
    init_parser.add_argument("--run-id")

    artifact_validate_parser = artifact_subparsers.add_parser("validate", help="校验运行制品目录")
    artifact_validate_parser.add_argument("--run-dir", type=Path, required=True)

    export_parser = artifact_subparsers.add_parser("export", help="导出运行制品")
    export_parser.add_argument("--run-dir", type=Path, required=True)
    export_parser.add_argument("--destination", type=Path, required=True)
    export_parser.add_argument("--artifact", dest="artifact_ids", action="append")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    root = args.root.resolve()
    try:
        if args.command == "validate":
            errors = validate_registry(root)
            if errors:
                print("Registry 校验失败：", file=sys.stderr)
                for error in errors:
                    print(f"- {error}", file=sys.stderr)
                return 1
            files = _load_registry_files(root)
            print(
                "Registry valid: "
                f"{len(files['skills']['skills'])} skills, "
                f"{len(files['workflows']['workflows'])} workflows, "
                f"{len(files['artifacts']['artifacts'])} artifacts"
            )
            return 0
        if args.command == "resolve":
            _print_json(resolve_workflow(root, args.workflow, args.stack))
            return 0
        if args.command == "artifact" and args.artifact_command == "init":
            _print_json(
                init_artifact_run(
                    root,
                    args.workflow,
                    args.stack,
                    args.request_file,
                    args.run_id,
                )
            )
            return 0
        if args.command == "artifact" and args.artifact_command == "validate":
            errors = validate_artifact_run(root, args.run_dir)
            if errors:
                print("Artifact 校验失败：", file=sys.stderr)
                for error in errors:
                    print(f"- {error}", file=sys.stderr)
                return 1
            print("Artifact valid")
            return 0
        if args.command == "artifact" and args.artifact_command == "export":
            _print_json(export_artifacts(root, args.run_dir, args.destination, args.artifact_ids))
            return 0
        parser.error("未知命令")
    except RegistryError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
