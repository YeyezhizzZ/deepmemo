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
    rewrites: {
      'specs/current/agentic-testing.md': 'specs/agentic-testing.md',
      'specs/current/ai-chat-rag.md': 'specs/ai-chat-rag.md',
      'specs/current/asset-manager.md': 'specs/asset-manager.md',
      'specs/current/fs-watcher.md': 'specs/fs-watcher.md',
      'specs/current/query-routing.md': 'specs/query-routing.md',
      'specs/current/test-infrastructure.md': 'specs/test-infrastructure.md',
      'specs/current/wiki-graph.md': 'specs/wiki-graph.md',
      'specs/current/wiki-ingestion.md': 'specs/wiki-ingestion.md'
    },
    markdown: {
      theme: {
        light: 'github-light',
        dark: 'github-dark'
      }
    },
    mermaid: {
      theme: 'neutral'
    },
    themeConfig: {
      logo: '/logo.svg',
      search: { provider: 'local' },
      nav: [
        { text: '教程', link: '/guide/getting-started' },
        { text: '操作指南', link: '/how-to/configure-llm' },
        { text: '参考手册', link: '/reference/api' },
        { text: '概念解释', link: '/explanation/architecture' },
        { text: 'Specs', link: '/specs/' }
      ],
      sidebar: {
        '/guide/': [
          {
            text: '教程',
            items: [
              { text: '5 分钟快速上手', link: '/guide/getting-started' },
              { text: '写第一篇日记', link: '/guide/first-diary' },
              { text: '体验 AI 问答', link: '/guide/first-qa' },
              { text: '探索 Wiki 图谱', link: '/guide/explore-wiki' }
            ]
          }
        ],
        '/how-to/': [
          {
            text: '操作指南',
            items: [
              { text: '配置 LLM API', link: '/how-to/configure-llm' },
              { text: '管理知识库', link: '/how-to/manage-knowledge' },
              { text: '重建 Wiki', link: '/how-to/rebuild-wiki' },
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
              { text: 'Wiki 知识图谱', link: '/explanation/wiki-graph' },
              { text: 'RAG 搜索流程', link: '/explanation/rag-pipeline' },
              { text: '沙漏测试模型', link: '/explanation/testing-model' }
            ]
          }
        ],
        '/specs/': [
          {
            text: 'Spec 体系',
            items: [
              { text: '导航', link: '/specs/' },
              { text: 'Constitution', link: '/specs/constitution' },
              { text: 'AI Chat & RAG', link: '/specs/ai-chat-rag' },
              { text: 'Query Routing', link: '/specs/query-routing' },
              { text: 'Wiki Graph', link: '/specs/wiki-graph' },
              { text: 'Wiki Ingestion', link: '/specs/wiki-ingestion' },
              { text: 'File System Watcher', link: '/specs/fs-watcher' },
              { text: 'Asset Manager', link: '/specs/asset-manager' },
              { text: 'Test Infrastructure', link: '/specs/test-infrastructure' },
              { text: 'Agentic Testing', link: '/specs/agentic-testing' }
            ]
          }
        ]
      },
      socialLinks: [{ icon: 'github', link: repo }],
      editLink: {
        pattern: `${repo}/edit/main/docs/:path`,
        text: '在 GitHub 上编辑此页'
      },
      footer: {
        message: 'Local-first knowledge workbench',
        copyright: 'MIT License'
      }
    }
  })
);
