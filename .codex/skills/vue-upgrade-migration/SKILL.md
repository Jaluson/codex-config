---
name: vue-upgrade-migration
description: 规划、实施和验证 Vue 3 + TypeScript + Vite 单页应用的 Vue、Vite、TypeScript、Vue Router、Pinia、测试工具、构建插件或配置升级迁移；用户要求版本升级、兼容性评估、废弃 API 迁移、构建失败排查或升级回归验证时使用。
---

# Vue 3 升级迁移

## 目标

在明确目标版本、兼容范围、验证矩阵和回滚策略的基础上完成可控升级。优先读取仓库和官方资料，不静默升级无关依赖，不用本机 Node/pnpm 版本替代项目支持范围。

## 工作流程

### 1. 盘点现状和目标

- 先检查 `git status`、相关 diff、`package.json`、锁文件、workspace、Node/pnpm 约束、Vite 配置、TypeScript 配置、插件、测试、CI、容器和部署配置。
- 读取根目录 `AGENTS.md` 和 `.dev-env.yaml`；执行 pnpm、构建、测试或迁移脚本前显式按 UTF-8 读取配置，使用 `frontend.package_manager` 的 `pnpm`，不修改系统环境变量。
- 如果迁移脚本联动后端构建，按 `.dev-env.yaml` 的 `development.java.home` 和 `development.maven.home` 为当前进程设置 `JAVA_HOME`、`MAVEN_HOME`；单独前端命令不猜测或替换这些路径。
- 明确当前版本、目标版本、最低支持 Node、浏览器范围、是否允许 API/配置不兼容，以及路由、Store、API、构建产物和发布窗口要求；缺少目标时不得自行猜测。
- 输出直接依赖、传递依赖、插件、配置键、类型、反射式注册、序列化和公共组件契约的风险清单。

### 2. 依据可靠资料设计迁移

- 对 Vue、Vite、TypeScript、Vue Router、Pinia、Vitest 或关键插件的行为不确定处，使用 Context7（如果可用）或对应官方迁移指南确认，并优先使用与目标版本匹配的资料。
- 检查发行说明、迁移指南、废弃 API、默认配置变化、构建产物变化、浏览器支持、测试环境和安全变化。
- 将升级拆成可验证的小步，明确每一步的安装/锁文件、编译、测试、构建、发布和回滚条件；不把无关重构混入迁移。

### 3. 实施兼容性变更

- 按项目现有包管理和版本管理方式修改 `package.json`、lockfile、Vite/TypeScript/测试配置和必要的源代码；保留 pnpm workspace 结构。
- 处理 Vue 3 SFC、`script setup`、类型化 props/emits、模板类型、路由、Store、插件、组件库、CSS 处理和 API 客户端的迁移差异。
- 对公共 props、emits、slots、路由 URL、Store 状态/动作、API DTO、本地存储格式和生成产物变化，明确兼容窗口、双读/回填、发布顺序和回滚方式。
- 不擅自引入 Nuxt、SSR、Nitro、Vue 2 迁移路径、preview/experimental 特性或无关依赖；不为消除警告而关闭类型检查、测试或安全控制。

### 4. 分层验证和交付

- 先运行安装后的类型检查、编译和受影响的定向测试，再运行相关 test、lint、production build 和已有 E2E；不得只运行跳过测试的构建。
- 验证启动、路由、组件渲染、表单、权限、Store、API mock、错误处理、序列化、静态资源、source map 和构建产物。
- 按 CI 或部署支持矩阵验证目标 Node、浏览器和 pnpm 版本；检查警告、依赖冲突、重复包、配置绑定、锁文件和包体变化。
- 检查迁移顺序、配置默认值、敏感数据、观测指标、灰度方式和回滚可行性；使用 `git diff` 和 `git diff --check` 确认变更范围。

## 失败处理与边界

- 依赖下载、Node、pnpm、浏览器、CI、外部服务或构建环境不可用时，明确阻塞项和已完成的静态检查，不把局部通过当作迁移完成。
- 升级失败时保留安装、编译和测试证据，按预先定义的回滚点恢复，不执行无依据的连续版本跳跃。
- 纯业务缺陷使用 `vue-bug-fixing`；行为保持重构使用 `vue-refactoring`；不以升级为理由顺手优化或重写无关代码。
- 本 skill 默认面向 Vue 3 + TypeScript + Vite SPA，不覆盖 Nuxt、SSR、Nitro 和 Vue 2 专项迁移。
- 所有新增或修改文本使用 UTF-8；不执行无关的破坏性命令。

## 编排契约

- 由 `$orchestrator` 调用时，按 Workflow Registry 指定的阶段执行，不重复执行其他阶段；直接调用本 skill 时仍执行完整迁移流程。
- 支持阶段：`inventory`、`migration-plan`、`compatibility-change`、`verify`。
- 读取当前 run 中注册的输入 Artifact，将现状盘点、迁移计划、兼容性变更和验证结果写入注册的输出 Artifact；不得使用未声明的路径传递上下文。
- 每个迁移阶段保留回滚点和兼容性证据；升级失败时停止无依据的连续跳跃并报告阻塞。
