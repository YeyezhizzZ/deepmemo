import { useEffect, useMemo, useState } from 'react';
import {
  BookOpen,
  Check,
  Database,
  EyeOff,
  GitBranch,
  Pin,
  RefreshCw,
  Sparkles,
  WandSparkles,
  Wrench,
} from 'lucide-react';
import type {
  KnowledgeCard,
  KnowledgeHealth,
  KnowledgeHtmlPage,
  KnowledgeReviewItem,
  KnowledgeView,
  KnowledgeViewModel,
} from '../types';

type KnowledgeUpdates = {
  title: string;
  definition: string;
  keyFacts: string[];
  tags: string[];
  aliases: string[];
  relatedCards: string[];
};

type Props = {
  cards: KnowledgeCard[];
  activeCard?: KnowledgeCard;
  health?: KnowledgeHealth;
  viewModel?: KnowledgeViewModel;
  view: KnowledgeView;
  loading: boolean;
  onViewChange: (view: KnowledgeView) => void;
  onSelectCard: (slug: string) => void;
  onSave: (slug: string, updates: KnowledgeUpdates) => void;
  onMaintain: () => void;
  onRefresh: () => void;
  onConfirmReview: (itemId: string) => void;
  onHideReview: (itemId: string) => void;
  onRewriteReview: (itemId: string, instruction: string) => void;
  onApplyReview: (itemId: string) => void;
  onPinCardField: (slug: string, field: string) => void;
};

const viewLabels: Record<KnowledgeView, string> = {
  overview: 'Overview',
  reader: 'Reader',
  review: 'Review',
  cards: 'Cards',
};

function splitLines(value: string): string[] {
  return value
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean);
}

function severityRank(item: KnowledgeReviewItem): number {
  return item.severity === 'high' ? 0 : item.severity === 'medium' ? 1 : 2;
}

export function KnowledgeWorkspace({
  cards,
  activeCard,
  health,
  viewModel,
  view,
  loading,
  onViewChange,
  onSelectCard,
  onSave,
  onMaintain,
  onRefresh,
  onConfirmReview,
  onHideReview,
  onRewriteReview,
  onApplyReview,
  onPinCardField,
}: Props) {
  const [activePageSlug, setActivePageSlug] = useState<string>();
  const [activeReviewId, setActiveReviewId] = useState<string>();
  const pages = viewModel?.pages ?? [];
  const reviewItems = useMemo(
    () => [...(viewModel?.reviewQueue ?? [])].sort((a, b) => severityRank(a) - severityRank(b) || a.id.localeCompare(b.id)),
    [viewModel?.reviewQueue],
  );
  const activePage = pages.find((page) => page.slug === activePageSlug) ?? pages[0];
  const activeReview = reviewItems.find((item) => item.id === activeReviewId) ?? reviewItems[0];

  useEffect(() => {
    if (pages.length > 0 && !pages.some((page) => page.slug === activePageSlug)) {
      setActivePageSlug(pages[0].slug);
    }
  }, [pages, activePageSlug]);

  useEffect(() => {
    if (reviewItems.length > 0 && !reviewItems.some((item) => item.id === activeReviewId)) {
      setActiveReviewId(reviewItems[0].id);
    }
  }, [reviewItems, activeReviewId]);

  return (
    <section className="knowledge-v3">
      <div className="knowledge-v3__toolbar">
        <div className="knowledge-tabs" aria-label="Knowledge view">
          {(Object.keys(viewLabels) as KnowledgeView[]).map((item) => (
            <button
              key={item}
              className={view === item ? 'knowledge-tabs__button--active' : ''}
              type="button"
              onClick={() => onViewChange(item)}
            >
              {item === 'overview' && <Database size={15} />}
              {item === 'reader' && <BookOpen size={15} />}
              {item === 'review' && <Sparkles size={15} />}
              {item === 'cards' && <Wrench size={15} />}
              {viewLabels[item]}
            </button>
          ))}
        </div>
        <button type="button" onClick={onRefresh} disabled={loading}>
          <RefreshCw size={15} className={loading ? 'spin' : ''} />
          Refresh View
        </button>
      </div>

      {view === 'overview' && (
        <KnowledgeOverview
          viewModel={viewModel}
          cards={cards}
          health={health}
          onViewChange={onViewChange}
          onSelectCard={onSelectCard}
        />
      )}
      {view === 'reader' && (
        <KnowledgeReader
          pages={pages}
          activePage={activePage}
          onSelectPage={setActivePageSlug}
          onSelectCard={onSelectCard}
        />
      )}
      {view === 'review' && (
        <KnowledgeReviewQueue
          items={reviewItems}
          activeItem={activeReview}
          onSelectItem={setActiveReviewId}
          onSelectCard={onSelectCard}
          onConfirm={onConfirmReview}
          onHide={onHideReview}
          onRewrite={onRewriteReview}
          onApply={onApplyReview}
          onPin={onPinCardField}
        />
      )}
      {view === 'cards' && (
        <KnowledgeCards
          cards={cards}
          activeCard={activeCard}
          health={health}
          loading={loading}
          onSelectCard={onSelectCard}
          onSave={onSave}
          onMaintain={onMaintain}
          onPin={onPinCardField}
        />
      )}
    </section>
  );
}

