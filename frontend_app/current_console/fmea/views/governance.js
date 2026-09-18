import {el, badge, details, field, table, button} from '../ui.js';

function id(value) { return encodeURIComponent(String(value || '')); }

const governanceDrafts = new WeakMap();

function draftFor(store) {
  const selection = store.state.selection;
  const current = governanceDrafts.get(store);
  if (!current || current.selection !== selection) {
    const draft = {selection, allowCachedPostOutputs: !current, submissionId: '', approvalAction: '', approvalId: '', publicationId: ''};
    governanceDrafts.set(store, draft);
    return draft;
  }
  return current;
}

function responseData(store, path) { return store.resource(path)?.data; }

function control(form, name) { return form.querySelector(`[name="${name}"]`); }
function formValue(form, name) { return String(control(form, name)?.value || '').trim(); }

function quotedVersion(value, label) {
  const text = String(value || '').trim();
  if (!/^[1-9][0-9]*$/.test(text)) throw new Error(`${label}必须是已读取的正整数版本`);
  return `"${text}"`;
}

function etagNumber(etag) {
  const match = /^"([1-9][0-9]*)"$/.exec(etag || '');
  return match ? match[1] : '';
}

function resourceVersion(store, path, label) {
  const etag = store.resource(path)?.etag;
  if (!/^"[1-9][0-9]*"$/.test(etag || '')) throw new Error(`请先查询${label}，取得服务端版本后再提交操作`);
  return etag;
}

function revisionHash(revision) { return revision?.revision_hash || ''; }

function renderRevision({store, reportError, revisionPath, revision}) {
  const panel = el('section', {className: 'panel'}, el('h3', {}, '修订与就绪状态'));
  panel.append(
    button('查询修订', () => store.read(revisionPath), store.state.busy),
    button('查询发布就绪', () => store.read(`${revisionPath}/readiness`), store.state.busy),
  );
  if (!revision) {
    panel.append(el('p', {className: 'muted'}, '尚未查询修订；修订哈希、分析版本和父修订不会由前端猜测。'));
    return panel;
  }
  panel.append(
    el('div', {className: 'badges'}, el('span', {className: 'badge'}, `修订版本：${revision.record_version}`)),
    el('p', {}, `修订 ${revision.revision_id} · 分析 ${revision.analysis_id} · 哈希 ${revision.revision_hash}`),
    details('修订 DTO', revision),
  );
  return panel;
}

function renderAssemblyForm({store, confirm, reportError, analysisId, revisionPath, revision, draft}) {
  const form = el('form', {className: 'panel'},
    el('h3', {}, '组装修订'),
    el('p', {className: 'muted'}, '组装是人工确认的治理写入；分析版本必须来自已读取修订 DTO 或操作者明确提供的服务端版本。'),
    field('父修订 ID（可留空）', 'parent_revision_id', revision?.parent_revision_id || ''),
    field('父修订哈希（可留空）', 'parent_revision_hash', revision?.parent_revision_hash || ''),
    field('分析 If-Match 版本（已读取）', 'analysis_record_version', revision?.analysis_record_version || '', {required: true, inputmode: 'numeric'}),
    button('组装修订', () => {
      try {
        const body = {
          parent_revision_id: formValue(form, 'parent_revision_id') || null,
          parent_revision_hash: formValue(form, 'parent_revision_hash') || null,
          confirm_human_approval: true,
        };
        draft.allowCachedPostOutputs = true;
        confirm('组装修订', `/api/v1/fmea/analyses/${id(analysisId)}/revisions`, body, quotedVersion(formValue(form, 'analysis_record_version'), '分析 If-Match 版本'), revisionPath);
      } catch (error) { reportError(error); }
    }, store.state.busy),
  );
  return form;
}

