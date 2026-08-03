"""开发规范检查器的标准库测试。"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))
import standards_tool  # noqa: E402


class StandardsToolTests(unittest.TestCase):
    def test_discover_vue_tools_and_sources(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "docs" / "开发规范").mkdir(parents=True)
            (root / "docs" / "开发规范" / "README.md").write_text("# 规范\n", encoding="utf-8")
            (root / "AGENTS.md").write_text("# 规则\n", encoding="utf-8")
            (root / ".dev-env.yaml").write_text(
                'frontend:\n  package_manager: "pnpm"\n', encoding="utf-8"
            )
            (root / "eslint.config.js").write_text("export default [];\n", encoding="utf-8")
            (root / "package.json").write_text(
                json.dumps(
                    {
                        "scripts": {
                            "lint": "eslint .",
                            "typecheck": "tsc --noEmit",
                            "test": "vitest run",
                            "dev": "vite",
                        }
                    }
                ),
                encoding="utf-8",
            )

            result = standards_tool.discover(root, "vue")

            self.assertEqual("vue", result["stack"])
            self.assertTrue(any(item["path"] == "docs/开发规范/README.md" for item in result["sources"]))
            command_ids = {item["id"] for item in result["commands"]}
            self.assertIn("pnpm-lint", command_ids)
            self.assertIn("pnpm-typecheck", command_ids)
            self.assertIn("pnpm-test", command_ids)
            self.assertNotIn("pnpm-dev", command_ids)

    def test_check_invalid_utf8_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            invalid_file = root / "src.txt"
            invalid_file.write_bytes(b"\xff\xfe")

            result = standards_tool.check(
                root,
                "vue",
                changed_files=["src.txt"],
            )

            self.assertEqual("blocked", result["status"])
            self.assertTrue(any(item["id"] == "utf8" and item["status"] == "blocked" for item in result["checks"]))

    def test_missing_standards_directory_is_warning(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            result = standards_tool.discover(Path(temporary_directory), "springboot")

            self.assertEqual("pass-with-warning", result["status"])
            self.assertTrue(any("docs/开发规范" in warning for warning in result["warnings"]))

    def test_maven_plugin_commands_are_discovered_without_running_them(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "pom.xml").write_text(
                """<project xmlns=\"http://maven.apache.org/POM/4.0.0\"><build><plugins>\n"
                "<plugin><artifactId>maven-checkstyle-plugin</artifactId></plugin>\n"
                "<plugin><artifactId>spotless-maven-plugin</artifactId></plugin>\n"
                "</plugins></build></project>""",
                encoding="utf-8",
            )
            (root / ".dev-env.yaml").write_text(
                'development:\n  java:\n    home: "missing-java"\n  maven:\n    home: "missing-maven"\n',
                encoding="utf-8",
            )

            result = standards_tool.discover(root, "springboot")

            command_ids = {item["id"] for item in result["commands"]}
            self.assertIn("maven-test", command_ids)
            self.assertIn("maven-verify", command_ids)
            self.assertIn("maven-checkstyle-check", command_ids)
            self.assertIn("maven-spotless-check", command_ids)

    def test_check_executes_existing_pnpm_script(self) -> None:
        if not (shutil.which("pnpm.cmd") or shutil.which("pnpm")):
            self.skipTest("当前环境没有 pnpm")
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / ".dev-env.yaml").write_text(
                'frontend:\n  package_manager: "pnpm"\n', encoding="utf-8"
            )
            (root / "package.json").write_text(
                json.dumps({"scripts": {"lint": "node -e \"process.exit(0)\""}}),
                encoding="utf-8",
            )

            result = standards_tool.check(root, "vue", full=False)

            self.assertTrue(
                any(item["id"] == "pnpm-lint" and item["status"] == "passed" for item in result["checks"]),
                result,
            )


if __name__ == "__main__":
    unittest.main()
