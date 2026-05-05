import type {
  ApiFileContentResponse,
  ApiFileReference,
  ApiFileMoveResponse,
  ApiFileWriteResponse,
  ApiChatToolResponse,
  ApiCitationsResponse,
  ApiFsNode,
  ApiMessageResponse,
  ApiSessionResponse,
  ApiSyncStatusResponse,
  AutoDraftResponse,
  FileReference,
  ChatTool,
  ChatToolSelection,
  ChatMessage,
  Citation,
  FsNode,
  Session,
  SyncStatus,
} from './types';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '/api';

function buildRequestUrl(path: string): string {
  if (API_BASE_URL === '/api' && path.startsWith('/api/')) {
    return path;
  }
  return `${API_BASE_URL}${path}`;
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(buildRequestUrl(path), {
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
    ...options,
  });

  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = (await response.json()) as { detail?: string };
      detail = body.detail ?? detail;
    } catch {
      // Keep the HTTP status text when the backend does not return JSON.
    }
    throw new Error(detail || `HTTP ${response.status}`);
  }

  return response.json() as Promise<T>;
}

function formatTime(value: string): string {
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(value));
}

export function mapSession(session: ApiSessionResponse): Session {
  return {
    sessionId: session.session_id,
    sessionName: session.session_name,
    messageIds: session.message_ids,
    createdAt: formatTime(session.created_at),
    updatedAt: formatTime(session.updated_at),
  };
}

export function mapMessage(message: ApiMessageResponse): ChatMessage {
  return {
    id: message.message_id,
    sessionId: message.session_id,
    role: message.role === 'ai' ? 'assistant' : 'user',
    content: message.content,
    createdAt: formatTime(message.created_at),
  };
}

function mapCitation(citation: ApiCitationsResponse['citations'][number]): Citation {
  return {
    localId: citation.local_id,
    evidenceId: citation.evidence_id,
    filePath: citation.file_path,
    content: citation.content,
  };
}

function mapFsNode(node: ApiFsNode): FsNode {
  return {
    id: node.path,
    name: node.name,
    path: node.path,
    type: node.type,
    syncStatus: node.sync_status,
    children: node.children?.map(mapFsNode),
  };
}

function mapChatTool(tool: ApiChatToolResponse): ChatTool {
  return {
    id: tool.id,
    name: tool.name,
    description: tool.description,
    executionType: tool.execution_type,
  };
}

function buildChatBody(sessionId: string, userMessage: string, tool?: ChatToolSelection): string {
  return JSON.stringify({
    session_id: sessionId,
    user_message: userMessage,
    tool: tool
      ? {
          tool_id: tool.toolId,
          scope: tool.scope ?? 'next_message',
        }
      : undefined,
  });
}

export async function getHealth(): Promise<{ message: string }> {
  return request<{ message: string }>('/');
}

export async function listSessions(): Promise<Session[]> {
  const sessions = await request<ApiSessionResponse[]>('/sessions');
  return sessions.map(mapSession);
}

export async function createSession(sessionName: string): Promise<Session> {
  const session = await request<ApiSessionResponse>('/sessions', {
    method: 'POST',
    body: JSON.stringify({ session_name: sessionName }),
  });
  return mapSession(session);
}

export async function deleteSession(sessionId: string): Promise<void> {
  await request<{ message: string }>(`/sessions/${sessionId}`, {
    method: 'DELETE',
  });
}

export async function listMessages(sessionId: string): Promise<ChatMessage[]> {
  const messages = await request<ApiMessageResponse[]>(`/chat/${sessionId}/messages`);
  return messages.map(mapMessage);
}

export async function getChatTools(): Promise<ChatTool[]> {
  const tools = await request<ApiChatToolResponse[]>('/chat/tools');
  return tools.map(mapChatTool);
}

export async function sendMessage(
  sessionId: string,
  userMessage: string,
  tool?: ChatToolSelection,
): Promise<ChatMessage> {
  const message = await request<ApiMessageResponse>('/chat', {
    method: 'POST',
    body: buildChatBody(sessionId, userMessage, tool),
  });
  return mapMessage(message);
}

