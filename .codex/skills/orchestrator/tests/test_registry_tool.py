"""Registry 和 Artifact 工具的标准库测试。"""

from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))
import registry_tool  # noqa: E402


REPOSITORY_ROOT = registry_tool.DEFAULT_ROOT


class RegistryToolTests(unittest.TestCase):
    def test_registry_is_valid(self) -> None:
        errors = registry_tool.validate_registry(REPOSITORY_ROOT)
        self.assertEqual([], errors, "\n".join(errors))

    def test_all_workflows_resolve_for_both_stacks(self) -> None:
        files = registry_tool._load_registry_files(REPOSITORY_ROOT)
        for workflow in files["workflows"]["workflows"]:
            for stack in workflow["supported_stacks"]:
                resolved = registry_tool.resolve_workflow(REPOSITORY_ROOT, workflow["id"], stack)
                self.assertEqual(workflow["id"], resolved["workflow_id"])
                self.assertEqual(stack, resolved["stack"])
                self.assertTrue(resolved["stages"])
                for stage in resolved["stages"]:
                    if stage["owner"] == "support":
                        self.assertEqual("api-documentation", stage["skill_id"])

    def test_api_documentation_support_stages_are_registered(self) -> None:
        files = registry_tool._load_registry_files(REPOSITORY_ROOT)
        expected_workflows = {
            "bug-fixing",
            "feature-development",
            "refactoring",
            "upgrade-migration",
        }
        for workflow in files["workflows"]["workflows"]:
            support_stages = [
                stage for stage in workflow["stages"] if stage["owner"] == "support"
            ]
            if workflow["id"] in expected_workflows:
                self.assertEqual(
                    ["api-doc-inspect", "api-doc-update", "api-doc-verify"],
                    [stage["id"] for stage in support_stages],
                )
                self.assertTrue(
                    all(stage["skill"] == "api-documentation" for stage in support_stages)
                )
            else:
                self.assertEqual([], support_stages)

    def test_restricted_yaml_rejects_unsupported_features(self) -> None:
        with self.assertRaises(registry_tool.RegistryError):
            registry_tool.parse_restricted_yaml("schema:\n\tvalue: true\n")
        with self.assertRaises(registry_tool.RegistryError):
            registry_tool.parse_restricted_yaml("value: &anchor text\n")

    def test_invalid_skill_path_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            shutil.copytree(REPOSITORY_ROOT / ".codex", root / ".codex")
            skills_file = root / ".codex" / "registry" / "skills.yaml"
            content = skills_file.read_text(encoding="utf-8")
            content = content.replace(
                "path: .codex/skills/springboot-bug-fixing",
                "path: .codex/skills/missing-skill",
                1,
            )
            skills_file.write_text(content, encoding="utf-8", newline="\n")
            errors = registry_tool.validate_registry(root)
            self.assertTrue(any("技能目录不存在" in error for error in errors), errors)

    def test_invalid_support_skill_reference_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            shutil.copytree(REPOSITORY_ROOT / ".codex", root / ".codex")
            workflows_file = root / ".codex" / "registry" / "workflows.yaml"
            content = workflows_file.read_text(encoding="utf-8")
            content = content.replace(
                "skill: api-documentation\n        phase: inspect",
                "skill: missing-support-skill\n        phase: inspect",
                1,
            )
            workflows_file.write_text(content, encoding="utf-8", newline="\n")
            errors = registry_tool.validate_registry(root)
            self.assertTrue(any("未知技能" in error for error in errors), errors)

    def test_invalid_support_phase_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            shutil.copytree(REPOSITORY_ROOT / ".codex", root / ".codex")
            workflows_file = root / ".codex" / "registry" / "workflows.yaml"
            content = workflows_file.read_text(encoding="utf-8")
            content = content.replace(
                "skill: api-documentation\n        phase: inspect",
                "skill: api-documentation\n        phase: missing-phase",
                1,
            )
            workflows_file.write_text(content, encoding="utf-8", newline="\n")
            errors = registry_tool.validate_registry(root)
            self.assertTrue(any("missing-phase" in error for error in errors), errors)

    def test_artifact_lifecycle_and_export(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            shutil.copytree(REPOSITORY_ROOT / ".codex", root / ".codex")
            request_file = root / "request.txt"
            request_file.write_text("请验证一个缺陷修复任务。\n", encoding="utf-8", newline="\n")

            initialized = registry_tool.init_artifact_run(
                root,
                "bug-fixing",
                "springboot",
                request_file,
                "20260803T000000Z-test",
            )
            run_dir = Path(initialized["run_dir"])
            self.assertTrue((run_dir / "manifest.yaml").is_file())
            self.assertTrue((run_dir / "request.md").is_file())
            self.assertEqual([], registry_tool.validate_artifact_run(root, run_dir))

            export_parent = root / "exported"
            exported = registry_tool.export_artifacts(root, run_dir, export_parent)
            self.assertEqual(["request-brief"], exported["artifacts"])
            self.assertTrue((export_parent / "manifest.yaml").is_file())
            self.assertTrue((export_parent / "request.md").is_file())
            with self.assertRaises(registry_tool.RegistryError):
                registry_tool.export_artifacts(root, run_dir, export_parent)

            unknown_destination = root / "unknown-export"
            with self.assertRaises(registry_tool.RegistryError):
                registry_tool.export_artifacts(
                    root,
                    run_dir,
                    unknown_destination,
                    ["not-generated"],
                )
            self.assertFalse(unknown_destination.exists())

    def test_artifact_run_id_cannot_escape_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            shutil.copytree(REPOSITORY_ROOT / ".codex", root / ".codex")
            request_file = root / "request.txt"
            request_file.write_text("请求\n", encoding="utf-8", newline="\n")
            with self.assertRaises(registry_tool.RegistryError):
                registry_tool.init_artifact_run(
                    root,
                    "bug-fixing",
                    "springboot",
                    request_file,
                    "../escape",
                )

    def test_cli_validate_and_resolve(self) -> None:
        output = StringIO()
        with redirect_stdout(output):
            result = registry_tool.main(["--root", str(REPOSITORY_ROOT), "validate"])
        self.assertEqual(0, result)
        self.assertIn("15 skills", output.getvalue())

        output = StringIO()
        with redirect_stdout(output):
            result = registry_tool.main(
                [
                    "--root",
                    str(REPOSITORY_ROOT),
                    "resolve",
                    "--workflow",
                    "feature-development",
                    "--stack",
                    "vue",
                ]
            )
        self.assertEqual(0, result)
        self.assertIn('"skill_id": "vue-feature-development"', output.getvalue())


if __name__ == "__main__":
    unittest.main()
