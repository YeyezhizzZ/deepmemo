import { useEffect, useMemo, useRef, useState } from 'react';
import Vditor from 'vditor';
import 'vditor/dist/index.css';
import {
  AlertCircle,
  AtSign,
  Bot,
  Check,
  ChevronDown,
  ChevronRight,
  Clock3,
  Code2,
  Command,
  Database,
  FilePlus2,
  FileText,
  Folder,
  FolderOpen,
  FolderPlus,
  HardDrive,
  Link2,
  MessageSquare,
  MessageSquarePlus,
  MoreHorizontal,
  Network,
  RefreshCw,
  Send,
  Sparkles,
  Trash2,
  WandSparkles,
  Wrench,
  X,
} from 'lucide-react';
import {
  createDiaryAutoDraft,
  createDirectory,
  createFile,
  createSession,
  deleteSession,
  getFileContent,
  getFileReferences,
  getFileTree,
  getHealth,
  getChatTools,
  getMessageCitations,
  listMessages,
  listSessions,
  moveFile,
  sendMessage,
  sendMessageStream,
  updateFileSyncStatus,
  writeFile,
} from './api';
import type { ChatMessage, ChatTool, Citation, FileReference, FsNode, Session, SyncStatus } from './types';

const exampleQuestions = [
  'DeepMemo 的产品想法是什么？',
  '最近的学习记录里有哪些工程经验？',
  '我关于 LLM-Spine 记录了哪些想法？',
];

type WorkspaceMode = 'editor' | 'qa';
type FileNode = FsNode;

type SourceChunk = {
  index: number;
  path: string;
  startLine: number;
  endLine: number;
  score?: number;
  query?: string;
  excerpt: string;
};

type SourcePanelItem = SourceChunk & {
  messageId: string;
  evidenceId?: string;
  modified?: string;
};

type ParsedMarkdown = {
  bodyLines: string[];
  sources: SourceChunk[];
};

function trimTrailingBlankLines(lines: string[]): string[] {
  const next = [...lines];
  while (next.length > 0 && next[next.length - 1].trim() === '') {
    next.pop();
  }
  return next;
}

function parseMarkdownWithSources(content: string): ParsedMarkdown {
  const lines = content.split('\n');
  const referenceIndex = lines.findIndex((line) => line.trim() === '## 引用');
  if (referenceIndex === -1) {
    return { bodyLines: lines, sources: [] };
  }

  const sourceHeaderPattern =
    /^\[(\d+)\]\s+(.+):(\d+)-(\d+)(?:\s+·\s+score=([0-9.]+))?(?:(?:\s+·\s+query=(.*))|(?:\s+\(query=(.*)\)))?\s*$/;
  const sources: SourceChunk[] = [];
  let current: SourceChunk | undefined;

  const pushCurrent = () => {
    if (current) {
      sources.push({
        ...current,
        excerpt: trimTrailingBlankLines(current.excerpt.split('\n')).join('\n'),
      });
    }
  };

  for (const rawLine of lines.slice(referenceIndex + 1)) {
    const line = rawLine.trimEnd();
    const match = sourceHeaderPattern.exec(line);
    if (match) {
      pushCurrent();
      const parsedScore = match[5] ? Number(match[5]) : undefined;
      current = {
        index: Number(match[1]),
        path: match[2],
        startLine: Number(match[3]),
        endLine: Number(match[4]),
        score: parsedScore !== undefined && Number.isFinite(parsedScore) ? parsedScore : undefined,
        query: match[6] ?? match[7],
        excerpt: '',
      };
      continue;
    }

    if (current && line.trim().startsWith('>')) {
      const excerptLine = line.trim().replace(/^>\s?/, '');
      current.excerpt = current.excerpt ? `${current.excerpt}\n${excerptLine}` : excerptLine;
    }
  }
  pushCurrent();

  if (sources.length === 0) {
    return { bodyLines: lines, sources: [] };
  }

  return {
    bodyLines: trimTrailingBlankLines(lines.slice(0, referenceIndex)),
    sources,
  };
}

function scoreLevel(score?: number): 'high' | 'medium' | 'low' {
  if (score === undefined || score < 0.5) return 'low';
  if (score < 0.75) return 'medium';
  return 'high';
}

function createOptimisticUserMessage(sessionId: string, content: string): ChatMessage {
  return {
    id: `local-user-${Date.now()}`,
    sessionId,
    role: 'user',
    content,
    createdAt: new Intl.DateTimeFormat('zh-CN', {
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    }).format(new Date()),
  };
}

function createSessionName(): string {
  return `会话 ${new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date())}`;
}

function collectFiles(nodes: FileNode[]): FileNode[] {
  return nodes.flatMap((node) => {
    if (node.type === 'file') return [node];
    return collectFiles(node.children ?? []);
  });
}

function findNode(nodes: FileNode[], id: string): FileNode | undefined {
  for (const node of nodes) {
    if (node.id === id) return node;
    const child = node.children ? findNode(node.children, id) : undefined;
    if (child) return child;
  }
  return undefined;
}

function findNodeByPath(nodes: FileNode[], path: string): FileNode | undefined {
  const normalized = path.replace(/^data\//, '');
  for (const node of nodes) {
    if (node.path === normalized) return node;
    const child = node.children ? findNodeByPath(node.children, normalized) : undefined;
    if (child) return child;
  }
  return undefined;
}

function countNodes(nodes: FileNode[]): { files: number; folders: number } {
  return nodes.reduce(
    (total, node) => {
      if (node.type === 'file') {
        total.files += 1;
      } else {
        total.folders += 1;
        const childCount = countNodes(node.children ?? []);
        total.files += childCount.files;
        total.folders += childCount.folders;
      }
      return total;
    },
    { files: 0, folders: 0 },
  );
}

function findFirstFile(nodes: FileNode[]): FileNode | undefined {
  const allFiles = collectFiles(nodes);
  return allFiles.find((node) => node.path === 'ideas/DeepMemo.md')
    ?? allFiles.find((node) => node.name.endsWith('.md'))
    ?? allFiles[0];
}

function updateNodeStatus(nodes: FileNode[], path: string, syncStatus: SyncStatus): FileNode[] {
  return nodes.map((node) => {
    if (node.path === path) {
      return { ...node, syncStatus };
    }
    if (node.children) {
      return { ...node, children: updateNodeStatus(node.children, path, syncStatus) };
    }
    return node;
  });
}

function deriveEntityOptions(nodes: FileNode[], content: string): string[] {
  const fileNames = collectFiles(nodes)
    .filter((node) => node.path.startsWith('memory/') || node.path.startsWith('ideas/'))
    .map((node) => node.name.replace(/\.md$/i, '').trim())
    .filter(Boolean);
  const wikiLinks = Array.from(content.matchAll(/\[\[([^\]]+)\]\]/g), (match) => match[1].trim());
  return Array.from(new Set([...wikiLinks, ...fileNames])).slice(0, 12);
}

function formatEditorMarkdown(value: string): string {
  return value
    .split('\n')
    .map((line) => line.trimEnd())
    .join('\n')
    .replace(/\n{3,}/g, '\n\n')
    .trimStart();
}

