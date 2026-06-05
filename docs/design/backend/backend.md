# 架构设计
要做一个做知识库问答助手的后端
首先不设计多用户，只做mvp

编程语言：python
构建虚拟环境：uv
llm初始化：openaisdk
数据库选型和应用设计：sqlite
api框架：fastapi
llm配置文件：config/llm_api.yaml

## sqlite schema

session表
session_id string (UUID，主键)
session_name string
message_ids string (JSON 数组，存 message_id 列表)
created_at datetime
updated_at datetime

message表
message_id string (UUID，主键)
session_id string (外键关联 session)
role string (user/ai)
content string (AI 返回存 markdown 格式)
created_at datetime

## 其他约定

- session 和 message 的 ID 均使用 UUID v4
- messages_ids 字段存 JSON 数组字符串，如 ["msg_id_1", "msg_id_2"]
- 查询时反序列化 JSON 获取 message_ids 列表，再查 message 表
- llm config 文件放在项目根目录 config/llm_api.yaml
- 不做用户认证，MVP 版本所有会话都在同一个数据库里
