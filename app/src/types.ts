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

export type WikiPageSummary = {
  path: string;
  title: string;
  type: string;
  status: string;
  tags: string[];
  sources: string[];
  related: string[];
  lastUpdated: string;
  summary: string;
};

export type WikiPageDetail = WikiPageSummary & {
  body: string;
  content: string;
};

export type WikiGraphNode = {
  path: string;
  title: string;
  type: string;
  status: string;
  tags: string[];
  sources: string[];
  related: string[];
  lastUpdated: string;
  summary: string;
  body: string;
  communityId: string;
  incoming: number;
  outgoing: number;
  degree: number;
  neighbors: string[];
  sourcePaths: string[];
  subtype: string;
};

export type WikiGraphEdge = {
  from: string;
  to: string;
  weight: number;
  directLink: number;
  sourceOverlap: number;
  adamicAdar: number;
  typeAffinity: number;
};

export type WikiCommunity = {
  id: string;
  title: string;
  summary: string;
  nodePaths: string[];
  hubPath: string;
  updatedAt: string;
  topTags: string[];
  nodeCount: number;
  edgeCount: number;
};

export type WikiGraphMeta = {
  buildDate: string;
  sourceDir: string;
  totalNodes: number;
  totalEdges: number;
  totalCommunities: number;
  degraded: boolean;
  insightsDegraded: boolean;
};

export type WikiGraphInsights = {
  surprisingConnections: Array<{
    from: string;
    to: string;
    weight: number;
    fromCommunity?: string;
    toCommunity?: string;
  }>;
  isolatedNodes: Array<{
    id: string;
    label: string;
    degree: number;
    community?: string;
  }>;
  bridgeNodes: Array<{
    id: string;
    label: string;
    community?: string;
    connectedCommunities: string[];
    communityCount: number;
  }>;
  sparseCommunities: Array<{
    id: string;
    label: string;
    nodeCount: number;
    density: number;
    members: string[];
    internalEdges: number;
  }>;
  meta: {
    degraded: boolean;
    nodeCount: number;
    edgeCount: number;
    maxInsightNodes: number;
    maxInsightEdges: number;
  };
};

export type WikiGraph = {
  meta: WikiGraphMeta;
  communities: WikiCommunity[];
  nodes: WikiGraphNode[];
  nodeMap: Map<string, WikiGraphNode>;
  edges: WikiGraphEdge[];
  backlinks: Map<string, string[]>;
  insights: WikiGraphInsights;
};

export type ApiFileReference = {
  session_id: string;
  session_name: string;
  message_id: string;
  role: 'user' | 'ai';
  content: string;
  created_at: string;
};

export type ApiWikiPageSummary = {
  path: string;
  title: string;
  type: string;
  status: string;
  tags: string[];
  sources: string[];
  related: string[];
  last_updated: string;
  summary: string;
};

export type ApiWikiPageDetail = ApiWikiPageSummary & {
  body: string;
  content: string;
};

export type ApiWikiGraphNode = {
  path: string;
  title: string;
  type: string;
  status: string;
  tags: string[];
  sources: string[];
  related: string[];
  last_updated: string;
  summary: string;
  body: string;
  community_id: string;
  incoming: number;
  outgoing: number;
  degree: number;
  neighbors: string[];
  source_paths: string[];
  subtype: string;
};

export type ApiWikiGraphEdge = {
  from: string;
  to: string;
  weight: number;
  direct_link: number;
  source_overlap: number;
  adamic_adar: number;
  type_affinity: number;
};

export type ApiWikiGraphCommunity = {
  id: string;
  title: string;
  summary: string;
  node_paths: string[];
  hub_path: string;
  updated_at: string;
  top_tags: string[];
  node_count: number;
  edge_count: number;
};

export type ApiWikiGraphResponse = {
  meta: {
    build_date: string;
    source_dir: string;
    total_nodes: number;
    total_edges: number;
    total_communities: number;
    degraded: boolean;
    insights_degraded: boolean;
  };
  nodes: ApiWikiGraphNode[];
  edges: ApiWikiGraphEdge[];
  communities: ApiWikiGraphCommunity[];
  insights: {
    surprising_connections: Array<{
      from: string;
      to: string;
      weight: number;
      from_community?: string;
      to_community?: string;
    }>;
    isolated_nodes: Array<{
      id: string;
      label: string;
      degree: number;
      community?: string;
    }>;
    bridge_nodes: Array<{
      id: string;
      label: string;
      community?: string;
      connected_communities: string[];
      community_count: number;
    }>;
    sparse_communities: Array<{
      id: string;
      label: string;
      node_count: number;
      density: number;
      members: string[];
      internal_edges: number;
    }>;
    meta: {
      degraded: boolean;
      node_count: number;
      edge_count: number;
      max_insight_nodes: number;
      max_insight_edges: number;
    };
  };
};

export type ApiWikiRebuildResponse = {
  message: string;
  sources: number;
  entities: number;
  concepts: number;
  syntheses: number;
  total_pages: number;
  changed_sources: number;
  reused_sources: number;
};
