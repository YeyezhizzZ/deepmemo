# V3 前端设计文档

## 目标

V3 的前端不再只是一个编辑器页面，而是一个面向知识生产的工作台。它需要同时支持三类核心任务：

1. `Editor`：编辑原始 Markdown 文件，完成写作、整理、重构。
2. `QA`：围绕已有内容提问、追问、回溯证据。
3. `Wiki`：浏览、筛选、审核、合并和发布结构化知识。

因此，前端应采用 **Workspace 切换** 的组织方式，而不是把 Wiki 仅仅做成编辑器里的一个子标签。

## 背景：为什么从自制 contenteditable 切换到 Vditor

此前 DeepMemo 前端使用自制 `contenteditable` 实现 Markdown 编辑功能。但在实际使用中，自制方案遇到了三类难以解决的底层问题：

1. **输入法（IME）问题**：用户在输入中文时，IME 的 composition 事件与 contenteditable 的 text 更新逻辑冲突，导致选词上屏后内容被清空。
2. **回车换行解析**：不同浏览器对 `Enter` 键生成的节点（`<p>` vs `<br>`）不统一，导致 Markdown 源码中出现非法节点结构。
3. **光标位置映射**：在 DOM 树结构变化后（比如插入标题语法标记），光标偏移计算错误，造成用户输入位置跳飘。

Codex 协助排查后，建议采用 **Vditor** 的 WYSIWYG 内核——一个成熟的 Markdown 编辑器，直接规避了上述所有问题。

---

## Workspace 总设计

### 顶层入口

顶层只保留三个平级 Workspace：

| Workspace | 作用 | 典型任务 |
|---|---|---|
| `Editor` | 文件级写作与修改 | 新建、重命名、补写、格式化、AI 润色 |
| `QA` | 会话式问答与证据回溯 | 提问、追问、查看引用、跳转到证据 |
| `Wiki` | 知识库浏览与维护 | 搜索、查看页面、合并、拆分、审核、发布 |

这里的关键是：

- `Editor` 和 `QA` 是任务模式，回答的是“我现在要做什么”。
- `Wiki` 是知识模式，回答的是“我已经沉淀了什么、怎么维护、怎么复用”。
- 三者应该平级，不要把 Wiki 藏在 Editor 里，否则它会退化成另一个文档视图。

### 全局布局

建议采用统一骨架：

```text
Top Bar
  ├── Workspace Switcher
  ├── 全局搜索入口
  └── 状态 / 刷新 / 同步信息

Left Sidebar
  ├── 当前 Workspace 导航
  ├── 树 / 列表 / 会话 / 页面索引
  └── 筛选与快捷入口

Center Workspace
  ├── 主内容区
  └── 当前对象的详情 / 编辑 / 预览

Right Context Panel
  ├── 引用 / 证据
  ├── 相关页 / backlinks
  ├── 审核动作
  └── 变更历史
```

### Workspace 切换规则

- 切换 Workspace 不应销毁全局状态，只切换主内容和左侧导航内容。
- `Editor`、`QA`、`Wiki` 共享同一个应用壳。
- 当前对象需要保留最近访问状态，例如：
  - `Editor` 保留上一个文件
  - `QA` 保留上一个会话
  - `Wiki` 保留上一个页面或筛选条件

---

## 核心改动概览

| 文件 | 改动 |
|------|------|
| `app/package.json` | 新增依赖 `vditor: ^3.11.2` |
| `app/src/App.tsx:260` | 新增 `VditorMarkdownEditor` 组件 |
| `app/src/App.tsx:644` | 编辑器区域替换为 `<VditorMarkdownEditor>` |
| `app/src/styles.css:528` | Vditor 容器样式，让其填满编辑区 |
| `app/src/App.tsx` | 增加 `Wiki` Workspace 的主视图与状态切换 |
| `app/src/styles.css` | 补充 Wiki 列表、详情、证据面板的布局样式 |

---

## VditorMarkdownEditor 组件详解

