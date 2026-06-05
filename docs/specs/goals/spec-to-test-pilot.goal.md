# Goal Spec: Spec-to-Test 试点落地

## 1. Goal
建立可重复执行的 Spec-to-Test 自动化工作流，把测试用例生成入口固定为明确的 Requirement 和 Scenario。

## 2. Why this goal matters
DeepMemo 已经有测试底座，但测试用例来源仍容易依赖 Agent 临场发挥的自由裁量权，导致测试用例可能没有完全覆盖核心的 Spec。

## 3. Related Specs
* **Current Specs**: `current/agentic-testing.md`, `constitution.md`
* **Open Questions**: 无

## 4. Desired Behavior
* 增加可重复执行的 Spec-to-Test workflow，用于应用行为改动。
* 要求每个已接受的 Scenario 必须映射到具体的测试层级，否则显式标记为 docs-only decision。
* 提供一个可复用 prompt 或脚本工具，专门用于读取 Specs 生成测试代码。

## 5. Non-goals
* 本目标不涉及增加新的业务功能代码。
* 不替换现有的 `pytest` 架构，只是改善“测试代码由谁/怎么生成”的环节。

## 6. Requirements
* 生成流程必须支持解析 Markdown 中的 `Scenario:` 块。

## 7. Acceptance Criteria
* 提供了一个清晰的操作手册（或脚本），能够成功把给定的一段 Spec Scenario 转化为 `tests/` 中的可运行代码。

## 8. Implementation Strategy
此 Goal 需要增强现有的 `agentic-test` Skill 工具，补充对文档解析的正则和生成。

## 9. Task Breakdown
- [ ] 读取 `openspec/changes/spec-to-test-pilot` 残留的设计草图
- [ ] 编写专用的 Spec-to-Test 提词模板 `docs/design/agentic_test/spec_to_test_prompt.md`
- [ ] 更新 `agentic-testing.md` 基线，正式确认该流程

## 10. Validation Plan
使用一个实际的小功能变更，走一遍完整的 Spec -> Generate Test -> Code -> Pass 的闭环。

## 11. Docs Sync Requirements
更新 `.agents/skills/agentic-test/SKILL.md` 的指引。
