# DeepMe Scope Isolation

* **Status**: Proposed

## 1. Context

DeepMemo 当前把所有问答请求绑定到同一个全局 `data/` 目录。DeepMe 需要同时支持作者公开知识库和匿名临时文件空间，任何请求都不能在两个知识范围之间回退或混用证据。

本阶段先建立公开 scope、匿名访客、不可变知识版本和按 scope 构造的问答服务。临时文件上传在后续 spec 中实现。

## 2. Intended Behavior

### 2.1 Public Scope

- 服务启动时从配置的公开知识目录生成不可变快照。
- 快照使用内容哈希作为版本的一部分。
- 系统只存在一个公开 scope。
- 新版快照注册完成后才能成为当前版本。
- 问答开始时解析一次 scope 和版本，整个请求保持不变。

### 2.2 Anonymous Visitor

- 新 API 使用签名 HttpOnly Cookie 识别匿名访客。
- 会话绑定访客和 scope。
- 当前访客只能读取自己的会话、消息和引用。
- 无权访问统一返回404。

### 2.3 Scoped Chat

- `/api/v1` 提供站点、会话、流式问答和引用接口。
- Chat 请求只接收 `session_id` 和问题。
- 后端从 session 解析 scope，客户端不能在 Chat 请求中覆盖 scope。
- DeepMe 公开问答关闭 Web Search、Chat Tools、Knowledge Commands 和 Conversation Memory。
- 回答和引用记录实际使用的 `scope_id` 与 `knowledge_version`。

### 2.4 Compatibility

- 原有 `/sessions`、`/chat`、Editor、Wiki 和 Knowledge API 暂时保留。
- 新数据列必须允许旧接口继续读写。
- 当前测试必须继续通过。

## 3. Alternative Approaches

### 3.1 直接修改旧接口

改动更少，但会同时影响 Editor、Knowledge Engine 和旧浏览器测试，回归范围过大。

### 3.2 每个 scope 启动独立进程

隔离清晰，但匿名临时文件会带来大量进程和端口管理，不适合 MVP。

### 3.3 请求级 Scope Resolver

本阶段采用此方案。API 验证 session 后得到不可变 `ResolvedScope`，再创建或复用对应版本的只读 QA 服务。

## 4. Risks & Dependencies

- SQLite migration 必须兼容已有数据库。
- 测试环境需要注入独立 runtime 和公开知识目录。
- 公共知识快照只能复制 Markdown，必须拒绝符号链接和路径越界。
- Cookie secret 在生产环境必须显式配置。
- 当前 Card-first 检索会返回生成 Wiki，DeepMe 公开问答阶段先关闭 Card 检索，只引用原始 Markdown。
