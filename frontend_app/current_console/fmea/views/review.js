import {el, badge, details, field, select, table, button} from '../ui.js';
export function renderReviewView({store, confirm, reportError}) {
  const context = store.state.context;
  const panel = el('section', {}, el('h2', {}, '字段复核'), el('p', {}, '模型建议不是人工结论'));
  if (!context) { panel.append(el('p', {}, '请先载入行上下文。')); return panel; }
  panel.append(el('p', {className: 'muted'}, `资源版本：${context.row.record_version}`));
  const rowBase = `/api/v1/fmea/rows/${encodeURIComponent(store.state.selection.rowId)}`;
  const contextPath = store.contextPath();
  panel.append(el('section', {className: 'panel'}, table(['字段', '当前值', '主张状态', '证据状态', '证据 ID'], context.field_reviews.map(item => [item.target_field, Array.isArray(item.value) ? item.value.join('；') : item.value, badge(item.claim_status), badge(item.support_status), item.evidence_ids.join('、')]))));
  const suggestion = context.latest_suggestion;
  if (suggestion) panel.append(el('section', {className: 'panel', 'data-authority': 'model-suggestion'}, el('h3', {}, '△ 模型建议（未作为人工结论）'), el('p', {}, suggestion.rationale), el('p', {}, `建议 ${suggestion.suggestion_id} · 来源行版本 ${suggestion.source_record_version}${suggestion.stale ? ' · 已过期' : ''}`), details('逐字段建议与证据', suggestion)));
  const decisionPath = `${rowBase}/review-decisions`;
  const history = store.resource(decisionPath)?.data;
  const decisions = history?.items || context.decision_history;
  for (const decision of decisions) panel.append(el('section', {className: 'panel', 'data-authority': 'human-confirmed'}, el('h3', {}, '✓ 人工复核记录'), el('p', {}, `${decision.actor_id} · ${decision.action}`), el('p', {}, decision.reason), details('完整复核记录', decision)));
  panel.append(button('载入复核记录', () => store.read(decisionPath, {cursor: null}), store.state.busy));
  if (history?.next_cursor) panel.append(button('下一页复核记录', () => store.read(decisionPath, {cursor: history.next_cursor}), store.state.busy));
  const requestSuggestion = async () => {
    try {
      if (store.hasUnresolvedWrite) throw new Error('仍有进行中或未决的写入，请先核实或重试原请求');
      const path = `${rowBase}/review-suggestion-runs`;
      const op = store.client.operation(path, {review_policy: 'default', focus_fields: []}, store.resource(contextPath)?.etag);
      const result = await store.submit(op);
      if (result) { store.state.notice = '模型建议请求已提交'; store.changed(); }
    } catch (error) { reportError(error); }
  };
  panel.append(el('div', {className: 'actions'}, button('请求模型建议', requestSuggestion, store.state.busy || store.hasUnresolvedWrite)));
  const run = store.resource(`${rowBase}/review-suggestion-runs`)?.data;
  if (run) {
    const path = `/api/v1/fmea/review-suggestion-runs/${encodeURIComponent(run.run_id)}`;
    panel.append(details('建议运行状态', store.resource(path)?.data || run), button('刷新建议运行', () => store.read(path), store.state.busy), button('载入最新建议', () => store.loadContext(), store.state.busy));
  }
  const form = el('form', {className: 'panel'}, el('h3', {}, '提交人工复核'), select('复核操作', 'action', [['accept', '接受'], ['modify_and_accept', '修改后接受'], ['reject', '拒绝'], ['request_evidence', '请求补充证据'], ['defer', '暂缓']]), field('建议 ID（可留空）', 'suggestion_id', suggestion?.suggestion_id || ''), field('复核理由', 'reason', '', {required: true, maxlength: 500, multiline: true}), field('字段修改 JSON', 'edits', '[]', {multiline: true}), field('补证请求 JSON', 'evidence_requests', '[]', {multiline: true}), field('未解决问题确认 JSON', 'unresolved_acknowledgements', '[]', {multiline: true}), el('p', {className: 'muted'}, '只有明确核对后才提交。字段修改、补证与未解决问题按服务端合同校验；界面不会自动接受模型内容。'), el('button', {type: 'submit', disabled: store.state.busy || !context.reviewability}, '复核并确认'));
  form.addEventListener('submit', event => {
    event.preventDefault();
    try {
      const data = new FormData(form);
      const action = data.get('action');
      const reasons = {accept: 'ACCEPT_AS_IS', modify_and_accept: 'FIELD_CORRECTION', reject: 'UNSUPPORTED_CLAIM', request_evidence: 'EVIDENCE_REQUIRED', defer: 'DEFERRED_FOR_EXPERT'};
      const body = {action, suggestion_id: data.get('suggestion_id') || null, reason_code: reasons[action], reason: data.get('reason'), edits: JSON.parse(data.get('edits')), evidence_requests: JSON.parse(data.get('evidence_requests')), unresolved_acknowledgements: JSON.parse(data.get('unresolved_acknowledgements'))};
      confirm('提交人工复核', decisionPath, body, store.resource(contextPath)?.etag, contextPath);
    } catch (error) { reportError(error); }
  });
  panel.append(form);
  return panel;
}
