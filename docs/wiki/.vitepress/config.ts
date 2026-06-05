import { defineConfig } from 'vitepress';
import { withMermaid } from 'vitepress-plugin-mermaid';

const repo = 'https://github.com/YeyezhizzZ/deepmemo';

export default withMermaid(
  defineConfig({
    title: 'DeepMemo',
    description: 'Local-first Markdown 知识库工作台',
    base: '/deepmemo/',
    cleanUrls: true,
    lastUpdated: true,
    markdown: {
      theme: {
        light: 'github-light',
        dark: 'github-dark'
      }
    },
    mermaid: {
      theme: 'neutral'
    },
    vite: {
      resolve: {
        preserveSymlinks: true
      }
    },
    themeConfig: {
      logo: '/logo.svg',
      search: { provider: 'local' },
      nav: [
        { text: '教程', link: '/guide/getting-started' },
        { text: 'Wiki', link: '/wiki/' },
        { text: 'Design', link: '/design/' },
        { text: 'Specs', link: '/specs/' },
        { text: '操作指南', link: '/how-to/configure-llm' },
        { text: '参考手册', link: '/reference/api' },
        { text: '概念解释', link: '/explanation/architecture' }
      ],
      sidebar: {
        '/guide/': [
          {
            text: '教程',
            items: [
              { text: '5 分钟快速上手', link: '/guide/getting-started' },
              { text: '写第一篇日记', link: '/guide/first-diary' },
              { text: '体验 AI 问答', link: '/guide/first-qa' }
            ]
          }
        ],
        '/wiki/': [
          {
            text: 'Wiki',
            items: [
              { text: 'Wiki 导航', link: '/wiki/' },
              { text: '探索 Wiki 图谱', link: '/wiki/explore' },
              { text: '重建 Wiki', link: '/wiki/rebuild' },
              { text: 'Wiki 知识图谱', link: '/wiki/graph' },
              { text: 'LLM Wiki 架构设计', link: '/wiki/design' },
              { text: '阶段性思考记录', link: '/wiki/notes' }
            ]
          }
        ],
        '/design/': [
          {
            text: 'Design',
            items: [
              { text: '设计导航', link: '/design/' },
              { text: '问题记录', link: '/design/issues' }
            ]
          },
          {
            text: 'Agentic Test',
            items: [
              { text: 'Agentic Testing Plan', link: '/design/agentic_test/agentic_testing_plan' },
              { text: 'Implementation Plan', link: '/design/agentic_test/implementation_plan' },
              { text: 'Spec-to-Test Prompt', link: '/design/agentic_test/spec_to_test_prompt' }
            ]
          },
          {
            text: 'AI',
            items: [
              { text: 'AI', link: '/design/ai/ai' },
              { text: 'AI Hot', link: '/design/ai/ai_hot' },
              { text: 'Web Search', link: '/design/ai/web_search' },
              { text: 'Tavily Quickstart', link: '/design/ai/reference/tavily_quickstart' },
              { text: 'Tavily SDK Reference', link: '/design/ai/reference/tavily_sdk_reference' }
            ]
          },
          {
            text: 'Backend',
            items: [
              { text: 'API', link: '/design/backend/api' },
              { text: 'Backend', link: '/design/backend/backend' },
              { text: 'Backend V2', link: '/design/backend/backend_v2' }
            ]
          },
          {
            text: 'Frontend',
            items: [
              { text: 'Frontend', link: '/design/frontend/frontend' },
              { text: 'Frontend V2', link: '/design/frontend/frontend_v2' },
              { text: 'Frontend V3', link: '/design/frontend/frontend_v3' }
            ]
          },
          {
            text: 'Version',
            items: [
              { text: 'V1', link: '/design/version/v1' },
              { text: 'V2', link: '/design/version/v2' }
            ]
          }
        ],
        '/specs/': [
          {
            text: 'Specs',
            items: [
              { text: 'Spec 导航', link: '/specs/' },
              { text: 'README', link: '/specs/README' },
              { text: 'Constitution', link: '/specs/constitution' },
              { text: 'Deprecated', link: '/specs/deprecated' }
            ]
          },
          {
            text: 'Current',
            items: [
              { text: 'Agentic Testing', link: '/specs/current/agentic-testing' },
              { text: 'AI Chat RAG', link: '/specs/current/ai-chat-rag' },
              { text: 'Asset Manager', link: '/specs/current/asset-manager' },
              { text: 'File System Watcher', link: '/specs/current/fs-watcher' },
              { text: 'Query Routing', link: '/specs/current/query-routing' },
              { text: 'Test Infrastructure', link: '/specs/current/test-infrastructure' },
              { text: 'Wiki Graph', link: '/specs/current/wiki-graph' },
              { text: 'Wiki Ingestion', link: '/specs/current/wiki-ingestion' }
            ]
          },
          {
            text: 'Goals',
            items: [
              { text: 'Chat Orchestrator', link: '/specs/goals/chat-orchestrator.goal' },
              { text: 'Document Indexing', link: '/specs/goals/document-indexing.goal' },
              { text: 'Legacy Cleanup', link: '/specs/goals/legacy-cleanup.goal' },
              { text: 'Memory Model', link: '/specs/goals/memory-model.goal' },
              { text: 'Project Wiki Generation', link: '/specs/goals/project-wiki-generation.goal' },
              { text: 'Retrieval Pipeline', link: '/specs/goals/retrieval-pipeline.goal' },
              { text: 'Spec-to-Test Pilot', link: '/specs/goals/spec-to-test-pilot.goal' }
            ]
          },
          {
            text: 'Review',
            items: [
              { text: 'Open Questions', link: '/specs/review/open-questions' },
              { text: 'Framework Comparison', link: '/specs/review/spec-framework-comparison' },
              { text: 'Review Draft', link: '/specs/review/spec-review-draft' }
            ]
          },
          {
            text: 'Templates',
            items: [
              { text: 'Current Spec Template', link: '/specs/templates/current-spec-template' },
              { text: 'Goal Spec Template', link: '/specs/templates/goal-spec-template' },
              { text: 'Implementation Task Template', link: '/specs/templates/implementation-task-template' },
              { text: 'Proposed Spec Template', link: '/specs/templates/proposed-spec-template' }
            ]
          }
        ],
        '/how-to/': [
          {
            text: '操作指南',
            items: [
              { text: '配置 LLM API', link: '/how-to/configure-llm' },
              { text: '管理知识库', link: '/how-to/manage-knowledge' },
              { text: '运行测试', link: '/how-to/run-tests' },
              { text: '贡献代码', link: '/how-to/contribute' }
            ]
          }
        ],
        '/reference/': [
          {
            text: '参考手册',
            items: [
              { text: 'REST API', link: '/reference/api' },
              { text: '配置项', link: '/reference/config' },
              { text: '数据模型', link: '/reference/data-models' },
              { text: '项目结构', link: '/reference/project-structure' },
              { text: '脚本命令', link: '/reference/cli-scripts' }
            ]
          }
        ],
        '/explanation/': [
          {
            text: '概念解释',
            items: [
              { text: '系统架构', link: '/explanation/architecture' },
              { text: 'Local-first 哲学', link: '/explanation/local-first' },
              { text: 'RAG 搜索流程', link: '/explanation/rag-pipeline' },
              { text: '沙漏测试模型', link: '/explanation/testing-model' }
            ]
          }
        ],
      },
      socialLinks: [{ icon: 'github', link: repo }],
      editLink: {
        pattern: `${repo}/edit/main/docs/wiki/:path`,
        text: '在 GitHub 上编辑此页'
      },
      footer: {
        message: 'Local-first knowledge workbench',
        copyright: 'MIT License'
      }
    }
  })
);
