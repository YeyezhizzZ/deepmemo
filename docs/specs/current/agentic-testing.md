# Agentic Testing

* **Status**: Current / Human Reviewed

## 1. Scope
Agentic Testing 定义 DeepMemo 中 AI-Coding 的质量控制流程。它把立宪纪律和增量规格维护结合起来，再映射到仓库内可重复执行的测试资产。

## 2. Preserved Behaviors
* **Spec Kit 原则映射**：系统强制将 Constitution 中的 `spec-first` 和 `test-first` 映射为日常验证。
* **OpenSpec 基线维护**：将验证通过的行为写入 `docs/specs/current/` 作为 baseline。
* **Scenario 驱动测试**：API 行为映射到 L1（`tests/api/`），多步骤 workflow 映射到 L3（`tests/e2e/scenarios.yaml`）。
* **自动化报告**：完成代码修改后，强制执行验证脚本收集证据。

## 3. Evidence
* `tests/api/`
* `tests/e2e/scenarios.yaml`
* `scripts/verify.py`
* `.agents/skills/agentic-test/`

## 4. Current Flow
功能开发 -> 增加 Spec Scenario -> 实现测试 -> 实现代码 -> 运行 `uv run python scripts/verify.py --mode quick` -> 手动执行 `mode full`。

## 5. Interfaces / Related Files
* 强依赖于 `AGENTS.md` 赋予的 Agent 规矩。

## 6. Known Gaps
* E2E 测试对纯文本 Scenario 到实际测试用例的映射有时缺乏自动化生成。

## 7. Regression Risks
* 测试断言的轻易更改将削弱此模型的防护力。
