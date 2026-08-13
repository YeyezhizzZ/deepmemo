# DeepMe MVP Completion Goal

* **Status**: Complete

## 1. Goal

完成 DeepMe PRD 中临时文件问答、版本级检索、公开双模式前端、每日同步和自部署能力。

## 2. Related Specs

- `docs/product/deepme-prd.md`
- `docs/design/deepme-system-architecture.md`
- `docs/specs/proposed/deepme-scope-isolation.md`
- `docs/specs/proposed/deepme-temporary-workspace.md`
- `docs/specs/proposed/deepme-versioned-retrieval.md`

## 3. Desired Behavior

1. “问我”默认连接作者公开知识版本。
2. “问你的资料”支持 Markdown、TXT 和可提取文本的 PDF。
3. 两种模式的会话、索引、引用和缓存严格隔离。
4. 公开知识目录按配置周期检查，构建失败继续使用旧版本。
5. 前端不显示 Editor、Wiki、Pulse 或文件树。
6. 项目可以通过 Docker Compose 自部署并替换公开知识目录。

## 4. Non-goals

- 用户账户。
- OCR。
- 长期云端文件托管。
- 多站点平台。
- 外部向量数据库。

## 5. Task Breakdown

- [x] 实现 Workspace API、文件配额和上传存储。
- [x] 实现 SQLite Job Queue 和 Worker。
- [x] 实现 Markdown、TXT、PDF Normalizer。
- [x] 实现版本索引、Ngram、可选 Embedding 和精排。
- [x] 实现 temporary session、问答和引用。
- [x] 实现 TTL 与主动删除。
- [x] 实现 DeepMe 双模式前端。
- [x] 更新 Browser 场景。
- [x] 增加 Docker Compose、运行配置和示例知识目录。
- [x] 完成 API、E2E、浏览器和构建验证。

## 6. Validation Plan

- `uv run python scripts/verify.py --mode quick`
- `uv run pytest tests/e2e -q --tb=short`
- `uv run python scripts/verify.py --mode full`
- `npm run docs:build`，工作目录为 `docs/wiki`
- `docker compose config`

## 7. Completion Criteria

- PRD 的10条验收场景均有自动化或明确验证记录。
- 跨 scope 泄漏测试为0。
- 主动删除后旧会话立即不可访问。
- 公开构建失败不会切换当前版本。
- 默认前端完成“问我”和“问你的资料”两条流程。

## 8. Validation Result

- 完整 pytest 共110项通过。
- Playwright Chromium 共3个场景通过。
- React TypeScript 与 Vite 生产构建通过。
- VitePress 文档构建通过。
- `uv lock --check` 和 `git diff --check` 通过。
- 生产静态首页、静态 JS 和公开路由隔离通过独立进程验证。
- Compose YAML 结构解析通过。当前机器没有 Docker CLI，未执行镜像构建。