```typescript
// App.tsx:260-333
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

  // 保持 onChange 回调引用最新（避免闭包陈旧）
  useEffect(() => {
    onChangeRef.current = onChange;
  }, [onChange]);

  // 保持 onSave 回调引用最新
  useEffect(() => {
    onSaveRef.current = onSave;
  }, [onSave]);

  // 初始化 Vditor 实例（仅执行一次）
  useEffect(() => {
    if (!mountRef.current) return undefined;

    const editor = new Vditor(mountRef.current, {
      value,                  // 初始内容
      mode: 'wysiwyg',        // WYSIWYG 模式（非 IR / SV）
      height: '100%',
      minHeight: 0,
      placeholder: 'Markdown',
      cache: { enable: false }, // 禁用本地缓存，避免多实例状态污染
      toolbar: [],             // 隐藏工具栏（我们不需要默认工具栏）
      counter: { enable: false },
      preview: {
        markdown: {
          autoSpace: true,     // 自动在中英文间加空格
        },
      },
      input: (nextValue) => {
        // Vditor 每次内容变化调用此回调
        latestValueRef.current = nextValue;
        onChangeRef.current(nextValue); // 冒泡到父组件
      },
      keydown: (event) => {
        // 拦截 Ctrl/Cmd + S，触发父组件保存
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

    // 组件卸载时销毁 Vditor 实例
    return () => {
      editor.destroy();
      if (editorRef.current === editor) {
        editorRef.current = undefined;
      }
    };
  }, []); // 空依赖，只执行一次

  // 外部 value 变化时（通常是切换文件），同步到 Vditor 内部
  useEffect(() => {
    const editor = editorRef.current;
    if (!editor || latestValueRef.current === value) return;
    latestValueRef.current = value;
    editor.setValue(value, true); // true = 同步模式，跳过 history 记录
  }, [value]);

  return <div className="vditor-editor-host" ref={mountRef} />;
}
```

### 关键设计决策

1. **双向数据流（父组件 ↔ Vditor）**
   - 父组件通过 `value` prop 传入内容，Vditor 通过 `input` 回调冒泡变更
   - 切换文件时触发 `editor.setValue()`，而非通过 prop 重新创建实例
   - 使用 `latestValueRef` 避免 Vditor 回调中的闭包陈旧问题

2. **缓存禁用（`cache: { enable: false }`）**
   - Vditor 默认将内容存 `localStorage`，多文件切换时会污染状态
   - 禁用后每次全量从父组件获取，行为更可预测

3. **工具栏隐藏（`toolbar: []`）**
   - DeepMemo 的编辑操作通过 slash command / AI 补完 / 快捷键提供
   - 不需要 Vditor 原生的格式化工具栏

4. **Ctrl/Cmd+S 保存**
   - Vditor 内置 `keydown` 回调拦截快捷键，委托给父组件的 `onSave`
   - 与后端 `a44ef67 feat: 编辑器支持 Ctrl+S 保存` commit 对应

---

## CSS 样式集成

```css
/* styles.css:528-565 */

/* 让 .vditor-editor-host 填满父容器 */
.vditor-editor-host,
.editor-pane--live > .vditor-editor-host,
.vditor-editor-host .vditor {
  height: 100%;
  min-height: 0;
}

/* Vditor 根容器 flex 布局，去掉默认边框 */
.vditor-editor-host .vditor {
  display: flex;
  flex-direction: column;
  border: 0;
  border-radius: 0;
  --border-color: var(--border);  /* 复用全局 CSS 变量 */
}

/* 内容区 flex: 1 填满剩余高度 */
.vditor-editor-host .vditor-content {
  flex: 1;
  min-height: 0;
}

/* WYSIWYG 编辑区域样式 */
.vditor-editor-host .vditor-wysiwyg {
  height: 100% !important;
  min-height: 0 !important;
  background: #fff;
  color: var(--text);
  font-size: 15px;
  line-height: 1.75;
  padding: 24px 28px 56px;   /* 与原 textarea 相同的内边距 */
}

/* 隐藏工具栏（我们不需要） */
.vditor-editor-host .vditor-toolbar {
  display: none;
}

/* reset 区域（Vditor 内部的 contenteditable）颜色适配 */
.vditor-editor-host .vditor-reset {
  color: var(--text);
}
```

### 样式设计要点

- **高度继承**：`height: 100%` + `min-height: 0` 确保 Vditor 在 `grid`/`flex` 父容器中正确填满
- **全局 CSS 变量**：`--border` 等变量来自 `:root`，保持与项目其他部分一致
- **工具栏隐藏**：Vditor 的工具栏 DOM 仍然存在但 `display: none`，避免重新初始化
- **padding 保持**：WYSIWYG 编辑区的 padding (24px 28px 56px) 与原来 `<textarea>` 的样式完全对齐

---

## 在 EditorContent 中的使用

```typescript
// App.tsx:641-649
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
    <div className="floating-menu entity-menu">...</div>
  )}
  {slashOpen && (
    <div className="floating-menu slash-menu">...</div>
  )}
</div>
```

