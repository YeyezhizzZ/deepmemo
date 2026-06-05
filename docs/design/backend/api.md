# DeepMemo API Design Document (V2)

## Overview

**Base URL**: `http://localhost:8000`

**Content-Type**: `application/json`

**Authentication**: Currently none (internal use only)

---

## Table of Contents

1. [Health Check](#1-health-check)
2. [File System API (`/api/fs`)](#2-file-system-api-apifs)
3. [Session API (`/sessions`)](#3-session-api-sessions)
4. [Chat API (`/chat`)](#4-chat-api-chat)
5. [Citations API (`/api/chat/citations`)](#5-citations-api-apichatcitations)
6. [File References API (`/chat/file-references`)](#6-file-references-api-chatfile-references)
7. [Diary API (`/api/diary`)](#7-diary-api-apidiary)
8. [Pulse API (`/api/pulse`)](#8-pulse-api-apipulse)
9. [Data Models](#9-data-models)

---

## 1. Health Check

### GET `/`

Health check endpoint.

**Response** `200 OK`:
```json
{
  "message": "DeepMemo API is running"
}
```

---

## 2. File System API (`/api/fs`)

### GET `/api/fs/tree`

Returns the full directory tree of `data/` with sync status for each node.

**Response** `200 OK`:
```json
[
  {
    "name": "diary",
    "path": "diary",
    "type": "directory",
    "sync_status": "synced",
    "children": [
      {
        "name": "2026-05-03.md",
        "path": "diary/2026-05-03.md",
        "type": "file",
        "sync_status": "dirty"
      }
    ]
  },
  {
    "name": "ideas",
    "path": "ideas",
    "type": "directory",
    "sync_status": "synced",
    "children": []
  }
]
```

**`sync_status` Values**:
| Value | Description | Frontend Color |
|-------|-------------|----------------|
| `synced` | Synced with server | Green |
| `dirty` | Local changes not saved | Orange |
| `draft` | Draft (not yet saved) | Gray |
| `processing` | Being processed | Blue |
| `error` | Error occurred | Red |

---

### GET `/api/fs/content`

Reads file content from disk.

**Query Parameters**:
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `path` | string | Yes | Relative path from `data/`, e.g. `diary/2026-05-03.md` |

**Response** `200 OK`:
```json
{
  "path": "diary/2026-05-03.md",
  "content": "# 日记内容..."
}
```

**Response** `404 Not Found`:
```json
{
  "detail": "File not found: diary/2026-05-03.md"
}
```

---

### POST `/api/fs/write`

Creates or overwrites a file on disk. Updates `file_meta` table.

**Request Body**:
```json
{
  "path": "diary/2026-05-04.md",
  "content": "# 新日记内容"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `path` | string | Yes | Relative path from `data/` |
| `content` | string | Yes | File content (Markdown) |

**Response** `200 OK`:
```json
{
  "message": "File written successfully",
  "file_path": "diary/2026-05-04.md",
  "file_hash": "a1b2c3d4e5f6...",
  "sync_status": "synced",
  "last_modified": "2026-05-04T10:30:00"
}
```

---

### POST `/api/fs/move`

Moves or renames a file. Used for drag-and-drop or rename operations.

**Request Body**:
```json
{
  "old_path": "diary/2026-05-03.md",
  "new_path": "diary/2026-05-03_old.md"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `old_path` | string | Yes | Current path |
| `new_path` | string | Yes | Target path |

**Response** `200 OK`:
```json
{
  "message": "File moved successfully",
  "old_path": "diary/2026-05-03.md",
  "new_path": "diary/2026-05-03_old.md",
  "file_hash": "a1b2c3d4e5f6...",
  "sync_status": "synced"
}
```

**Response** `404 Not Found`:
```json
{
  "detail": "Source file not found: diary/2026-05-03.md"
}
```

---

### PATCH `/api/fs/sync-status`

Updates the sync status of a file in `file_meta` table.

**Request Body**:
```json
{
  "path": "diary/2026-05-03.md",
  "sync_status": "dirty"
}
```

**Response** `200 OK`:
```json
{
  "message": "Sync status updated",
  "path": "diary/2026-05-03.md",
  "sync_status": "dirty"
}
```

---

### POST `/api/fs/create-file`

Creates a new empty file.

**Request Body**:
```json
{
  "path": "diary/2026-05-04.md",
  "content": ""
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `path` | string | Yes | Relative path from `data/` |
| `content` | string | No | Initial content (default: empty) |

**Response** `200 OK`:
```json
{
  "message": "File created successfully",
  "file_path": "diary/2026-05-04.md",
  "file_hash": "d41d8cd98f00b204e9800998ecf8427e",
  "sync_status": "synced"
}
```

**Response** `409 Conflict`:
```json
{
  "detail": "File already exists: diary/2026-05-04.md"
}
```

---

### POST `/api/fs/create-directory`

Creates a new directory.

**Request Body**:
```json
{
  "path": "ideas/projects"
}
```

**Response** `200 OK`:
```json
{
  "message": "Directory created successfully",
  "dir_path": "ideas/projects",
  "sync_status": "synced"
}
```

**Response** `409 Conflict`:
```json
{
  "detail": "Directory already exists: ideas/projects"
}
```

---

## 3. Session API (`/sessions`)

### POST `/sessions`

Creates a new chat session.

**Request Body**:
```json
{
  "session_name": "我的第一个会话"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `session_name` | string | Yes | Display name for the session |

**Response** `200 OK`:
```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "session_name": "我的第一个会话",
  "message_ids": [],
  "created_at": "2026-05-04T10:00:00",
  "updated_at": "2026-05-04T10:00:00"
}
```

---

### GET `/sessions`

Returns all sessions, ordered by `created_at` descending.

**Response** `200 OK`:
```json
[
  {
    "session_id": "550e8400-e29b-41d4-a716-446655440000",
    "session_name": "我的第一个会话",
    "message_ids": ["msg-id-1", "msg-id-2"],
    "created_at": "2026-05-04T10:00:00",
    "updated_at": "2026-05-04T10:30:00"
  }
]
```

---

### GET `/sessions/{session_id}`

Returns a single session by ID.

**Response** `200 OK`: Same structure as single item in list above.

**Response** `404 Not Found`:
```json
{
  "detail": "Session not found"
}
```

---

### DELETE `/sessions/{session_id}`

Deletes a session and all its messages.

**Response** `200 OK`:
```json
{
  "message": "Session deleted"
}
```

---

## 4. Chat API (`/chat`)

### POST `/chat`

Sends a user message and receives an AI response. The AI response includes citations extracted from the knowledge base.

**Request Body**:
```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "user_message": "今天学了什么？"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `session_id` | string | Yes | Target session ID |
| `user_message` | string | Yes | User's question |

**Response** `200 OK`:
```json
{
  "message_id": "660e8400-e29b-41d4-a716-446655440001",
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "role": "ai",
  "content": "# 今日学习总结\n\n根据你的知识库，今天你学习了...\n\n[1] diary/2026-05-03.md:45-52",
  "created_at": "2026-05-04T10:30:00"
}
```

> **Note**: `content` is Markdown. Citations appear as `[1]`, `[2]` etc. and are linked to the Source Panel.

---

### GET `/chat/{session_id}/messages`

Returns all messages in a session, ordered by `created_at`.

**Response** `200 OK`:
```json
[
  {
    "message_id": "user-msg-uuid",
    "session_id": "session-uuid",
    "role": "user",
    "content": "今天学了什么？",
    "created_at": "2026-05-04T10:30:00"
  },
  {
    "message_id": "ai-msg-uuid",
    "session_id": "session-uuid",
    "role": "ai",
    "content": "# 今日学习总结...",
    "created_at": "2026-05-04T10:30:01"
  }
]
```

---

## 5. Citations API (`/api/chat/citations`)

### GET `/api/chat/citations`

Returns detailed citation evidence for a specific message. Used by the right-side Source Panel when viewing QA mode.

**Query Parameters**:
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `message_id` | string | Yes | The message ID to get citations for |

**Response** `200 OK`:
```json
{
  "message_id": "ai-msg-uuid",
  "citations": [
    {
      "local_id": 1,
      "evidence_id": "src-001",
      "file_path": "diary/2026-05-03.md",
      "content": "今天完成了 FastAPI 的学习..."
    },
    {
      "local_id": 2,
      "evidence_id": "src-002",
      "file_path": "ideas/llm-notes.md",
      "content": "Attention 机制是 Transformer 的核心..."
    }
  ]
}
```

**Response** `404 Not Found`:
```json
{
  "detail": "Message not found"
}
```

---

## 6. File References API (`/chat/file-references`)

### GET `/chat/file-references`

Returns all chat messages that reference a specific file. Used in Editor mode to show which sessions have cited the current file.

**Query Parameters**:
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `path` | string | Yes | File path relative to `data/` |

**Response** `200 OK`:
```json
{
  "references": [
    {
      "session_id": "session-uuid-1",
      "session_name": "会话 05/03",
      "message_id": "ai-msg-uuid",
      "role": "ai",
      "content": "# 回答\n\n根据 diary/2026-05-03.md，你提到了...",
      "created_at": "2026-05-03T15:30:00"
    }
  ]
}
```

---

## 7. Diary API (`/api/diary`)

### POST `/api/diary/auto-draft`

Generates a diary draft from raw materials in `data/raw/`. Scans the most recent `.md` file in the raw directory and generates a diary draft using AI.

**Request Body** (optional):
```json
{
  "raw_dir": "raw",
  "output_dir": "diary"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `raw_dir` | string | No | Source directory for raw materials (default: `raw`) |
| `output_dir` | string | No | Target directory hint (default: `diary`) |

**Response** `200 OK`:
```json
{
  "source_file": "raw_note.md",
  "draft": "# 2026年5月4日\n\n今天完成了...",
  "message": "Draft generated (LLM integration pending)"
}
```

**Response** `200 OK` (no raw files):
```json
{
  "message": "No raw files found",
  "draft": ""
}
```

---

## 8. Pulse API (`/api/pulse`)

### GET `/api/pulse/today`

Aggregates today's Git commits and raw materials for diary writing inspiration.

**Response** `200 OK`:
```json
{
  "date": "2026-05-04",
  "git_commits": [
    {
      "hash": "abc1234",
      "subject": "feat: add user authentication",
      "author": "Guo Ziyang",
      "date": "2026-05-04T14:30:00"
    }
  ],
  "raw_materials": [
    {
      "name": "meeting_notes.md",
      "path": "raw/meeting_notes.md",
      "type": "file",
      "modified": "2026-05-04T12:00:00"
    }
  ]
}
```

---

## 9. Data Models

### 9.1 Session

| Field | Type | Description |
|-------|------|-------------|
| `session_id` | string (UUID) | Primary key |
| `session_name` | string | Display name |
| `message_ids` | string (JSON Array) | List of message IDs in order |
| `created_at` | string (ISO 8601) | Creation timestamp |
| `updated_at` | string (ISO 8601) | Last update timestamp |

### 9.2 Message

| Field | Type | Description |
|-------|------|-------------|
| `message_id` | string (UUID) | Primary key |
| `session_id` | string (UUID) | Foreign key to session |
| `role` | string | `user` or `ai` |
| `content` | string | Markdown content |
| `citations` | string (JSON Array) | Array of citation objects (AI messages only) |
| `created_at` | string (ISO 8601) | Creation timestamp |

### 9.3 Citation Object

Stored in `message.citations` as JSON array:

```json
[
  {
    "local_id": 1,
    "evidence_id": "src-001",
    "file_path": "diary/2026-05-03.md",
    "content": "原文片段..."
  }
]
```

| Field | Type | Description |
|-------|------|-------------|
| `local_id` | integer | Sequential citation number in message (1, 2, 3...) |
| `evidence_id` | string | Unique identifier for this evidence |
| `file_path` | string | Path to source file |
| `content` | string | Excerpt from source |

### 9.4 FileMeta

| Field | Type | Description |
|-------|------|-------------|
| `id` | string (UUID) | Primary key |
| `file_path` | string | Relative path from `data/` |
| `file_hash` | string | MD5 hash of file content |
| `sync_status` | string | One of: `synced`, `dirty`, `draft`, `processing`, `error` |
| `last_modified` | string (ISO 8601) | Last modification timestamp |
| `created_at` | string (ISO 8601) | Creation timestamp |

---

## Error Response Format

All error responses follow this format:

```json
{
  "detail": "Error description message"
}
```

Common HTTP status codes:

| Status | Meaning |
|--------|---------|
| `200` | Success |
| `400` | Bad Request (invalid input) |
| `404` | Not Found |
| `409` | Conflict (e.g., file already exists) |
| `500` | Internal Server Error |

---

## Frontend Integration Checklist

### Initialization
- [ ] `GET /` - Verify backend is online
- [ ] `GET /sessions` - Load existing sessions
- [ ] `GET /api/fs/tree` - Load file tree

### File Operations
- [ ] `GET /api/fs/content?path=xxx` - Read file
- [ ] `POST /api/fs/write` - Save file
- [ ] `POST /api/fs/move` - Rename/move file
- [ ] `POST /api/fs/create-file` - Create new file
- [ ] `POST /api/fs/create-directory` - Create new folder
- [ ] `PATCH /api/fs/sync-status` - Update status indicator

### Chat Operations
- [ ] `POST /sessions` - Create new session
- [ ] `POST /chat` - Send message
- [ ] `GET /chat/{session_id}/messages` - Load message history
- [ ] `GET /api/chat/citations?message_id=xxx` - Get citation details
- [ ] `GET /chat/file-references?path=xxx` - Get sessions that cited a file

### Diary & Pulse
- [ ] `POST /api/diary/auto-draft` - Generate diary draft
- [ ] `GET /api/pulse/today` - Get today's Git commits and raw materials