export type Session = {
  sessionId: string;
  sessionName: string;
  messageIds: string[];
  sessionTopic?: string;
  sessionSummary?: string;
  createdAt: string;
  updatedAt: string;
  createdAtIso: string;
  updatedAtIso: string;
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
  modifiedAt?: string;
  children?: FsNode[];
};

export type ApiSessionResponse = {
  session_id: string;
  session_name: string;
  message_ids: string[];
  session_topic?: string;
  session_summary?: string;
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
  modified?: string;
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

export type EvidenceSource = {
  path: string;
  evidence: string;
  confidence: number;
  source_id: string;
  source_hash: string;
  start_line: number;
  end_line: number;
};

export type KnowledgeCard = {
  id: string;
  slug: string;
  title: string;
  type: 'source' | 'entity' | 'concept' | 'decision' | 'pattern' | 'lesson' | 'synthesis' | 'query';
  density: 'high' | 'medium' | 'low';
  definition: string;
  keyFacts: string[];
  sources: EvidenceSource[];
  relatedCards: string[];
  tags: string[];
  aliases: string[];
  createdAt: string;
  updatedAt: string;
  updateCount: number;
  stalenessScore: number;
  humanEdited: boolean;
  humanEditedFields: string[];
  confidence: number;
  provenanceState: 'extracted' | 'merged' | 'inferred' | 'ambiguous' | 'human';
  contradictedBy: string[];
  orphaned: boolean;
  modelId: string;
  promptVersion: string;
};

export type KnowledgeHealth = {
  stats: {
    total_cards: number;
    by_type: Record<string, number>;
    avg_staleness: number;
    last_compile?: string | null;
  };
  orphan_cards: string[];
  conflict_pairs?: string[][];
  merge_suggestions?: string[][];
  index_path?: string;
};

export type RepoWikiPage = {
  slug: string;
  title: string;
  content: string;
  cardSlugs: string[];
  path: string;
};

export type KnowledgeView = 'overview' | 'reader' | 'review' | 'cards';

export type KnowledgeViewStats = KnowledgeHealth['stats'] & {
  review_open: number;
  page_count: number;
  relation_count: number;
};

export type KnowledgeOverviewSection = {
  id: string;
  title: string;
  value: number;
  summary: string;
};

export type KnowledgeHtmlSection = {
  cardSlug: string;
  title: string;
  type: KnowledgeCard['type'];
  definition: string;
  keyFacts: string[];
  sources: EvidenceSource[];
  relatedCards: string[];
  tags: string[];
};

export type KnowledgeHtmlPage = {
  slug: string;
  title: string;
  path: string;
  summary: string;
  cardSlugs: string[];
  sections: KnowledgeHtmlSection[];
};

export type KnowledgeCardSummary = {
  slug: string;
  title: string;
  type: KnowledgeCard['type'];
  definition: string;
  tags: string[];
  sourceCount: number;
  stalenessScore: number;
  humanEdited: boolean;
  humanEditedFields: string[];
};

export type KnowledgeReviewItem = {
  id: string;
  kind:
    | 'compile_candidate'
    | 'new_card'
    | 'changed_card'
    | 'stale_card'
    | 'conflict'
    | 'merge_suggestion'
    | 'repowiki_section';
  severity: 'high' | 'medium' | 'low';
  title: string;
  summary: string;
  cardSlugs: string[];
  sourcePaths: string[];
  suggestedAction: 'confirm' | 'pin' | 'rewrite' | 'merge' | 'hide';
  status: 'open' | 'confirmed' | 'hidden' | 'rewritten';
  updatedAt?: string;
  rewrite?: {
    field: string;
    instruction: string;
    proposedDefinition: string;
  };
};

export type KnowledgeRelationNode = {
  id: string;
  title: string;
  type: KnowledgeCard['type'];
  tags: string[];
  sourceCount: number;
  degreeHint: number;
};

export type KnowledgeRelationEdge = {
  from: string;
  to: string;
  reason: 'related_card' | 'contradicts';
  confidence?: number;
};

export type KnowledgeRelationGraph = {
  nodes: KnowledgeRelationNode[];
  edges: KnowledgeRelationEdge[];
};

export type KnowledgeViewModel = {
  generatedAt: string;
  stats: KnowledgeViewStats;
  overview: KnowledgeOverviewSection[];
  pages: KnowledgeHtmlPage[];
  cards: KnowledgeCardSummary[];
  reviewQueue: KnowledgeReviewItem[];
  graph: KnowledgeRelationGraph;
};

export type ApiKnowledgeCard = {
  id: string;
  slug: string;
  title: string;
  type: KnowledgeCard['type'];
  density: KnowledgeCard['density'];
  definition: string;
  key_facts: string[];
  sources: EvidenceSource[];
  related_cards: string[];
  tags: string[];
  aliases: string[];
  created_at: string;
  updated_at: string;
  update_count: number;
  staleness_score: number;
  human_edited: boolean;
  human_edited_fields: string[];
  confidence: number;
  provenance_state: KnowledgeCard['provenanceState'];
  contradicted_by: string[];
  orphaned: boolean;
  model_id: string;
  prompt_version: string;
};

export type ApiRepoWikiPage = {
  slug: string;
  title: string;
  content: string;
  card_slugs: string[];
  path: string;
};

export type ApiKnowledgeHtmlSection = {
  card_slug: string;
  title: string;
  type: KnowledgeCard['type'];
  definition: string;
  key_facts: string[];
  sources: EvidenceSource[];
  related_cards: string[];
  tags: string[];
};

export type ApiKnowledgeHtmlPage = {
  slug: string;
  title: string;
  path: string;
  summary: string;
  card_slugs: string[];
  sections: ApiKnowledgeHtmlSection[];
};

export type ApiKnowledgeCardSummary = {
  slug: string;
  title: string;
  type: KnowledgeCard['type'];
  definition: string;
  tags: string[];
  source_count: number;
  staleness_score: number;
  human_edited: boolean;
  human_edited_fields: string[];
};

export type ApiKnowledgeReviewItem = {
  id: string;
  kind: KnowledgeReviewItem['kind'];
  severity: KnowledgeReviewItem['severity'];
  title: string;
  summary: string;
  card_slugs: string[];
  source_paths: string[];
  suggested_action: KnowledgeReviewItem['suggestedAction'];
  status: KnowledgeReviewItem['status'];
  updated_at?: string | null;
  rewrite?: {
    field: string;
    instruction: string;
    proposed_definition: string;
  } | null;
};

export type ApiKnowledgeRelationNode = {
  id: string;
  title: string;
  type: KnowledgeCard['type'];
  tags: string[];
  source_count: number;
  degree_hint: number;
};

export type ApiKnowledgeRelationEdge = {
  from: string;
  to: string;
  reason: KnowledgeRelationEdge['reason'];
  confidence?: number;
};

export type ApiKnowledgeViewModel = {
  generated_at: string;
  stats: KnowledgeViewStats;
  overview: KnowledgeOverviewSection[];
  pages: ApiKnowledgeHtmlPage[];
  cards: ApiKnowledgeCardSummary[];
  review_queue: ApiKnowledgeReviewItem[];
  graph: {
    nodes: ApiKnowledgeRelationNode[];
    edges: ApiKnowledgeRelationEdge[];
  };
};

export type ApiFileReference = {
  session_id: string;
  session_name: string;
  message_id: string;
  role: 'user' | 'ai';
  content: string;
  created_at: string;
};