function KnowledgeOverview({
  viewModel,
  cards,
  health,
  onViewChange,
  onSelectCard,
}: {
  viewModel?: KnowledgeViewModel;
  cards: KnowledgeCard[];
  health?: KnowledgeHealth;
  onViewChange: (view: KnowledgeView) => void;
  onSelectCard: (slug: string) => void;
}) {
  const openReviews = viewModel?.reviewQueue.filter((item) => item.status === 'open') ?? [];
  return (
    <div className="knowledge-v3__overview">
      <div className="knowledge-v3__summary-grid">
        {(viewModel?.overview ?? []).map((item) => (
          <button
            key={item.id}
            className="knowledge-v3__metric"
            type="button"
            onClick={() => onViewChange(item.id === 'reader' ? 'reader' : item.id === 'review' ? 'review' : 'overview')}
          >
            <span>{item.title}</span>
            <strong>{item.value}</strong>
            <small>{item.summary}</small>
          </button>
        ))}
        {viewModel?.overview.length ? null : (
          <div className="knowledge-empty">
            <Database size={24} />
            <strong>Knowledge View</strong>
            <span>{cards.length} cards indexed</span>
          </div>
        )}
      </div>

      <div className="knowledge-v3__overview-grid">
        <section className="knowledge-v3__panel">
          <div className="knowledge-v3__panel-header">
            <strong>Open Review</strong>
            <span>{openReviews.length} items</span>
          </div>
          <div className="knowledge-v3__compact-list">
            {openReviews.slice(0, 6).map((item) => (
              <button key={item.id} type="button" onClick={() => onViewChange('review')}>
                <span className={`knowledge-v3__severity knowledge-v3__severity--${item.severity}`}>{item.severity}</span>
                <strong>{item.title}</strong>
                <small>{item.summary}</small>
              </button>
            ))}
            {openReviews.length === 0 && <p className="knowledge-v3__muted">No open review items.</p>}
          </div>
        </section>

        <section className="knowledge-v3__panel">
          <div className="knowledge-v3__panel-header">
            <strong>Relations</strong>
            <span>{viewModel?.graph.edges.length ?? 0} edges</span>
          </div>
          <KnowledgeRelationCanvas graph={viewModel?.graph} onSelectCard={onSelectCard} />
        </section>

        <section className="knowledge-v3__panel">
          <div className="knowledge-v3__panel-header">
            <strong>Health</strong>
            <span>{health?.orphan_cards.length ?? 0} orphan</span>
          </div>
          <div className="knowledge-v3__health-list">
            <span>Total Cards: {viewModel?.stats.total_cards ?? cards.length}</span>
            <span>Avg Staleness: {health?.stats.avg_staleness ?? 0}</span>
            <span>Merge Hints: {health?.merge_suggestions?.length ?? 0}</span>
          </div>
        </section>
      </div>
    </div>
  );
}