function renderReadiness({store, confirm, reportError, revisionPath, readinessPath, revision, draft}) {
  const readiness = responseData(store, readinessPath);
  const suggestionPath = `${revisionPath}/readiness-suggestion-runs`;
  const suggestion = draft.allowCachedPostOutputs ? responseData(store, suggestionPath) : undefined;
  const panel = el('section', {className: 'panel'},
    el('h3', {}, '发布就绪（只读服务端结果）'),
    button('查询就绪结果', () => store.read(readinessPath), store.state.busy),
  );
  if (readiness) {
    panel.append(
      el('div', {className: 'badges'}, el('span', {className: 'badge'}, readiness.ready ? '服务端判定：可发布' : '服务端判定：不可发布')),
      el('p', {}, `修订 ${readiness.revision_id} · 目标修订版本 ${readiness.target_record_version} · deterministic=${readiness.deterministic}`),
      table(['问题代码', '严重性', '来源', '证据 ID', '确认决定'], (readiness.issues || []).map(issue => [
        issue.code, issue.severity, `${issue.source_type}:${issue.source_id}`, issue.evidence_ids.join('、'), issue.acknowledgement_decision_id || '未确认',
      ])),
      details('就绪 DTO', readiness),
    );
  } else {
    panel.append(el('p', {className: 'muted'}, '尚未查询 readiness；页面不会自行判断阻塞项。'));
  }
  panel.append(
    button('请求就绪清单建议', () => {
      try {
        // A new selection must explicitly authorize consuming the next POST output.
        draft.allowCachedPostOutputs = true;
        confirm('请求就绪清单建议', suggestionPath, {}, resourceVersion(store, revisionPath, '修订'), readinessPath);
      } catch (error) { reportError(error); }
    }, store.state.busy),
  );
  if (suggestion) panel.append(el('section', {'data-authority': 'model-suggestion'}, details('模型就绪建议（未作为人工结论）', suggestion)));
  return panel;
}

function renderApprovalSubmission({store, confirm, reportError, revisionPath, revision, draft}) {
  const path = `${revisionPath}/approval-submissions`;
  const result = draft.allowCachedPostOutputs ? responseData(store, path) : undefined;
  if (result?.submission_id) draft.submissionId = result.submission_id;
  const approvalEventsPath = `/api/v1/fmea/revisions/${id(revision?.revision_id || '')}/approval-events`;
  const form = el('form', {className: 'panel'},
    el('h3', {}, '提交审批'),
    field('修订哈希', 'submission_revision_hash', revisionHash(revision), {required: true}),
    button('提交审批', () => {
      try {
        const hash = formValue(form, 'submission_revision_hash');
        if (!hash) throw new Error('提交审批必须填写已读取的 revision_hash');
        draft.allowCachedPostOutputs = true;
        draft.submissionId = result?.submission_id || draft.submissionId;
        confirm('提交审批', path, {revision_hash: hash, confirm_human_approval: true}, resourceVersion(store, revisionPath, '修订'), approvalEventsPath);
      } catch (error) { reportError(error); }
    }, store.state.busy),
  );
  const panel = el('section', {}, form);
  if (result) panel.append(el('section', {className: 'panel', 'data-authority': 'human-confirmed'}, details('审批提交结果', result)));
  return panel;
}

