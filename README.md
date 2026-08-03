# codex-config

面向 Codex 的工程技能与任务编排配置仓库。项目提供 Spring Boot 和 Vue 3 两类技术栈的专用技能，并通过 Registry、Workflow Registry 和 Artifact 管理复杂任务的阶段路由与可追溯交接。

## 功能概览

- 14 个叶子技能：Spring Boot 7 个，Vue 7 个。
- 7 类标准工程工作流：缺陷修复、功能开发、代码审查、性能优化、安全重构、测试开发和升级迁移。
- 统一的任务编排器：根据工作类型和技术栈选择叶子技能，按注册顺序执行阶段。
- Artifact 生命周期管理：隔离请求、证据、变更和验证结果，并在阶段之间显式交接。
- Registry 校验和工作流解析工具：仅使用 Python 标准库，不访问网络或修改系统环境。

## 目录结构

```text
.
├── .codex/
│   ├── registry/                 # 技能、工作流和 Artifact 注册表
│   ├── skills/
│   │   ├── orchestrator/         # 多阶段任务编排器及工具测试
│   │   ├── springboot-*/         # Spring Boot 叶子技能
│   │   └── vue-*/                # Vue 3 叶子技能
│   └── artifacts/                # 运行时制品目录，仅保留 .gitignore
├── .dev-env.yaml                 # 项目开发环境约定
├── AGENTS.md                     # Agent 工作规则
└── LICENSE
```

`.codex/registry/` 是编排元数据的权威来源；运行时 Artifact 默认位于 `.codex/artifacts/<run-id>/`，其中可能包含敏感的请求、日志或验证信息，因此不会提交到 Git。

## 支持的技能

### Spring Boot

| 技能 | 用途 |
| --- | --- |
| `springboot-bug-fixing` | 诊断、复现、修复和验证缺陷 |
| `springboot-code-review` | 只读代码审查和风险评估 |
| `springboot-feature-development` | 端到端开发业务功能 |
| `springboot-performance-optimization` | 基于证据进行性能优化 |
| `springboot-refactoring` | 保持行为兼容的代码重构 |
| `springboot-test-development` | 设计和补充自动化测试 |
| `springboot-upgrade-migration` | JDK、Spring Boot 和依赖升级迁移 |

### Vue 3

| 技能 | 用途 |
| --- | --- |
| `vue-bug-fixing` | 诊断、复现、修复和验证前端缺陷 |
| `vue-code-review` | 只读代码审查和上线风险评估 |
| `vue-feature-development` | 端到端开发前端功能 |
| `vue-performance-optimization` | 基于指标和 profiling 进行性能优化 |
| `vue-refactoring` | 保持组件契约和行为兼容的重构 |
| `vue-test-development` | 设计和补充组件、状态及接口测试 |
| `vue-upgrade-migration` | Vue、Vite、TypeScript 及相关生态升级 |

## 工作流

所有工作流同时支持 `springboot` 和 `vue` 技术栈。工作流阶段由 `.codex/registry/workflows.yaml` 定义，叶子技能负责技术栈相关的阶段执行。

| 工作流 | 阶段示例 |
| --- | --- |
| `bug-fixing` | `intake` → `evidence` → `reproduce` → `diagnose` → `fix` → `regression-test` → `verify` |
| `feature-development` | `intake` → `contract` → `inspect` → `compatibility` → `design` → `implement` → `test` → `verify` |
| `code-review` | `intake` → `context` → `risk-review` → `findings` → `verify` → `report` |
| `performance-optimization` | `intake` → `baseline` → `bottleneck` → `optimize` → `compare` → `regression` |
| `refactoring` | `intake` → `invariants` → `baseline` → `refactor` → `equivalence` → `verify` |
| `test-development` | `intake` → `context` → `scenario-design` → `implement-tests` → `execute-analyze` |
| `upgrade-migration` | `intake` → `inventory` → `migration-plan` → `compatibility-change` → `verify` |

## 使用方式

### 直接调用叶子技能

适用于边界清晰的单阶段或单领域任务，例如：

```text
使用 $springboot-bug-fixing 修复这个 Spring Boot 缺陷。
使用 $vue-code-review 审查这组 Vue 3 变更。
```

### 使用任务编排器

当任务同时涉及调查、设计、实现、测试、验证或需要阶段交接时，使用 `$orchestrator`。编排器会：

1. 识别工作类型和技术栈。
2. 从 Registry 解析对应工作流和叶子技能。
3. 初始化隔离的 Artifact 运行目录。
4. 按阶段检查输入和输出制品，保留验证证据。
5. 在最终交接中报告已执行阶段、验证结果和未完成项。

### 使用 Registry 工具

从仓库根目录执行以下命令：

```bash
# 校验技能、工作流、Artifact 注册表及叶子技能路径
python .codex/skills/orchestrator/scripts/registry_tool.py validate

# 解析指定技术栈的工作流
python .codex/skills/orchestrator/scripts/registry_tool.py resolve --workflow bug-fixing --stack springboot

# 初始化一次 Artifact 运行
python .codex/skills/orchestrator/scripts/registry_tool.py artifact init --workflow bug-fixing --stack springboot --request-file ./request.md --run-id 20260803T000000Z-demo

# 校验运行目录
python .codex/skills/orchestrator/scripts/registry_tool.py artifact validate --run-dir ./.codex/artifacts/20260803T000000Z-demo

# 导出全部已生成制品；目标目录应不存在
python .codex/skills/orchestrator/scripts/registry_tool.py artifact export --run-dir ./.codex/artifacts/20260803T000000Z-demo --destination ./exported
```

工具支持通过重复传入 `--artifact <artifact-id>` 只导出指定制品。运行 ID 必须是安全的单层目录名，不能通过路径穿越写出 `.codex/artifacts/`。

## 验证

```bash
python .codex/skills/orchestrator/scripts/registry_tool.py validate
python -m unittest discover -s .codex/skills/orchestrator/tests -p "test_*.py"
```

当前仓库是 Codex 配置和技能仓库，不包含具体的 Spring Boot 或 Vue 应用源码。叶子技能执行目标项目的构建、测试或迁移命令时，应遵循目标项目自身的 `AGENTS.md` 和 `.dev-env.yaml` 约定。

## 贡献约定

- 新增或修改的文本文件使用 UTF-8 编码。
- 新增技能时同步提供 `SKILL.md` 和 `agents/openai.yaml`，并在 Registry 中登记。
- 修改工作流时同步更新技能阶段契约、Artifact 引用和对应测试。
- 提交前运行 Registry 校验和编排工具单元测试。

## 许可证

本项目遵循 [LICENSE](LICENSE) 中的许可证条款。