布局层级：
```
.editor-surface (grid, 填满中间栏)
  └── .editor-pane--live (grid rows: 34px + minmax(0,1fr))
        ├── .editor-pane__label ("Markdown" 标签，固定高度 34px)
        └── .vditor-editor-host (flex column, flex:1 填满)
              └── .vditor (Vditor 实例)
                    └── .vditor-wysiwyg (实际 contenteditable)
```

---

## 与旧版 textarea 的行为对比

| 维度 | 旧版 `<textarea>` | V3 Vditor WYSIWYG |
|------|-------------------|-------------------|
| 输入法支持 | 偶发内容丢失 | 正常 |
| 回车换行 | 纯 `\n`，统一 | Vditor DOM 结构，无干扰 |
| 光标位置 | 自己维护 | Vditor 内置管理 |
| Markdown 预览 | 需额外渲染 | 所见即所得 |
| Ctrl+S | 自行监听 | Vditor keydown 回调 |
| 外部内容同步 | 直接修改 value | `editor.setValue()` |
| 工具栏 | 无 | 已隐藏 |

---

## 验证方式

```bash
# 构建验证
cd app && npm run build

# 启动后端
uv run uvicorn src.app.main:app --reload

# 启动前端（另一个终端）
cd app && npm run dev

# 访问
# 前端: http://127.0.0.1:5173/
# 后端文档: http://127.0.0.1:8000/docs
```

确认点：
1. 编辑器能正常输入中文（输入法选词不丢失）
2. 切换文件后内容正确更新（`setValue` 生效）

---

## Wiki Workspace 设计

### 设计目标

Wiki Workspace 不是“文档阅读器”，而是一个知识图谱工作台。它必须支持：

- 先按知识社区进入，再在社区内看图
- 快速看到社区规模、主题和健康度
- 在图里定位相关节点
- 在右侧查看节点信息、来源与关联
- 发现重复、冲突、孤儿节点，并逐步沉淀为稳定知识资产

### Wiki 的核心模型

Wiki Workspace 以“知识社区”为一级入口，图谱数据直接来自 `data/wiki/**/*.md`：

- 一个知识社区对应一张局部图谱
- 社区内部节点高度相关
- 社区之间弱相关或不相关
- 图谱节点是稳定的 wiki 页面，类型主要是 `source / entity / concept / synthesis`
- 社区是用户的认知入口，节点是用户的操作对象

建议数据模型如下：

| 对象 | 作用 |
|---|---|
| `community` | 一个知识社区，承载局部图谱的入口和摘要 |
| `node` | 图谱中的节点，对应稳定的 wiki 页面 |
| `edge` | 节点之间的关系边 |
| `source` | 节点背后的 raw / diary 原始 Markdown |
| `status` | 节点和社区的维护状态 |

图谱构建信号参考 `reference/llm_wiki/llm-wiki-skill` 的四信号模型：

- `direct link`：显式链接或直接引用
- `source overlap`：共享的 diary 支持来源
- `Adamic-Adar`：共同邻居带来的结构相似度
- `type affinity`：source / entity / concept 的类型亲和度

前端不需要自己重算这些信号，只消费后端返回的 `GET /wiki/graph` 结果。

### Wiki 内部结构

Wiki Workspace 内部建议分成三个主视图：

| 子视图 | 作用 |
|---|---|
| `Communities` | 左侧社区列表，中间图谱，右侧节点详情，默认入口 |
| `Search` | 全局检索标题、正文、标签、来源、别名，并定位到社区和节点 |
| `Review` | 处理待审核节点、冲突节点、低置信度节点 |

### 页面布局

默认路径建议是：

1. 进入 `Wiki`
2. 左侧显示知识社区列表
3. 中间显示当前社区图谱
4. 右侧显示当前选中节点的信息

```text
WikiWorkspace
  ├── Left: Communities
  ├── Center: Community Graph
  └── Right: Node Detail
```

### 知识社区列表展示字段

每个社区在左侧至少展示：

- `title`
- `summary`
- `node_count`
- `edge_count`
- `updated_at`
- `top_tags`

如果空间允许，再显示：

- `hub_nodes`
- `health`
- `confidence`

### 图谱中心视图

中间区域只负责展示当前社区图谱：

- 节点按关系布局
- 选中节点高亮
- 邻居节点弱高亮
- 不同类型节点用不同颜色和大小
- 图谱支持缩放、平移和节点点击

### 节点详情页结构

右侧面板只负责当前选中节点的信息：

- `title`
- `type`
- `status`
- `summary`
- `sources`
- `related`
- `backlinks`
- `tags`
- `last_updated`
- 操作按钮：`Edit`、`Merge`、`Split`、`Promote`、`Archive`

