---
name: springboot-feature-development
description: 使用现有 Java + Maven Spring Boot 仓库端到端开发新增或按需求变更的业务功能；适用于 API、业务流程、持久化、配置、权限、缓存、消息、外部服务、数据库迁移及相关测试，要求按目标 JDK 8–25 和 Spring Boot 版本选择兼容的新特性并完成验证。纯缺陷修复、代码审查、行为保持重构、测试补充、性能优化和版本升级使用对应专项 skill。
---

# Spring Boot 功能开发

## 目标

以仓库事实和可验证的验收标准为依据，完成 Spring Boot 功能从需求拆解、设计、实现到测试和构建验证的完整闭环。优先复用现有架构、依赖、命名、异常格式、配置方式和测试工具；只有在确有必要时才引入新的约定或依赖。

## 适用边界

- 以新增业务能力、接口、领域流程或按需求变更业务行为为主要目标时使用本 skill。
- 纯缺陷修复使用 springboot-bug-fixing；只要求审查使用 springboot-code-review；只要求行为保持重构使用 springboot-refactoring。
- 只补充或修复测试使用 springboot-test-development；以性能证据为目标使用 springboot-performance-optimization；JDK、Spring Boot 或依赖版本迁移使用 springboot-upgrade-migration。
- 新业务功能同时包含配套测试时，本 skill 负责完整交付；只有测试本身是目标时才使用测试专项 skill。

## 工作流程

### 1. 明确功能契约

- 将用户请求整理为目标、范围、输入、输出、业务规则、错误语义、权限要求和验收场景。
- 区分必须实现、可选增强和明确不在范围内的内容。
- 优先从仓库和现有接口中推导细节；只有缺少且会影响实现的决策时才询问用户。
- 在修改代码前列出涉及的模块、接口、数据、配置、迁移、测试和兼容性影响。

### 2. 保护并理解仓库

- 先查看 `git status` 和相关 diff，保留用户已有的未提交修改，不覆盖或回滚无关工作。
- 定位 Maven 根项目和实际模块，检查 `pom.xml`、Maven Wrapper、源码/测试目录、包结构和相似功能。
- 检查 Spring Boot parent 或 BOM、Java 编译配置、主要依赖、profile、CI、容器和部署配置。
- 查找现有的 API 文档、异常处理、权限配置、数据库迁移、测试容器、日志/指标和外部客户端封装。
- 记录现有约定后再设计变更；不要因为个人偏好替换成熟的项目模式。

### 3. 判定 JDK 与 Spring Boot 兼容范围

- 综合读取 `maven.compiler.release`、`maven.compiler.source/target`、`java.version`、Maven Toolchains、CI JDK 矩阵和构建镜像。
- 将 `--release` 视为编译 API 的强约束；存在多个支持版本时，以最低目标 JDK 作为公共代码的兼容上限。不要用本机 JDK 版本代替项目目标版本。
- 检查 Spring Boot 版本及其依赖对目标 JDK 的支持；JDK、Spring Boot 和 CI 配置冲突时，先报告冲突，不要静默升级。
- API 或框架行为不确定时，使用 Context7（如果可用）或 Spring、OpenJDK 官方文档确认，并优先选择与项目版本匹配的资料。

### 4. 充分使用目标 JDK 的稳定特性

将新特性优先应用于新增代码和直接相关的修改代码；不为使用新语法而重写无关模块，也不降低代码可读性或破坏 Spring 代理、序列化和框架约定。

| 目标 JDK | 优先考虑的稳定特性 | 约束 |
| --- | --- | --- |
| JDK 8 | `java.time`、lambda、Stream、try-with-resources、接口默认方法 | 不使用 JDK 9+ 的集合工厂、`var`、records 或更新 API。谨慎使用 `Optional`，避免作为字段或参数滥用。 |
| JDK 11 | `var` 局部变量、`String.isBlank/strip/lines/repeat`、`Files.readString/writeString`、标准 `HttpClient` | 仍须遵守项目已有的客户端、日志和异常封装，不因 JDK 自带 API 绕过基础设施层。 |
| JDK 17 | records、sealed classes、`instanceof` 模式匹配、switch expressions、text blocks、`Stream.toList()` | 检查 Jackson、Spring 代理、JPA 和序列化对 records/不可变类型的支持。 |
| JDK 21 | record patterns、switch 模式匹配、virtual threads、sequenced collections | 只有在 Spring Boot 版本、线程模型和阻塞 I/O 场景适配时才使用 virtual threads。 |
| JDK 25 | 已正式发布且适用于生产代码的语言/API 特性，如 scoped values、flexible constructor bodies、module import declarations、KDF API | 不默认启用 preview；compact source files 等特性只在确实适合的独立入口或工具场景使用，不强行用于常规 Spring Bean。 |