function renderApprovalDecisions({store, confirm, reportError, revisionPath, revision, draft}) {
  const submissionPath = `${revisionPath}/approval-submissions`;
  const submission = draft.allowCachedPostOutputs ? responseData(store, submissionPath) : undefined;
  if (submission?.submission_id) draft.submissionId = submission.submission_id;
  const approvalEventsPath = `/api/v1/fmea/revisions/${id(revision?.revision_id || '')}/approval-events`;
  const submissionId = draft.submissionId;
  const decisionPath = draft.approvalAction && submissionId
    ? `/api/v1/fmea/approval-submissions/${id(submissionId)}/${draft.approvalAction}`
    : '';
  const approvalResponse = decisionPath ? store.resource(decisionPath) : undefined;
  const approvalResult = approvalResponse?.data;
  // Mutation receipts have no status. Only the exact successful approvals POST
  // for this selection is a known approval; rejection receipts also contain approval_id.
  draft.approvalId = draft.approvalAction === 'approvals'
    && draft.decisionRevisionId === store.state.selection?.revisionId
    ? approvalResult?.approval_id || '' : '';
  const approvalId = draft.approvalId;
  const approvalEtag = approvalResponse?.etag || '';
  const revisionId = revision?.revision_id || store.state.selection?.revisionId || '';
  const hash = revisionHash(revision);
  const decisionForm = el('form', {className: 'panel'},
    el('h3', {}, '批准或拒绝审批'),
    field('审批提交 ID', 'submission_id', submission?.submission_id || '', {required: true}),
    field('审批提交版本（已读取）', 'submission_record_version', etagNumber(store.resource(submissionPath)?.etag) || submission?.record_version || '', {required: true, inputmode: 'numeric'}),
    field('修订 ID', 'decision_revision_id', revisionId, {required: true}),
    field('修订哈希', 'decision_revision_hash', hash, {required: true}),
    field('审批理由', 'approval_reason', '', {required: true, maxlength: 4096, multiline: true}),
  );
  const decide = (action, label) => {
    try {
      const submissionId = formValue(decisionForm, 'submission_id');
      const revisionIdValue = formValue(decisionForm, 'decision_revision_id');
      const revisionHashValue = formValue(decisionForm, 'decision_revision_hash');
      const reason = formValue(decisionForm, 'approval_reason');
      if (!submissionId || !revisionIdValue || !revisionHashValue || !reason) throw new Error(`${label}需要完整的资源 ID、修订哈希和理由`);
      const path = `/api/v1/fmea/approval-submissions/${id(submissionId)}/${action}`;
      const body = {revision_id: revisionIdValue, revision_hash: revisionHashValue, reason, confirm_human_approval: true};
      draft.submissionId = submissionId;
      draft.approvalAction = action;
      draft.decisionRevisionId = revisionIdValue;
      draft.allowCachedPostOutputs = true;
      confirm(label, path, body, quotedVersion(formValue(decisionForm, 'submission_record_version'), '审批提交版本'), approvalEventsPath);
    } catch (error) { reportError(error); }
  };
  decisionForm.append(
    el('div', {className: 'actions'},
      button('批准审批', () => decide('approvals', '批准审批'), store.state.busy),
      button('拒绝审批', () => decide('rejections', '拒绝审批'), store.state.busy),
    ),
  );
  const panel = el('section', {}, decisionForm);
  if (approvalResult) panel.append(el('section', {className: 'panel', 'data-authority': 'human-confirmed'}, details('审批决定结果', approvalResult)));
  if (approvalId) panel.append(renderApprovalWithdrawal({store, confirm, reportError, approvalId, approvalEtag, revision, refreshPath: approvalEventsPath}));
  return panel;
}

function renderApprovalWithdrawal({store, confirm, reportError, approvalId, approvalEtag, revision, refreshPath}) {
  const form = el('form', {className: 'panel'},
    el('h3', {}, '撤回审批'),
    field('审批 ID', 'withdrawal_approval_id', approvalId, {required: true}),
    field('审批版本（已读取）', 'approval_record_version', etagNumber(approvalEtag), {required: true, inputmode: 'numeric'}),
    field('修订哈希', 'withdrawal_revision_hash', revisionHash(revision), {required: true}),
    field('撤回理由', 'approval_withdrawal_reason', '', {required: true, maxlength: 4096, multiline: true}),
    button('撤回审批', () => {
      try {
        const selectedApprovalId = formValue(form, 'withdrawal_approval_id');
        const hash = formValue(form, 'withdrawal_revision_hash');
        const reason = formValue(form, 'approval_withdrawal_reason');
        if (!selectedApprovalId || !hash || !reason) throw new Error('撤回审批需要审批 ID、修订哈希和理由');
        const path = `/api/v1/fmea/approvals/${id(selectedApprovalId)}/withdrawals`;
        confirm('撤回审批', path, {revision_hash: hash, reason, confirm_approval_withdrawal: true}, quotedVersion(formValue(form, 'approval_record_version'), '审批版本'), refreshPath);
      } catch (error) { reportError(error); }
    }, store.state.busy),
  );
  return form;
}

