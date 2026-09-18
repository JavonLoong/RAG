import {el, badge, details, field, table, button} from '../ui.js';

const SVG_NS = 'http://www.w3.org/2000/svg';
const propagationDrafts = new WeakMap();

function id(value) { return encodeURIComponent(String(value || '')); }

function draftFor(store) {
  const selection = store.state.selection;
  const current = propagationDrafts.get(store);
  if (!current || current.selection !== selection) {
    const draft = {selection, graphRevisionId: '', propagationRunId: '', allowCachedOutputs: !current};
    propagationDrafts.set(store, draft);
    return draft;
  }
  return current;
}

function resourceVersion(store, path, label) {
  const etag = store.resource(path)?.etag;
  if (!/^"[1-9][0-9]*"$/.test(etag || '')) throw new Error(`请先查询${label}，取得服务端版本后再提交操作`);
  return etag;
}

function quotedVersion(value, label) {
  const text = String(value || '').trim();
  if (!/^[1-9][0-9]*$/.test(text)) throw new Error(`${label}必须是已读取的正整数版本`);
  return `"${text}"`;
}

function control(form, name) { return form.querySelector(`[name="${name}"]`); }
function formValue(form, name) { return String(control(form, name)?.value || '').trim(); }

function parseJson(form, name, label, fallback = undefined) {
  const raw = formValue(form, name);
  if (!raw && fallback !== undefined) return fallback;
  try { return JSON.parse(raw); } catch { throw new Error(`${label}必须是有效 JSON`); }
}

function svgElement(tagName, attributes = {}, ...children) {
  const node = document.createElementNS?.(SVG_NS, tagName) || document.createElement(tagName);
  for (const [name, value] of Object.entries(attributes)) node.setAttribute(name, String(value));
  node.append(...children.filter(child => child != null));
  return node;
}

function renderGraphSvg(graph) {
  const nodes = Array.isArray(graph?.nodes) ? graph.nodes : [];
  const edges = Array.isArray(graph?.edges) ? graph.edges : [];
  const width = 720;
  const height = Math.max(180, Math.min(640, 100 + nodes.length * 64));
  const svg = svgElement('svg', {
    viewBox: `0 0 ${width} ${height}`,
    role: 'img',
    'aria-label': '传播图只读投影',
    focusable: 'false',
  });
  const positions = new Map();
  nodes.forEach((node, index) => {
    const x = 80 + (index % 4) * 170;
    const y = 60 + Math.floor(index / 4) * 110;
    positions.set(node.node_id, {x, y});
  });
  for (const edge of edges) {
    const source = positions.get(edge.source_entity_id);
    const target = positions.get(edge.target_entity_id);
    if (!source || !target) continue;
    svg.append(svgElement('line', {x1: source.x, y1: source.y, x2: target.x, y2: target.y, stroke: '#6b8fa9', 'stroke-width': 2}));
  }
  nodes.forEach((node, index) => {
    const position = positions.get(node.node_id);
    const label = `${node.node_id} · ${node.node_type}`;
    svg.append(
      svgElement('circle', {cx: position.x, cy: position.y, r: 24, fill: '#e2eaf1', stroke: '#125d8e', 'stroke-width': 2}),
      svgElement('text', {x: position.x, y: position.y + 4, 'text-anchor': 'middle', 'font-size': 10, fill: '#192b3b'}, String(index + 1)),
      svgElement('title', {}, label),
    );
  });
  if (!nodes.length) svg.append(svgElement('text', {x: 16, y: 32, fill: '#516575'}, '服务端未提供节点'));
  return svg;
}

function renderGraphSummary(graph, response) {
  if (!graph) return el('p', {className: 'banner'}, '尚未查询传播图。请使用服务端返回的 graph_revision_id。');
  return el('section', {className: 'panel', 'data-authority': graph.status === 'proposed' ? 'model-suggestion' : undefined},
    el('h3', {}, '传播图（只读）'),
    el('div', {className: 'badges'}, badge(graph.status), el('span', {className: 'badge'}, `图版本：${graph.record_version}`)),
    el('p', {}, `图修订 ${graph.graph_revision_id} · 分析 ${graph.analysis_id} · 拓扑 ${graph.topology_snapshot_id}`),
    renderGraphSvg(graph),
    table(['边 ID', '源 → 目标', '关系', '审查状态', '发布状态'], (graph.edges || []).map(edge => [
      edge.edge_id,
      `${edge.source_entity_id} → ${edge.target_entity_id}`,
      edge.relation_type,
      badge(edge.review_status),
      badge(edge.publication_status),
    ])),
    el('p', {className: 'muted'}, `未解决问题：${(graph.unresolved_issue_codes || []).join('、') || '无'}`),
    details('传播图 DTO', graph),
    response?.etag ? el('p', {className: 'muted'}, `If-Match 来源：${response.etag}`) : null,
  );
}