### Wiki 与 Editor / QA 的关系

- `Editor` 负责生产原始内容。
- `QA` 负责围绕内容做问答，产出证据链和临时结论。
- `Wiki` 负责把稳定知识编译成社区和图谱。

三者之间应该互相跳转：

- 从 `QA` 的引用卡跳到 `Wiki` 的节点或 source
- 从 `Wiki` 的节点跳回 raw 文件或原始会话
- 从 `Editor` 中选中的文件跳到对应的 Wiki 节点

这能保证系统不是三个孤岛，而是一条连续的知识流水线。

---

## 实现顺序建议

### 第 1 步：先把 Workspace 壳做出来

- 顶部加入 `Editor / QA / Wiki` 切换器
- 保留当前编辑器和问答功能
- 新增 `Wiki` 的占位视图

### 第 2 步：实现知识社区列表

- 从 `GET /wiki/graph` 读取完整图谱
- 图谱由后端基于 `data/wiki/**/*.md` 构建
- 社区由后端基于页面级图谱和 Louvain / fallback 聚类得到，而不是前端硬算 connected components
- 左侧按社区展示，而不是按页面展示

### 第 3 步：实现社区图谱

- 中间区域只显示当前社区内的局部图
- 节点支持点击、缩放、平移
- 节点选中后更新右侧详情

### 第 4 步：实现节点详情

- 支持查看 summary、body、sources、related、backlinks
- 右侧显示节点证据链和操作入口
- 支持从节点详情跳转到 wiki 页面或原始 diary 源文件

### 第 5 步：实现 Review 与 Search

- Review 用于冲突节点、待审核节点、低置信度节点
- Search 用于跨社区检索和快速定位入口

### 第 6 步：把 Wiki 与 Ingest 接起来

- 能从 raw 或 source 触发生成
- 能从前端触发 `data/diary -> data/wiki` 的重建，并重新拉取图谱
- 生成结果是“高频知识页”而不是“每日记录页”：daily diary 只作为 evidence，wiki 页面由 recurring entities / concepts / syntheses 组成
- 能刷新 index / overview / log
- 能对生成结果做人工确认和发布
3. Ctrl/Cmd+S 触发保存（后端收到请求）
4. Slash command (`/`) 和 entity mention (`@`) 浮层正常弹出
5. `npm run build` 无报错

---

## V3 实施记录：CDN 本地化 & StrictMode 修复

### 问题一：Vditor CDN 脚本加载失败导致组件崩溃

**现象**：页面完全空白，浏览器控制台报 `VditorMarkdownEditor` 组件错误，但 error message 为空字符串。

**根因分析**：

Vditor 初始化分两步异步加载外部脚本：

1. **i18n 脚本**：`${cdn}/dist/js/i18n/zh_CN.js` — 在构造函数中通过 `<script>` 标签动态注入
2. **Lute 引擎**：`${cdn}/dist/js/lute/lute.min.js` — 在 `init()` 方法中加载，是 Markdown ↔ HTML 双向转换的核心依赖

默认 CDN 为 `https://unpkg.com/vditor@3.x`。当网络不可达或加载失败时，`addScript` 函数的 `onerror` 回调以 `Event` 对象（非 `Error`）reject Promise，导致 React 捕获到的异常 `message` 为空。

关键代码路径（参考 `reference/vditor/src/`）：

```typescript
// reference/vditor/src/ts/util/addScript.ts
export const addScript = (path: string, id: string) => {
    return new Promise((resolve, reject) => {
        // ...
        scriptElement.onerror = (event) => {
            reject(event);  // Event 对象没有 .message 属性
        }
    });
};

// reference/vditor/src/index.ts:90 — i18n 加载
addScript(`${mergedOptions.cdn}/dist/js/i18n/${mergedOptions.lang}.js`, i18nScriptID)
    .then(() => { this.init(id, mergedOptions); })
    .catch(error => { this.showErrorTip(...); });

// reference/vditor/src/index.ts:521 — Lute 加载（无 .catch()）
addScript(mergedOptions._lutePath || `${mergedOptions.cdn}/dist/js/lute/lute.min.js`, "vditorLuteScript")
    .then(() => { /* initUI, after callback */ });
    // ← 没有 .catch()，reject 会变成 unhandled rejection
```

**修复方案**：将 Vditor 运行时资源（i18n、Lute、icons）从 npm 包复制到 `public/` 目录，通过 Vite dev server 本地服务，消除外部 CDN 依赖。