function KnowledgeReader({
  pages,
  activePage,
  onSelectPage,
  onSelectCard,
}: {
  pages: KnowledgeHtmlPage[];
  activePage?: KnowledgeHtmlPage;
  onSelectPage: (slug: string) => void;
  onSelectCard: (slug: string) => void;
}) {
  return (
    <div className="knowledge-reader-v3">
      <nav className="knowledge-reader-v3__pages" aria-label="Knowledge HTML pages">
        {pages.map((page) => (
          <button
            key={page.slug}
            className={page.slug === activePage?.slug ? 'knowledge-reader-v3__page knowledge-reader-v3__page--active' : 'knowledge-reader-v3__page'}
            type="button"
            onClick={() => onSelectPage(page.slug)}
          >
            <BookOpen size={15} />
            <span>{page.title}</span>
            <small>{page.sections.length}</small>
          </button>
        ))}
        {pages.length === 0 && <div className="knowledge-list__empty">暂无 HTML Reader 页面</div>}
      </nav>

      <article className="knowledge-reader-v3__article">
        {activePage ? (
          <>
            <header className="knowledge-reader-v3__header">
              <div>
                <span>{activePage.path}</span>
                <h1>{activePage.title}</h1>
                <p>{activePage.summary}</p>
              </div>
              <strong>{activePage.cardSlugs.length} Cards</strong>
            </header>
            <div className="knowledge-reader-v3__sections">
              {activePage.sections.map((section) => (
                <section key={section.cardSlug} className="knowledge-reader-v3__section">
                  <div className="knowledge-reader-v3__section-header">
                    <span className={`knowledge-item__badge knowledge-item__badge--${section.type}`}>{section.type}</span>
                    <button type="button" onClick={() => onSelectCard(section.cardSlug)}>
                      <Database size={14} />
                      {section.cardSlug}
                    </button>
                  </div>
                  <h2>{section.title}</h2>
                  <p>{section.definition}</p>
                  {section.keyFacts.length > 0 && (
                    <ul>
                      {section.keyFacts.map((fact) => <li key={fact}>{fact}</li>)}
                    </ul>
                  )}
                  <div className="knowledge-reader-v3__sources">
                    {section.sources.map((source) => (
                      <span key={`${section.cardSlug}-${source.path}-${source.evidence}`}>
                        {source.path}
                        {source.start_line > 0 ? ` · L${source.start_line}-${source.end_line}` : ''}
                        {' · '}
                        {Math.round(source.confidence * 100)}%
                      </span>
                    ))}
                  </div>
                </section>
              ))}
            </div>
          </>
        ) : (
          <div className="knowledge-empty">
            <BookOpen size={24} />
            <strong>HTML Reader</strong>
            <span>从可追溯 Wiki Pages 渲染结构化人类阅读界面</span>
          </div>
        )}
      </article>
    </div>
  );
}

