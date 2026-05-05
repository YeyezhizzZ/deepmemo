export type Session = {
  sessionId: string;
  sessionName: string;
  messageIds: string[];
  createdAt: string;
  updatedAt: string;
};

export type ChatMessage = {
  id: string;
  sessionId: string;
  role: 'user' | 'assistant';
  content: string;
  createdAt: string;
};

export type Citation = {
  localId: number;
  evidenceId: string;
  filePath: string;
  content: string;
};

export type SyncStatus = 'synced' | 'dirty' | 'draft' | 'processing' | 'error';

export type ChatToolExecutionType = 'inline' | 'job';

export type ChatTool = {
  id: string;
  name: string;
  description: string;
  executionType: ChatToolExecutionType;
};

export type ChatToolSelection = {
  toolId: string;
  scope?: 'next_message' | 'session';
};

export type FsNode = {
  id: string;
  name: string;
  path: string;
  type: 'file' | 'directory';
  syncStatus: SyncStatus;
  children?: FsNode[];
};

export type ApiSessionResponse = {
  session_id: string;
  session_name: string;
  message_ids: string[];
  created_at: string;
  updated_at: string;
};

export type ApiMessageResponse = {
  message_id: string;
  session_id: string;
  role: 'user' | 'ai';
  content: string;
  created_at: string;
};

export type ApiCitationResponse = {
  local_id: number;
  evidence_id: string;
  file_path: string;
  content: string;
};

export type ApiCitationsResponse = {
  message_id: string;
  citations: ApiCitationResponse[];
};

export type ApiSyncStatus = SyncStatus;

export type ApiChatToolResponse = {
  id: string;
  name: string;
  description: string;
  execution_type: ChatToolExecutionType;
};

export type ApiFsNode = {
  name: string;
  path: string;
  type: 'file' | 'directory';
  sync_status: ApiSyncStatus;
  children?: ApiFsNode[];
};

export type ApiFileContentResponse = {
  path: string;
  content: string;
};

export type ApiFileWriteResponse = {
  message: string;
  file_path: string;
  file_hash: string;
  sync_status: ApiSyncStatus;
  last_modified: string;
};

export type ApiFileMoveResponse = {
  message: string;
  old_path: string;
  new_path: string;
  file_hash: string;
  sync_status: ApiSyncStatus;
};

export type ApiSyncStatusResponse = {
  message: string;
  path: string;
  sync_status: ApiSyncStatus;
};

export type AutoDraftResponse = {
  sourceFile?: string;
  draft: string;
  message: string;
};

export type FileReference = {
  sessionId: string;
  sessionName: string;
  messageId: string;
  role: 'user' | 'assistant';
  content: string;
  createdAt: string;
};

export type ApiFileReference = {
  session_id: string;
  session_name: string;
  message_id: string;
  role: 'user' | 'ai';
  content: string;
  created_at: string;
};
