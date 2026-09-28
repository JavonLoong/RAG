# Layout contract

Touch these files for console chrome:

- `frontend_app/current_console/index.html`
- `frontend_app/current_console/styles/industrial-ops.css`
- `frontend_app/current_console/modules/console-app.js`

`styles/console.css` still contains old two-column rules. Win them with a more specific `body.industrial-console.workbench-unified` selector. Do not re-enable those old tracks.

## Required CSS

```css
body.industrial-console.workbench-unified .data-grid,
body.industrial-console.workbench-unified .search-layout,
body.industrial-console.workbench-unified .delivery-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  align-items: start;
}

body.industrial-console.workbench-unified .duty-split.is-sidebar-open {
  grid-template-columns: minmax(0, 1fr) minmax(320px, 0.7fr);
}

body.industrial-console .duty-sidebar[hidden] {
  display: none !important;
}
```

The open-state selector must stay more specific than the resting one-column rule. A later `@media` that sets `.data-grid { 1fr }` is fine; do not let it beat `.duty-split.is-sidebar-open` on desktop.

## Required markup

```html
<div class="data-grid duty-split" data-sidebar="kgInspectSidebar">
  <div class="stack">
    <article class="panel">
      <div class="panel-head">
        <div><h3>Duty title</h3></div>
        <button class="ghost-btn" type="button"
          data-sidebar-toggle="kgInspectSidebar" aria-expanded="false">
          <iconify-icon icon="ph:sidebar-simple-fill"></iconify-icon>
          <span>打开图谱</span>
        </button>
      </div>
      <!-- primary duty only -->
    </article>
  </div>
  <aside class="duty-sidebar" id="kgInspectSidebar" hidden>
    <!-- inspector: graph, logs, task board -->
  </aside>
</div>
```

Current ids:

| Duty | Toggle label | Sidebar id |
| --- | --- | --- |
| M2 知识组织 | 打开图谱 / 收起图谱 | `kgInspectSidebar` |
| M4 可信交付 | 打开任务台 / 收起任务台 | `deliveryInspectSidebar` |

M1 and M3 stay single-column. Do not invent a right column for empty result lists.

## Required JS

`setDutySidebar(id, open)` must:

1. set `aside.hidden = !open`
2. toggle `.is-sidebar-open` on the nearest `.duty-split` or `[data-sidebar]`
3. sync `aria-expanded` and the 打开 / 收起 label
4. dispatch `resize` after opening the graph pane so the SVG can relayout

Bind clicks once via `bindDutySidebars()` on boot next to `bindSplitMenus()`.

## Specificity trap

If the resting grid is two columns and the aside is `[hidden] { display: none }`, CSS Grid still paints an empty second track. That is the blank-white failure. Resting template must be one column; two columns only with `.is-sidebar-open`.

## Gear collision

`mountDutySettingsInline` moves `.gear-panel` out of `.gear-settings`. Two gears in one panel need distinct ids plus `data-gear-sheet` on the toggle, or the first sibling steals every click.

## Split menus

`.panel { overflow: hidden }` clips menus. Use `overflow: visible` and `.panel.is-menu-open { z-index: 40 }` so later panels do not paint over an open menu.

## Cache bust

After CSS/JS edits, bump:

- `styles/industrial-ops.css?v=`
- `modules/console-app.js?v=`

Hard-refresh `http://127.0.0.1:8000` (start `python api_server/current_console/server.py` if it is down).
