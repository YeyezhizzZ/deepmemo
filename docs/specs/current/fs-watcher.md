# File System Watcher

* **Status**: Current / Human Reviewed

## 1. Scope
后台系统级组件，负责静默监听文件系统的变更，并将状态同步至数据库。

## 2. Preserved Behaviors
* **MD5 Hashing**：利用 Watchdog 监听 `data/` 下的文件，通过比对 MD5 值来判断内容是否真正发生了变更。
* **状态打标**：对发生变更的文件，在 `data.db` (`file_meta` 表) 中将其 `sync_status` 标记为 `dirty`，供其他组件消费。
* **Knowledge Card 增量编译**：`diary/` 与 `raw/` 下 Markdown 变更后，watcher 使用防抖计时触发对应文件的 Knowledge Card 编译。

## 3. Evidence
* `src/app/core/watcher.py`
* `src/knowledge/card_compiler.py`

## 4. Current Flow
启动 FastAPI 时挂载 Watchdog 线程 -> `data/` 目录发生系统级变动 -> 过滤非 Markdown 文件 -> 计算 MD5 -> 与 DB 对比 -> 更新 `sync_status` 为 dirty -> 如果路径属于 `diary/` 或 `raw/`，按 `DEEPMEMO_KNOWLEDGE_DEBOUNCE_SECONDS` 防抖编译 Card。

## 5. Interfaces / Related Files
* `database.py` 提供数据存储
* 被 Knowledge Engine 增量编译机制依赖

## 6. Known Gaps
* 偶尔存在遗漏事件的可能，启动时没有进行全量对齐强制检查。
* 防抖任务在进程退出时不会持久化 pending 队列。

## 7. Regression Risks
* 修改文件元数据状态可能导致前后端同步状态不一致，或导致 Knowledge Card 增量编译无法触发。
