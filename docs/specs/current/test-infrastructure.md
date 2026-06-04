# Test Infrastructure

* **Status**: Current / Human Reviewed

## 1. Scope
沙漏型测试模型（Sandglass testing model），保障系统的回归安全性。

## 2. Preserved Behaviors
* **L1 API 合约测试** (`tests/api/`)
* **L2 Unit 纯函数测试** (`tests/unit/`)
* **L3 智能体 E2E 测试** (`tests/e2e/`)
* **Browser 端到端测试** (`app/tests/browser/`)

## 3. Evidence
* `tests/` 和 `app/tests/`
* `scripts/verify.py`

## 4. Current Flow
开发或重构 -> `uv run python scripts/verify.py --mode quick` 跑 L1 和 L2 测试 -> 发布前 `verify.py --mode full` 跑 Playwright。
