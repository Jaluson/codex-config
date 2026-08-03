---
name: springboot-upgrade-migration
description: 规划、实施和验证 Java + Maven Spring Boot 项目的 JDK、Spring Boot、依赖、插件或配置升级迁移；用户要求版本升级、兼容性评估、废弃 API 迁移、javax 到 jakarta 迁移或升级失败排查时使用。
---

# Spring Boot 升级迁移

## 目标

在明确目标版本、兼容范围、验证矩阵和回滚策略的基础上完成可控升级。优先读取仓库和官方资料，不静默升级无关依赖，不用本机 JDK 版本替代项目支持范围。

## 工作流程

### 1. 盘点现状和目标

- 先检查 git status、相关 diff、Maven parent 或 BOM、插件、Wrapper、Java release、Toolchains、CI、容器镜像、profile 和部署配置。
- 读取根目录 .dev-env.yaml，检查 Java 和 Maven 路径及实际版本；仅对当前进程设置 JAVA_HOME 和 MAVEN_HOME。
- 明确当前版本、目标版本、最低支持 JDK、运行环境、是否允许 API 或配置不兼容，以及数据库和消息迁移要求；缺失目标时不得自行猜测。
- 输出依赖图和兼容性矩阵，标记直接依赖、传递依赖、插件、反射、序列化、JPA、代理和外部客户端风险。

### 2. 依据可靠资料设计迁移

- 对 JDK、Spring Boot、Spring Framework 和关键依赖的行为不确定处，使用 Context7 或对应官方文档确认，并优先使用与目标版本匹配的资料。
- 检查发行说明、迁移指南、废弃 API、默认配置变化、自动配置变化、安全变化、日志和指标变化。
- 将升级拆成可验证的小步，明确每一步的编译、测试、数据、部署和回滚条件；不将无关重构混入迁移。

### 3. 实施兼容性变更

- 按项目已有 parent、BOM、Wrapper、插件和版本管理方式修改依赖与构建配置，避免手工覆盖受 BOM 管理的版本。
- 处理 Java API、Spring API、配置键、包名、序列化、验证、Security、Web、JPA、消息和测试框架的迁移差异。
- 对 javax 到 jakarta、数据库 schema、消息契约、缓存格式或公共 API 变化，明确双读、双写、兼容窗口、回填和回滚方案。
- 不启用 preview 或 experimental 特性，不擅自改变最低 JDK、依赖策略、公共配置或部署方式。

### 4. 分层验证和交付

- 先运行编译和受影响模块的定向测试，再运行 test、verify 或完整构建；覆盖启动、Web、权限、事务、持久化、消息、外部客户端和迁移测试。
- 按 CI 或部署支持矩阵验证所有目标 JDK；检查警告、依赖冲突、重复类、配置绑定、生成文档和容器启动。
- 检查数据库迁移顺序、回滚可行性、配置默认值、密钥引用、观测指标和发布顺序。
- 使用 Maven Wrapper；Windows 优先使用 mvnw.cmd。检查 git diff、git diff --check 和最终依赖变更。

## 失败处理与边界

- 依赖下载、JDK、CI、容器、数据库或外部服务不可用时，明确阻塞项和已完成的静态检查，不把局部通过当作迁移完成。
- 升级失败时保留编译或测试证据，按预先定义的回滚点恢复，不执行无依据的连续版本跳跃。
- 纯业务缺陷使用 springboot-bug-fixing；不以升级为理由顺手重构或优化无关代码。
- 所有新增或修改文本使用 UTF-8；不执行无关的破坏性命令。

## 接口文档门禁

- 若升级改变对外 HTTP/Web API 的路径、方法、参数、响应、状态码、错误、鉴权或兼容行为，调用 `$api-documentation` 更新 `docs/接口文档/${模块}-${功能}.md`；只保留一份当前文档，历史变化写入修订记录。
- 若升级未改变公共接口，在交付结果或当前 run Artifact 中明确记录“无需更新接口文档”。

## 开发规范

- 直接调用本 skill 时，先读取项目根目录 `docs/开发规范/README.md`（存在时）和项目已有质量工具；不凭个人偏好添加风格规则。
- 由 `$orchestrator` 调用时，规范检查由 `development-standards` 阶段统一执行，本 skill 只遵循其报告和本任务专属约束。

## 编排契约

- 由 `$orchestrator` 调用时，按 Workflow Registry 指定的阶段执行，不重复执行其他阶段；直接调用本 skill 时仍执行完整迁移流程。
- 支持阶段：`inventory`、`migration-plan`、`compatibility-change`、`verify`。
- 读取当前 run 中注册的输入 Artifact，将现状盘点、迁移计划、兼容性变更和验证结果写入注册的输出 Artifact；不得使用未声明的路径传递上下文。
- 每个迁移阶段保留回滚点和兼容性证据；升级失败时停止无依据的连续跳跃并报告阻塞。
