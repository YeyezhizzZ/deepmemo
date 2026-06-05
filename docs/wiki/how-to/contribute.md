# 贡献代码

DeepMemo 使用 spec-driven 工作流。不要直接根据当前代码形状做行为改动；代码是事实观察来源，不是设计权威。

## 开发前

1. 阅读 `docs/specs/README.md`。
2. 阅读 `docs/specs/constitution.md`。
3. 阅读受影响的 `docs/specs/current/` baseline specs。
4. 找到对应 `docs/specs/goals/` Goal，并确认它已 Ready for Implementation。
5. 检查 `docs/specs/deprecated.md`，不要依赖 D 类行为。

## 实现时

- 新 API 先补 L1 API contract 测试。
- Bugfix 先把 bug 固化为回归测试。
- 用户可见 workflow 先写 L3 scenario。
- 不污染真实 `data/`、`data.db`、本地 agent memory 或真实外部服务。

## 验证

常规收尾：

```bash
uv run python scripts/verify.py --mode quick
```

涉及浏览器 workflow 或跨模块行为时运行：

```bash
uv run python scripts/verify.py --mode full
```

Docs-only 改动至少运行：

```bash
git diff --check
```

如果改了 VitePress 文档站，还要运行：

```bash
cd docs/wiki
npm run docs:build
```

## 提交

提交信息建议说明目标和范围，例如：

```text
docs: update docs site
```

如果某个 Goal 实现完成并通过验证，需要把 Goal 状态更新为 `Implemented`，并同步受影响的 current specs。
