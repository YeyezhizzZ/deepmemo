# DeepMemo 工程宪法 (Constitution)

* **Status**: Current / Human Reviewed (Ratified: 2026-06-04)

这是凌驾于所有具体业务逻辑之上的核心设计原则。

## 1. Scope
所有对 DeepMemo 进行改动的 AI 代码代理或人类开发者。

## 2. Preserved Behaviors

### I. 本地 Markdown 是知识真值
DeepMemo SHALL 以本地 Markdown 文件作为用户知识的长期真值。应用可以索引、总结、链接、可视化 Markdown，但 SQLite、生成的 wiki 页面和 LLM 输出都不能替代用户拥有的 Markdown 原文。

### II. 行为代码必须先有 Spec
任何触及 `src/`、`app/src/`、公开 API 合约、数据持久化、用户可见流程或 agent skill 的行为改动，MUST 先有 spec 资产。

### III. 回归保护必须测试优先
Bugfix MUST 在实现前或实现同时把 bug 固化为回归测试。新增 API MUST 增加或更新 L1 API contract 测试。新增用户可见 workflow MUST 先写自然语言 E2E scenario，再实现可执行测试。

### IV. 沙漏型测试模型
DeepMemo SHALL 优先用 API contract 测试保护后端可观察行为；只为稳定纯函数写窄单测；只为高价值用户闭环写 E2E 或 Browser 测试。测试保护的是产品合约，不是 agent 可以安全重构的内部编排细节。

### V. 验证必须隔离并默认 Mock
测试 MUST 使用临时 `data/` 和临时 SQLite 状态。测试 MUST NOT 修改真实用户知识库、真实 `data.db` 或本地敏感 agent memory。LLM 调用、网络调用和外部服务 MUST 默认 mock，除非用户明确要求集成验证。

## 3. Evidence
* 所有子项目源码根目录及 `tests/`。

## 4. Current Flow
无。这是约束性原则，非执行流。

## 5. Interfaces / Related Files
* `AGENTS.md` (引用本文件作为总纲)

## 6. Known Gaps
* 无

## 7. Regression Risks
* 如果违反测试隔离原则，可能污染真实的 `data.db`。
