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
  ApiKnowledgeCard,
  KnowledgeCard,
  KnowledgeHealth,
  ApiRepoWikiPage,
  RepoWikiPage,
  ApiKnowledgeViewModel,
  ApiKnowledgeHtmlPage,
  ApiKnowledgeReviewItem,
  ApiKnowledgeRelationNode,
  ApiKnowledgeCardSummary,
  KnowledgeViewModel,
  KnowledgeHtmlPage,
  KnowledgeReviewItem,
  KnowledgeRelationNode,
  KnowledgeCardSummary,
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
    sessionTopic: session.session_topic,
    sessionSummary: session.session_summary,
    createdAt: formatTime(session.created_at),
    updatedAt: formatTime(session.updated_at),
    createdAtIso: session.created_at,
    updatedAtIso: session.updated_at,
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
    modifiedAt: node.modified,
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

function mapKnowledgeCard(card: ApiKnowledgeCard): KnowledgeCard {
  return {
    id: card.id,
    slug: card.slug,
    title: card.title,
    type: card.type,
    density: card.density,
    definition: card.definition,
    keyFacts: card.key_facts,
    sources: card.sources,
    relatedCards: card.related_cards,
    tags: card.tags,
    aliases: card.aliases,
    createdAt: card.created_at,
    updatedAt: card.updated_at,
    updateCount: card.update_count,
    stalenessScore: card.staleness_score,
    humanEdited: card.human_edited,
    humanEditedFields: card.human_edited_fields,
    confidence: card.confidence,
    provenanceState: card.provenance_state,
    contradictedBy: card.contradicted_by,
    orphaned: card.orphaned,
    modelId: card.model_id,
    promptVersion: card.prompt_version,
  };
}

function mapRepoWikiPage(page: ApiRepoWikiPage): RepoWikiPage {
  return {
    slug: page.slug,
    title: page.title,
    content: page.content,
    cardSlugs: page.card_slugs,
    path: page.path,
  };
}

function mapKnowledgeHtmlPage(page: ApiKnowledgeHtmlPage): KnowledgeHtmlPage {
  return {
    slug: page.slug,
    title: page.title,
    path: page.path,
    summary: page.summary,
    cardSlugs: page.card_slugs,
    sections: page.sections.map((section) => ({
      cardSlug: section.card_slug,
      title: section.title,
      type: section.type,
      definition: section.definition,
      keyFacts: section.key_facts,
      sources: section.sources,
      relatedCards: section.related_cards,
      tags: section.tags,
    })),
  };
}

function mapKnowledgeReviewItem(item: ApiKnowledgeReviewItem): KnowledgeReviewItem {
  return {
    id: item.id,
    kind: item.kind,
    severity: item.severity,
    title: item.title,
    summary: item.summary,
    cardSlugs: item.card_slugs,
    sourcePaths: item.source_paths,
    suggestedAction: item.suggested_action,
    status: item.status,
    updatedAt: item.updated_at ?? undefined,
    rewrite: item.rewrite
      ? {
          field: item.rewrite.field,
          instruction: item.rewrite.instruction,
          proposedDefinition: item.rewrite.proposed_definition,
        }
      : undefined,
  };
}

function mapKnowledgeRelationNode(node: ApiKnowledgeRelationNode): KnowledgeRelationNode {
  return {
    id: node.id,
    title: node.title,
    type: node.type,
    tags: node.tags,
    sourceCount: node.source_count,
    degreeHint: node.degree_hint,
  };
}

function mapKnowledgeCardSummary(card: ApiKnowledgeCardSummary): KnowledgeCardSummary {
  return {
    slug: card.slug,
    title: card.title,
    type: card.type,
    definition: card.definition,
    tags: card.tags,
    sourceCount: card.source_count,
    stalenessScore: card.staleness_score,
    humanEdited: card.human_edited,
    humanEditedFields: card.human_edited_fields,
  };
}

