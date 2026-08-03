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

    def test_fingerprint_normalizes_line_endings(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            agents = root / "AGENTS.md"
            agents.write_text("# 规则\n\n- 使用 UTF-8\n", encoding="utf-8")

            first = standards_tool.discover(root, "vue")
            agents.write_bytes("# 规则\r\n\r\n- 使用 UTF-8\r\n".encode("utf-8"))
            second = standards_tool.discover(root, "vue")

            self.assertEqual(first["fingerprint"]["value"], second["fingerprint"]["value"])

    def test_user_rules_change_is_reported_against_baseline(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "AGENTS.md").write_text("# 规则\n", encoding="utf-8")
            rules = root / "user-rules.md"
            rules.write_text("本次要求使用 4 个空格。\n", encoding="utf-8")
            baseline = standards_tool.discover(root, "vue", user_rules_file=rules)["fingerprint"]
            baseline_path = root / "standards-fingerprint.json"
            baseline_path.write_text(json.dumps(baseline, ensure_ascii=False), encoding="utf-8")

            incompatible = dict(baseline)
            incompatible["stack"] = "springboot"
            baseline_path.write_text(json.dumps(incompatible, ensure_ascii=False), encoding="utf-8")
            with self.assertRaises(standards_tool.ToolError):
                standards_tool.check(
                    root,
                    "vue",
                    changed_files=["AGENTS.md"],
                    user_rules_file=rules,
                    baseline_fingerprint=baseline_path,
                )
            baseline_path.write_text(json.dumps(baseline, ensure_ascii=False), encoding="utf-8")

            rules.write_text("本次要求使用 2 个空格。\n", encoding="utf-8")
            result = standards_tool.check(
                root,
                "vue",
                changed_files=["AGENTS.md"],
                user_rules_file=rules,
                baseline_fingerprint=baseline_path,
            )

            self.assertTrue(result["fingerprint_comparison"]["changed"])
            self.assertIn("<user-rules>", [item["path"] for item in result["fingerprint_comparison"]["changed_inputs"]])
            self.assertTrue(any(item["id"] == "standards-fingerprint" for item in result["checks"]))

    def test_discover_exposes_only_known_file_scoped_fixers(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / ".dev-env.yaml").write_text(
                'frontend:\n  package_manager: "pnpm"\n', encoding="utf-8"
            )
            (root / "eslint.config.js").write_text("export default [];\n", encoding="utf-8")
            (root / "prettier.config.js").write_text("export default {};\n", encoding="utf-8")
            (root / "package.json").write_text(
                json.dumps(
                    {
                        "scripts": {
                            "lint:fix": "eslint --fix .",
                            "format:write": "prettier --write .",
                        },
                        "devDependencies": {"eslint": "1.0.0", "prettier": "1.0.0"},
                    }
                ),
                encoding="utf-8",
            )

            result = standards_tool.discover(root, "vue")
            fixer_ids = {item["id"] for item in result["fixers"]}
            self.assertEqual({"eslint-fix", "prettier-fix"}, fixer_ids)
            self.assertTrue(all(item["scope"] == "changed-files" for item in result["fixers"]))
            fix_commands = standards_tool._fix_commands(result["fixers"], ["src/App.vue", "README.md", "src/App.java"])
            self.assertEqual({"eslint-fix", "prettier-fix"}, {item["id"] for item in fix_commands})
            self.assertTrue(all(item["argv"][-1] in {"src/App.vue", "README.md"} for item in fix_commands))

    def test_fix_without_changed_files_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            result = standards_tool.check(Path(temporary_directory), "vue", fix=True)

            self.assertEqual("blocked", result["status"])
            self.assertTrue(any(item["id"] == "fix-scope" and item["status"] == "blocked" for item in result["fixes"]))


if __name__ == "__main__":
    unittest.main()
