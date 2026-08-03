---
name: vue-refactoring
description: 在不改变外部行为、组件契约、路由、状态语义、API 数据和运行兼容性的前提下重构现有 Vue 3 + TypeScript + Vite 单页应用；用户要求拆分组件、提取 composable、消除重复、调整目录或改善可维护性但不新增业务规则时使用。
---

# Vue 3 安全重构

## 目标

在可验证的行为基线之上改善组件职责、可读性、依赖方向和可维护性，同时保持用户可见行为、组件公共契约、路由、Store、API、样式和错误语义不变。将重构与新功能、缺陷修复、性能优化和版本升级分开处理。

## 工作流程

### 1. 明确不变量和范围

- 先检查 `git status`、相关 diff、模块结构、组件调用方、路由、Store、API、样式、测试和构建约定，保留用户已有修改。
- 列出必须保持不变的 props、emits、slots、暴露方法、DOM 语义、路由/查询参数、Store 状态与动作、API 请求响应、本地存储键、权限、焦点和错误展示。
- 执行测试、构建或脚本前读取 `AGENTS.md` 和 `.dev-env.yaml`，显式按 UTF-8 读取配置，按 `frontend.package_manager` 使用 `pnpm`，仅对当前进程生效。
- 如果脚本联动后端构建，按 `.dev-env.yaml` 的 `development.java.home` 和 `development.maven.home` 为当前进程设置 `JAVA_HOME`、`MAVEN_HOME`；单独前端命令不猜测或替换这些路径。
- 如果请求同时包含业务规则变化、Bug 修复、性能目标或依赖升级，先拆出范围；未获授权时不混入重构。

### 2. 建立行为基线

- 运行现有定向测试并检查页面、路由、表单、Store 和 API 关键流程；缺少基线时记录缺口和风险。
- 识别 Vue 敏感边界：响应式代理与解构、computed/watch 依赖、生命周期清理、`provide/inject`、模板 ref、异步请求、路由守卫和组件库封装。
- 对公共组件、composable、Store 或 API 类型移动/改名，先确认所有调用方、导出入口、别名和测试引用。

### 3. 分步实施重构

- 选择单一结构目标，按小步修改：提取展示组件、提取纯函数/composable、消除重复、整理目录或调整依赖方向。
- 保持 `<script setup lang="ts">`、类型化 props/emits、组件生命周期和响应式边界；不要通过复制状态或改变 watch 时机制造隐性行为变化。
- 保持事件名、插槽名、默认值、路由行为、Store API、API DTO、CSS 选择器和可访问性语义；确需兼容适配时保留旧入口并说明淘汰计划。
- 不使用全量格式化、无关改名、组件库替换、依赖升级或大范围重排掩盖实际重构。

### 4. 验证行为等价

- 运行单元、组件、路由/Store 集成和已有 E2E 测试，覆盖成功、边界、异常、权限、异步、卸载、键盘和响应式布局场景。
- 对 API、路由、本地存储或公共组件有影响的重构，检查生成类型、请求结果、序列化格式、调用方和回滚方式。
- 使用 `package.json` 中实际存在的 lint、typecheck、test 和 build 命令；检查 `git diff`、`git diff --check` 和变更规模。

## 交付和边界

- 交付重构目标、保持的不变量、结构变化、测试命令和结果、未覆盖风险及后续拆分建议。
- 如果行为基线失败，先判断是既有失败还是重构回归；不得静默删除或放宽失败测试。
- 如果发现真实缺陷，记录复现证据并按用户授权转入 `vue-bug-fixing`；业务规则变化转入 `vue-feature-development`。
- 本 skill 默认面向 Vue 3 + TypeScript + Vite SPA，不覆盖 Nuxt、SSR、Nitro 和 Vue 2 迁移。
- 所有新增或修改文本使用 UTF-8；不执行无关的破坏性命令。

## 编排契约

- 由 `$orchestrator` 调用时，按 Workflow Registry 指定的阶段执行，不重复执行其他阶段；直接调用本 skill 时仍执行完整重构流程。
- 支持阶段：`invariants`、`baseline`、`refactor`、`equivalence`、`verify`。
- 读取当前 run 中注册的输入 Artifact，将不变量、基线、变更和等价验证结果写入注册的输出 Artifact；不得使用未声明的路径传递上下文。
- 修改前保护行为基线；发现行为变化或基线失败时保留证据并暂停，不静默放宽测试。
