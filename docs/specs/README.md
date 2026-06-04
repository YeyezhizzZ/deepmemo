# DeepMemo Spec 体系

本项目采用 **Goal-oriented** 的 Spec 体系，由人工评审（Human Review）保证设计权威，AI 代理（Codex）负责执行。
**切记：当前代码库只代表 observed facts，不代表 intended design。只有位于此目录下的 current specs 才具有权威性。**

## 目录结构

- `current/`：已经实现、并且 Human Review 确认应该保留的行为（源自 A 类事实）。开发新功能前必读。
- `goals/`：面向 Codex 的执行入口。包含了开发目标、需求、拆解步骤和验证计划。AI 应该阅读并执行这里的 spec。
- `proposed/`：尚未进入 ready 状态的未来功能、重构方向或设计草案（源自 C 类想法）。
- `review/`：包含待讨论的 open questions 和框架对比，这部分**不能作为实现需求**。
- `deprecated.md`：废弃代码和特性的记录（D 类）。
- `templates/`：用于生成新 spec 的标准模板。

## 工作流

1. **查阅**：开发前必须阅读 `current/` 中的相关文档，确保不破坏既有规范。
2. **制定**：新功能必须先通过 `goals/` 写出目标、任务拆解和验收标准。
3. **执行**：AI 严格按照 `goals/` 的 Task Breakdown 实施，执行 Validation Plan。
4. **归档**：实现完毕后，更新 `current/` 的行为基线，或归档相关设计。
