import {el, badge, details, button} from '../ui.js';
export function renderAnalysisView({store}) {
  const {context, selection} = store.state;
  const panel = el('section', {className: 'panel'}, el('h2', {}, '分析总览'));
  if (!context) return panel.appendChild(el('p', {}, '尚未载入行上下文。')).parentNode;
  panel.append(el('p', {}, `${context.identity.item_label} / ${context.identity.function_label}`), el('p', {className: 'muted'}, `分析 ${selection.analysisId} · 行 ${selection.rowId} · 修订 ${selection.revisionId}`), el('div', {className: 'badges'}, badge(context.row.claim_status), badge(context.row.review_status), badge(context.row.publication_status)), el('div', {className: 'banner'}, `行版本 ${context.row.record_version}。复核、风险、批准与发布是独立状态。`), el('p', {}, context.row.failure_mode), details('检索来源与警告', context.retrieval), details('原始行数据', context.row), button('刷新上下文', () => store.loadContext(), store.state.busy));
  for (const warning of context.warnings || []) panel.append(el('p', {}, warning));
  return panel;
}
