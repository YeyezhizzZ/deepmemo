import {
  ArrowUp,
  BookOpen,
  Check,
  Clock3,
  FileText,
  LoaderCircle,
  MessageCircle,
  ShieldCheck,
  Trash2,
  UploadCloud,
  X,
} from 'lucide-react';
import { FormEvent, useEffect, useMemo, useRef, useState } from 'react';
import {
  createSession,
  createWorkspace,
  deleteWorkspace,
  getCitations,
  getSite,
  getWorkspace,
  streamMessage,
  uploadWorkspaceFiles,
  type DeepMeCitation,
  type DeepMeMessage,
  type DeepMeSession,
  type SiteInfo,
  type Workspace,
} from './deepme-api';

type Mode = 'system' | 'temporary';

const emptyConversations: Record<Mode, DeepMeMessage[]> = {
  system: [],
  temporary: [],
};

function formatTime(value?: string) {
  if (!value) return '';
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(value));
}

function friendlyError(error: unknown) {
  const value = error instanceof Error ? error.message : String(error);
  const messages: Record<string, string> = {
    scope_not_ready: '资料仍在处理中，请稍后再试。',
    scope_expired: '临时资料已到期，请重新上传。',
    upload_limit_exceeded: '上传文件数量或大小超过限制。',
    unsupported_file: '仅支持 Markdown、TXT 和可提取文本的 PDF。',
    answer_failed: '回答生成失败，请稍后重试。',
  };
  return messages[value] ?? value;
}

function MessageContent({
  content,
  citations,
  onCitation,
}: {
  content: string;
  citations: DeepMeCitation[];
  onCitation: (citation: DeepMeCitation) => void;
}) {
  const citationById = useMemo(
    () => new Map(citations.map((citation) => [citation.local_id, citation])),
    [citations],
  );
  return (
    <div className="deepme-message-content">
      {content.split('\n').map((line, lineIndex) => (
        <p key={`${lineIndex}-${line}`}>
          {line.split(/(\[\d+\])/g).map((part, partIndex) => {
            const match = /^\[(\d+)\]$/.exec(part);
            if (!match) return <span key={partIndex}>{part}</span>;
            const citation = citationById.get(Number(match[1]));
            if (!citation) return <span key={partIndex}>{part}</span>;
            return (
              <button
                className="deepme-citation-chip"
                key={partIndex}
                onClick={() => onCitation(citation)}
                type="button"
              >
                {part}
              </button>
            );
          })}
        </p>
      ))}
    </div>
  );
}

