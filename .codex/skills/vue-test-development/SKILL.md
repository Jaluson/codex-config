---
name: vue-test-development
description: 为现有 Vue 3 + TypeScript + Vite 单页应用设计、补充或修复自动化测试；用户要求提高覆盖率、增加组件或 composable 测试、验证路由/状态/API 分支、补充回归测试、修复不稳定测试或建立前端测试策略时使用，且测试本身是主要目标。
---

# Vue 3 测试开发

## 目标

以验收场景和风险为依据补齐可靠、可读、可重复的自动化测试，优先验证真实用户行为和失败路径。默认只修改测试及测试资源；需要修改生产代码时必须说明可测试性原因和影响。

## 工作流程

### 1. 了解测试和运行环境

- 先检查 `git status`、前端模块、`package.json`、锁文件、测试脚本、Vitest/Jest、Vue Test Utils、Testing Library、Playwright/Cypress、Mock 工具、CI 和测试资源。
- 读取被测 SFC、composable、Store、路由、API 客户端、配置、权限和组件库，列出成功、边界、非法输入、异常、交互和回归场景。
- 执行 pnpm、测试、构建或脚本前读取 `AGENTS.md` 和 `.dev-env.yaml`，显式按 UTF-8 读取，使用 `frontend.package_manager` 的 `pnpm`，检查实际 Node/pnpm 版本并不修改系统环境。
- 如果测试或构建脚本联动后端，按 `.dev-env.yaml` 的 `development.java.home` 和 `development.maven.home` 为当前进程设置 `JAVA_HOME`、`MAVEN_HOME`；单独前端命令不猜测或替换这些路径。
- 遵循仓库已有测试栈；无既有约定时以 Vitest + Vue Test Utils 作为默认建议，不因测试任务自动替换工具或升级依赖。

### 2. 选择最小合适的测试层级

- 纯格式化、校验、状态转换和 composable 逻辑使用快速单元测试。
- 组件 props、emits、slots、用户事件、条件渲染、加载/错误/空状态和可访问性使用组件测试。
- 路由、Store、API mock、权限和跨组件交互使用范围明确的集成测试。
- 只有项目已有 Playwright/Cypress 时才补充 E2E；优先覆盖关键用户流程，不用 E2E 替代所有单元测试。
- 不为覆盖率数字测试实现细节、私有变量或框架本身；测试应从用户行为或公开契约观察结果。

### 3. 编写稳定测试

- 每个测试表达一个可读的行为，使用仓库已有 fixture、工厂、mock、渲染工具和断言约定。
- 覆盖成功、边界、非法输入、异常转换、权限拒绝、重复提交、异步竞态、路由变化、Store 重置、卸载清理和相关回归。
- 控制时间、随机数、网络、浏览器 API、线程和动画；优先使用 fake timers、确定性数据、可控 promise 和等待条件。
- 不使用无界 `sleep`、真实生产服务、不稳定的测试顺序、脆弱的快照或吞掉异常；清理 mock、DOM、Store 和全局状态。
- 测试类型化 props/emits 时验证公开契约和运行时结果；不要为了通过类型检查把生产代码改成 `any`。

### 4. 执行和分析

- 先运行受影响的定向测试，再按实际 `package.json` 脚本运行相关 test、typecheck、lint 或 production build；记录完整命令和结果。
- 对失败测试检查堆栈、DOM、网络 mock、时区、语言、端口、并行执行、资源清理和重复运行稳定性；不得简单增加等待时间掩盖问题。
- 需要跨浏览器或 Node 版本验证时，按 CI 支持矩阵执行；不能把单一本机通过报告为全部兼容。
- 检查 `git diff`、`git diff --check`，确认没有意外修改生产代码、锁文件或生成文件。

## 交付和边界

- 交付新增或修复的场景、测试层级、执行命令、结果、未执行项和环境阻塞。
- 新业务功能的完整实现由 `vue-feature-development` 负责；真实生产缺陷记录复现证据并转入 `vue-bug-fixing`，除非用户明确授权修改生产代码。
- 测试暴露的性能或版本问题分别转入 `vue-performance-optimization` 或 `vue-upgrade-migration`，不在测试任务中扩大范围。
- 本 skill 默认面向 Vue 3 + TypeScript + Vite SPA，不覆盖 Nuxt、SSR、Nitro 和 Vue 2 专项测试。
- 所有新增或修改文本使用 UTF-8；不执行无关的破坏性命令。