export async function sendMessageStream(
  sessionId: string,
  userMessage: string,
  onChunk: (token: string) => void,
  tool?: ChatToolSelection,
): Promise<ChatMessage | undefined> {
  const response = await fetch(buildRequestUrl('/chat/stream'), {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: buildChatBody(sessionId, userMessage, tool),
  });

  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = (await response.json()) as { detail?: string };
      detail = body.detail ?? detail;
    } catch {
      // Keep the HTTP status text when the backend does not return JSON.
    }
    throw new Error(detail || `HTTP ${response.status}`);
  }

  const reader = response.body?.getReader();
  if (!reader) {
    throw new Error('Response body is not readable');
  }

  const decoder = new TextDecoder();
  let buffer = '';
  let savedMessage: ChatMessage | undefined;

  const handleEventBlock = (block: string) => {
    const data = block
      .split(/\r?\n/)
      .filter((line) => line.startsWith('data:'))
      .map((line) => line.replace(/^data:\s?/, ''))
      .join('\n')
      .trim();

    if (!data) return;

    const event = JSON.parse(data) as {
      type?: string;
      content?: string;
      message?: ApiMessageResponse;
    };

    if (event.type === 'token') {
      onChunk(event.content ?? '');
      return;
    }

    if (event.type === 'done') {
      savedMessage = event.message ? mapMessage(event.message) : undefined;
      return;
    }

    if (event.type === 'error') {
      throw new Error(event.content || '流式生成失败');
    }
  };

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const blocks = buffer.split(/\r?\n\r?\n/);
    buffer = blocks.pop() ?? '';

    for (const block of blocks) {
      handleEventBlock(block);
    }
  }

  buffer += decoder.decode();
  if (buffer.trim()) {
    handleEventBlock(buffer);
  }

  return savedMessage;
}

export async function getMessageCitations(messageId: string): Promise<Citation[]> {
  const response = await request<ApiCitationsResponse>(`/api/chat/citations?message_id=${encodeURIComponent(messageId)}`);
  return response.citations.map(mapCitation);
}

export async function getFileTree(): Promise<FsNode[]> {
  const nodes = await request<ApiFsNode[]>('/api/fs/tree');
  return nodes.map(mapFsNode);
}

export async function getFileContent(path: string): Promise<ApiFileContentResponse> {
  return request<ApiFileContentResponse>(`/api/fs/content?path=${encodeURIComponent(path)}`);
}

export async function writeFile(path: string, content: string): Promise<ApiFileWriteResponse> {
  return request<ApiFileWriteResponse>('/api/fs/write', {
    method: 'POST',
    body: JSON.stringify({ path, content }),
  });
}

export async function moveFile(oldPath: string, newPath: string): Promise<ApiFileMoveResponse> {
  return request<ApiFileMoveResponse>('/api/fs/move', {
    method: 'POST',
    body: JSON.stringify({ old_path: oldPath, new_path: newPath }),
  });
}

export async function updateFileSyncStatus(path: string, syncStatus: SyncStatus): Promise<ApiSyncStatusResponse> {
  return request<ApiSyncStatusResponse>('/api/fs/sync-status', {
    method: 'PATCH',
    body: JSON.stringify({ path, sync_status: syncStatus }),
  });
}

export async function createDiaryAutoDraft(rawDir = 'raw', outputDir = 'diary'): Promise<AutoDraftResponse> {
  const response = await request<{ source_file?: string; draft: string; message: string }>('/api/diary/auto-draft', {
    method: 'POST',
    body: JSON.stringify({ raw_dir: rawDir, output_dir: outputDir }),
  });
  return {
    sourceFile: response.source_file,
    draft: response.draft,
    message: response.message,
  };
}

export interface CreateFileResponse {
  message: string;
  file_path: string;
  file_hash: string;
  sync_status: string;
}

export interface CreateDirResponse {
  message: string;
  dir_path: string;
  sync_status: string;
}

export async function createFile(path: string, content = ''): Promise<CreateFileResponse> {
  return request<CreateFileResponse>('/api/fs/create-file', {
    method: 'POST',
    body: JSON.stringify({ path, content }),
  });
}

export async function createDirectory(path: string): Promise<CreateDirResponse> {
  return request<CreateDirResponse>('/api/fs/create-directory', {
    method: 'POST',
    body: JSON.stringify({ path }),
  });
}

export async function getFileReferences(filePath: string): Promise<FileReference[]> {
  const response = await request<ApiFileReference[]>(
    `/api/chat/file-references?path=${encodeURIComponent(filePath)}`,
  );
  return response.map((ref) => ({
    sessionId: ref.session_id,
    sessionName: ref.session_name,
    messageId: ref.message_id,
    role: ref.role === 'ai' ? 'assistant' : 'user',
    content: ref.content,
    createdAt: formatTime(ref.created_at),
  }));
}