function renderStartForm({store, confirm, reportError, analysisId, draft}) {
  const form = el('form', {className: 'panel'},
    el('h3', {}, '请求传播分析'),
    el('p', {className: 'muted'}, '源行 ID、证据包 ID 和分析版本必须由操作者明确提供；服务器资源包版本不在前端重建。'),
    field('源行 ID JSON 数组', 'source_row_ids', '', {required: true, multiline: true, placeholder: '["row-1"]'}),
    field('证据包 ID', 'evidence_pack_id', '', {required: true}),
    field('分析 If-Match 版本（已读取）', 'analysis_record_version', '', {required: true, inputmode: 'numeric'}),
    button('提交传播分析请求', () => {
      try {
        const sourceRowIds = parseJson(form, 'source_row_ids', '源行 ID JSON');
        if (!Array.isArray(sourceRowIds) || !sourceRowIds.length || sourceRowIds.some(item => typeof item !== 'string' || !item.trim())) {
          throw new Error('源行 ID JSON 必须是非空字符串数组');
        }
        const evidencePackId = formValue(form, 'evidence_pack_id');
        if (!evidencePackId) throw new Error('证据包 ID 必须明确填写');
        const body = {source_row_ids: sourceRowIds, evidence_pack_id: evidencePackId};
        const path = `/api/v1/fmea/analyses/${id(analysisId)}/propagation-runs`;
        draft.allowCachedOutputs = true;
        confirm('提交传播分析请求', path, body, quotedVersion(formValue(form, 'analysis_record_version'), '分析 If-Match 版本'));
      } catch (error) { reportError(error); }
    }, store.state.busy),
  );
  return form;
}

function renderRunStatus({store, reportError, draft, run}) {
  const form = el('form', {},
    field('传播运行 ID', 'propagation_run_id', draft.propagationRunId || run?.run_id || '', {required: true}),
    button('查询传播运行状态', () => {
      try {
        const runId = formValue(form, 'propagation_run_id');
        if (!runId) throw new Error('请输入已返回的传播运行 ID');
        draft.propagationRunId = runId;
        store.read(`/api/v1/fmea/propagation-runs/${id(runId)}`);
      } catch (error) { reportError(error); }
    }, store.state.busy),
  );
  const panel = el('section', {className: 'panel'}, el('h3', {}, '传播分析运行状态'));
  if (run) panel.append(details('最近提交结果', run));
  panel.append(form);
  const runId = draft.propagationRunId || formValue(form, 'propagation_run_id');
  if (runId) {
    const response = store.resource(`/api/v1/fmea/propagation-runs/${id(runId)}`);
    if (response?.data) panel.append(details('查询到的运行状态', response.data));
  }
  return panel;
}

function renderPaths({store, reportError, graphId}) {
  const path = `/api/v1/fmea/propagation-graphs/${id(graphId)}/paths`;
  const response = store.resource(path);
  const page = response?.data;
  const panel = el('section', {className: 'panel'},
    el('h3', {}, '传播路径（只读分页）'),
    button('查询传播路径', () => store.read(path, {cursor: null, limit: 50}), store.state.busy),
  );
  if (!page) return panel;
  panel.append(table(['路径 ID', '源 → 目标', '长度', '环路', '需人工复核'], (page.items || []).map(item => [
    item.path_id,
    `${item.source_entity_id} → ${item.target_entity_id}`,
    item.path_length,
    item.is_cyclic ? '是' : '否',
    item.requires_human_review ? '是' : '否',
  ])));
  for (const item of page.items || []) panel.append(details(`路径 ${item.path_id} 的服务端 DTO`, item));
  if (page.next_cursor) panel.append(button('下一页传播路径', () => store.read(path, {cursor: page.next_cursor, limit: page.limit}), store.state.busy));
  return panel;
}