function KnowledgeReviewQueue({
  items,
  activeItem,
  onSelectItem,
  onSelectCard,
  onConfirm,
  onHide,
  onRewrite,
  onApply,
  onPin,
}: {
  items: KnowledgeReviewItem[];
  activeItem?: KnowledgeReviewItem;
  onSelectItem: (itemId: string) => void;
  onSelectCard: (slug: string) => void;
  onConfirm: (itemId: string) => void;
  onHide: (itemId: string) => void;
  onRewrite: (itemId: string, instruction: string) => void;
  onApply: (itemId: string) => void;
  onPin: (slug: string, field: string) => void;
}) {
  const [instruction, setInstruction] = useState('Make this clearer for human review.');
  const firstCardSlug = activeItem?.cardSlugs[0];

  return (
    <div className="knowledge-review-v3">
      <nav className="knowledge-review-v3__queue" aria-label="Knowledge review queue">
        {items.map((item) => (
          <button
            key={item.id}
            className={item.id === activeItem?.id ? 'knowledge-review-v3__item knowledge-review-v3__item--active' : 'knowledge-review-v3__item'}
            type="button"
            onClick={() => onSelectItem(item.id)}
          >
            <span className={`knowledge-v3__severity knowledge-v3__severity--${item.severity}`}>{item.severity}</span>
            <strong>{item.title}</strong>
            <small>{item.status} · {item.kind}</small>
          </button>
        ))}
        {items.length === 0 && <div className="knowledge-list__empty">暂无 Review 项</div>}
      </nav>

      <article className="knowledge-review-v3__detail">
        {activeItem ? (
          <>
            <header className="knowledge-review-v3__header">
              <span className={`knowledge-v3__severity knowledge-v3__severity--${activeItem.severity}`}>{activeItem.severity}</span>
              <div>
                <h1>{activeItem.title}</h1>
                <p>{activeItem.summary}</p>
              </div>
              <strong>{activeItem.status}</strong>
            </header>

            <div className="knowledge-review-v3__chips">
              {activeItem.cardSlugs.map((slug) => (
                <button key={slug} type="button" onClick={() => onSelectCard(slug)}>
                  <Database size={14} />
                  {slug}
                </button>
              ))}
              {activeItem.sourcePaths.map((path) => <span key={path}>{path}</span>)}
            </div>

            {activeItem.rewrite && (
              <section className="knowledge-review-v3__rewrite">
                <strong>Rewrite Proposal</strong>
                <p>{activeItem.rewrite.proposedDefinition}</p>
                <button type="button" onClick={() => onApply(activeItem.id)}>
                  <Check size={15} />
                  Apply Rewrite
                </button>
              </section>
            )}

            <label className="knowledge-review-v3__instruction">
              <span>Rewrite instruction</span>
              <textarea value={instruction} onChange={(event) => setInstruction(event.target.value)} rows={3} />
            </label>

            <div className="knowledge-review-v3__actions">
              <button type="button" onClick={() => onConfirm(activeItem.id)}>
                <Check size={15} />
                Confirm
              </button>
              <button type="button" onClick={() => onHide(activeItem.id)}>
                <EyeOff size={15} />
                Hide
              </button>
              <button type="button" onClick={() => onRewrite(activeItem.id, instruction)}>
                <WandSparkles size={15} />
                Request Rewrite
              </button>
              <button type="button" disabled={!firstCardSlug} onClick={() => firstCardSlug && onPin(firstCardSlug, 'definition')}>
                <Pin size={15} />
                Pin Definition
              </button>
            </div>
          </>
        ) : (
          <div className="knowledge-empty">
            <Sparkles size={24} />
            <strong>Review Queue</strong>
            <span>显式确认、隐藏、固定或请求重写生成知识</span>
          </div>
        )}
      </article>
    </div>
  );
}

function KnowledgeRelationCanvas({
  graph,
  onSelectCard,
}: {
  graph?: KnowledgeViewModel['graph'];
  onSelectCard: (slug: string) => void;
}) {
  const nodes = graph?.nodes ?? [];
  const edges = graph?.edges ?? [];
  const layout = useMemo(() => {
    if (nodes.length === 0) return new Map<string, { x: number; y: number }>();
    return new Map(
      nodes.map((node, index) => {
        const angle = (Math.PI * 2 * index) / nodes.length - Math.PI / 2;
        const radius = nodes.length <= 2 ? 28 : 38;
        return [node.id, { x: 50 + Math.cos(angle) * radius, y: 50 + Math.sin(angle) * radius }];
      }),
    );
  }, [nodes]);

  if (nodes.length === 0) {
    return (
      <div className="knowledge-relation-canvas knowledge-relation-canvas--empty">
        <GitBranch size={18} />
        <span>No relations yet</span>
      </div>
    );
  }

  return (
    <div className="knowledge-relation-canvas">
      <svg className="knowledge-relation-canvas__edges" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
        {edges.map((edge) => {
          const from = layout.get(edge.from);
          const to = layout.get(edge.to);
          if (!from || !to) return null;
          return <line key={`${edge.from}-${edge.to}-${edge.reason}`} x1={from.x} y1={from.y} x2={to.x} y2={to.y} />;
        })}
      </svg>
      {nodes.map((node) => {
        const point = layout.get(node.id) ?? { x: 50, y: 50 };
        return (
          <button
            key={node.id}
            className={`knowledge-relation-node knowledge-relation-node--${node.type}`}
            type="button"
            style={{ left: `${point.x}%`, top: `${point.y}%` }}
            onClick={() => onSelectCard(node.id)}
            title={node.title}
          >
            <span>{node.title}</span>
          </button>
        );
      })}
    </div>
  );
}

