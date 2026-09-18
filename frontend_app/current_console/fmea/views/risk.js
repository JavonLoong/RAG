import {el, badge, details, field, table, button} from '../ui.js';

function id(value) { return encodeURIComponent(String(value || '')); }

const riskDrafts = new WeakMap();

function valueText(value) {
  if (value == null) return '未提供';
  if (Array.isArray(value)) return value.join('；');
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
}

function quotedVersion(value, label) {
  const text = String(value || '').trim();
  if (!/^[1-9][0-9]*$/.test(text)) throw new Error(`${label}必须是已读取的正整数版本`);
  return `"${text}"`;
}

function resourceVersion(store, path, label) {
  const etag = store.resource(path)?.etag;
  if (!/^"[1-9][0-9]*"$/.test(etag || '')) throw new Error(`请先查询${label}，取得服务端版本后再提交操作`);
  return etag;
}

function control(form, name) {
  return form.querySelector(`[name="${name}"]`);
}

function formValue(form, name) { return String(control(form, name)?.value || '').trim(); }

function parseJson(form, name, expected, label) {
  const raw = formValue(form, name);
  let value;
  try { value = JSON.parse(raw); } catch { throw new Error(`${label}必须是有效 JSON`); }
  if (!expected(value)) throw new Error(`${label}不符合服务端请求合同`);
  return value;
}

function renderAssessment(assessment, response) {
  if (!assessment) return null;
  const dimensionRows = (assessment.dimensions || []).map(item => [
    item.name,
    valueText(item.value),
    valueText(item.uncertainty),
    valueText(item.evidence_ids),
    item.reason,
  ]);
  const panel = el('section', {className: 'panel'},
    el('h3', {}, '服务端风险评估'),
    el('div', {className: 'badges'}, badge(assessment.status), el('span', {className: 'badge'}, `资源版本：${assessment.record_version}`)),
    el('p', {}, `评估 ${assessment.assessment_id} · 行 ${assessment.row_id} · 来源行版本 ${assessment.source_record_version}`),
    table(['维度', '后端值', '不确定性', '证据 ID', '理由'], dimensionRows),
    assessment.derived ? details('后端派生评估（只读）', assessment.derived) : el('p', {className: 'muted'}, '服务端未提供派生评估。'),
    details('风险评估 DTO', assessment),
  );
  if (response?.etag) panel.append(el('p', {className: 'muted'}, `If-Match 来源：${response.etag}`));
  return panel;
}

function riskProposalForm({store, confirm, reportError, riskPath, contextPath, assessment}) {
  const form = el('form', {className: 'panel'},
    el('h3', {}, '请求风险评分建议'),
    el('p', {className: 'muted'}, '资源包、模板与规则版本必须由操作者明确提供；页面不会替你推断或创建版本。'),
    field('证据包 ID', 'evidence_pack_id', assessment?.evidence_pack_id || '', {required: true}),
    field('领域包 ID', 'domain_pack_id', assessment?.domain_pack_id || '', {required: true}),
    field('领域包版本', 'domain_pack_version', assessment?.domain_pack_version || '', {required: true}),
    field('模板 ID', 'template_id', '', {required: true}),
    field('模板版本', 'template_version', '', {required: true}),
    field('评分规则包 ID', 'rule_pack_id', assessment?.rule_pack_id || '', {required: true}),
    field('评分规则包版本', 'rule_pack_version', assessment?.rule_pack_version || '', {required: true}),
    button('提交风险评分建议', () => {
      try {
        const body = Object.fromEntries([
          'evidence_pack_id', 'domain_pack_id', 'domain_pack_version', 'template_id',
          'template_version', 'rule_pack_id', 'rule_pack_version',
        ].map(name => [name, formValue(form, name)]));
        if (Object.values(body).some(value => !value)) throw new Error('风险评分建议请求的每个字段都必须明确填写');
        confirm('提交风险评分建议', `${riskPath.replace(/\/risk$/, '')}/risk-proposal-runs`, body, resourceVersion(store, contextPath, '行上下文'), riskPath);
      } catch (error) { reportError(error); }
    }, store.state.busy),
  );
  return form;
}