export function DeepMeApp() {
  const [site, setSite] = useState<SiteInfo>();
  const [mode, setMode] = useState<Mode>('system');
  const [sessions, setSessions] = useState<Partial<Record<Mode, DeepMeSession>>>({});
  const [conversations, setConversations] =
    useState<Record<Mode, DeepMeMessage[]>>(emptyConversations);
  const [citations, setCitations] = useState<Record<string, DeepMeCitation[]>>({});
  const [activeCitation, setActiveCitation] = useState<DeepMeCitation>();
  const [workspace, setWorkspace] = useState<Workspace>();
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState<string>();
  const abortRef = useRef<AbortController>();
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const messages = conversations[mode];
  const activeSession = sessions[mode];
  const sourceLabel =
    mode === 'system'
      ? '作者的公开知识库'
      : workspace?.status === 'ready'
        ? `你上传的 ${workspace.files.length} 个文件`
        : '等待上传资料';

  useEffect(() => {
    getSite()
      .then(setSite)
      .catch((caught) => setError(friendlyError(caught)))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, streaming]);

  useEffect(() => {
    if (!workspace || !['processing', 'empty'].includes(workspace.status)) return;
    if (workspace.status === 'empty' && workspace.files.length === 0) return;
    const timer = window.setInterval(() => {
      getWorkspace(workspace.workspace_id)
        .then((next) => {
          setWorkspace(next);
          if (next.status === 'ready' || next.status === 'error') {
            window.clearInterval(timer);
          }
        })
        .catch((caught) => {
          setError(friendlyError(caught));
          window.clearInterval(timer);
        });
    }, 1000);
    return () => window.clearInterval(timer);
  }, [workspace?.workspace_id, workspace?.status, workspace?.files.length]);

  async function ensureSession(targetMode: Mode) {
    const existing = sessions[targetMode];
    if (existing) return existing;
    if (targetMode === 'temporary' && workspace?.status !== 'ready') {
      throw new Error('scope_not_ready');
    }
    const created = await createSession(
      targetMode,
      targetMode === 'temporary' ? workspace?.workspace_id : undefined,
    );
    setSessions((current) => ({ ...current, [targetMode]: created }));
    return created;
  }

  async function submitQuestion(question: string) {
    const trimmed = question.trim();
    if (!trimmed || streaming) return;
    setError(undefined);
    setInput('');
    let session: DeepMeSession;
    try {
      session = await ensureSession(mode);
    } catch (caught) {
      setError(friendlyError(caught));
      return;
    }

    const userMessage: DeepMeMessage = {
      message_id: `local-user-${Date.now()}`,
      session_id: session.session_id,
      role: 'user',
      content: trimmed,
      answer_status: 'pending',
      created_at: new Date().toISOString(),
    };
    const assistantId = `local-ai-${Date.now()}`;
    const assistantMessage: DeepMeMessage = {
      message_id: assistantId,
      session_id: session.session_id,
      role: 'ai',
      content: '',
      answer_status: 'streaming',
      created_at: new Date().toISOString(),
    };
    setConversations((current) => ({
      ...current,
      [mode]: [...current[mode], userMessage, assistantMessage],
    }));
    setStreaming(true);
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      await streamMessage(
        session.session_id,
        trimmed,
        {
          onToken: (token) => {
            setConversations((current) => ({
              ...current,
              [mode]: current[mode].map((message) =>
                message.message_id === assistantId
                  ? { ...message, content: message.content + token }
                  : message,
              ),
            }));
          },
          onDone: (done) => {
            setConversations((current) => ({
              ...current,
              [mode]: current[mode].map((message) =>
                message.message_id === assistantId
                  ? {
                      ...message,
                      message_id: done.message_id,
                      answer_status: done.answer_status,
                      created_at: done.created_at,
                    }
                  : message,
              ),
            }));
            if (done.citation_count > 0) {
              void getCitations(done.message_id)
                .then((items) => {
                  setCitations((current) => ({
                    ...current,
                    [done.message_id]: items,
                  }));
                })
                .catch((caught) => setError(friendlyError(caught)));
            }
          },
        },
        controller.signal,
      );
    } catch (caught) {
      if (!controller.signal.aborted) {
        setError(friendlyError(caught));
        setConversations((current) => ({
          ...current,
          [mode]: current[mode].filter((message) => message.message_id !== assistantId),
        }));
      }
    } finally {
      setStreaming(false);
      abortRef.current = undefined;
    }
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    void submitQuestion(input);
  }

  async function handleFiles(files: FileList | null) {
    if (!files?.length) return;
    setError(undefined);
    setUploading(true);
    try {
      const target = workspace ?? (await createWorkspace());
      setWorkspace(target);
      await uploadWorkspaceFiles(target.workspace_id, Array.from(files));
      const next = await getWorkspace(target.workspace_id);
      setWorkspace(next);
      setSessions((current) => ({ ...current, temporary: undefined }));
      setConversations((current) => ({ ...current, temporary: [] }));
    } catch (caught) {
      setError(friendlyError(caught));
    } finally {
      setUploading(false);
    }
  }

  async function handleDeleteWorkspace() {
    if (!workspace) return;
    setError(undefined);
    try {
      await deleteWorkspace(workspace.workspace_id);
      setWorkspace(undefined);
      setSessions((current) => ({ ...current, temporary: undefined }));
      setConversations((current) => ({ ...current, temporary: [] }));
      setActiveCitation(undefined);
    } catch (caught) {
      setError(friendlyError(caught));
    }
  }

  if (loading) {
    return (
      <main aria-label="DeepMe 首页" className="deepme-loading">
        <LoaderCircle className="spin" />
        <span>正在读取知识版本</span>
      </main>
    );
  }

  return (
    <main aria-label="DeepMe 首页" className="deepme-app">
      <header className="deepme-header">
        <div className="deepme-brand">
          <div className="deepme-avatar">D</div>
          <div>
            <strong>{site?.name ?? 'DeepMe'}</strong>
            <span>{site?.bio}</span>
          </div>
        </div>
        <div className="deepme-mode-switch" aria-label="问答模式">
          <button
            aria-pressed={mode === 'system'}
            className={mode === 'system' ? 'active' : ''}
            onClick={() => setMode('system')}
            type="button"
          >
            <MessageCircle size={16} />
            问我
          </button>
          <button
            aria-pressed={mode === 'temporary'}
            className={mode === 'temporary' ? 'active' : ''}
            onClick={() => setMode('temporary')}
            type="button"
          >
            <UploadCloud size={16} />
            问你的资料
          </button>
        </div>
        <div className="deepme-version">
          <ShieldCheck size={15} />
          <span>{site?.knowledge_version.slice(0, 11)}</span>
        </div>
      </header>

      <section className="deepme-source-bar" aria-label="当前知识来源">
        <BookOpen size={15} />
        <span>当前知识来源</span>
        <strong>{sourceLabel}</strong>
        {mode === 'temporary' && workspace?.expires_at && (
          <span className="deepme-expiry">
            <Clock3 size={14} />
            {formatTime(workspace.expires_at)} 自动删除
          </span>
        )}
        {mode === 'temporary' && workspace && (
          <>
            <label className="deepme-source-add">
              <input
                accept=".md,.txt,.pdf"
                aria-label="继续添加知识文件"
                disabled={uploading || workspace.status === 'processing'}
                multiple
                onChange={(event) => void handleFiles(event.target.files)}
                type="file"
              />
              <UploadCloud size={13} />
              添加文件
            </label>
            <button
              className="deepme-source-delete"
              onClick={() => void handleDeleteWorkspace()}
              type="button"
            >
              <Trash2 size={13} />
              删除资料
            </button>
          </>
        )}
      </section>

      <div className="deepme-layout">
        <section className="deepme-chat">
          {messages.length === 0 && mode === 'system' && (
            <div className="deepme-hero">
              <span className="deepme-eyebrow">GROUNDED IN PUBLIC NOTES</span>
              <h1>面试我之前，先问我的知识库。</h1>
              <p>
                回答来自公开的项目记录、技术决策和长期复盘。每个事实都可以回到原文。
              </p>
              <div className="deepme-suggestions">
                {site?.suggested_questions.map((question) => (
                  <button
                    key={question}
                    onClick={() => void submitQuestion(question)}
                    type="button"
                  >
                    {question}
                    <ArrowUp size={15} />
                  </button>
                ))}
              </div>
            </div>
          )}

          {messages.length === 0 && mode === 'temporary' && (
            <div className="deepme-upload-card">
              <div className="deepme-upload-icon">
                {workspace?.status === 'processing' ? (
                  <LoaderCircle className="spin" />
                ) : (
                  <UploadCloud />
                )}
              </div>
              <h1>
                {workspace?.status === 'processing'
                  ? '正在整理你的资料'
                  : workspace?.status === 'ready'
                    ? '资料已经可以提问'
                    : '上传资料，开始一次私密问答'}
              </h1>
              <p>支持 Markdown、TXT 和可提取文本的 PDF。文件默认24小时后删除。</p>
              <label className="deepme-upload-button">
                <input
                  accept=".md,.txt,.pdf"
                  aria-label="上传知识文件"
                  disabled={uploading || workspace?.status === 'processing'}
                  multiple
                  onChange={(event) => void handleFiles(event.target.files)}
                  type="file"
                />
                {uploading ? <LoaderCircle className="spin" size={18} /> : <UploadCloud size={18} />}
                {workspace?.status === 'ready' ? '继续添加文件' : '选择文件'}
              </label>
              {workspace?.files.length ? (
                <div className="deepme-file-list" aria-label="已上传文件">
                  {workspace.files.map((file) => (
                    <div key={file.file_id}>
                      <FileText size={16} />
                      <span>{file.original_name}</span>
                      {file.status === 'ready' ? (
                        <Check className="success" size={16} />
                      ) : file.status === 'error' ? (
                        <X className="error" size={16} />
                      ) : (
                        <LoaderCircle className="spin" size={16} />
                      )}
                    </div>
                  ))}
                </div>
              ) : null}
              {workspace?.status === 'ready' && (
                <span className="deepme-workspace-ready" data-testid="workspace-ready">
                  <Check size={15} />
                  资料已就绪
                </span>
              )}
              {workspace && (
                <button
                  className="deepme-delete-button"
                  onClick={() => void handleDeleteWorkspace()}
                  type="button"
                >
                  <Trash2 size={15} />
                  立即删除资料
                </button>
              )}
            </div>
          )}

          {messages.length > 0 && (
            <div className="deepme-thread" aria-label="问答记录">
              {messages.map((message) => (
                <article
                  className={`deepme-message ${message.role === 'user' ? 'user' : 'assistant'}`}
                  key={message.message_id}
                >
                  <div className="deepme-message-role">
                    {message.role === 'user' ? '你' : site?.name ?? 'DeepMe'}
                  </div>
                  <MessageContent
                    citations={citations[message.message_id] ?? []}
                    content={message.content || '正在思考…'}
                    onCitation={setActiveCitation}
                  />
                  {message.answer_status === 'insufficient_evidence' && (
                    <span className="deepme-answer-status">当前知识范围没有足够证据</span>
                  )}
                </article>
              ))}
              <div ref={messagesEndRef} />
            </div>
          )}

          {error && (
            <div className="deepme-error" role="alert">
              {error}
              <button onClick={() => setError(undefined)} type="button">
                <X size={15} />
              </button>
            </div>
          )}

          <form className="deepme-composer" onSubmit={handleSubmit}>
            <textarea
              aria-label="提问输入框"
              disabled={mode === 'temporary' && workspace?.status !== 'ready'}
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' && !event.shiftKey) {
                  event.preventDefault();
                  void submitQuestion(input);
                }
              }}
              placeholder={
                mode === 'system'
                  ? '询问项目、技术决策或复盘…'
                  : workspace?.status === 'ready'
                    ? '基于你上传的资料提问…'
                    : '请先上传资料'
              }
              rows={1}
              value={input}
            />
            {streaming ? (
              <button
                aria-label="停止生成"
                className="deepme-send"
                onClick={() => abortRef.current?.abort()}
                type="button"
              >
                <X size={18} />
              </button>
            ) : (
              <button
                aria-label="发送"
                className="deepme-send"
                disabled={!input.trim() || (mode === 'temporary' && workspace?.status !== 'ready')}
                type="submit"
              >
                <ArrowUp size={18} />
              </button>
            )}
          </form>
          <p className="deepme-disclosure">
            回答会将问题和相关证据片段发送给站点配置的模型服务。上传内容不会进入作者知识库。
          </p>
        </section>

        {activeCitation && (
          <aside aria-label="引用来源" className="deepme-citation-drawer">
            <div className="deepme-citation-header">
              <div>
                <span>证据 {activeCitation.local_id}</span>
                <strong>{activeCitation.display_name ?? activeCitation.file_path}</strong>
              </div>
              <button onClick={() => setActiveCitation(undefined)} type="button">
                <X size={18} />
              </button>
            </div>
            <div className="deepme-citation-meta">
              {activeCitation.source_type === 'pdf' && activeCitation.page_start
                ? `第 ${activeCitation.page_start}${activeCitation.page_end !== activeCitation.page_start ? `-${activeCitation.page_end}` : ''} 页`
                : `第 ${activeCitation.start_line}-${activeCitation.end_line} 行`}
            </div>
            <pre>{activeCitation.content}</pre>
            <div className="deepme-citation-version">
              知识版本 {activeCitation.knowledge_version}
            </div>
          </aside>
        )}
      </div>
    </main>
  );
}
