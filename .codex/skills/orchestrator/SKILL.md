---
name: orchestrator
description: 面向复杂或跨阶段的软件工程任务，依据 Registry 和 Workflow Registry 选择技术栈专用 skill，初始化隔离 Artifact，按阶段执行并校验制品门禁；当请求同时涉及调查、设计、实现、测试、验证或需要可追溯交接时使用。
---

# 工程任务编排

## 目标

将复杂任务拆成可追踪的阶段，选择合适的技术栈叶子 skill 和跨栈 support skill，使用隔离的 Artifact 传递上下文，并在每个阶段结束时保留可验证证据。现有叶子 skill 仍可直接调用；只有跨阶段、跨技能或需要交接记录的任务才使用本 skill。

## 设计与实现方向

设计与实现时遵守[通用设计与实现方向](../通用设计与实现方向.md)。

## 编排流程

### 1. 明确路由

- 将请求归类为 `bug-fixing`、`feature-development`、`code-review`、`performance-optimization`、`refactoring`、`test-development` 或 `upgrade-migration`。
- 将目标技术栈归类为 `springboot` 或 `vue`；无法从仓库和请求确定时先询问，不猜测。
- 读取 `.codex/registry/skills.yaml`、`.codex/registry/artifacts.yaml` 和 `.codex/registry/workflows.yaml`，不要凭记忆创建不存在的阶段或制品。
- 使用 `scripts/registry_tool.py resolve --workflow <id> --stack <id>` 解析确定的工作流；解析失败时先修复注册表或报告阻塞。

### 2. 初始化运行制品

- 使用 `artifact init` 为本次任务创建 `.codex/artifacts/<run-id>/`，写入 `manifest.yaml` 和 UTF-8 的 `request.md`。
- 不把密钥、访问令牌、生产数据或未经脱敏的敏感日志写入制品；必要时记录脱敏方法和证据来源。
- 运行 ID 必须是安全的单层目录名；不得把用户输入直接拼接为路径。

### 3. 执行阶段

- 按 Workflow Registry 的顺序执行阶段；每次只把该阶段声明的输入制品交给对应的叶子或 support skill。
- 叶子或 support skill 直接调用时执行自己的完整流程；由本 skill 编排时只执行 Registry 指定的阶段，并把结果写入声明的制品文件。
- 阶段交接至少传递：`run_id`、`workflow_id`、`stack`、`stage_id`、`skill_id`、输入制品路径、输出制品路径和验收条件。
- 代码审查阶段保持只读；修改阶段遵循用户授权、仓库规则和叶子 skill 的范围边界。
- 不重复抄录前一阶段的上下文；优先读取已有 Artifact，并在报告中引用路径。

### 4. 执行制品门禁

- 阶段开始前确认所有 `consumes` 制品已经存在且属于当前 run。
- 阶段成功后确认所有必需 `produces` 制品存在、路径位于当前 run 目录内、编码为 UTF-8，并更新 `manifest.yaml`。
- `on_failure: block` 的阶段失败时停止后续修改，标记 run 为 `blocked` 或 `failed`，保留原始错误和已完成制品。
- `on_failure: continue-with-warning` 只允许在 Registry 明确声明时继续，并在后续诊断和最终交接中显式记录证据缺口。
- 不自动重试会产生副作用的实现、迁移、部署、外部调用或数据操作；重试前先确认幂等性和当前制品状态。

### 5. 交付和导出

- 最终制品至少包含验证报告、未执行项、环境阻塞、残留风险、回滚方式和变更摘要。
- 使用 `artifact validate --run-dir <path>` 校验运行目录；失败时不得宣称任务已完成。
- 需要提交审计证据时使用 `artifact export --run-dir <path> --destination <path>` 导出选定制品；运行目录默认被 Git 忽略。
- 汇报实际执行的工作流、叶子 skill、阶段状态、制品路径、测试命令和通过/失败/未执行结果。

## 注册表和工具约定

- Registry 是编排元数据的权威来源；叶子和 support `SKILL.md` 的 frontmatter 只负责 Codex 触发，二者的名称和路径必须一致。
- `owner: leaf` 使用当前技术栈的 `skill_by_stack`；`owner: support` 必须使用阶段显式声明的跨栈 Skill，例如接口文档门禁使用 `api-documentation`，不能把 support Skill 当成技术栈主路由。
- 注册表使用受限 YAML：支持两格缩进的映射、列表、标量和注释；不使用 Tab、锚点、别名、标签或多文档语法。
- 使用 `scripts/registry_tool.py validate` 检查技能路径、阶段、制品引用、工作流输入输出和状态约束。
- 工具只使用 Python 标准库，不调用网络、不修改系统环境变量、不执行 Maven 或 pnpm 命令。

## 失败处理与边界

- 工作类型或技术栈不明确时询问用户，不通过宽泛关键词规则静默路由。
- Registry、Artifact manifest 或阶段输出损坏时暂停编排，保留错误和当前状态，不删除已有证据。
- 环境命令由叶子 skill 按项目 `AGENTS.md` 和 `.dev-env.yaml` 执行；本 skill 不替代技术栈专项规则。
- 不把 Artifact 当作业务真相；代码、测试结果、日志和外部系统状态仍需由实际证据确认。
- 所有新增或修改文本使用 UTF-8；不执行无关的破坏性命令。