function mapKnowledgeViewModel(view: ApiKnowledgeViewModel): KnowledgeViewModel {
  return {
    generatedAt: view.generated_at,
    stats: view.stats,
    overview: view.overview,
    pages: view.pages.map(mapKnowledgeHtmlPage),
    cards: view.cards.map(mapKnowledgeCardSummary),
    reviewQueue: view.review_queue.map(mapKnowledgeReviewItem),
    graph: {
      nodes: view.graph.nodes.map(mapKnowledgeRelationNode),
      edges: view.graph.edges,
    },
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

export async function listKnowledgeCards(): Promise<KnowledgeCard[]> {
  const response = await request<{ cards: ApiKnowledgeCard[] }>('/api/knowledge/cards');
  return response.cards.map(mapKnowledgeCard);
}

export async function updateKnowledgeCard(slug: string, updates: Partial<Pick<KnowledgeCard, 'title' | 'definition' | 'keyFacts' | 'tags' | 'aliases' | 'relatedCards'>>): Promise<KnowledgeCard> {
  const payload: Record<string, unknown> = {};
  if (updates.title !== undefined) payload.title = updates.title;
  if (updates.definition !== undefined) payload.definition = updates.definition;
  if (updates.keyFacts !== undefined) payload.key_facts = updates.keyFacts;
  if (updates.tags !== undefined) payload.tags = updates.tags;
  if (updates.aliases !== undefined) payload.aliases = updates.aliases;
  if (updates.relatedCards !== undefined) payload.related_cards = updates.relatedCards;
  const response = await request<ApiKnowledgeCard>(`/api/knowledge/cards/${encodeURIComponent(slug)}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  });
  return mapKnowledgeCard(response);
}

export async function compileKnowledge(): Promise<{
  card_slugs: string[];
  compiled_files: string[];
  skipped_files: string[];
  deleted_files: string[];
  candidate_ids: string[];
  warnings: string[];
  errors: string[];
  prompt_version: string;
}> {
  return request<{
    card_slugs: string[];
    compiled_files: string[];
    skipped_files: string[];
    deleted_files: string[];
    candidate_ids: string[];
    warnings: string[];
    errors: string[];
    prompt_version: string;
  }>('/api/knowledge/compile', { method: 'POST' });
}

export async function maintainKnowledge(): Promise<KnowledgeHealth> {
  return request<KnowledgeHealth>('/api/knowledge/maintain', { method: 'POST' });
}

export async function getKnowledgeHealth(): Promise<KnowledgeHealth> {
  return request<KnowledgeHealth>('/api/knowledge/health');
}

export async function rebuildRepoWiki(): Promise<{ pages: string[]; page_count: number }> {
  return request<{ pages: string[]; page_count: number }>('/api/knowledge/repowiki/rebuild', { method: 'POST' });
}

export async function listRepoWikiPages(): Promise<RepoWikiPage[]> {
  const response = await request<{ pages: ApiRepoWikiPage[] }>('/api/knowledge/repowiki/pages');
  return response.pages.map(mapRepoWikiPage);
}

export async function getRepoWikiPage(slug: string): Promise<RepoWikiPage> {
  const response = await request<ApiRepoWikiPage>(`/api/knowledge/repowiki/pages/${encodeURIComponent(slug)}`);
  return mapRepoWikiPage(response);
}

export async function getKnowledgeView(): Promise<KnowledgeViewModel> {
  const response = await request<ApiKnowledgeViewModel>('/api/knowledge/view');
  return mapKnowledgeViewModel(response);
}

export async function listKnowledgeViewPages(): Promise<KnowledgeHtmlPage[]> {
  const response = await request<{ pages: ApiKnowledgeHtmlPage[] }>('/api/knowledge/view/pages');
  return response.pages.map(mapKnowledgeHtmlPage);
}

export async function getKnowledgeViewPage(slug: string): Promise<KnowledgeHtmlPage> {
  const response = await request<ApiKnowledgeHtmlPage>(`/api/knowledge/view/pages/${encodeURIComponent(slug)}`);
  return mapKnowledgeHtmlPage(response);
}

export async function listKnowledgeReviewItems(): Promise<KnowledgeReviewItem[]> {
  const response = await request<{ items: ApiKnowledgeReviewItem[] }>('/api/knowledge/view/review');
  return response.items.map(mapKnowledgeReviewItem);
}

export async function confirmKnowledgeReviewItem(itemId: string): Promise<KnowledgeReviewItem> {
  const response = await request<ApiKnowledgeReviewItem>(`/api/knowledge/view/review/${encodeURIComponent(itemId)}/confirm`, {
    method: 'POST',
  });
  return mapKnowledgeReviewItem(response);
}

export async function hideKnowledgeReviewItem(itemId: string): Promise<KnowledgeReviewItem> {
  const response = await request<ApiKnowledgeReviewItem>(`/api/knowledge/view/review/${encodeURIComponent(itemId)}/hide`, {
    method: 'POST',
  });
  return mapKnowledgeReviewItem(response);
}

export async function rewriteKnowledgeReviewItem(itemId: string, instruction: string): Promise<KnowledgeReviewItem> {
  const response = await request<ApiKnowledgeReviewItem>(`/api/knowledge/view/review/${encodeURIComponent(itemId)}/rewrite`, {
    method: 'POST',
    body: JSON.stringify({ instruction }),
  });
  return mapKnowledgeReviewItem(response);
}

export async function applyKnowledgeReviewItem(itemId: string): Promise<KnowledgeReviewItem> {
  const response = await request<ApiKnowledgeReviewItem>(`/api/knowledge/view/review/${encodeURIComponent(itemId)}/apply`, {
    method: 'POST',
  });
  return mapKnowledgeReviewItem(response);
}

export async function pinKnowledgeCardField(slug: string, field: string): Promise<KnowledgeCard> {
  const response = await request<ApiKnowledgeCard>(`/api/knowledge/view/cards/${encodeURIComponent(slug)}/pin`, {
    method: 'POST',
    body: JSON.stringify({ field }),
  });
  return mapKnowledgeCard(response);
}