function renderProposalRun({store, reportError, riskPath, rowBase, assessment}) {
  const proposalResponse = store.resource(`${rowBase}/risk-proposal-runs`);
  let draft = riskDrafts.get(store);
  if (!draft || draft.selection !== store.state.selection) {
    // Reauthentication also replaces selection identity. Do not rehydrate its old receipt.
    draft = {selection: store.state.selection, riskRunId: '',
      lastResponse: draft ? proposalResponse : undefined, run: null};
    riskDrafts.set(store, draft);
  }
  if (proposalResponse && proposalResponse !== draft.lastResponse) {
    draft.lastResponse = proposalResponse;
    draft.run = proposalResponse.data;
    draft.riskRunId = draft.run?.run_id || '';
  }
  const run = draft.run;
  const runId = draft.riskRunId;
  const status = runId ? store.resource(`/api/v1/fmea/risk-proposal-runs/${id(runId)}`)?.data : undefined;
  const panel = el('section', {className: 'panel', 'data-authority': 'model-suggestion'},
    el('h3', {}, '模型风险建议运行'),
    el('p', {}, '模型输出只作为建议，不能替代人工风险结论。'),
  );
  if (run) panel.append(details('最近提交结果', run));
  const form = el('form', {},
    field('风险建议运行 ID', 'risk_run_id', runId, {required: true}),
    button('查询风险建议状态', () => {
      try {
        const selected = formValue(form, 'risk_run_id');
        if (!selected) throw new Error('请输入已返回的风险建议运行 ID');
        draft.riskRunId = selected;
        store.read(`/api/v1/fmea/risk-proposal-runs/${id(selected)}`);
      } catch (error) { reportError(error); }
    }, store.state.busy),
  );
  panel.append(form);
  if (status) panel.append(details('查询到的风险建议状态', status));
  const current = status?.assessment || (run?.run_id === runId ? run?.assessment : null);
  if (current?.proposal_id) panel.append(el('p', {}, `候选提案 ${current.proposal_id}；请在人核对后确认或拒绝。`));
  return panel;
}

function renderDecisionControls({store, confirm, reportError, riskPath, assessment}) {
  if (!assessment?.proposal_id) return el('p', {className: 'muted'}, '服务端尚未提供可确认或拒绝的 proposal_id。');
  const proposalId = assessment.proposal_id;
  const context = el('section', {className: 'panel'},
    el('h3', {}, '人工风险决定'),
    el('p', {className: 'muted'}, `候选提案：${proposalId}。确认和拒绝都会携带当前服务端 ETag。`),
  );
  const rejectionForm = el('form', {},
    field('拒绝理由', 'risk_rejection_reason', '', {required: true, maxlength: 4096, multiline: true}),
    button('拒绝风险评分', () => {
      try {
        const reason = formValue(rejectionForm, 'risk_rejection_reason');
        if (!reason) throw new Error('拒绝风险评分必须填写理由');
        confirm('拒绝风险评分', `${riskPath.replace(/\/risk$/, '')}/risk-rejections`, {proposal_id: proposalId, reason}, resourceVersion(store, riskPath, '风险评估'), riskPath);
      } catch (error) { reportError(error); }
    }, store.state.busy),
  );
  context.append(
    button('确认风险评分', () => {
      try {
        confirm('确认风险评分', `${riskPath.replace(/\/risk$/, '')}/risk-confirmations`, {proposal_id: proposalId}, resourceVersion(store, riskPath, '风险评估'), riskPath);
      } catch (error) { reportError(error); }
    }, store.state.busy),
    rejectionForm,
  );
  return context;
}

export function renderRiskView({store, confirm, reportError}) {
  const rowId = store.state.selection?.rowId || '';
  const rowBase = `/api/v1/fmea/rows/${id(rowId)}`;
  const riskPath = `${rowBase}/risk`;
  const contextPath = store.contextPath?.() || `${rowBase}/review-context`;
  const response = store.resource(riskPath);
  const assessment = response?.data;
  const panel = el('section', {},
    el('h2', {}, '风险评分'),
    el('p', {}, '风险字段、派生值和状态均来自服务端 DTO；此视图不重算风险。'),
    button('查询风险评估', () => store.read(riskPath), store.state.busy),
  );
  if (response?.data) panel.append(renderAssessment(assessment, response));
  else panel.append(el('p', {className: 'banner'}, '尚未查询风险评估。请使用已有行 ID，读取服务端资源后再进行操作。'));
  panel.append(riskProposalForm({store, confirm, reportError, riskPath, contextPath, assessment}));
  panel.append(renderProposalRun({store, reportError, riskPath, rowBase, assessment}));
  panel.append(renderDecisionControls({store, confirm, reportError, riskPath, assessment}));
  const confirmation = store.resource(`${rowBase}/risk-confirmations`)?.data;
  if (confirmation) panel.append(el('section', {className: 'panel', 'data-authority': 'human-confirmed'}, details('人工风险确认结果', confirmation)));
  const rejection = store.resource(`${rowBase}/risk-rejections`)?.data;
  if (rejection) panel.append(el('section', {className: 'panel', 'data-authority': 'human-confirmed'}, details('人工风险拒绝结果', rejection)));
  return panel;
}