function renderPublication({store, confirm, reportError, revisionPath, revision, draft}) {
  const publishPath = `${revisionPath}/publications`;
  const publicationResult = draft.allowCachedPostOutputs ? responseData(store, publishPath) : undefined;
  if (publicationResult?.publication_id) draft.publicationId = publicationResult.publication_id;
  const publicationId = draft.publicationId;
  const approvalId = draft.approvalId;
  const publishForm = el('form', {className: 'panel'},
    el('h3', {}, '发布修订'),
    field('审批 ID', 'publication_approval_id', approvalId, {required: true}),
    field('修订哈希', 'publication_revision_hash', revisionHash(revision), {required: true}),
    button('发布修订', () => {
      try {
        const selectedApprovalId = formValue(publishForm, 'publication_approval_id');
        const hash = formValue(publishForm, 'publication_revision_hash');
        if (!selectedApprovalId || !hash) throw new Error('发布修订需要审批 ID 和已读取的 revision_hash');
        draft.allowCachedPostOutputs = true;
        confirm('发布修订', publishPath, {approval_id: selectedApprovalId, revision_hash: hash, confirm_publication: true}, resourceVersion(store, revisionPath, '修订'), {
          onSuccess: data => `/api/v1/fmea/publications/${encodeURIComponent(data.publication_id)}`,
          onConflict: revisionPath,
        });
      } catch (error) { reportError(error); }
    }, store.state.busy),
  );
  const panel = el('section', {}, publishForm);
  if (publicationResult) panel.append(el('section', {className: 'panel', 'data-authority': 'human-confirmed'}, details('发布结果', publicationResult)));
  panel.append(renderPublicationQueries({store, confirm, reportError, publicationId, revision, draft}));
  return panel;
}

function renderPublicationQueries({store, confirm, reportError, publicationId, revision, draft}) {
  const form = el('form', {className: 'panel'},
    el('h3', {}, '查询与管理发布资源'),
    field('发布 ID', 'publication_id', publicationId, {required: true}),
    field('发布版本（已读取）', 'publication_record_version', '', {required: true, inputmode: 'numeric'}),
    button('查询发布记录', () => {
      try {
        const selected = formValue(form, 'publication_id');
        if (!selected) throw new Error('请输入已返回的 publication_id');
        draft.publicationId = selected;
        const path = `/api/v1/fmea/publications/${id(selected)}`;
        store.read(path);
      } catch (error) { reportError(error); }
    }, store.state.busy),
    button('查询发布快照', () => {
      try {
        const selected = formValue(form, 'publication_id');
        if (!selected) throw new Error('请输入已返回的 publication_id');
        store.read(`/api/v1/fmea/publications/${id(selected)}/snapshot`);
      } catch (error) { reportError(error); }
    }, store.state.busy),
    el('div', {className: 'actions'},
      button('查询审批事件', () => store.read('/api/v1/fmea/revisions/' + id(revision?.revision_id || '' ) + '/approval-events', {cursor: null, limit: 50}), store.state.busy),
      button('查询发布生命周期事件', () => {
        try {
          const selected = formValue(form, 'publication_id');
          if (!selected) throw new Error('请输入已返回的 publication_id');
          store.read(`/api/v1/fmea/publications/${id(selected)}/lifecycle-events`, {cursor: null, limit: 50});
        } catch (error) { reportError(error); }
      }, store.state.busy),
    ),
  );
  const panel = el('section', {}, form);
  const approvalEventsPath = `/api/v1/fmea/revisions/${id(revision?.revision_id || '')}/approval-events`;
  const approvalEvents = responseData(store, approvalEventsPath);
  if (approvalEvents) panel.append(renderHistory('审批事件', approvalEvents, () => store.read(approvalEventsPath, {cursor: approvalEvents.next_cursor, limit: approvalEvents.limit})));
  const selected = formValue(form, 'publication_id');
  if (!selected) return panel;
  const publicationPath = `/api/v1/fmea/publications/${id(selected)}`;
  const publicationResponse = store.resource(publicationPath);
  const publication = publicationResponse?.data;
  if (publication) {
    const versionInput = control(form, 'publication_record_version');
    if (versionInput && !versionInput.value) versionInput.value = etagNumber(publicationResponse.etag) || publication.record_version || '';
    panel.append(details('发布记录 DTO', publication));
  }
  const snapshot = responseData(store, `${publicationPath}/snapshot`);
  if (snapshot) panel.append(details('发布快照 DTO（只读）', snapshot));
  const publicationEventsPath = `${publicationPath}/lifecycle-events`;
  const publicationEvents = responseData(store, publicationEventsPath);
  if (publicationEvents) panel.append(renderHistory('发布生命周期事件', publicationEvents, () => store.read(publicationEventsPath, {cursor: publicationEvents.next_cursor, limit: publicationEvents.limit})));
  panel.append(renderPublicationMutations({store, confirm, reportError, form, publicationPath, publication, revision}));
  return panel;
}

