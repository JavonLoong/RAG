---
name: industrial-ops-workbench
description: >-
  Restyle or implement the PowerRAG current_console as an industrial GraphRAG
  knowledge-organization workbench: full-width main column, collapse empty
  panes, optional duty sidebars, merged actions, gear settings, cool palette,
  Phosphor icons. Use when changing console UI, layout, 侧边栏, 空白, 充满屏幕,
  折叠, 打开侧边栏, industrial ops chrome, M1-M5 nav, or frontend_app/current_console.
---

# Industrial Ops Workbench

Treat `frontend_app/current_console` as a plant-ops GraphRAG workbench, not a consumer RAG demo. Read [references/layout-contract.md](references/layout-contract.md) before editing HTML/CSS/JS layout.

Evidence-bound M2–M5 delivery rules live in `govern-graphrag-delivery`. This skill covers chrome, density, and space. When a console control would have called an LLM API (schema 推荐, 图谱抽取, 问答, FMEA 生成), do not collect a key in the UI path — follow `govern-graphrag-delivery` agent-native slots and let the invoking agent fill the payload.

## Layout law

Apply this every time a page is grouped or split:

1. 右边一般是空白的，那些我们就直接让它充满屏幕。
2. 能折叠的都折叠，充分利用空间。
3. 需要侧边栏的，给一个打开侧边栏的选项。
4. 没有打开侧边栏的时候也是充分利用了，就跟没有侧边栏的一样。

Never reserve a second grid track for a hidden or empty inspector. A `display:none` aside inside a two-column grid still leaves a blank column — default to one column.

## Product chrome

- Pipeline only: **M1 资料接入** → **M2 知识组织** → **M3 图谱问答** → **M4 可信交付** → **M5 验收**.
- `WORKBENCH_ORDER = ["data","kg_data","kg_search","delivery","acceptance"]`.
- Admin / overview stay in the drawer. Do not add 语义检索 or a RAG/GraphRAG mode toggle to the nav.
- Keep `#page-kg` and `#page-search` hidden leftovers; do not remount them into the workbench.
- Brand: 动力装备知识组织 · GraphRAG. Actor: `local-user`.
- Customer-visible uploads stay filtered by `HIDDEN_LOCAL_UPLOAD_RE` and collection `power_equipment_demo`.
- Serve FastAPI at `http://127.0.0.1:8000` in the system browser. Do not start, debug, or package Electron.

## Density

- Primary actions on a duty: `添加▾` / `入库` / `更多` (`split-action`). Do not scatter 清除、导出、选择文件夹、勾选并回答 as sibling buttons.
- Defaults live in a gear (`gear-settings` / `gear-toggle` / `gear-panel`). Assign each gear a unique `data-gear-sheet` when two gears share a panel.
- Put 已处理文件 and quality summaries in a gear, not a standing column.
- Collapse empty inspectors, tall empty canvases, and unused schema editors. Show them when the user opens a sidebar or gear, or when data exists.
- After a graph actually renders, call `setDutySidebar("kgInspectSidebar", true)`. Do not auto-open an empty graph pane.

## Visual system

- Cool slate only. Canvas `#e6e9ee`, panels `#ffffff`, accent `#2c5f8a`. No yellowish brand, no `#b7aa94`.
- Icons: Iconify Phosphor fill (`ph:*-fill`). On-page wells `#e8eef5`; header icons monochrome on dark. Never put icons in dark-blue circular wells.
- Font stack: YaHei / PingFang before Inter.
- Industrial density: tight heads, no card shadows, 2px radius. Override leftover `console.css` two-column grids from `industrial-ops.css`.

## Implementation order

1. Map the page: main duty vs inspector vs settings vs overflow menu.
2. Main duty is a single `minmax(0,1fr)` column.
3. Inspectors go in `<aside class="duty-sidebar" hidden>` inside `.duty-split`.
4. Add one `[data-sidebar-toggle]` labeled 打开… / 收起….
5. Wire `setDutySidebar` / `bindDutySidebars` so closed state removes `is-sidebar-open`.
6. Bump `industrial-ops.css?v=` and `console-app.js?v=` after those files change.
7. Verify in the browser at `http://127.0.0.1:8000` — closed sidebar is full width; open sidebar shows the inspector; collapse restores full width. A single screenshot is not enough.

## Do not

- Force `grid-template-columns: 1fr 0.8fr` (or similar) as the resting layout.
- Leave a 480px / `52vh` empty graph box in the default view.
- Reintroduce Lucide, yellow chrome, or a standalone RAG page.
- Mark an industrial-UI `/goal` complete unless the user issued a new `/goal`.
- Invent completion percentages.
