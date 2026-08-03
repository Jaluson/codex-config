# 开发规范

本目录维护面向开发者与 Codex Agent 的通用全栈开发规范，重点覆盖 Spring Boot 后端、Vue 3 + TypeScript + Vite 前端、HTTP/Web API、数据契约、测试质量、安全可靠性、代码审查和交付协作。

规范强调可验证的工程行为，不凭个人偏好规定空格、换行、类名或日志模板。具体格式和静态质量优先交给目标项目已有的格式化器、Lint、类型检查、测试、构建和架构检查工具。

## 快速导航

| 文档 | 用途 |
| --- | --- |
| [工程治理与协作流程](./01-工程治理与协作流程.md) | 从需求接收到交付的阶段、证据和责任边界 |
| [通用编码与文档规范](./02-通用编码与文档规范.md) | 文本、代码、配置、文档、路径和依赖的通用约束 |
| [Spring Boot 后端开发规范](./03-Spring-Boot后端开发规范.md) | 后端分层、契约、校验、事务、数据、异步和兼容性 |
| [Vue 3 前端开发规范](./04-Vue3前端开发规范.md) | 组件、状态、路由、API、交互、安全、可访问性和性能 |
| [接口与数据契约规范](./05-接口与数据契约规范.md) | 对外接口、数据演进、错误语义、兼容性和文档门禁 |
| [测试与质量门禁规范](./06-测试与质量门禁规范.md) | 测试设计、检查命令、规范指纹、证据和失败处理 |
| [安全可靠性与发布规范](./07-安全可靠性与发布规范.md) | 密钥、权限、敏感数据、外部依赖、迁移、观测和回滚 |
| [代码审查与交付规范](./08-代码审查与交付规范.md) | Review、提交、变更说明、交接和交付结论 |
| [变更设计与验收清单](./模板/变更设计与验收清单.md) | 新功能、修复、重构和升级的设计记录模板 |
| [代码审查报告](./模板/代码审查报告.md) | 只读审查的证据和问题记录模板 |
| [验证与交付报告](./模板/验证与交付报告.md) | 测试、质量门禁、阻塞项和残留风险模板 |

## 适用范围

- **通用规则**适用于所有代码、配置、测试、文档和 Agent 交接制品。
- **后端规则**适用于 Java + Spring Boot + Maven 项目；目标 JDK 支持范围以目标项目配置为准，当前技能覆盖 JDK 8–25。
- **前端规则**适用于 Vue 3 + TypeScript + Vite 单页应用；包管理器和脚本以目标项目配置为准，当前仓库默认约定使用 pnpm。
- **仓库规则**适用于本 `codex-config` 仓库自身的 Registry、Skill、Artifact 和 Python 工具。
- 本仓库不是业务应用，当前没有 `pom.xml`、`package.json` 或 CI。业务项目命令不能因为本文档出现就被视为已配置或已执行。

## 规则等级和结论

规范正文使用以下词语：

- **MUST / 必须**：不满足即不可交付，除非有明确的风险接受或用户授权记录。
- **SHOULD / 应当**：默认遵守；偏离时记录原因、影响和替代证据。
- **MAY / 可以**：允许采用，不形成单独违规结论。

检查结论使用以下级别：

- **阻断**：已配置工具失败；安全、契约、正确性、数据一致性或必要验证存在明确问题；环境导致必要检查无法完成。
- **告警**：可选工具或目录缺失；只有低置信度样例支持的风格差异；非关键 `SHOULD` 偏离。
- **未知**：证据不足，不能直接判定为违规或通过。
- **通过**：检查已执行并获得成功证据，不代表未执行的检查也通过。

每项检查至少记录来源、命令、退出码或工具状态、文件/阶段位置、证据、影响和结论。未执行、失败和环境阻塞不得写成通过。

## 规则来源优先级

发生冲突时按以下顺序处理：

1. 用户明确要求、安全要求和已经确认的公共契约。
2. 项目根目录 `AGENTS.md`、`.dev-env.yaml`、构建配置、CI 配置和已提交的质量工具配置。
3. 项目接口文档、数据库/消息契约和本目录规范。
4. 框架默认习惯和 Agent 通用知识。

本仓库现有权威来源包括：

- [AGENTS.md](../../AGENTS.md)：Agent、编码、语言和环境规则。
- [.dev-env.yaml](../../.dev-env.yaml)：当前仓库的 JDK、Maven 和前端包管理器约定。
- [.codex/registry](../../.codex/registry)：Skill、Workflow 和 Artifact 的结构契约。
- [.codex/skills](../../.codex/skills)：各类工作流及跨栈门禁的行为契约。
- 目标项目自身的构建、测试、Lint、类型和 CI 配置：具体命令的首要来源。

既有代码样例只能提供低置信度参考，不能单独产生阻断项。若规则没有可靠来源或可验证证据，应报告未知或告警，并提出补充工具/文档的建议。

## 标准工作流

常规变更按“需求与范围 → 证据与现状 → 契约与设计 → 实现 → 分层测试 → 规范检查 → 代码审查 → 验证与交付”推进。复杂任务由 `$orchestrator` 按 Registry 选择工作流和 Skill，并用 Artifact 交接；简单任务可直接调用对应 Skill，但仍遵守本目录和目标项目规则。

涉及对外 HTTP/Web API 的新增、修改、删除、鉴权、错误、状态码、幂等性或兼容行为时，必须同步检查 [接口文档 Skill](../../.codex/skills/api-documentation/SKILL.md) 的唯一文档和修订记录要求。

涉及规范来源、质量工具、指纹或检查结论时，使用 [development-standards Skill](../../.codex/skills/development-standards/SKILL.md)。自动纠正只有在用户明确授权时才可执行，并且必须限定到已知工具和变更文件。

## 本仓库当前可执行检查

在运行项目命令前读取 `.dev-env.yaml`，并只在当前进程设置所需环境变量。本仓库当前可执行的主要检查为：

```text
python -X utf8 .codex/skills/orchestrator/scripts/registry_tool.py validate
python -X utf8 -m unittest discover -s .codex/skills/orchestrator/tests -p "test_*.py"
python -X utf8 -m unittest discover -s .codex/skills/development-standards/tests -p "test_*.py"
python -X utf8 .codex/skills/development-standards/scripts/standards_tool.py check --root . --stack springboot --changed-from-git --full
python -X utf8 .codex/skills/development-standards/scripts/standards_tool.py check --root . --stack vue --changed-from-git --full
```

其中 Spring Boot/Vue 检查器在本仓库没有发现 `pom.xml`/`package.json` 时会产生告警；这表示没有目标项目质量命令可执行，不表示业务项目质量已通过。

## 维护规则

- 新增或修改规范时，必须同步更新本 README 的导航、适用范围或修订记录。
- 任何规范变更都使用 UTF-8；不得对无关既有文件批量转换编码。
- 规范变更应说明动机、影响范围、是否改变门禁、迁移方式和验证结果。
- 当 `AGENTS.md`、`.dev-env.yaml`、Registry、Skill、构建配置或 CI 改变时，重新发现规范来源并更新相关专题。
- `development-standards` 使用规范来源 SHA-256 指纹识别变化；不能复用已经过期的 `standards-context` 或指纹。

## 修订记录

| 修订 | 日期 | 内容 |
| --- | --- | --- |
| R1 | 2026-08-03 | 建立 Spring Boot + Vue 3 全栈开发规范、质量门禁和交付模板体系 |