function renderHistory(title, page, next) {
  const section = el('section', {className: 'panel'}, el('h4', {}, title));
  section.append(table(['事件 ID', '命令', '演员', '理由', '应用版本'], (page.items || []).map(item => [
    item.event_id, item.command, `${item.actor_id} (${item.actor_type})`, item.reason, item.applied_record_version || '未应用',
  ])));
  if (page.next_cursor) section.append(button(`下一页${title}`, next));
  return section;
}

function renderPublicationMutations({store, confirm, reportError, form, publicationPath, publication, revision}) {
  const publicationId = formValue(form, 'publication_id');
  const withdrawalForm = el('form', {className: 'panel'},
    el('h4', {}, '撤回发布'),
    field('撤回理由', 'publication_withdrawal_reason', '', {required: true, maxlength: 4096, multiline: true}),
    field('替代发布 ID（可留空）', 'replacement_publication_id', ''),
    button('撤回发布', () => {
      try {
        const reason = formValue(withdrawalForm, 'publication_withdrawal_reason');
        if (!reason) throw new Error('撤回发布必须填写理由');
        const path = `/api/v1/fmea/publications/${id(publicationId)}/withdrawals`;
        const etag = resourceVersion(store, publicationPath, '发布记录');
        confirm('撤回发布', path, {reason, replacement_publication_id: formValue(withdrawalForm, 'replacement_publication_id') || null, confirm_publication_withdrawal: true}, etag, publicationPath);
      } catch (error) { reportError(error); }
    }, store.state.busy),
  );
  const supersedeForm = el('form', {className: 'panel'},
    el('h4', {}, '替代发布'),
    field('替代发布 ID', 'supersede_replacement_publication_id', '', {required: true}),
    field('替代发布版本（已读取）', 'replacement_record_version', '', {required: true, inputmode: 'numeric'}),
    field('替代理由', 'supersession_reason', '', {required: true, maxlength: 4096, multiline: true}),
    button('替代发布', () => {
      try {
        const replacementId = formValue(supersedeForm, 'supersede_replacement_publication_id');
        const replacementVersion = formValue(supersedeForm, 'replacement_record_version');
        const reason = formValue(supersedeForm, 'supersession_reason');
        if (!replacementId || !replacementVersion || !reason) throw new Error('替代发布需要替代资源 ID、已读取版本和理由');
        const path = `/api/v1/fmea/publications/${id(publicationId)}/supersessions`;
        confirm('替代发布', path, {replacement_publication_id: replacementId, replacement_record_version: Number(replacementVersion), reason, confirm_supersession: true}, resourceVersion(store, publicationPath, '发布记录'), publicationPath);
      } catch (error) { reportError(error); }
    }, store.state.busy),
  );
  const panel = el('section', {className: 'panel'}, withdrawalForm, supersedeForm);
  if (publication) panel.append(details('当前发布 DTO', publication));
  return panel;
}

export function renderGovernanceView({store, confirm, reportError}) {
  const draft = draftFor(store);
  const analysisId = store.state.selection?.analysisId || '';
  const revisionId = store.state.selection?.revisionId || '';
  const revisionPath = `/api/v1/fmea/revisions/${id(revisionId)}`;
  const readinessPath = `${revisionPath}/readiness`;
  const revisionResponse = store.resource(revisionPath);
  const revision = revisionResponse?.data;
  const panel = el('section', {},
    el('h2', {}, '治理与发布'),
    el('p', {className: 'banner'}, '草稿、就绪、审批、发布与生命周期状态只展示服务端返回；模型建议不是人工结论。'),
    renderRevision({store, reportError, revisionPath, revision}),
    renderAssemblyForm({store, confirm, reportError, analysisId, revisionPath, revision, draft}),
    renderReadiness({store, confirm, reportError, revisionPath, readinessPath, revision, draft}),
    renderApprovalSubmission({store, confirm, reportError, revisionPath, revision, draft}),
    renderApprovalDecisions({store, confirm, reportError, revisionPath, revision, draft}),
    renderPublication({store, confirm, reportError, revisionPath, revision, draft}),
  );
  const assemblyResult = draft.allowCachedPostOutputs ? responseData(store, `/api/v1/fmea/analyses/${id(analysisId)}/revisions`) : undefined;
  if (assemblyResult) panel.append(el('section', {className: 'panel', 'data-authority': 'human-confirmed'}, details('修订组装结果', assemblyResult)));
  return panel;
}
