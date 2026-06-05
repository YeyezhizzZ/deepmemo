# DeepMemo Backend V2：文件系统驱动与知识状态机架构

1. 核心职责划分
文件系统真理源 (FS-as-Source)：物理磁盘上的 .md 文件是知识的唯一真值，确保数据的长久可读与可迁移性。

状态镜像 (State Mirroring)：利用 SQLite 维护文件的"元状态"（如同步进度、Hash 值），实现前端 UI 的毫秒级响应。

上下文聚合 (Context Aggregator)：收集 Git 提交、浏览器记录等非结构化素材，作为日记写作的"脉搏"数据。

2. SQLite Schema 增强
-- 1. 文件元数据表：维护物理文件与数据库的同步状态
CREATE TABLE file_meta (
    id TEXT PRIMARY KEY,
    file_path TEXT UNIQUE,       -- 相对路径，如 diary/2026-05-03.md
    file_hash TEXT,             -- 内容 MD5，用于判断是否发生实质变动
    sync_status TEXT NOT NULL CHECK (
        sync_status IN ('synced', 'dirty', 'draft', 'processing', 'error')
    ),
    last_modified DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 2. 消息表：存储对话内容与指纹化引用
CREATE TABLE message (
    message_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('user', 'ai')),
    content TEXT NOT NULL,
    citations TEXT DEFAULT '[]',  -- JSON: [{"local_id": 1, "evidence_id": "...", "file_path": "...", "content": "..."}]
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES session(session_id)
);

3. API 路由设计
📂 文件系统模块 (FS API)

GET /api/fs/tree：返回 data/ 的树状结构，并联合查询 file_meta 获取每个节点的 sync_status。

GET /api/fs/content?path=xxx：读取文件内容。

POST /api/fs/write：写入 MD 文件。逻辑：写入磁盘 → 更新 file_hash → 状态设为 dirty。

POST /api/fs/move：处理重命名/拖拽。逻辑：更新物理路径 → 更新 file_meta 中的 file_path。

💬 智能对话模块 (Chat API)

POST /api/chat：对话接口，返回结果包含 citations 数组。

GET /api/chat/citations?message_id=xxx：获取特定消息的详细引用证据链。

💓 知识洞察模块 (Pulse API)

GET /api/pulse/today：聚合今日 Git Commits 和原始素材。扫描 data/raw → 解析非 MD 记录 → 返回列表。

4. 关键技术点实现
Watcher 监听器 (状态切换)

当文件被修改时：
1. 计算文件新 Hash
2. 查询 DB，如果 Hash 不同，标记为 dirty
3. 通过回调通知前端

5. 项目结构
.
├── app/
│   ├── main.py            # FastAPI 入口
│   ├── database.py        # SQLite 连接与初始化
│   ├── core/
│   │   ├── watcher.py     # 磁盘监听器
│   │   └── fs_manager.py  # 物理 IO 封装
│   └── routers/           # 路由层
│       ├── fs.py          # 文件系统 API
│       ├── chat.py        # 对话 API
│       └── pulse.py       # 今日动态 API
├── data/                  # 物理知识库 (Git 托管)
│   ├── diary/
│   ├── ideas/
│   └── raw/               # 存放原始素材
└── src/
    └── ai/                # AI 服务层