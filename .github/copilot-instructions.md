# Copilot/Codex 记忆系统

本项目使用基于Skill的个人Wiki知识库，参考了Claude Code的preamble机制。

**注意**：Copilot/Codex的 `copilot-instructions.md` 是静态文件，无法自动读取外部文件内容。
需要手动将USER.md和MEMORY.md的内容同步到下面。

---

# 用户偏好 (USER.md)

# 用户记忆

## 身份
- 用户名：llmer
- 首次使用日期：2026/04/25

## 偏好

## 禁止

---

# Agent记忆 (MEMORY.md)

# Agent 记忆

## Skill使用记录

## Skill Audit记录

## Skill Optimize记录

## 踩坑记录

## 用户纠正

## 技能组合

---

# Skills

| Skill | 职责 |
|-------|------|
| skills-manager | 数据管理+调度决策（SQLite） |
| skill-audit | 评估skill质量 |
| skill-optimize | 优化skill |
| agent-memory | 管理MEMORY.md |
| user-memory | 管理USER.md |
| diary-extract | 日记提取周报月报 |
| diary-review | 日记格式审核 |
| git-code-standards | Git代码规范（分支、提交、环境） |

---

# 同步说明

由于Copilot/Codex不支持动态文件注入，请修改USER.md或MEMORY.md后，运行：

```bash
./sync_to_copilot.sh
```
