---
name: vue-performance-optimization
description: 基于基线、Web Vitals、浏览器 profiling、网络分析、构建产物或用户指标优化 Vue 3 + TypeScript + Vite 单页应用性能；用户描述首屏、交互延迟、渲染、包体、内存、请求、CPU 或性能回归时使用。
---

# Vue 3 性能优化

## 目标

先用可重复的工作负载和运行证据确认瓶颈，再实施可衡量、可回滚且不破坏正确性的优化。避免凭经验添加缓存、并发、深度响应式或复杂构建配置，也不把性能任务扩大为无关重构或升级。

## 工作流程

### 1. 明确目标和基线

- 明确目标指标、页面/交互、用户设备、网络、数据规模、浏览器、采样窗口和验收阈值；至少记录相关 Web Vitals、交互延迟、错误率和资源指标。
- 先检查 `git status`、模块结构、`package.json`、锁文件、Vite 配置、路由、组件、Store、API、静态资源、部署缓存和已有 benchmark。
- 执行 pnpm、构建、profiling 或脚本前读取 `AGENTS.md` 和 `.dev-env.yaml`，显式按 UTF-8 读取配置，使用 `frontend.package_manager` 的 `pnpm`；不对生产环境执行未经授权的压测或配置切换。
- 如果脚本联动后端构建，按 `.dev-env.yaml` 的 `development.java.home` 和 `development.maven.home` 为当前进程设置 `JAVA_HOME`、`MAVEN_HOME`；单独前端命令不猜测或替换这些路径。

### 2. 定位实际瓶颈

- 使用浏览器 Performance/Memory、网络面板、Vue Devtools、构建统计或仓库已有观测定位瓶颈；记录测量方法和原始结果。
- 检查初始化和路由加载、JS/CSS/图片包体、请求瀑布、缓存、长任务、重复渲染、昂贵 computed/watch、深层响应式、大列表和事件处理。
- 区分测量结果、根因假设和放大因素；没有基线时先建立观测，不直接提交猜测性优化。
- 同时检查优化对类型、错误处理、可访问性、权限、顺序、数据一致性和用户可见行为的影响。

### 3. 实施受控优化

- 一次聚焦一个主要瓶颈，优先采用已有基础设施和最小变更；保留必要的开关、回滚路径和配置默认行为。
- 按证据选择路由/组件懒加载、请求合并或取消、资源压缩与缓存、列表渲染、响应式边界、计算缓存或事件节流，不为形式上的优化引入新框架。
- 不以删除错误处理、降低可访问性、减少数据校验、关闭安全控制或牺牲正确性换取单一指标改善。
- 不擅自升级 Vue、Vite、TypeScript 或构建插件；涉及版本变化转入 `vue-upgrade-migration`。

### 4. 验证收益和回归

- 使用与基线相同的工作负载、数据规模、环境和采样方式记录优化前后指标，至少比较目标指标、错误率、包体、CPU/内存和网络资源。
- 运行受影响的单元、组件、路由/Store 集成和既有 E2E 测试；检查缓存失效、慢网、重复操作、卸载、错误和权限场景。
- 结果未达到目标或引入回归时，保留数据并回滚无收益变更，不用主观判断宣称优化成功。
- 检查 `git diff`、`git diff --check` 和构建产物，确认没有意外生成文件、依赖升级或配置泄露。

## 交付和边界

- 交付瓶颈证据、基线、变更、优化后结果、资源代价、测试命令、未执行项、发布开关和回滚方式。
- 不对生产执行压测、profiling 或配置切换，除非用户明确授权且具备安全窗口和回滚方案。
- 纯结构整理使用 `vue-refactoring`；真实缺陷使用 `vue-bug-fixing`；Vue 生态版本迁移使用 `vue-upgrade-migration`。
- 本 skill 默认面向 Vue 3 + TypeScript + Vite SPA，不覆盖 Nuxt、SSR、Nitro 和 Vue 2 专项优化。
- 所有新增或修改文本使用 UTF-8；不执行无关的破坏性命令。

## 开发规范

- 直接调用本 skill 时，先读取项目根目录 `docs/开发规范/README.md`（存在时）和项目已有质量工具；不凭个人偏好添加风格规则。
- 由 `$orchestrator` 调用时，规范检查由 `development-standards` 阶段统一执行，本 skill 只遵循其报告和本任务专属约束。

## 编排契约

- 由 `$orchestrator` 调用时，按 Workflow Registry 指定的阶段执行，不重复执行其他阶段；直接调用本 skill 时仍执行完整优化流程。
- 支持阶段：`baseline`、`bottleneck`、`optimize`、`compare`、`regression`。
- 读取当前 run 中注册的输入 Artifact，将基线、瓶颈、优化和对比证据写入注册的输出 Artifact；不得使用未声明的路径传递上下文。
- 没有可重复基线或验证收益时保留事实和阻塞，不用主观判断宣称优化成功。
