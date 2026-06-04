# Spec Framework Comparison

## Dimension Comparison

| Dimension | OpenSpec Candidate | Spec Kit Candidate | Decision for This Project |
| --------- | ------------------ | ------------------ | ------------------------- |
| **Directory Structure** | `specs/`, `changes/` 物理隔离 | 全部堆在 `.specify/memory/`、`plan/`、`tasks/` 中 | 采用自定义结构：`current/`, `goals/`, `proposed/`, `review/` |
| **Spec Lifecycle** | 严格的状态机（Draft -> Accepted -> Merged） | 通过 PR/Issue 流转，文档状态偏向弱约定 | 定义明确的状态机，尤其是 Goal Specs 需要有 `Ready for Implementation` 和 `Implemented` |
| **Current Behavior** | 保存在 `specs/` 中作为 canonical baseline | 混杂在 memory 设计文档中，不区分历史与未来 | 保存在 `current/`，必须由 A 类转化，且附带 Evidence |
| **Proposed Change** | 保存在 `changes/<name>/` 中隔离管理 | 在 `plan/` 目录下用 checklist 管理 | 保存在 `proposed/` 或转化为可执行的 `goals/` |
| **Goal Expression** | 较弱，偏向描述系统“是什么” | 较弱，偏向“要执行什么任务” | 专门设立 `goals/`，采用强烈的 Goal-oriented 结构解决 AI 迷失问题 |
| **Requirements Format** | 声明式，偏向接口和行为规范 | 动作式，偏向重构步骤 | 两者结合，在 Goal spec 中同时定义 Desired Behavior 和 Acceptance Criteria |
| **Task Breakdown** | 无专门的任务分解 | 强大的 checklist 支持 | 吸收进 Goal spec，要求明确“代码实现大致分几步” |
| **Validation Support** | 弱，主要依赖测试用例关联 | 强，可在 plan 中专门列出验证步骤 | 吸收进 Goal spec，要求明确“需求如何验证” |
| **Codex Readability** | 中。容易找到基线，但不易理解如何动手改代码 | 高。任务导向强，但容易迷失大局观 | 极高。通过 Current + Goal 的双层结构，既有全局认知又有明确任务 |
| **Maintainability** | 极高，基线永远干净 | 中，容易产生大量过期 plan 垃圾 | 高，废弃内容进入 `deprecated.md`，过期目标状态更新为 Superseded |
| **Overhead** | 高，修改一点点都需要走 delta 变更流程 | 中，但找文档比较麻烦 | 中，使用模板（templates）降低撰写成本 |
| **Fit for vibe-coded**| 中，无法很好兼容未定论的探索性代码 | 低，假定项目一开始就有清晰的边界 | 高，允许 `review/` 暂存 B 类未定论代码，A 类入库，不强迫完美 |
| **Fit for future AI** | 中等，适合读取，不适合增量生成 | 高，适合执行 | 完美，AI agent 通过 `goals/` 获得上下文和具体执行步骤 |

## 合并策略与取舍理由

本项目由大量 Vibe Coding 生成，这意味着代码库里既有宝贵的核心逻辑，也有大量的实验性代码和技术债。
- **放弃 OpenSpec 的过于极端的 Delta 机制**：因为在项目未完全稳定前，强求每次修改都写一个完整的 proposal 和 spec 差异（delta）会拖慢开发进度。
- **吸收 Spec Kit 的任务执行力**：AI 编码最需要的是 Task Breakdown 和 Validation Plan。
- **最终采用的三层分离架构**：
  1. `current/` 作为事实基线，用于约束 AI 不要破坏已确定的功能。
  2. `goals/` 作为增量开发的驱动引擎，吸收了 Spec Kit 的优势，非常适合分步骤投喂给 Codex。
  3. `review/` 与 `deprecated.md` 作为垃圾桶和缓冲区，防止代码库中的 vibe coding 产物污染了基准设计。
