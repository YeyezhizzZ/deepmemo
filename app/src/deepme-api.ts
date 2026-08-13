export type SiteInfo = {
  name: string;
  bio: string;
  avatar: string;
  public_scope_id: string;
  knowledge_version: string;
  updated_at: string;
  suggested_questions: string[];
};

export type DeepMeSession = {
  session_id: string;
  scope_id: string;
  mode: 'system' | 'temporary';
  session_name: string;
  session_topic: string;
  knowledge_version?: string;
  created_at: string;
  updated_at: string;
  expires_at: string;
};

export type DeepMeMessage = {
  message_id: string;
  session_id: string;
  role: 'user' | 'ai';
  content: string;
  answer_status: string;
  knowledge_scope_id?: string;
  knowledge_version?: string;
  created_at: string;
};

export type DeepMeCitation = {
  local_id: number;
  evidence_id: string;
  scope_id: string;
  knowledge_version: string;
  file_path: string;
  display_name?: string;
  source_type: string;
  start_line: number;
  end_line: number;
  page_start?: number;
  page_end?: number;
  content_hash?: string;
  content: string;
};

export type WorkspaceFile = {
  file_id: string;
  original_name: string;
  content_type: string;
  byte_size: number;
  sha256: string;
  status: 'pending' | 'parsing' | 'ready' | 'error';
  error_code?: string;
};

export type Workspace = {
  workspace_id: string;
  scope_id: string;
  status: 'empty' | 'processing' | 'ready' | 'error' | 'deleting' | 'deleted';
  knowledge_version?: string;
  expires_at: string;
  files: WorkspaceFile[];
};

export type StreamMeta = {
  session_id: string;
  scope_id: string;
  knowledge_version: string;
};

export type StreamDone = {
  message_id: string;
  answer_status: string;
  citation_count: number;
  created_at: string;
};

const API_ROOT = '/api/v1';

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_ROOT}${path}`, {
    credentials: 'same-origin',
    ...options,
    headers: {
      ...(options?.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }),
      ...options?.headers,
    },
  });
  if (!response.ok) {
    let message = `HTTP ${response.status}`;
    try {
      const body = (await response.json()) as {
        detail?: string | { code?: string; message?: string };
      };
      if (typeof body.detail === 'string') {
        message = body.detail;
      } else if (body.detail) {
        message = body.detail.message ?? body.detail.code ?? message;
      }
    } catch {
      // Keep the status fallback.
    }
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}

export function getSite(): Promise<SiteInfo> {
  return request<SiteInfo>('/site');
}

export function createSession(
  mode: 'system' | 'temporary',
  workspaceId?: string,
): Promise<DeepMeSession> {
  return request<DeepMeSession>('/sessions', {
    method: 'POST',
    body: JSON.stringify({
      mode,
      workspace_id: workspaceId ?? null,
    }),
  });
}

export function getMessages(sessionId: string): Promise<DeepMeMessage[]> {
  return request<DeepMeMessage[]>(`/sessions/${encodeURIComponent(sessionId)}/messages`);
}

export async function getCitations(messageId: string): Promise<DeepMeCitation[]> {
  const response = await request<{ citations: DeepMeCitation[] }>(
    `/messages/${encodeURIComponent(messageId)}/citations`,
  );
  return response.citations;
}

export function createWorkspace(): Promise<Workspace> {
  return request<Workspace>('/workspaces', { method: 'POST' });
}

export function getWorkspace(workspaceId: string): Promise<Workspace> {
  return request<Workspace>(`/workspaces/${encodeURIComponent(workspaceId)}`);
}

export async function uploadWorkspaceFiles(
  workspaceId: string,
  files: File[],
): Promise<void> {
  const form = new FormData();
  files.forEach((file) => form.append('files', file));
  await request(`/workspaces/${encodeURIComponent(workspaceId)}/files`, {
    method: 'POST',
    body: form,
  });
}

export async function deleteWorkspace(workspaceId: string): Promise<void> {
  await request(`/workspaces/${encodeURIComponent(workspaceId)}`, {
    method: 'DELETE',
  });
}

export async function streamMessage(
  sessionId: string,
  userMessage: string,
  handlers: {
    onMeta?: (meta: StreamMeta) => void;
    onToken: (token: string) => void;
    onDone: (done: StreamDone) => void;
  },
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch(`${API_ROOT}/chat/stream`, {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      session_id: sessionId,
      user_message: userMessage,
    }),
    signal,
  });
  if (!response.ok) {
    let message = `HTTP ${response.status}`;
    try {
      const body = (await response.json()) as {
        detail?: string | { code?: string };
      };
      message =
        typeof body.detail === 'string'
          ? body.detail
          : body.detail?.code ?? message;
    } catch {
      // Keep the status fallback.
    }
    throw new Error(message);
  }
  const reader = response.body?.getReader();
  if (!reader) throw new Error('stream_unavailable');
  const decoder = new TextDecoder();
  let buffer = '';

  const handleBlock = (block: string) => {
    const lines = block.split(/\r?\n/);
    const event = lines.find((line) => line.startsWith('event:'))?.slice(6).trim();
    const data = lines
      .filter((line) => line.startsWith('data:'))
      .map((line) => line.slice(5).trim())
      .join('\n');
    if (!event || !data) return;
    const payload = JSON.parse(data) as Record<string, unknown>;
    if (event === 'meta') handlers.onMeta?.(payload as StreamMeta);
    if (event === 'token') handlers.onToken(String(payload.content ?? ''));
    if (event === 'done') handlers.onDone(payload as StreamDone);
    if (event === 'error') {
      throw new Error(String(payload.message ?? payload.code ?? 'answer_failed'));
    }
  };

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const blocks = buffer.split(/\r?\n\r?\n/);
    buffer = blocks.pop() ?? '';
    blocks.forEach(handleBlock);
  }
  buffer += decoder.decode();
  if (buffer.trim()) handleBlock(buffer);
}