function KnowledgeCards({
  cards,
  activeCard,
  health,
  loading,
  onSelectCard,
  onSave,
  onMaintain,
  onPin,
}: {
  cards: KnowledgeCard[];
  activeCard?: KnowledgeCard;
  health?: KnowledgeHealth;
  loading: boolean;
  onSelectCard: (slug: string) => void;
  onSave: (slug: string, updates: KnowledgeUpdates) => void;
  onMaintain: () => void;
  onPin: (slug: string, field: string) => void;
}) {
  const [draft, setDraft] = useState({
    title: '',
    definition: '',
    keyFacts: '',
    tags: '',
    aliases: '',
    relatedCards: '',
  });

  useEffect(() => {
    setDraft({
      title: activeCard?.title ?? '',
      definition: activeCard?.definition ?? '',
      keyFacts: activeCard?.keyFacts.join('\n') ?? '',
      tags: activeCard?.tags.join(', ') ?? '',
      aliases: activeCard?.aliases.join(', ') ?? '',
      relatedCards: activeCard?.relatedCards.join(', ') ?? '',
    });
  }, [activeCard?.slug]);

  if (!activeCard) {
    return (
      <div className="knowledge-empty">
        <Database size={24} />
        <strong>Wiki Pages</strong>
        <span>{cards.length} cards indexed</span>
      </div>
    );
  }

  return (
    <div className="knowledge-cards-v3">
      <aside className="knowledge-cards-v3__list">
        {cards.map((card) => (
          <button
            key={card.slug}
            className={card.slug === activeCard.slug ? 'knowledge-cards-v3__card knowledge-cards-v3__card--active' : 'knowledge-cards-v3__card'}
            type="button"
            onClick={() => onSelectCard(card.slug)}
          >
            <span className={`knowledge-item__badge knowledge-item__badge--${card.type}`}>{card.type}</span>
            <strong>{card.title}</strong>
          </button>
        ))}
      </aside>
      <section className="knowledge-cards-v3__editor">
        <div className="knowledge-toolbar">
          <div className="knowledge-stats">
            <span>{health?.stats.total_cards ?? cards.length} cards</span>
            <span>{health?.orphan_cards.length ?? 0} orphan</span>
            <span>{health?.merge_suggestions?.length ?? 0} merge hints</span>
          </div>
          <button type="button" onClick={onMaintain} disabled={loading}>
            <Wrench size={15} />
            Maintain
          </button>
        </div>
        <div className="knowledge-editor">
          <label>
            <span>Title</span>
            <input value={draft.title} onChange={(event) => setDraft((current) => ({ ...current, title: event.target.value }))} />
          </label>
          <label>
            <span>Definition</span>
            <textarea value={draft.definition} onChange={(event) => setDraft((current) => ({ ...current, definition: event.target.value }))} rows={4} />
          </label>
          <label>
            <span>Key Facts</span>
            <textarea value={draft.keyFacts} onChange={(event) => setDraft((current) => ({ ...current, keyFacts: event.target.value }))} rows={6} />
          </label>
          <div className="knowledge-editor__grid">
            <label>
              <span>Tags</span>
              <input value={draft.tags} onChange={(event) => setDraft((current) => ({ ...current, tags: event.target.value }))} />
            </label>
            <label>
              <span>Aliases</span>
              <input value={draft.aliases} onChange={(event) => setDraft((current) => ({ ...current, aliases: event.target.value }))} />
            </label>
          </div>
          <label>
            <span>Related Cards</span>
            <input value={draft.relatedCards} onChange={(event) => setDraft((current) => ({ ...current, relatedCards: event.target.value }))} />
          </label>
        </div>
        <div className="knowledge-meta">
          <span>{activeCard.type}</span>
          <span>updated {activeCard.updatedAt}</span>
          <span>{activeCard.humanEdited ? `human edited: ${activeCard.humanEditedFields.join(', ')}` : 'auto compiled'}</span>
        </div>
        <div className="knowledge-savebar">
          <button
            type="button"
            onClick={() => onSave(activeCard.slug, {
              title: draft.title,
              definition: draft.definition,
              keyFacts: splitLines(draft.keyFacts),
              tags: splitLines(draft.tags.replace(/,/g, '\n')),
              aliases: splitLines(draft.aliases.replace(/,/g, '\n')),
              relatedCards: splitLines(draft.relatedCards.replace(/,/g, '\n')),
            })}
            disabled={loading}
          >
            <Check size={15} />
            Save Card
          </button>
          <button type="button" onClick={() => onPin(activeCard.slug, 'definition')} disabled={loading}>
            <Pin size={15} />
            Pin Definition
          </button>
        </div>
      </section>
    </div>
  );
}
