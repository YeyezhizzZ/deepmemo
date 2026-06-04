# Query Routing

* **Status**: Current / Human Reviewed

## 1. Scope
涵盖决定问答请求最终访问哪些本地目录或触发外部网络搜索的路由策略层。

## 2. Preserved Behaviors
* **基于硬编码数组的路由匹配**：系统通过一系列 Python lists（如 `realtime_terms`, `idea_terms`, `diary_terms`, `mock_terms`）使用简单的 substring 包含关系判断路由。
* **Mock 演示保留**：包含 `"deepmemo", "demo", "mock"` 等词的请求会被明确路由到 `data/mock` 目录。这是被确认的 GitHub 展示刚需，属于**合法特性**。

## 3. Evidence
* `src/ai/query_router.py`

## 4. Current Flow
接受改写后的 Query，匹配内部列表，输出 `RouteDecision`，告诉 LocalSearch 去哪些目录搜（`path_hints`），以及是否告诉 Orchestrator 允许连网（`needs_web`）。

## 5. Interfaces / Related Files
* 下游直接影响 `LocalSearchAgent` 访问的目录根。

## 6. Known Gaps
* 扩展性差，难以通过动态知识进行意图推导。

## 7. Regression Risks
* 修改 `mock` 特性会导致项目的公开对外展示能力失效。