function VditorMarkdownEditor({
  value,
  onChange,
  onSave,
}: {
  value: string;
  onChange: (value: string) => void;
  onSave: () => void;
}) {
  const mountRef = useRef<HTMLDivElement>(null);
  const editorRef = useRef<Vditor>();
  const latestValueRef = useRef(value);
  const onChangeRef = useRef(onChange);
  const onSaveRef = useRef(onSave);

  useEffect(() => {
    onChangeRef.current = onChange;
  }, [onChange]);

  useEffect(() => {
    onSaveRef.current = onSave;
  }, [onSave]);

  useEffect(() => {
    if (!mountRef.current) return undefined;

    const editor = new Vditor(mountRef.current, {
      value,
      mode: 'wysiwyg',
      cdn: '/vditor',          // 从本地 public/vditor 加载资源，避免依赖 unpkg CDN
      height: '100%',
      minHeight: 0,
      placeholder: 'Markdown',
      cache: { enable: false },
      toolbar: [],
      counter: { enable: false },
      preview: {
        markdown: {
          autoSpace: true,
        },
      },
      input: (nextValue) => {
        latestValueRef.current = nextValue;
        onChangeRef.current(nextValue);
      },
      keydown: (event) => {
        if ((event.ctrlKey || event.metaKey) && event.key === 's') {
          event.preventDefault();
          onSaveRef.current();
        }
      },
      after: () => {
        editorRef.current = editor;
      },
    });

    editorRef.current = editor;

    return () => {
      editor.destroy();
      if (editorRef.current === editor) {
        editorRef.current = undefined;
      }
    };
  }, []);

  useEffect(() => {
    const editor = editorRef.current;
    if (!editor || latestValueRef.current === value) return;
    latestValueRef.current = value;
    editor.setValue(value, true);
  }, [value]);

  return <div className="vditor-editor-host" ref={mountRef} />;
}

function getMessageSources(message?: ChatMessage): SourceChunk[] {
  if (!message || message.role !== 'assistant') return [];
  return parseMarkdownWithSources(message.content).sources;
}

function mapCitationsToSources(messageId: string, citations: Citation[]): SourcePanelItem[] {
  return citations.map((citation) => ({
    messageId,
    index: citation.localId,
    path: citation.filePath,
    startLine: 0,
    endLine: 0,
    evidenceId: citation.evidenceId,
    excerpt: citation.content,
  }));
}

function mapParsedSources(messageId: string, sources: SourceChunk[]): SourcePanelItem[] {
  return sources.map((source) => ({ ...source, messageId }));
}

function StatusDot({ status }: { status?: SyncStatus }) {
  const labelMap: Record<SyncStatus, string> = {
    synced: '已同步',
    dirty: '有变动',
    draft: '草稿',
    processing: '处理中',
    error: '错误',
  };
  const nextStatus = status ?? 'draft';
  return (
    <span
      className={`status-dot status-dot--${nextStatus}`}
      title={labelMap[nextStatus]}
    />
  );
}

function DataExplorer({
  files,
  activeFileId,
  expanded,
  refreshing,
  onSelectFile,
  onToggleFolder,
  onRenameNode,
  onCreateFile,
  onCreateFolder,
  onRefresh,
}: {
  files: FileNode[];
  activeFileId?: string;
  expanded: Set<string>;
  refreshing: boolean;
  onSelectFile: (id: string) => void;
  onToggleFolder: (id: string) => void;
  onRenameNode: (node: FileNode) => void;
  onCreateFile: () => void;
  onCreateFolder: () => void;
  onRefresh: () => void;
}) {
  const counts = useMemo(() => countNodes(files), [files]);

  return (
    <aside className="data-explorer">
      <div className="data-explorer__header">
        <div className="brand">
          <div className="brand__mark">D</div>
          <div className="brand__copy">
            <div className="brand__name">DeepMemo</div>
            <div className="brand__env">Agent Workspace</div>
          </div>
        </div>
      </div>

      <div className="explorer-toolbar" aria-label="资源操作">
        <button type="button" title="新建文件" onClick={onCreateFile}>
          <FilePlus2 size={16} />
          <span>File</span>
        </button>
        <button type="button" title="新建文件夹" onClick={onCreateFolder}>
          <FolderPlus size={16} />
          <span>Folder</span>
        </button>
        <button type="button" title="刷新" onClick={onRefresh} disabled={refreshing}>
          <RefreshCw size={16} className={refreshing ? 'spin' : ''} />
        </button>
      </div>

      <nav className="file-tree" aria-label="data 文件树">
        {files.map((node) => (
          <FileTreeNode
            key={node.id}
            node={node}
            level={0}
            activeFileId={activeFileId}
            expanded={expanded}
            onSelectFile={onSelectFile}
            onToggleFolder={onToggleFolder}
            onRenameNode={onRenameNode}
            onCreateFile={onCreateFile}
          />
        ))}
      </nav>

      <div className="data-explorer__footer">
        <div className="storage-card">
          <HardDrive size={16} />
          <div>
            <strong>38.4 MB</strong>
            <span>{counts.files} files · {counts.folders} folders</span>
          </div>
        </div>
      </div>
    </aside>
  );
}