function renderReviewForm({store, confirm, reportError, graphPath, graph}) {
  if (!graph) return null;
  const form = el('form', {className: 'panel'},
    el('h3', {}, '人工传播复核'),
    el('p', {className: 'muted'}, '只能复核服务端返回的 edge_id；页面不会编辑、补造或重新计算传播边。'),
    field('边决策 JSON', 'edge_decisions', '', {required: true, multiline: true, placeholder: '[{"edge_id":"…","action":"accept","reason":"…"}]'}),
    field('未解决问题确认 JSON', 'acknowledgements', '', {multiline: true, placeholder: '["ISSUE_CODE"]'}),
    button('确认传播复核', () => {
      try {
        const edgeDecisions = parseJson(form, 'edge_decisions', '边决策 JSON');
        if (!Array.isArray(edgeDecisions) || !edgeDecisions.length) throw new Error('边决策 JSON 必须是非空数组');
        for (const item of edgeDecisions) {
          if (!item || typeof item.edge_id !== 'string' || !item.edge_id || !['accept', 'reject'].includes(item.action) || typeof item.reason !== 'string' || !item.reason.trim()) {
            throw new Error('边决策 JSON 不符合服务端请求合同');
          }
        }
        const acknowledgements = parseJson(form, 'acknowledgements', '未解决问题确认 JSON', []);
        if (!Array.isArray(acknowledgements) || acknowledgements.some(item => typeof item !== 'string' || !item.trim())) throw new Error('未解决问题确认 JSON 不符合服务端请求合同');
        confirm('确认传播复核', `${graphPath}/reviews`, {edge_decisions: edgeDecisions, acknowledgements}, resourceVersion(store, graphPath, '传播图'), graphPath);
      } catch (error) { reportError(error); }
    }, store.state.busy),
  );
  return form;
}

export function renderPropagationView({store, confirm, reportError}) {
  const analysisId = store.state.selection?.analysisId || '';
  const draft = draftFor(store);
  const startPath = `/api/v1/fmea/analyses/${id(analysisId)}/propagation-runs`;
  const startRun = draft.allowCachedOutputs ? store.resource(startPath)?.data : undefined;
  if (startRun?.run_id) draft.propagationRunId = startRun.run_id;
  if (startRun?.graph?.graph_revision_id) draft.graphRevisionId = startRun.graph.graph_revision_id;
  const graphId = draft.graphRevisionId;
  const graphPath = graphId ? `/api/v1/fmea/propagation-graphs/${id(graphId)}` : '';
  const graphResponse = graphPath ? store.resource(graphPath) : undefined;
  const graph = graphResponse?.data;
  const panel = el('section', {},
    el('h2', {}, '传播分析'),
    el('p', {}, '图、路径和审查结果以服务端 DTO 为准；传播图在本页只读。'),
  );
  const graphQuery = el('form', {className: 'panel'},
    el('h3', {}, '查询传播图'),
    field('图修订 ID', 'graph_revision_id', draft.graphRevisionId, {required: true}),
    button('查询传播图', () => {
      try {
        const selected = String(graphQuery.querySelector('[name="graph_revision_id"]')?.value || '').trim();
        if (!selected) throw new Error('请输入已返回的 graph_revision_id');
        draft.graphRevisionId = selected;
        store.read(`/api/v1/fmea/propagation-graphs/${id(selected)}`);
      } catch (error) { reportError(error); }
    }, store.state.busy),
  );
  panel.append(graphQuery, renderGraphSummary(graph, graphResponse));
  panel.append(renderStartForm({store, confirm, reportError, analysisId, draft}));
  panel.append(renderRunStatus({store, reportError, draft, run: startRun}));
  if (graphId) {
    panel.append(renderPaths({store, reportError, graphId}));
    panel.append(renderReviewForm({store, confirm, reportError, graphPath, graph}));
    const review = store.resource(`${graphPath}/reviews`)?.data;
    if (review) panel.append(el('section', {className: 'panel', 'data-authority': 'human-confirmed'}, details('人工传播复核结果', review)));
  }
  return panel;
}
