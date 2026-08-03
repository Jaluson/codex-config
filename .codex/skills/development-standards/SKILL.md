---
name: development-standards
description: 自动发现并执行项目已有的格式化、Lint、类型、测试、构建和架构检查，按证据分级输出开发规范报告；当需要统一代码风格、验证变更质量或接入 Codex 工作流门禁时使用。
---

# 开发规范检查

## 目标

以项目现有规则和可执行工具为准，生成可追溯的检查结果。不要凭个人偏好补充空格、注释、命名或日志规则；没有可靠来源的风格差异只能作为告警。

## 工具入口

使用 bundled script [`scripts/standards_tool.py`](scripts/standards_tool.py)：

```text
python .codex/skills/development-standards/scripts/standards_tool.py discover --root <项目根目录> --stack <springboot|vue>
python .codex/skills/development-standards/scripts/standards_tool.py check --root <项目根目录> --stack <springboot|vue> --changed-from-git --full
```

脚本只使用 Python 标准库，不访问网络、不安装依赖、不修改系统环境变量。项目命令在当前子进程中使用目标项目 `.dev-env.yaml` 的环境配置。

## 工作流程

### 1. 发现规范来源 (`inspect`)

- 明确当前项目根目录和技术栈，不从技能仓库路径猜测目标项目。
- 读取项目根目录的 `AGENTS.md`、`.dev-env.yaml` 和存在的 `docs/开发规范/README.md`。
- 发现 `.editorconfig`、Maven 插件、`package.json` scripts、ESLint、Prettier、TypeScript、CI 和测试配置。
- 运行 `discover`，将规则来源、可用工具、命令、缺失项和警告写入注册的 `standards-context` Artifact。

### 2. 检查变更和全量质量 (`check`)

- 读取 staged、unstaged 和未跟踪文件；必要时使用阶段输入中的变更范围。
- 先执行 UTF-8、`git diff --check` 等通用只读检查，再执行变更范围可支持的项目工具。
- 使用 `--full` 时，执行项目已经存在的全量 Lint、类型、测试、构建、Maven `verify` 或质量插件检查。
- 只执行已发现且安全的命令；不执行格式化写入、依赖安装、迁移、部署或未知 shell 字符串。
- 将 `standards_tool.py check` 的输出写入 `standards-report` Artifact。

## 证据和门禁

- 用户要求、项目 `AGENTS.md`、`docs/开发规范`、公共契约和已配置工具是权威来源。
- 既有代码样例只能提供低置信度建议；Agent 常识和个人风格不能形成违规结论。
- 已配置工具执行失败、明确的安全/契约/正确性问题或必要验证缺失为阻断。
- 规范目录或可选工具不存在、只有样例风格差异或检查未配置为告警。
- 工具无法启动、超时或环境缺失时，报告为环境阻塞，不得报告为通过。
- 每条发现包含来源、检查命令、退出码、文件位置或输出证据、影响和状态。

## 直接调用和编排边界

- 直接调用本 skill 时完成发现、变更范围检查和用户要求的全量检查，并如实报告未执行项。
- 由 `$orchestrator` 调用时，只执行 Workflow Registry 当前阶段声明的 `inspect` 或 `check`，读取和写入当前 run 的注册 Artifact。
- 本 skill 默认只读；项目质量命令可能产生未跟踪的构建缓存，但不得改写受版本控制的源文件、配置、锁文件或格式化结果。
- 所有报告使用 UTF-8；报告中不得写入密钥、令牌、生产数据或未经脱敏的命令输出。