function FileTreeNode({
  node,
  level,
  activeFileId,
  expanded,
  onSelectFile,
  onToggleFolder,
  onRenameNode,
  onCreateFile,
}: {
  node: FileNode;
  level: number;
  activeFileId?: string;
  expanded: Set<string>;
  onSelectFile: (id: string) => void;
  onToggleFolder: (id: string) => void;
  onRenameNode: (node: FileNode) => void;
  onCreateFile: (parentPath: string) => void;
}) {
  const isFolder = node.type === 'directory';
  const isExpanded = expanded.has(node.id);
  const isActive = node.id === activeFileId;

  const handleClick = () => {
    if (isFolder) {
      onToggleFolder(node.id);
    } else {
      onSelectFile(node.id);
    }
  };

  return (
    <div className="file-node">
      <button
        className={`file-node__row ${isActive ? 'file-node__row--active' : ''}`}
        type="button"
        style={{ paddingLeft: 10 + level * 16 }}
        onClick={handleClick}
        title={node.path}
      >
        <span className="file-node__chevron">
          {isFolder ? (isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />) : null}
        </span>
        {isFolder ? (
          isExpanded ? <FolderOpen className="file-node__icon" size={16} /> : <Folder className="file-node__icon" size={16} />
        ) : (
          <FileText className="file-node__icon" size={16} />
        )}
        <span className="file-node__name">{node.name}</span>
        {!isFolder && <StatusDot status={node.syncStatus} />}
        <span className="file-node__hover-actions">
          <span role="button" tabIndex={-1} title="新建文件" onClick={(event) => {
            event.stopPropagation();
            onCreateFile(node.path);
          }}>
            <FilePlus2 size={13} />
          </span>
        </span>
      </button>
      {isFolder && isExpanded && (
        <div>
          {(node.children ?? []).map((child) => (
            <FileTreeNode
              key={child.id}
              node={child}
              level={level + 1}
              activeFileId={activeFileId}
              expanded={expanded}
              onSelectFile={onSelectFile}
              onToggleFolder={onToggleFolder}
              onRenameNode={onRenameNode}
              onCreateFile={onCreateFile}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function WorkspaceHeader({
  activeFile,
  mode,
  saving,
  onModeChange,
  onAiComplete,
  onSave,
  onFormat,
}: {
  activeFile?: FileNode;
  mode: WorkspaceMode;
  saving: boolean;
  onModeChange: (mode: WorkspaceMode) => void;
  onAiComplete: () => void;
  onSave: () => void;
  onFormat: () => void;
}) {
  return (
    <header className="workspace-header">
      <div className="path-chip" title={activeFile?.path}>
        <Database size={16} />
        <span>{activeFile ? `data/${activeFile.path}` : 'data/'}</span>
      </div>

      <div className="mode-switch" aria-label="工作模式">
        <button
          className={mode === 'editor' ? 'mode-switch__button mode-switch__button--active' : 'mode-switch__button'}
          type="button"
          onClick={() => onModeChange('editor')}
        >
          <FileText size={15} />
          编辑器模式
        </button>
        <button
          className={mode === 'qa' ? 'mode-switch__button mode-switch__button--active' : 'mode-switch__button'}
          type="button"
          onClick={() => onModeChange('qa')}
        >
          <MessageSquare size={15} />
          问答模式
        </button>
      </div>

      <div className="workspace-actions">
        <button type="button" onClick={onAiComplete}>
          <WandSparkles size={15} />
          AI 补完
        </button>
        <button type="button" onClick={onSave} disabled={saving || !activeFile}>
          <Check size={15} />
          {saving ? '保存中' : '保存'}
        </button>
        <button type="button" onClick={onFormat}>
          <Command size={15} />
          格式化
        </button>
      </div>
    </header>
  );
}

function EditorContent({
  activeFile,
  value,
  streaming,
  entityOptions,
  onChange,
  onInsertEntity,
  onSlashCommand,
  onSave,
}: {
  activeFile?: FileNode;
  value: string;
  streaming: boolean;
  entityOptions: string[];
  onChange: (value: string) => void;
  onInsertEntity: (entity: string) => void;
  onSlashCommand: (command: 'daily' | 'extract' | 'polish') => void;
  onSave: () => void;
}) {
  const atQuery = useMemo(() => {
    const match = /@([\w-]*)$/i.exec(value);
    return match?.[1] ?? undefined;
  }, [value]);
  const slashOpen = /(^|\n)\/$/i.test(value);
  const entityMatches = useMemo(() => {
    if (atQuery === undefined) return [];
    return entityOptions.filter((entity) => entity.toLowerCase().includes(atQuery.toLowerCase())).slice(0, 5);
  }, [atQuery, entityOptions]);

  return (
    <section className="editor-content">
      <div className="editor-meta">
        <div>
          <strong>{activeFile?.name ?? 'untitled.md'}</strong>
          <span>{activeFile ? `data/${activeFile.path}` : '未选择文件'} · Markdown</span>
        </div>
        <div className="editor-meta__right">
          {streaming && (
            <span className="streaming-indicator">
              <Sparkles size={14} />
              Drafting
            </span>
          )}
          <StatusDot status={activeFile?.syncStatus} />
        </div>
      </div>

      <div className="editor-surface editor-surface--live">
        <div className="editor-pane editor-pane--live">
          <div className="editor-pane__label">Markdown</div>
          <VditorMarkdownEditor
            value={value}
            onChange={onChange}
            onSave={onSave}
          />
        </div>
        {entityMatches.length > 0 && (
          <div className="floating-menu entity-menu">
            {entityMatches.map((entity) => (
              <button type="button" key={entity} onClick={() => onInsertEntity(entity)}>
                <AtSign size={14} />
                {entity}
              </button>
            ))}
          </div>
        )}
        {slashOpen && (
          <div className="floating-menu slash-menu">
            <button type="button" onClick={() => onSlashCommand('daily')}>
              <Clock3 size={14} />
              今日日记模板
            </button>
            <button type="button" onClick={() => onSlashCommand('extract')}>
              <Network size={14} />
              抽取实体关系
            </button>
            <button type="button" onClick={() => onSlashCommand('polish')}>
              <WandSparkles size={14} />
              润色选中段落
            </button>
          </div>
        )}
      </div>
    </section>
  );
}

function MarkdownLite({
  content,
  activeCitationIndex,
  onCitationHover,
  onCitationSelect,
}: {
  content: string;
  activeCitationIndex?: number;
  onCitationHover?: (index?: number) => void;
  onCitationSelect?: (index: number) => void;
}) {
  const { bodyLines, sources } = useMemo(() => parseMarkdownWithSources(content), [content]);
  const [activeSourceIndexes, setActiveSourceIndexes] = useState<Set<number>>(new Set());
  const sourceIndexes = useMemo(() => new Set(sources.map((source) => source.index)), [sources]);

  useEffect(() => {
    setActiveSourceIndexes(new Set());
  }, [content]);

  const toggleSource = (index: number) => {
    setActiveSourceIndexes((prev) => {
      const next = new Set(prev);
      if (next.has(index)) {
        next.delete(index);
      } else {
        next.add(index);
      }
      return next;
    });
  };

  const renderInlineText = (line: string, lineIndex: number) => {
    const parts = line.split(/(\[\d+\])/g);
    return parts.map((part, partIndex) => {
      const match = /^\[(\d+)\]$/.exec(part);
      const sourceIndex = match ? Number(match[1]) : undefined;
      if (sourceIndex && sourceIndexes.has(sourceIndex)) {
        const isActive = activeCitationIndex === sourceIndex || activeSourceIndexes.has(sourceIndex);
        return (
          <button
            className={`citation ${isActive ? 'citation--active' : ''}`}
            type="button"
            key={`${lineIndex}-${partIndex}-${part}`}
            onMouseEnter={() => onCitationHover?.(sourceIndex)}
            onMouseLeave={() => onCitationHover?.(undefined)}
            onClick={() => {
              toggleSource(sourceIndex);
              onCitationSelect?.(sourceIndex);
            }}
          >
            {part}
          </button>
        );
      }

      return <span key={`${lineIndex}-${partIndex}-${part}`}>{part}</span>;
    });
  };

  return (
    <div className="markdown-lite">
      {bodyLines.map((line, index) => {
        if (line.startsWith('### ')) {
          return <h3 key={`${line}-${index}`}>{renderInlineText(line.slice(4), index)}</h3>;
        }
        if (line.startsWith('## ')) {
          return <h2 key={`${line}-${index}`}>{renderInlineText(line.slice(3), index)}</h2>;
        }
        if (line.startsWith('# ')) {
          return <h1 key={`${line}-${index}`}>{renderInlineText(line.slice(2), index)}</h1>;
        }
        if (line.startsWith('- ')) {
          return (
            <p key={`${line}-${index}`} className="markdown-lite__list">
              • {renderInlineText(line.slice(2), index)}
            </p>
          );
        }
        if (line.trim() === '') {
          return <div className="markdown-lite__gap" key={`gap-${index}`} />;
        }
        return <p key={`${line}-${index}`}>{renderInlineText(line, index)}</p>;
      })}
    </div>
  );
}

function MessageList({
  messages,
  loading,
  booting,
  activeMessageId,
  activeCitationIndex,
  onAskExample,
  onActivateMessage,
  onCitationHover,
}: {
  messages: ChatMessage[];
  loading: boolean;
  booting: boolean;
  activeMessageId?: string;
  activeCitationIndex?: number;
  onAskExample: (question: string) => void;
  onActivateMessage: (message: ChatMessage) => void;
  onCitationHover: (index?: number) => void;
}) {
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!activeMessageId) return;
    const activeNode = Array.from(
      listRef.current?.querySelectorAll<HTMLElement>('[data-message-id]') ?? [],
    ).find((node) => node.dataset.messageId === activeMessageId);
    activeNode?.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }, [activeMessageId, messages]);

  if (booting) {
    return (
      <div className="empty-state">
        <div className="typing">
          <span />
          <span />
          <span />
        </div>
      </div>
    );
  }

  if (messages.length === 0 && !loading) {
    return (
      <div className="empty-state">
        <div className="empty-state__icon">
          <Sparkles size={28} />
        </div>
        <h1>询问你的知识库</h1>
        <div className="example-grid">
          {exampleQuestions.map((question) => (
            <button type="button" key={question} onClick={() => onAskExample(question)}>
              {question}
            </button>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="message-list" aria-live="polite" ref={listRef}>
      {messages.map((message) => (
        <article
          className={`message message--${message.role} ${activeMessageId === message.id ? 'message--active' : ''}`}
          data-message-id={message.id}
          key={message.id}
          onClick={() => onActivateMessage(message)}
        >
          <div className="message__meta">{message.role === 'user' ? '你' : 'DeepMemo'} · {message.createdAt}</div>
          <div className="message__bubble">
            <MarkdownLite
              content={message.content}
              activeCitationIndex={activeMessageId === message.id ? activeCitationIndex : undefined}
              onCitationHover={(index) => {
                onActivateMessage(message);
                onCitationHover(index);
              }}
              onCitationSelect={(index) => {
                onActivateMessage(message);
                onCitationHover(index);
              }}
            />
          </div>
        </article>
      ))}
      {loading && messages.filter(m => m.role === 'assistant').length === 0 && (
        <article className="message message--assistant">
          <div className="message__meta">DeepMemo · 等待后端回复</div>
          <div className="message__bubble">
            <div className="typing">
              <span />
              <span />
              <span />
            </div>
          </div>
        </article>
      )}
    </div>
  );
}

function ConversationHeader({
  sessions,
  activeSessionId,
  creating,
  deleting,
  onSelectSession,
  onCreateSession,
  onDeleteSession,
}: {
  sessions: Session[];
  activeSessionId?: string;
  creating: boolean;
  deleting: boolean;
  onSelectSession: (id: string) => void;
  onCreateSession: () => void;
  onDeleteSession: (id: string) => void;
}) {
  return (
    <div className="conversation-header">
      <select
        value={activeSessionId ?? ''}
        onChange={(event) => onSelectSession(event.target.value)}
        disabled={sessions.length === 0}
        aria-label="选择会话"
      >
        {sessions.length === 0 && <option value="">无会话</option>}
        {sessions.map((session) => (
          <option value={session.sessionId} key={session.sessionId}>
            {session.sessionName} · {session.messageIds.length}
          </option>
        ))}
      </select>
      <button type="button" onClick={onCreateSession} disabled={creating} title="新建会话">
        <MessageSquarePlus size={16} />
        新建
      </button>
      <button
        className="icon-button"
        type="button"
        disabled={deleting || !activeSessionId}
        onClick={() => activeSessionId && onDeleteSession(activeSessionId)}
        title="删除当前会话"
      >
        <Trash2 size={16} />
      </button>
    </div>
  );
}

function AiCommandBar({
  value,
  onChange,
  onSubmit,
  onAutoDraft,
  onRefactor,
  tools,
  selectedToolId,
  toolsLoading,
  onSelectTool,
  onClearTool,
  loading,
  draftLoading,
  disabled,
  activeSession,
}: {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  onAutoDraft: () => void;
  onRefactor: () => void;
  tools: ChatTool[];
  selectedToolId?: string;
  toolsLoading: boolean;
  onSelectTool: (toolId: string) => void;
  onClearTool: () => void;
  loading: boolean;
  draftLoading: boolean;
  disabled: boolean;
  activeSession?: Session;
}) {
  const [toolMenuOpen, setToolMenuOpen] = useState(false);
  const selectedTool = tools.find((tool) => tool.id === selectedToolId);

  return (
    <form
      className="ai-command-bar"
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit();
      }}
    >
      <div className="ai-command-bar__meta">
        <span>
          <Sparkles size={14} />
          正在基于本地知识库提供建议
        </span>
        <span>{activeSession?.sessionName ?? '未选择会话'}</span>
      </div>
      {selectedTool && (
        <div className="ai-command-bar__tool-row">
          <span className="tool-chip" title={selectedTool.description}>
            <Wrench size={13} />
            {selectedTool.name}
            <button type="button" onClick={onClearTool} title="移除工具">
              <X size={13} />
            </button>
          </span>
        </div>
      )}
      <div className="ai-command-bar__box">
        <textarea
          value={value}
          onChange={(event) => onChange(event.target.value)}
          placeholder="输入问题，或拖入 Markdown 文件"
          rows={3}
          disabled={disabled}
        />
        <div className="ai-command-bar__actions">
          <div className="tool-picker">
            <button
              type="button"
              onClick={() => setToolMenuOpen((open) => !open)}
              disabled={disabled || toolsLoading || tools.length === 0}
              aria-expanded={toolMenuOpen}
              title="工具"
            >
              <Wrench size={16} />
              工具
            </button>
            {toolMenuOpen && (
              <div className="tool-picker__menu">
                {tools.map((tool) => (
                  <button
                    className={tool.id === selectedToolId ? 'tool-picker__item tool-picker__item--active' : 'tool-picker__item'}
                    type="button"
                    key={tool.id}
                    onClick={() => {
                      onSelectTool(tool.id);
                      setToolMenuOpen(false);
                    }}
                  >
                    <span>
                      <strong>{tool.name}</strong>
                      <small>{tool.executionType === 'job' ? '任务' : '即时'}</small>
                    </span>
                    <em>{tool.description}</em>
                  </button>
                ))}
              </div>
            )}
          </div>
          <button type="button" onClick={onAutoDraft} disabled={draftLoading}>
            <WandSparkles size={16} />
            Auto-Draft
          </button>
          <button type="button" onClick={onRefactor}>
            <Code2 size={16} />
            Refactor
          </button>
          <button className="send-button" type="submit" disabled={loading || disabled || value.trim().length === 0}>
            <Send size={16} />
            发送
          </button>
        </div>
      </div>
    </form>
  );
}

function HybridWorkspace({
  mode,
  activeFile,
  editorValue,
  streaming,
  messages,
  sessions,
  activeSessionId,
  activeSession,
  input,
  loading,
  booting,
  creating,
  deleting,
  tools,
  selectedToolId,
  toolsLoading,
  entityOptions,
  activeMessageId,
  activeCitationIndex,
  onEditorChange,
  onInsertEntity,
  onSlashCommand,
  onSave,
  onAskExample,
  onSelectSession,
  onCreateSession,
  onDeleteSession,
  onInputChange,
  onSubmit,
  onAutoDraft,
  onRefactor,
  onSelectTool,
  onClearTool,
  onActivateMessage,
  onCitationHover,
}: {
  mode: WorkspaceMode;
  activeFile?: FileNode;
  editorValue: string;
  streaming: boolean;
  messages: ChatMessage[];
  sessions: Session[];
  activeSessionId?: string;
  activeSession?: Session;
  input: string;
  loading: boolean;
  booting: boolean;
  creating: boolean;
  deleting: boolean;
  tools: ChatTool[];
  selectedToolId?: string;
  toolsLoading: boolean;
  entityOptions: string[];
  activeMessageId?: string;
  activeCitationIndex?: number;
  onEditorChange: (value: string) => void;
  onInsertEntity: (entity: string) => void;
  onSlashCommand: (command: 'daily' | 'extract' | 'polish') => void;
  onSave: () => void;
  onAskExample: (question: string) => void;
  onSelectSession: (id: string) => void;
  onCreateSession: () => void;
  onDeleteSession: (id: string) => void;
  onInputChange: (value: string) => void;
  onSubmit: () => void;
  onAutoDraft: () => void;
  onRefactor: () => void;
  onSelectTool: (toolId: string) => void;
  onClearTool: () => void;
  onActivateMessage: (message: ChatMessage) => void;
  onCitationHover: (index?: number) => void;
}) {
  return (
    <section className={`hybrid-workspace hybrid-workspace--${mode}`}>
      <div className="workspace-body">
        {mode === 'editor' ? (
          <EditorContent
            activeFile={activeFile}
            value={editorValue}
            streaming={streaming}
            entityOptions={entityOptions}
            onChange={onEditorChange}
            onInsertEntity={onInsertEntity}
            onSlashCommand={onSlashCommand}
            onSave={onSave}
          />
        ) : (
          <div className="qa-panel">
            <ConversationHeader
              sessions={sessions}
              activeSessionId={activeSessionId}
              creating={creating}
              deleting={deleting}
              onSelectSession={onSelectSession}
              onCreateSession={onCreateSession}
              onDeleteSession={onDeleteSession}
            />
            <MessageList
              messages={messages}
              loading={loading}
              booting={booting}
              activeMessageId={activeMessageId}
              activeCitationIndex={activeCitationIndex}
              onAskExample={onAskExample}
              onActivateMessage={onActivateMessage}
              onCitationHover={onCitationHover}
            />
          </div>
        )}
      </div>

      {mode === 'qa' && (
        <AiCommandBar
          value={input}
          onChange={onInputChange}
          onSubmit={onSubmit}
          onAutoDraft={onAutoDraft}
          onRefactor={onRefactor}
          tools={tools}
          selectedToolId={selectedToolId}
          toolsLoading={toolsLoading}
          onSelectTool={onSelectTool}
          onClearTool={onClearTool}
          loading={loading}
          draftLoading={streaming}
          disabled={booting || !activeSessionId}
          activeSession={activeSession}
        />
      )}
    </section>
  );
}

function SourcePanel({
  mode,
  activeMessage,
  sources,
  sourcesLoading,
  sourcesError,
  activeCitationIndex,
  onCitationHover,
  onOpenSourceFile,
  activeFile,
  fileRefs,
  fileRefsLoading,
  fileRefsError,
  onNavigateToFileReference,
}: {
  mode: WorkspaceMode;
  activeMessage?: ChatMessage;
  sources: SourcePanelItem[];
  sourcesLoading: boolean;
  sourcesError?: string;
  activeCitationIndex?: number;
  onCitationHover: (index?: number) => void;
  onOpenSourceFile: (path: string) => void;
  activeFile?: FileNode;
  fileRefs: FileReference[];
  fileRefsLoading: boolean;
  fileRefsError?: string;
  onNavigateToFileReference: (ref: FileReference) => void;
}) {
  const isEditorMode = mode === 'editor';
  return (
    <aside className="source-panel">
      <div className="source-panel__header">
        <div>
          <strong>Source</strong>
          <span>{isEditorMode ? (activeFile?.name ?? '未选择文件') : (activeMessage?.createdAt ?? '未选择消息')}</span>
        </div>
      </div>

      <div className="source-panel__body">
        {isEditorMode ? (
          <FileReferencesView
            activeFile={activeFile}
            fileRefs={fileRefs}
            loading={fileRefsLoading}
            error={fileRefsError}
            onNavigate={onNavigateToFileReference}
          />
        ) : (
          <SourcesView
            message={activeMessage}
            sources={sources}
            loading={sourcesLoading}
            error={sourcesError}
            activeCitationIndex={activeCitationIndex}
            onCitationHover={onCitationHover}
            onOpenSourceFile={onOpenSourceFile}
          />
        )}
      </div>
    </aside>
  );
}

function FileReferencesView({
  activeFile,
  fileRefs,
  loading,
  error,
  onNavigate,
}: {
  activeFile?: FileNode;
  fileRefs: FileReference[];
  loading: boolean;
  error?: string;
  onNavigate: (ref: FileReference) => void;
}) {
  const [expandedRefKeys, setExpandedRefKeys] = useState<Set<string>>(new Set());

  useEffect(() => {
    setExpandedRefKeys(new Set());
  }, [activeFile?.path]);

  const toggleRef = (key: string) => {
    setExpandedRefKeys((current) => {
      const next = new Set(current);
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.add(key);
      }
      return next;
    });
  };

  if (!activeFile || activeFile.type !== 'file') {
    return (
      <div className="empty-panel">
        <FileText size={18} />
        <span>选择一个文件查看引用它的会话</span>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="empty-panel">
        <div className="typing">
          <span />
          <span />
          <span />
        </div>
        <span>正在查找引用当前文件的会话...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="empty-panel">
        <AlertCircle size={18} />
        <span>{error}</span>
      </div>
    );
  }

  if (fileRefs.length === 0) {
    return (
      <div className="empty-panel">
        <Link2 size={18} />
        <span>暂无会话引用此文件</span>
      </div>
    );
  }

  // Group by session
  const sessionGroups = new Map<string, { sessionName: string; refs: FileReference[] }>();
  for (const ref of fileRefs) {
    const existing = sessionGroups.get(ref.sessionId);
    if (existing) {
      existing.refs.push(ref);
    } else {
      sessionGroups.set(ref.sessionId, { sessionName: ref.sessionName, refs: [ref] });
    }
  }

  return (
    <div className="source-list">
      {[...sessionGroups.entries()].map(([sessionId, group]) => (
        <div className="file-ref-group" key={sessionId}>
          <div className="message-group">
            <MessageSquare size={13} />
            <strong>{group.sessionName}</strong>
            <span className="file-ref-count">{group.refs.length} 条引用</span>
          </div>
          {group.refs.map((ref) => {
            const refKey = `${ref.messageId}`;
            const isExpanded = expandedRefKeys.has(refKey);
            const preview = ref.content.length > 120 ? ref.content.slice(0, 120) + '...' : ref.content;
            return (
              <article className="source-card" key={refKey}>
                <button
                  className="file-ref-card__toggle"
                  type="button"
                  aria-expanded={isExpanded}
                  onClick={() => toggleRef(refKey)}
                >
                  <div className="source-card__top">
                    <span className="source-index">
                      {ref.role === 'assistant' ? <Bot size={13} /> : <span>你</span>}
                    </span>
                    <span className="source-card__meta">
                      <span>{ref.createdAt}</span>
                      {isExpanded ? <ChevronDown size={15} /> : <ChevronRight size={15} />}
                    </span>
                  </div>
                  <span className="source-card__path file-ref-preview">{preview}</span>
                </button>
                <button
                  className="source-card__open file-ref-card__open"
                  type="button"
                  onClick={() => onNavigate(ref)}
                >
                  <MessageSquare size={14} />
                  跳转到会话
                </button>
                {isExpanded && (
                  <div className="source-card__detail">
                    <p className="file-ref-content">{ref.content}</p>
                  </div>
                )}
              </article>
            );
          })}
        </div>
      ))}
    </div>
  );
}

function SourcesView({
  message,
  sources,
  loading,
  error,
  activeCitationIndex,
  onCitationHover,
  onOpenSourceFile,
}: {
  message?: ChatMessage;
  sources: SourcePanelItem[];
  loading: boolean;
  error?: string;
  activeCitationIndex?: number;
  onCitationHover: (index?: number) => void;
  onOpenSourceFile: (path: string) => void;
}) {
  const [expandedSourceKeys, setExpandedSourceKeys] = useState<Set<string>>(new Set());

  useEffect(() => {
    setExpandedSourceKeys(new Set());
  }, [message?.id]);

  const toggleSource = (key: string) => {
    setExpandedSourceKeys((current) => {
      const next = new Set(current);
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.add(key);
      }
      return next;
    });
  };

  if (!message) {
    return (
      <div className="empty-panel">
        <MessageSquare size={18} />
        <span>点击一条问答消息查看独立引用分组</span>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="empty-panel">
        <div className="typing">
          <span />
          <span />
          <span />
        </div>
        <span>正在读取引用证据链</span>
      </div>
    );
  }

  if (sources.length === 0) {
    return (
      <div className="empty-panel">
        <Link2 size={18} />
        <span>{error ? `引用接口不可用：${error}` : '当前消息暂无引用片段'}</span>
      </div>
    );
  }

  return (
    <div className="source-list">
      <div className="message-group">
        <span>Message Group</span>
        <strong>{message.role === 'assistant' ? 'DeepMemo' : '你'} · {message.createdAt}</strong>
      </div>
      {error && <div className="inline-warning">{error}，已使用消息正文中的引用片段。</div>}
      {sources.map((source) => {
        const sourceKey = `${source.messageId}-${source.index}-${source.path}`;
        const isExpanded = expandedSourceKeys.has(sourceKey);
        return (
          <article
            className={`source-card ${activeCitationIndex === source.index ? 'source-card--active' : ''}`}
            key={sourceKey}
            onMouseEnter={() => onCitationHover(source.index)}
            onMouseLeave={() => onCitationHover(undefined)}
          >
            <button
              className="source-card__summary"
              type="button"
              aria-expanded={isExpanded}
              onClick={() => toggleSource(sourceKey)}
            >
              <div className="source-card__top">
                <span className="source-index">[{source.index}]</span>
                <span className="source-card__meta">
                  {source.score !== undefined && (
                    <span className={`score score--${scoreLevel(source.score)}`}>
                      {Math.round(source.score * 100)}%
                    </span>
                  )}
                  {isExpanded ? <ChevronDown size={15} /> : <ChevronRight size={15} />}
                </span>
              </div>
              <span className="source-card__path">{source.path}</span>
              <span className="source-card__file">
                {source.startLine > 0 ? `Lines ${source.startLine}-${source.endLine}` : source.evidenceId ?? 'fingerprint citation'}
              </span>
            </button>
            <button className="source-card__open" type="button" onClick={() => onOpenSourceFile(source.path)}>
              <Link2 size={14} />
              跳转到源文件
            </button>
            {isExpanded && (
              <div className="source-card__detail">
                <p>{source.excerpt}</p>
              </div>
            )}
          </article>
        );
      })}
    </div>
  );
}

export function App() {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string>();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [chatTools, setChatTools] = useState<ChatTool[]>([]);
  const [toolsLoading, setToolsLoading] = useState(false);
  const [selectedToolId, setSelectedToolId] = useState<string>();
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [booting, setBooting] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [creating, setCreating] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState<string>();
  const [files, setFiles] = useState<FileNode[]>([]);
  const [activeFileId, setActiveFileId] = useState<string>();
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [mode, setMode] = useState<WorkspaceMode>('editor');
  const [fileContents, setFileContents] = useState<Record<string, string>>({});
  const [drafting, setDrafting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [activeMessageId, setActiveMessageId] = useState<string>();
  const [activeCitationIndex, setActiveCitationIndex] = useState<number>();
  const [remoteCitations, setRemoteCitations] = useState<Record<string, Citation[]>>({});
  const [citationLoading, setCitationLoading] = useState(false);
  const [citationError, setCitationError] = useState<string>();
  const [fileRefs, setFileRefs] = useState<FileReference[]>([]);
  const [fileRefsLoading, setFileRefsLoading] = useState(false);
  const [fileRefsError, setFileRefsError] = useState<string>();
  const pendingNavigationMessageId = useRef<string>();

  const activeFile = useMemo(
    () => (activeFileId ? findNode(files, activeFileId) : undefined),
    [activeFileId, files],
  );
  const activeSession = useMemo(
    () => sessions.find((session) => session.sessionId === activeSessionId),
    [activeSessionId, sessions],
  );
  const activeMessage = useMemo(
    () => activeMessageId ? messages.find((message) => message.id === activeMessageId) : undefined,
    [activeMessageId, messages],
  );
  const editorValue = activeFileId ? fileContents[activeFileId] ?? '' : '';
  const entityOptions = useMemo(() => deriveEntityOptions(files, editorValue), [files, editorValue]);
  const activeParsedSources = useMemo(() => getMessageSources(activeMessage), [activeMessage]);
  const activeSources = useMemo(() => {
    if (!activeMessage) return [];
    const citations = remoteCitations[activeMessage.id];
    if (citations && citations.length > 0) {
      return mapCitationsToSources(activeMessage.id, citations);
    }
    return mapParsedSources(activeMessage.id, activeParsedSources);
  }, [activeMessage, activeParsedSources, remoteCitations]);

  const setActiveEditorValue = (value: string) => {
    if (!activeFileId) return;
    setFileContents((current) => ({ ...current, [activeFileId]: value }));
    if (activeFile && activeFile.type === 'file' && activeFile.syncStatus === 'synced') {
      setFiles((current) => updateNodeStatus(current, activeFile.path, 'dirty'));
      updateFileSyncStatus(activeFile.path, 'dirty').catch(() => {
        setFiles((current) => updateNodeStatus(current, activeFile.path, 'error'));
      });
    }
  };

  const refreshSessionList = async (preferredSessionId?: string) => {
    const remoteSessions = await listSessions();
    setSessions(remoteSessions);
    const nextActiveId = preferredSessionId ?? activeSessionId ?? remoteSessions[0]?.sessionId;
    setActiveSessionId(nextActiveId);
    return nextActiveId;
  };

  const ensureSession = async () => {
    const remoteSessions = await listSessions();
    if (remoteSessions.length > 0) {
      setSessions(remoteSessions);
      setActiveSessionId(remoteSessions[0].sessionId);
      return remoteSessions[0].sessionId;
    }

    const created = await createSession(createSessionName());
    setSessions([created]);
    setActiveSessionId(created.sessionId);
    return created.sessionId;
  };

  const loadMessagesForSession = async (sessionId: string) => {
    const remoteMessages = await listMessages(sessionId);
    setMessages(remoteMessages);
    return remoteMessages;
  };

  const loadFileContent = async (node: FileNode) => {
    if (node.type !== 'file') return;
    const response = await getFileContent(node.path);
    setFileContents((current) => ({ ...current, [node.id]: response.content }));
  };

  const refreshFileTree = async (preferredFileId?: string) => {
    const remoteFiles = await getFileTree();
    setFiles(remoteFiles);
    setExpanded((current) => new Set([...current, ...remoteFiles.map((node) => node.id)]));

    const preferred = preferredFileId ? findNode(remoteFiles, preferredFileId) : undefined;
    const nextFile = preferred?.type === 'file' ? preferred : findFirstFile(remoteFiles);
    setActiveFileId(nextFile?.id);
    return nextFile;
  };

  useEffect(() => {
    let cancelled = false;

    setToolsLoading(true);
    getChatTools()
      .then((tools) => {
        if (!cancelled) {
          setChatTools(tools);
        }
      })
      .catch((caught) => {
        if (!cancelled) {
          setError(caught instanceof Error ? caught.message : '工具列表加载失败');
        }
      })
      .finally(() => {
        if (!cancelled) {
          setToolsLoading(false);
        }
      });

    async function boot() {
      setBooting(true);
      setError(undefined);
      try {
        await getHealth();
        if (cancelled) return;
        const sessionId = await ensureSession();
        if (cancelled) return;
        const nextFile = await refreshFileTree(activeFileId);
        if (cancelled) return;
        await Promise.all([
          loadMessagesForSession(sessionId),
          nextFile ? loadFileContent(nextFile) : Promise.resolve(),
        ]);
      } catch (caught) {
        if (cancelled) return;
        setError(caught instanceof Error ? caught.message : '后端连接失败');
      } finally {
        if (!cancelled) {
          setBooting(false);
        }
      }
    }

    boot();

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!activeSessionId || booting) return;
    setError(undefined);
    loadMessagesForSession(activeSessionId).catch((caught) => {
      setError(caught instanceof Error ? caught.message : '消息加载失败');
    });
  }, [activeSessionId, booting]);

  useEffect(() => {
    if (!activeFile || activeFile.type !== 'file' || fileContents[activeFile.id] !== undefined) return;
    let cancelled = false;
    setError(undefined);
    loadFileContent(activeFile).catch((caught) => {
      if (!cancelled) {
        setError(caught instanceof Error ? caught.message : '文件读取失败');
      }
    });
    return () => {
      cancelled = true;
    };
  }, [activeFile?.id]);

  useEffect(() => {
    if (mode !== 'qa') return;

    const pendingMessageId = pendingNavigationMessageId.current;
    if (pendingMessageId) {
      if (messages.some((message) => message.id === pendingMessageId)) {
        setActiveMessageId(pendingMessageId);
        pendingNavigationMessageId.current = undefined;
      }
      return;
    }

    const latestAssistant = [...messages].reverse().find((message) => message.role === 'assistant');
    const latestMessage = latestAssistant ?? messages[messages.length - 1];
    if (latestMessage && !messages.some((message) => message.id === activeMessageId)) {
      setActiveMessageId(latestMessage.id);
    }
  }, [mode, messages, activeMessageId]);

  useEffect(() => {
    if (!activeMessage || activeMessage.role !== 'assistant' || activeMessage.id.startsWith('local-')) {
      setCitationError(undefined);
      return;
    }
    if (remoteCitations[activeMessage.id]) return;

    let cancelled = false;
    setCitationLoading(true);
    setCitationError(undefined);
    getMessageCitations(activeMessage.id)
      .then((citations) => {
        if (!cancelled) {
          setRemoteCitations((current) => ({ ...current, [activeMessage.id]: citations }));
        }
      })
      .catch((caught) => {
        if (!cancelled) {
          setCitationError(caught instanceof Error ? caught.message : '引用加载失败');
          setRemoteCitations((current) => ({ ...current, [activeMessage.id]: [] }));
        }
      })
      .finally(() => {
        if (!cancelled) {
          setCitationLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [activeMessage?.id, activeMessage?.role, remoteCitations]);


  // Fetch file references when editing a file (editor mode)
  useEffect(() => {
    if (mode !== 'editor' || !activeFile || activeFile.type !== 'file') {
      setFileRefs([]);
      return;
    }
    let cancelled = false;
    setFileRefsLoading(true);
    setFileRefsError(undefined);
    getFileReferences(activeFile.path)
      .then((refs) => {
        if (!cancelled) setFileRefs(refs);
      })
      .catch((caught) => {
        if (!cancelled) {
          setFileRefsError(caught instanceof Error ? caught.message : '引用加载失败');
          setFileRefs([]);
        }
      })
      .finally(() => {
        if (!cancelled) setFileRefsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [mode, activeFile?.path, activeFile?.type]);

  const handleSelectSession = (sessionId: string) => {
    pendingNavigationMessageId.current = undefined;
    setActiveCitationIndex(undefined);
    setActiveSessionId(sessionId);
  };

  const handleNavigateToFileReference = async (ref: FileReference) => {
    pendingNavigationMessageId.current = ref.messageId;
    setError(undefined);
    setActiveSessionId(ref.sessionId);
    setActiveMessageId(ref.messageId);
    setActiveCitationIndex(undefined);
    setMode('qa');
    try {
      const remoteMessages = await loadMessagesForSession(ref.sessionId);
      if (remoteMessages.some((message) => message.id === ref.messageId)) {
        setActiveMessageId(ref.messageId);
      } else {
        pendingNavigationMessageId.current = undefined;
        const latestAssistant = [...remoteMessages].reverse().find((message) => message.role === 'assistant');
        const fallbackMessage = latestAssistant ?? remoteMessages[remoteMessages.length - 1];
        setActiveMessageId(fallbackMessage?.id);
        setError('已打开引用会话，但没有找到对应消息');
      }
    } catch (caught) {
      pendingNavigationMessageId.current = undefined;
      setError(caught instanceof Error ? caught.message : '会话跳转失败');
    }
  };
  const handleCreateSession = async () => {
    setCreating(true);
    setError(undefined);
    try {
      const created = await createSession(createSessionName());
      setSessions((current) => [created, ...current]);
      setActiveSessionId(created.sessionId);
      setMessages([]);
      setMode('qa');
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '新建会话失败');
    } finally {
      setCreating(false);
    }
  };

  const handleRefresh = async () => {
    setRefreshing(true);
    setError(undefined);
    try {
      await getHealth();
      const selectedId = await refreshSessionList(activeSessionId);
      const nextFile = await refreshFileTree(activeFileId);
      if (selectedId) {
        await loadMessagesForSession(selectedId);
      }
      if (nextFile) {
        await loadFileContent(nextFile);
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '刷新失败');
    } finally {
      setRefreshing(false);
    }
  };

  const handleDeleteSession = async (sessionId: string) => {
    setDeleting(true);
    setError(undefined);
    try {
      await deleteSession(sessionId);
      const remaining = sessions.filter((session) => session.sessionId !== sessionId);
      if (remaining.length > 0) {
        setSessions(remaining);
        if (activeSessionId === sessionId) {
          setActiveSessionId(remaining[0].sessionId);
          await loadMessagesForSession(remaining[0].sessionId);
        }
      } else {
        const created = await createSession(createSessionName());
        setSessions([created]);
        setActiveSessionId(created.sessionId);
        setMessages([]);
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '删除会话失败');
    } finally {
      setDeleting(false);
    }
  };

  const submitQuestion = async (question = input) => {
    const trimmed = question.trim();
    if (!trimmed || loading || !activeSessionId) return;

    const sessionId = activeSessionId;
    const outgoingToolId = selectedToolId && chatTools.some((tool) => tool.id === selectedToolId)
      ? selectedToolId
      : undefined;
    const optimisticUser = createOptimisticUserMessage(sessionId, trimmed);
    const tempAssistantId = `local-assistant-${Date.now()}`;
    const optimisticAssistant: ChatMessage = {
      id: tempAssistantId,
      sessionId,
      role: 'assistant',
      content: '',
      createdAt: new Intl.DateTimeFormat('zh-CN', {
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
      }).format(new Date()),
    };

    setMode('qa');
    setInput('');
    setSelectedToolId(undefined);
    setLoading(true);
    setError(undefined);
    setMessages((current) => [...current, optimisticUser, optimisticAssistant]);

    const streamedContent: string[] = [];
    try {
      const savedAssistant = await sendMessageStream(
        sessionId,
        trimmed,
        (token) => {
          streamedContent.push(token);
          setMessages((current) =>
            current.map((msg) =>
              msg.id === tempAssistantId
                ? { ...msg, content: streamedContent.join('') }
                : msg
            )
          );
        },
        outgoingToolId ? { toolId: outgoingToolId, scope: 'next_message' } : undefined,
      );

      if (savedAssistant) {
        setMessages((current) =>
          current.map((msg) => (msg.id === tempAssistantId ? savedAssistant : msg))
        );
        setActiveMessageId(savedAssistant.id);
      }

      await refreshSessionList(sessionId);
      const persistedMessages = await listMessages(sessionId);
      setMessages(persistedMessages);
      const persistedAssistant = savedAssistant
        ? persistedMessages.find((message) => message.id === savedAssistant.id)
        : [...persistedMessages].reverse().find((message) => message.role === 'assistant');
      setActiveMessageId(persistedAssistant?.id);
    } catch (caught) {
      try {
        await refreshSessionList(sessionId);
        const persistedMessages = await listMessages(sessionId);
        const hasPersistedAssistant = persistedMessages.some((message) => message.role === 'assistant');
        if (hasPersistedAssistant) {
          setMessages(persistedMessages);
        } else if (streamedContent.length === 0) {
          setMessages((current) => current.filter((message) => message.id !== tempAssistantId));
        }
      } catch {
        // keep current streamed content on refresh failure
      }
      setError(caught instanceof Error ? caught.message : '发送失败');
    } finally {
      setLoading(false);
    }
  };

  const handleToggleFolder = (id: string) => {
    setExpanded((current) => {
      const next = new Set(current);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  const handleSelectFile = (id: string) => {
    setActiveFileId(id);
    setMode('editor');
  };

  const handleActivateMessage = (message: ChatMessage) => {
    setActiveMessageId(message.id);
  };

  const handleOpenSourceFile = async (path: string) => {
    const node = findNodeByPath(files, path);
    if (!node || node.type !== 'file') {
      setError(`未在文件树中找到 ${path}`);
      return;
    }
    setActiveFileId(node.id);
    setMode('editor');
    setExpanded((current) => {
      const next = new Set(current);
      path.split('/').slice(0, -1).reduce((prefix, part) => {
        const nextPath = prefix ? `${prefix}/${part}` : part;
        next.add(nextPath);
        return nextPath;
      }, '');
      return next;
    });
    if (fileContents[node.id] === undefined) {
      await loadFileContent(node);
    }
  };

  const handleAutoDraft = async () => {
    if (drafting) return;
    setMode('editor');
    setDrafting(true);
    setError(undefined);
    try {
      const response = await createDiaryAutoDraft('raw', 'diary');
      if (response.draft.trim().length > 0) {
        setActiveEditorValue(response.draft);
      } else {
        setError(response.message || '后端没有生成草稿');
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '自动草稿生成失败');
    } finally {
      setDrafting(false);
    }
  };

  const handleSave = async () => {
    if (!activeFile || activeFile.type !== 'file') return;
    setSaving(true);
    setError(undefined);
    try {
      const response = await writeFile(activeFile.path, editorValue);
      setFiles((current) => updateNodeStatus(current, response.file_path, response.sync_status));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '文件保存失败');
      setFiles((current) => updateNodeStatus(current, activeFile.path, 'error'));
    } finally {
      setSaving(false);
    }
  };

  const handleRenameNode = async (node: FileNode) => {
    if (node.type !== 'file') {
      setError('当前后端 move 接口仅用于文件重命名');
      return;
    }
    const nextPath = window.prompt('输入新的相对路径', node.path)?.trim();
    if (!nextPath || nextPath === node.path) return;
    setError(undefined);
    try {
      const response = await moveFile(node.path, nextPath);
      setFileContents((current) => {
        const next = { ...current };
        if (next[node.id] !== undefined) {
          next[response.new_path] = next[node.id];
          delete next[node.id];
        }
        return next;
      });
      const nextFile = await refreshFileTree(response.new_path);
      if (nextFile) {
        await loadFileContent(nextFile);
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '重命名失败');
    }
  };

  const requestEditorAi = async (prompt: string, heading: string) => {
    if (!activeSessionId || loading) {
      setError('需要可用会话后才能调用后端 AI 接口');
      return;
    }
    const optimistic = createOptimisticUserMessage(activeSessionId, prompt);
    setLoading(true);
    setError(undefined);
    setMessages((current) => [...current, optimistic]);
    try {
      const aiMessage = await sendMessage(activeSessionId, prompt);
      setMessages((current) => [...current, aiMessage]);
      setActiveEditorValue(`${editorValue.trimEnd()}\n\n## ${heading}\n\n${aiMessage.content.trim()}\n`);
      await refreshSessionList(activeSessionId);
      const persistedMessages = await listMessages(activeSessionId);
      setMessages(persistedMessages);
    } catch (caught) {
      setMessages((current) => current.filter((message) => message.id !== optimistic.id));
      setError(caught instanceof Error ? caught.message : `${heading}失败`);
    } finally {
      setLoading(false);
      setMode('editor');
    }
  };

  const handleCreateFile = async (parentPath?: string) => {
    const base = parentPath ? `${parentPath}/` : '';
    const name = window.prompt('输入文件名', parentPath ? '' : 'diary/')?.trim();
    if (!name) return;
    const fullPath = name.startsWith(base) ? name : `${base}${name}`;
    setError(undefined);
    try {
      await createFile(fullPath, '');
      await refreshFileTree();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '创建文件失败');
    }
  };

  const handleCreateFolder = async () => {
    const name = window.prompt('输入文件夹名（如 ideas/projects）')?.trim();
    if (!name) return;
    setError(undefined);
    try {
      await createDirectory(name);
      await refreshFileTree();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '创建文件夹失败');
    }
  };

  const handleAiComplete = () => {
    requestEditorAi(
      `请基于当前文件 ${activeFile?.path ?? '未选择文件'}，补完下面的 Markdown，不要编造未给出的事实：\n\n${editorValue}`,
      'AI 补完',
    );
  };

  const handleFormat = () => {
    setActiveEditorValue(formatEditorMarkdown(editorValue));
  };

  const handleRefactor = () => {
    requestEditorAi(
      `请润色并重构当前 Markdown，保留事实和引用，按“结论 -> 证据 -> 下一步”的结构输出：\n\n${editorValue}`,
      'Refactor',
    );
  };

  const handleInsertEntity = (entity: string) => {
    setActiveEditorValue(editorValue.replace(/@([\w-]*)$/i, `[[${entity}]]`));
  };

  const handleSlashCommand = (command: 'daily' | 'extract' | 'polish') => {
    if (command === 'daily') {
      handleAutoDraft();
    }
    if (command === 'extract') {
      setActiveEditorValue(`${editorValue.replace(/\/$/i, '').trimEnd()}\n\n<!-- extract-knowledge queued -->\n`);
    }
    if (command === 'polish') {
      requestEditorAi(
        `请润色当前 Markdown，保持原意，压缩重复表达，并补充可追溯证据提示：\n\n${editorValue.replace(/\/$/i, '').trimEnd()}`,
        'Polish',
      );
    }
  };

  return (
    <div className="app-shell">
      <DataExplorer
        files={files}
        activeFileId={activeFileId}
        expanded={expanded}
        refreshing={refreshing}
        onSelectFile={handleSelectFile}
        onToggleFolder={handleToggleFolder}
        onRenameNode={handleRenameNode}
        onCreateFile={handleCreateFile}
        onCreateFolder={handleCreateFolder}
        onRefresh={handleRefresh}
      />

      <main className="workspace">
        <WorkspaceHeader
          activeFile={activeFile}
          mode={mode}
          saving={saving}
          onModeChange={setMode}
          onAiComplete={handleAiComplete}
          onSave={handleSave}
          onFormat={handleFormat}
        />
        {error && (
          <div className="error-banner">
            <AlertCircle size={16} />
            {error}
          </div>
        )}
        <HybridWorkspace
          mode={mode}
          activeFile={activeFile}
          editorValue={editorValue}
          streaming={drafting}
          messages={messages}
          sessions={sessions}
          activeSessionId={activeSessionId}
          activeSession={activeSession}
          input={input}
          loading={loading}
          booting={booting}
          creating={creating}
          deleting={deleting}
          tools={chatTools}
          selectedToolId={selectedToolId}
          toolsLoading={toolsLoading}
          entityOptions={entityOptions}
          activeMessageId={activeMessageId}
          activeCitationIndex={activeCitationIndex}
          onEditorChange={setActiveEditorValue}
          onInsertEntity={handleInsertEntity}
          onSlashCommand={handleSlashCommand}
          onSave={handleSave}
          onAskExample={submitQuestion}
          onSelectSession={handleSelectSession}
          onCreateSession={handleCreateSession}
          onDeleteSession={handleDeleteSession}
          onInputChange={setInput}
          onSubmit={() => submitQuestion()}
          onAutoDraft={handleAutoDraft}
          onRefactor={handleRefactor}
          onSelectTool={setSelectedToolId}
          onClearTool={() => setSelectedToolId(undefined)}
          onActivateMessage={handleActivateMessage}
          onCitationHover={setActiveCitationIndex}
        />
      </main>

      <SourcePanel
        mode={mode}
        activeMessage={activeMessage}
        sources={activeSources}
        sourcesLoading={citationLoading}
        sourcesError={citationError}
        activeCitationIndex={activeCitationIndex}
        onCitationHover={setActiveCitationIndex}
        onOpenSourceFile={handleOpenSourceFile}
        activeFile={activeFile}
        fileRefs={fileRefs}
        fileRefsLoading={fileRefsLoading}
        fileRefsError={fileRefsError}
        onNavigateToFileReference={handleNavigateToFileReference}
      />
    </div>
  );
}