- 对 JDK 8–25 中未列出的版本，依据项目实际 `--release` 和官方文档选择已正式发布的特性。
- 不引入 preview 或 experimental 特性，不擅自增加 `--enable-preview`，除非项目已经显式配置并且测试、运行和部署链路都支持。
- 选择新特性时同时检查 Spring Boot、Jackson、JPA、代理、反射、序列化和运行时配置的兼容性。

### 5. 设计变更链路

将功能表达为清晰的数据流，并为每一段确定责任边界：

`请求/事件 -> 边界校验 -> 应用服务 -> 领域规则 -> Repository/客户端 -> 持久化或外部系统 -> 响应/事件`

- 设计请求/响应 DTO，避免直接暴露 JPA Entity 或内部领域对象。
- 明确校验位置、错误码/HTTP 状态、事务边界、权限判断、幂等策略、并发行为和一致性要求。
- 按仓库现有方式选择 MVC、WebFlux、同步调用、异步消息、JPA、JDBC、Redis 或其他基础设施。
- 对跨模块或已有接口变更，检查向后兼容、数据回填、灰度发布和回滚影响。
- 简单功能保持简单；不要为了形式上的分层引入空壳接口、重复映射或无收益的抽象。

### 6. 实现功能

- 遵循现有包结构、命名、构造注入、事务注解、异常处理和日志规范。
- REST/Web 功能补齐 DTO、输入校验、成功响应、错误响应和 API 文档；保持既有状态码与错误格式。
- 持久化功能同步检查实体、Repository、索引、约束、事务、并发更新和数据库迁移；使用项目既有的 Flyway、Liquibase 或其他迁移方案。
- 配置功能使用类型安全的 `@ConfigurationProperties` 或项目既有方式，补齐默认值、校验、profile 配置和示例；不得写入密钥或敏感数据。
- 外部服务调用复用现有客户端和认证方式，明确超时、重试、错误转换、限流和降级边界。
- 消息或异步功能明确消息契约、幂等、重试、重复消费、死信和可观测性。
- 权限功能建立资源与操作的授权矩阵，在服务层或项目规定的边界执行授权，而不是只依赖前端或 Controller 隐藏入口。
- 只修改实现所需文件；不擅自升级依赖、改变公共配置或重排无关代码。

### 7. 编写分层测试

- 为领域规则和纯业务分支编写快速单元测试，覆盖成功、边界、非法输入和失败路径。
- Web MVC/WebFlux 项目优先使用现有的 `@WebMvcTest`、`@WebFluxTest` 或等价 slice 测试验证路由、校验、状态码、响应和异常映射。
- 数据访问使用项目已有的 `@DataJpaTest`、`@JdbcTest`、Testcontainers 或集成测试方式验证查询、约束、事务和迁移。
- 需要完整自动配置、权限链路、消息链路或外部适配时，补充范围明确的 `@SpringBootTest` 或项目既有集成测试，不用全量上下文测试替代所有单元测试。
- 配置绑定使用轻量的上下文或配置测试验证默认值、类型转换和非法配置；外部调用验证超时、错误和重试行为。
- 若项目有多 JDK CI 矩阵，在所有受支持的目标 JDK 上执行相关测试；不得把只在本机 JDK 通过的结果报告为完整验证。

### 8. 验证并交付

- 优先使用 Maven Wrapper：Windows 使用 `mvnw.cmd`，其他环境使用 `./mvnw`；没有 Wrapper 时再使用 `mvn`。
- 先运行受影响模块的定向测试，再按仓库约定运行相关模块的 `test`、`verify` 或完整构建。不能只运行跳过测试的构建作为验收依据。
- 使用项目已有的格式化、静态分析、架构检查和生成校验命令；不要为验证目的改写受版本控制的文件。
- 检查 `git diff`、`git diff --check`、变更文件、迁移顺序、配置键和测试结果，确认没有意外修改。
- 将验证结果分为已通过、未执行、失败和环境阻塞；网络、依赖下载、JDK 缺失或外部服务不可用时，明确记录原因和替代检查。
- 最终汇报变更摘要、接口/数据/配置影响、测试与构建命令及结果、迁移和发布注意事项、未决风险和后续建议。

## 必须遵守的边界

- 不覆盖用户已有修改，不执行无关的破坏性命令。
- 不猜测仓库规范、API 契约、数据库结构或依赖版本；无法从代码和文档确认时说明假设。
- 不把“代码已写完”当作“功能已验证”；测试未运行或失败必须如实报告。
- 不为了追求新 JDK 语法而突破项目的最低兼容版本、Spring Boot 版本或运行时约束。