```bash
# 将 vditor dist 资源复制到 public 目录
cd app
mkdir -p public/vditor/dist
cp -r node_modules/vditor/dist/js   public/vditor/dist/
cp -r node_modules/vditor/dist/css  public/vditor/dist/
cp -r node_modules/vditor/dist/images public/vditor/dist/
```

组件中指定 `cdn` 为本地路径：

```typescript
// App.tsx:289
const editor = new Vditor(mountRef.current, {
    cdn: '/vditor',   // 从本地 public/vditor/dist/ 加载资源
    // ... 其他配置不变
});
```

资源加载路径映射：
| Vditor 内部路径 | 本地 HTTP 路径 | 文件系统路径 |
|---|---|---|
| `${cdn}/dist/js/i18n/zh_CN.js` | `/vditor/dist/js/i18n/zh_CN.js` | `public/vditor/dist/js/i18n/zh_CN.js` |
| `${cdn}/dist/js/lute/lute.min.js` | `/vditor/dist/js/lute/lute.min.js` | `public/vditor/dist/js/lute/lute.min.js` |
| `${cdn}/dist/js/icons/ant.js` | `/vditor/dist/js/icons/ant.js` | `public/vditor/dist/js/icons/ant.js` |

---

### 问题二：React StrictMode 双重挂载与 Vditor 异步初始化冲突

**现象**：CDN 本地化后，Vditor 资源能正常加载（HTTP 200），但组件仍然崩溃。

**根因**：React 18 StrictMode 在开发模式下执行 `mount → unmount → mount`。Vditor 的 `init()` 方法内部仍有异步脚本加载（Lute），第一次 mount 的异步回调可能在 unmount 之后才 resolve，与第二次 mount 的新实例产生竞争。

Vditor 的 `destroy()` 方法设置了 `isDestroyed = true`，`init()` 会检查该标志：

```typescript
// reference/vditor/src/index.ts:488-491
private init(id: HTMLElement, mergedOptions: IOptions) {
    if (this.isDestroyed) {
        return;  // 销毁后不再初始化
    }
    // ...
}
```

但在 StrictMode 下，两次 mount 共享同一个 DOM 元素，`addScript` 中基于 `document.getElementById(id)` 的去重逻辑可能导致脚本加载状态不一致。

**临时修复**：移除 StrictMode 包裹，使组件单次挂载。

```typescript
// main.tsx — 移除 StrictMode
createRoot(document.getElementById('root') as HTMLElement).render(
    <App />,
);
```

**待完成的正式修复**：在 `VditorMarkdownEditor` 的 useEffect 中增加 `cancelled` 标志，并添加 Error Boundary 包裹组件，使 StrictMode 双重挂载时 Vditor 能正确销毁和重建。

---

### 修改文件清单

| 文件 | 改动类型 | 说明 |
|---|---|---|
| `app/public/vditor/dist/` | **新增目录** | 从 `node_modules/vditor/dist/` 复制的运行时资源（js/css/images） |
| `app/src/App.tsx:289` | **修改** | Vditor 配置添加 `cdn: '/vditor'` |
| `app/src/main.tsx` | **修改** | 移除 `<StrictMode>` 包裹（临时方案） |
| `app/vite.config.ts` | **修改** | 添加 `publicDir: 'public'` 声明 |

---

### 验证结果

```
# 构建验证
cd app && npm run build   ← 通过

# 资源可达性验证
curl -s http://127.0.0.1:5173/vditor/dist/js/i18n/zh_CN.js     → 200
curl -s http://127.0.0.1:5173/vditor/dist/js/lute/lute.min.js   → 200
curl -s http://127.0.0.1:5173/vditor/dist/js/icons/ant.js       → 200

# 功能验证（浏览器截图确认）
✓ 左侧文件树正常渲染
✓ 中间 Vditor WYSIWYG 编辑器正确显示 DeepMemo.md 内容
✓ 右侧 Source 面板正常
✓ 顶部工具栏（编辑器模式 / 问答模式 / AI 补完 / 保存 / 格式化）可见
```

---

### 待完成工作

1. **重新启用 StrictMode**：在 `VditorMarkdownEditor` useEffect 中加 `cancelled` 标志 + Error Boundary，使 StrictMode 双重挂载下 Vditor 能正确销毁重建
2. **getHealth() API 路径**：`api.ts` 中 `getHealth()` 调用 `request('/')` 经拼接变成 `/api/`，需确认代理转发和后端返回格式一致
3. **交互功能测试**：中文输入法、文件切换 setValue、Ctrl+S 保存、Slash command、@ entity mention 浮层弹出
