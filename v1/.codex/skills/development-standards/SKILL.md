---
name: development-standards
description: 动态发现项目开发规范并通过 SHA-256 指纹检测规范变化，执行已有格式化、Lint、类型、测试、构建和架构检查，并在明确授权时使用受限工具纠正变更；当需要统一代码风格、验证变更质量或接入 Codex 工作流门禁时使用。
---

# 开发规范检查与受限纠正

## 目标

以项目当前规范来源和可执行工具为准，生成可追溯的检查结果。规范来源每次都计算 SHA-256 指纹；当前运行的 `standards-context` 是基线，后续检查发现指纹变化时必须重新发现并报告变化。不要凭个人偏好补充空格、注释、命名或日志规则；没有可靠来源的风格差异只能作为告警。

## 规范目录分层

项目 `docs/开发规范/` 采用三层设计，必须保留并按以下顺序理解：

- `基础/`：跨技术栈的工程治理、编码、质量、安全和交付规则。
- `专项/`：技术栈、协议或业务边界专项规则；只有匹配当前任务时才作为适用规则。
- `模板/`：设计、审查、验证和交付记录模板；用于产出证据，不当作额外编码规则。

`docs/开发规范/README.md` 是分类和适用范围入口，分层正文是唯一权威来源。根目录不应存在与分层正文重复的平铺规范；发现时报告为规范组织告警，并以分层正文为准。指纹仍纳入 `docs/开发规范/` 下所有 UTF-8 文件，以便目录结构、导航和模板变化都能触发重新发现。

发现和报告时必须记录每个来源的分类、适用范围和是否命中当前技术栈；基础规则优先加载，专项规则按任务匹配，模板仅作为交付制品格式参考。

## 设计与实现方向

设计与实现时遵守[通用设计与实现方向](../通用设计与实现方向.md)。

## 工具入口

使用 bundled script [`scripts/standards_tool.py`](scripts/standards_tool.py)：

```text
python .codex/skills/development-standards/scripts/standards_tool.py discover --root <项目根目录> --stack <springboot|vue>
python .codex/skills/development-standards/scripts/standards_tool.py fingerprint --root <项目根目录> --stack <springboot|vue> --format json
python .codex/skills/development-standards/scripts/standards_tool.py check --root <项目根目录> --stack <springboot|vue> --changed-from-git --full
python .codex/skills/development-standards/scripts/standards_tool.py check --root <项目根目录> --stack <springboot|vue> --changed-from-git --fix
```

需要纳入当前任务用户规则时，所有命令都可以追加 `--user-rules-file <UTF-8 文件>`；编排模式使用当前运行的用户规则制品。检查阶段可追加 `--baseline-fingerprint <standards-fingerprint.json>` 比较 inspect 阶段的基线指纹。

脚本只使用 Python 标准库，不访问网络、不安装依赖、不修改系统环境变量。项目命令在当前子进程中使用目标项目 `.dev-env.yaml` 的环境配置。

## 工作流程

### 1. 发现规范来源 (`inspect`)

- 明确当前项目根目录和技术栈，不从技能仓库路径猜测目标项目。
- 读取项目根目录的 `AGENTS.md`、`.dev-env.yaml` 和存在的 `docs/开发规范/README.md`，再按 `基础/`、匹配的 `专项/`、必要的 `模板/` 读取来源。
- 发现 `.editorconfig`、Maven 插件、`package.json` scripts、ESLint、Prettier、TypeScript、CI 和测试配置。
- 运行 `discover`，计算规范指纹，将规则来源、可用工具、命令、缺失项和警告写入注册的 `standards-context` Artifact，并将机器可读指纹写入 `standards-fingerprint` Artifact。

### 2. 检查变更和全量质量 (`check`)

- 读取 staged、unstaged 和未跟踪文件；必要时使用阶段输入中的变更范围。
- 先执行 UTF-8、`git diff --check` 等通用只读检查，再执行变更范围可支持的项目工具。
- 使用 `--full` 时，执行项目已经存在的全量 Lint、类型、测试、构建、Maven `verify` 或质量插件检查。
- 使用 `--baseline-fingerprint` 重新计算当前指纹；指纹变化时重新发现最新规范，并在报告中列出新增、删除和修改的来源。
- 默认只读。只有用户明确要求纠正并传入 `--fix` 时，才执行已知且可限定到变更文件的修复器；当前支持 Vue 的 Prettier 和 ESLint。
- `--fix` 必须有明确变更文件；不执行任意 `package.json` 修复脚本、项目级 Spotless、依赖安装、迁移、部署或未知 shell 字符串。
- 将 `standards_tool.py check` 的输出写入 `standards-report` Artifact。

## 证据和门禁

- 用户要求、项目 `AGENTS.md`、`docs/开发规范`、公共契约和已配置工具是权威来源。
- 既有代码样例只能提供低置信度建议；Agent 常识和个人风格不能形成违规结论。
- 已配置工具执行失败、明确的安全/契约/正确性问题或必要验证缺失为阻断。
- 规范目录或可选工具不存在、只有样例风格差异或检查未配置为告警。
- 规范根目录存在平铺正文、分层重复或 README 导航失效时报告组织告警；若无法判断唯一权威来源则阻断，不能静默合并冲突规则。
- 工具无法启动、超时或环境缺失时，报告为环境阻塞，不得报告为通过。
- 规范指纹无法读取、基线损坏或规范来源无法按 UTF-8 读取时，报告为阻断，不得复用旧上下文。
- 每条发现包含来源、检查命令、退出码、文件位置或输出证据、影响和状态。

## 直接调用和编排边界

- 直接调用本 skill 时完成发现、变更范围检查和用户要求的全量检查，并如实报告未执行项。
- 由 `$orchestrator` 调用时，只执行 Workflow Registry 当前阶段声明的 `inspect` 或 `check`，读取和写入当前 run 的注册 Artifact；`standards-check` 同时读取 `standards-fingerprint` 和当前用户规则制品。
- 本 skill 默认只读；`--fix` 是显式写操作。项目质量命令可能产生未跟踪的构建缓存，但不得改写受版本控制的规范配置、锁文件或未授权文件。
- 所有报告使用 UTF-8；报告中不得写入密钥、令牌、生产数据或未经脱敏的命令输出。
