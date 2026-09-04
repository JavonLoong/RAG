import {badge, button, details, el, field} from '../ui.js';

const MAX_UPLOAD_BYTES = 256 * 1024;
const HASH = /^(?:sha256:)?[0-9a-f]{64}$/;
const ID_MAX = 256;
const VERSION_MAX = 128;
const viewStates = new WeakMap();

const TEMPLATE_PATCH_RUN_KEYS = [
  'input_template_version', 'target_template_id', 'target_template_version', 'target_template_hash',
  'domain_pack_id', 'domain_pack_version', 'domain_pack_hash', 'evidence_pack_id', 'evidence_pack_hash',
];
const TEMPLATE_PATCH_ACCEPT_KEYS = [
  'suggestion_id', 'patch_id', 'draft_id', 'draft_sha256', 'target_template_version', 'target_template_hash',
  'new_template_version', 'domain_pack_hash', 'evidence_pack_hash', 'confirm_template_change',
];
const TEMPLATE_PATCH_REJECT_KEYS = ['suggestion_id', 'patch_id', 'reason'];
const MIGRATION_DRY_RUN_KEYS = [
  'migration_id', 'source_revision_hash', 'target_domain_pack_id', 'target_domain_pack_version',
  'target_domain_pack_hash',
];

function stateFor(store) {
  const selection = store.state.selection;
  let state = viewStates.get(store);
  if (!state || state.selectionObject !== selection) {
    state = {selectionObject: selection, dryRunBody: null, dryRunOperation: null};
    viewStates.set(store, state);
  }
  return state;
}

function pathId(value) { return encodeURIComponent(value); }
function selectionOf(store) { return store.state.selection || {}; }
function revisionPath(store) { return `/api/v1/fmea/revisions/${pathId(selectionOf(store).revisionId)}`; }

function resourcesWithPrefix(store, prefix) {
  return Object.entries(store.state.resources || {})
    .filter(([path]) => path.startsWith(prefix))
    .sort(([a], [b]) => a.localeCompare(b));
}

function draftResource(store) {
  const imported = store.resource('/api/v1/fmea/template-drafts');
  const importedId = imported?.data?.draft_id;
  if (importedId) return {path: `/api/v1/fmea/template-drafts/${pathId(importedId)}`, resource: imported};
  const saved = resourcesWithPrefix(store, '/api/v1/fmea/template-drafts/')
    .map(([path, resource]) => ({path, resource}))
    .find(({path, resource}) => /^\/api\/v1\/fmea\/template-drafts\/[^/]+$/.test(path) && resource?.data?.draft_id);
  if (saved) return saved;
  return null;
}

function patchResource(store) {
  const draft = draftResource(store);
  if (!draft) return null;
  const belongsToDraft = resource => resource?.data?.candidate?.draft_id === draft.resource.data.draft_id;
  const currentCreated = store.resource(`${draft.path}/patch-runs`);
  if (belongsToDraft(currentCreated) && currentCreated.data.candidate.patch_id) {
    const patchId = currentCreated.data.candidate.patch_id;
    const path = `/api/v1/fmea/template-patches/${pathId(patchId)}`;
    const canonical = store.resource(path);
    return {path, resource: belongsToDraft(canonical) ? canonical : currentCreated};
  }
  return resourcesWithPrefix(store, '/api/v1/fmea/template-patches/')
    .map(([path, resource]) => ({path, resource}))
    .find(({path, resource}) => belongsToDraft(resource) && resource.data.candidate.patch_id
      && path === `/api/v1/fmea/template-patches/${pathId(resource.data.candidate.patch_id)}`);
}

function reportResource(store, state) {
  const createdPath = `/api/v1/fmea/revisions/${pathId(selectionOf(store).revisionId)}/migration-dry-runs`;
  const created = store.resource(createdPath);
  const reportId = created?.data?.report_id;
  if (typeof reportId === 'string' && reportId) return {path: `/api/v1/fmea/migration-reports/${pathId(reportId)}`, resource: created};
  return null;
}

function requireEtag(resource, label) {
  if (!/^"[1-9][0-9]*"$/.test(resource?.etag || '')) throw new Error(`${label}没有可用的服务端版本，请先读取资源`);
  return resource.etag;
}

function report(reportError, error) {
  reportError(error instanceof Error ? error : new Error(String(error)));
}

function exactObject(value, keys, label) {
  let parsed;
  try { parsed = JSON.parse(value); } catch { throw new Error(`${label}必须是有效 JSON`); }
  if (!parsed || Array.isArray(parsed) || typeof parsed !== 'object') throw new Error(`${label}必须是 JSON 对象`);
  const actual = Object.keys(parsed);
  const unexpected = actual.filter(key => !keys.includes(key));
  const missing = keys.filter(key => !Object.hasOwn(parsed, key));
  if (unexpected.length || missing.length) {
    const extraText = unexpected.length ? `；多余字段：${unexpected.join('、')}` : '';
    const missingText = missing.length ? `；缺少字段：${missing.join('、')}` : '';
    throw new Error(`${label}字段与服务端 DTO 不一致${extraText}${missingText}`);
  }
  return parsed;
}

function text(value, name, limit = ID_MAX) {
  if (typeof value !== 'string' || !value.trim() || value.length > limit) throw new Error(`${name}必须是非空字符串`);
  return value;
}

function hash(value, name) {
  const normalized = text(value, name, 71);
  if (!HASH.test(normalized)) throw new Error(`${name}必须是 64 位小写 SHA-256（可带 sha256: 前缀）`);
  return normalized;
}

function validateTemplatePatchRun(body) {
  for (const name of TEMPLATE_PATCH_RUN_KEYS) text(body[name], name, name.endsWith('version') ? VERSION_MAX : ID_MAX);
  for (const name of ['target_template_hash', 'domain_pack_hash', 'evidence_pack_hash']) hash(body[name], name);
  return body;
}

function validateAcceptance(body) {
  for (const name of TEMPLATE_PATCH_ACCEPT_KEYS.filter(key => key !== 'confirm_template_change')) {
    text(body[name], name, name.endsWith('version') ? VERSION_MAX : ID_MAX);
  }
  for (const name of ['draft_sha256', 'target_template_hash', 'domain_pack_hash', 'evidence_pack_hash']) hash(body[name], name);
  body.confirm_template_change = true;
  return body;
}

function validateRejection(body) {
  text(body.suggestion_id, 'suggestion_id');
  text(body.patch_id, 'patch_id');
  text(body.reason, 'reason', 4096);
  return body;
}

function validateMigrationDryRun(body) {
  text(body.migration_id, 'migration_id');
  hash(body.source_revision_hash, 'source_revision_hash');
  text(body.target_domain_pack_id, 'target_domain_pack_id');
  text(body.target_domain_pack_version, 'target_domain_pack_version', VERSION_MAX);
  hash(body.target_domain_pack_hash, 'target_domain_pack_hash');
  return body;
}

function schemaExample(keys) {
  return JSON.stringify(Object.fromEntries(keys.map(key => [key, ''])), null, 2);
}

function jsonEditor(label, name, value, keys) {
  return el('label', {className: 'json-editor'}, label, el('textarea', {
    name, value, required: true, rows: Math.max(5, keys.length + 1), 'data-schema-keys': keys.join(','),
  }));
}

function draftUploadForm(store, reportError) {
  const file = el('input', {type: 'file', name: 'template_file', accept: '.xlsx,.docx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/vnd.openxmlformats-officedocument.wordprocessingml.document', required: true});
  const form = el('form', {className: 'panel', 'data-operation': 'template-draft-import'},
    el('h3', {}, '导入模板草稿'),
    el('p', {className: 'muted'}, '仅接受 XLSX/DOCX，浏览器只读取内存字节；服务端上限 256 KiB。不会提交或展示本地路径。'),
    el('label', {}, '模板文件（XLSX/DOCX）', file),
    el('button', {type: 'submit', disabled: store.state.busy}, '导入模板草稿'),
  );
  form.addEventListener('submit', async event => {
    event.preventDefault();
    try {
      const selected = file.files?.[0];
      if (!selected) throw new Error('请选择 XLSX 或 DOCX 文件');
      const filename = typeof selected.name === 'string' ? selected.name : '';
      if (!filename || filename !== filename.split(/[\\/]/).pop()) throw new Error('模板文件名不安全');
      const extension = filename.toLowerCase().split('.').pop();
      if (!['xlsx', 'docx'].includes(extension)) throw new Error('模板文件必须是 XLSX 或 DOCX');
      if (!Number.isInteger(selected.size) || selected.size > MAX_UPLOAD_BYTES) throw new Error('模板文件超过 256 KiB 限制');
      const operation = store.client.templateImportOperation(selected);
      const result = await store.submit(operation);
      if (result) {
        store.state.notice = '模板草稿已导入；请核对服务端解析结果。';
        store.changed?.();
      }
    } catch (error) { report(reportError, error); }
  });
  return form;
}

function renderDraft(store, draftEntry) {
  if (!draftEntry) return el('p', {className: 'muted'}, '尚未读取服务端模板草稿。');
  const draft = draftEntry.resource.data;
  return el('section', {className: 'panel', 'data-resource': draftEntry.path},
    el('h3', {}, '当前模板草稿 ', badge(draft.status || 'draft')),
    el('p', {}, `${draft.draft_id || '未提供'} · ${draft.source_filename || '未提供'} · ${draft.source_type || '未提供'}`),
    el('p', {className: 'muted'}, `源文件 SHA-256：${draft.source_sha256 || '未提供'}；资源版本：${draftEntry.resource.etag || '服务端未返回'}`),
    details('解析结构与警告（只读）', {structure: draft.structure || [], proposed_fields: draft.proposed_fields || [], unknown_fields: draft.unknown_fields || [], ambiguous_fields: draft.ambiguous_fields || [], parser_warnings: draft.parser_warnings || []}),
  );
}

function patchRunForm(store, draftEntry, reportError) {
  const draft = draftEntry?.resource?.data || {};
  const example = schemaExample(TEMPLATE_PATCH_RUN_KEYS);
  const form = el('form', {className: 'panel', 'data-operation': 'template-patch-suggest'},
    el('h3', {}, '生成模板补丁建议'),
    el('p', {className: 'muted'}, '只提交服务端 TemplatePatchRunRequest；模型只产生建议，页面不会接受或修改模板。'),
    jsonEditor('TemplatePatchRunRequest JSON（按上游交接填写；字段来自真实 schema）', 'template_patch_run_json', draft.patch_run_example ? JSON.stringify(draft.patch_run_example, null, 2) : example, TEMPLATE_PATCH_RUN_KEYS),
    el('details', {}, el('summary', {}, '字段 schema'), el('pre', {}, example)),
    el('button', {type: 'submit', disabled: store.state.busy || !draftEntry}, '请求补丁建议'),
  );
  form.addEventListener('submit', async event => {
    event.preventDefault();
    try {
      if (!draftEntry) throw new Error('请先读取一个服务端模板草稿');
      const body = validateTemplatePatchRun(exactObject(new FormData(form).get('template_patch_run_json'), TEMPLATE_PATCH_RUN_KEYS, 'TemplatePatchRunRequest'));
      const path = `${draftEntry.path}/patch-runs`;
      const operation = store.client.operation(path, body, requireEtag(draftEntry.resource, '模板草稿'));
      store.submit(operation);
    } catch (error) { report(reportError, error); }
  });
  return form;
}

function patchDetails(store, patchEntry, reportError, confirmCallback) {
  if (!patchEntry) return el('p', {className: 'muted'}, '尚未生成模板补丁建议。');
  const patch = patchEntry.resource.data;
  if (patch.decision_id && ['accepted', 'rejected'].includes(patch.action)) {
    return el('section', {className: 'panel', 'data-resource': patchEntry.path, 'data-authority': patch.actor_type === 'human' ? 'human-confirmed' : 'server-decision'},
      el('h3', {}, '模板补丁决定 ', badge(patch.action)),
      el('p', {}, `${patch.decision_id} · ${patch.patch_id} · 资源版本 ${patchEntry.resource.etag || '服务端未返回'}`),
      el('p', {}, `决定者：${patch.actor_id} · ${patch.actor_type}`),
      details('服务端决定（只读）', patch),
      button('刷新补丁状态', () => store.read(patchEntry.path), store.state.busy),
    );
  }
  const candidate = patch.candidate || {};
  const draftEntry = draftResource(store);
  const draft = draftEntry?.resource?.data || {};
  const patchId = candidate.patch_id || patch.patch_id;
  const draftId = candidate.draft_id || patch.draft_id || draft.draft_id;
  const acceptance = {
    suggestion_id: patch.suggestion_id || '', patch_id: patchId || '', draft_id: draftId || '',
    draft_sha256: draft.source_sha256 || '', target_template_version: candidate.target_template_version || '',
    target_template_hash: candidate.target_template_hash || '', new_template_version: '',
    domain_pack_hash: candidate.domain_pack_hash || '', evidence_pack_hash: candidate.evidence_pack_hash || '',
    confirm_template_change: true,
  };
  const acceptForm = el('form', {className: 'panel', 'data-operation': 'template-patch-accept'},
    el('h3', {}, '人工接受模板补丁'),
    el('p', {className: 'muted'}, '必须由人工填写新模板版本并在确认对话框中勾选；不会自动接受模型建议。'),
    ...TEMPLATE_PATCH_ACCEPT_KEYS.filter(key => key !== 'confirm_template_change').map(key => field(key, key, acceptance[key], {required: true, maxlength: key.endsWith('version') ? VERSION_MAX : ID_MAX})),
    el('button', {type: 'submit', disabled: store.state.busy}, '接受模板补丁'),
  );
  acceptForm.addEventListener('submit', event => {
    event.preventDefault();
    try {
      const data = new FormData(acceptForm);
      const body = validateAcceptance(Object.fromEntries(TEMPLATE_PATCH_ACCEPT_KEYS.map(key => [key, key === 'confirm_template_change' ? true : data.get(key)])));
      const path = `/api/v1/fmea/template-patches/${pathId(patchId)}/acceptance`;
      confirmOperation(confirmCallback, reportError, '接受模板补丁', path, body, patchEntry.resource, patchEntry.path);
    } catch (error) { report(reportError, error); }
  });
  const rejectForm = el('form', {className: 'panel', 'data-operation': 'template-patch-reject'},
    el('h3', {}, '人工拒绝模板补丁'),
    field('suggestion_id', 'suggestion_id', acceptance.suggestion_id, {required: true}),
    field('patch_id', 'patch_id', patchId || '', {required: true}),
    field('reason', 'reason', '', {required: true, maxlength: 4096, multiline: true}),
    el('button', {type: 'submit', disabled: store.state.busy}, '拒绝模板补丁'),
  );
  rejectForm.addEventListener('submit', event => {
    event.preventDefault();
    try {
      const data = new FormData(rejectForm);
      const body = validateRejection(Object.fromEntries(TEMPLATE_PATCH_REJECT_KEYS.map(key => [key, data.get(key)])));
      const path = `/api/v1/fmea/template-patches/${pathId(patchId)}/rejection`;
      confirmOperation(confirmCallback, reportError, '拒绝模板补丁', path, body, patchEntry.resource, patchEntry.path);
    } catch (error) { report(reportError, error); }
  });
  return el('section', {},
    el('section', {className: 'panel', 'data-resource': patchEntry.path, 'data-authority': 'model-suggestion'},
      el('h3', {}, '模型模板补丁建议 ', badge(patch.status || 'suggested')),
      el('p', {}, `${patch.suggestion_id || '未提供'} · ${patchId || '未提供'} · 资源版本 ${patchEntry.resource.etag || '服务端未返回'}`),
      details('建议与 diff（只读）', patch),
      button('刷新补丁状态', () => store.read(patchEntry.path), store.state.busy),
    ), acceptForm, rejectForm,
  );
}

function confirmOperation(confirmCallback, reportError, title, path, body, resource, refreshPath) {
  try {
    confirmCallback(title, path, body, requireEtag(resource, '操作资源'), refreshPath);
  } catch (error) { report(reportError, error); }
}

function migrationForm(store, reportError, state) {
  const form = el('form', {className: 'panel', 'data-operation': 'migration-dry-run'},
    el('h3', {}, '迁移干跑'),
    el('p', {className: 'muted'}, `源修订由当前选择绑定：${selectionOf(store).revisionId}。If-Match 只取修订资源真实 ETag；不会填写或推断版本号。`),
    jsonEditor('MigrationDryRunRequest JSON（真实 schema 示例；不得填本地路径）', 'migration_dry_run_json', state.dryRunBody ? JSON.stringify(state.dryRunBody, null, 2) : schemaExample(MIGRATION_DRY_RUN_KEYS), MIGRATION_DRY_RUN_KEYS),
    el('details', {}, el('summary', {}, '字段 schema'), el('pre', {}, schemaExample(MIGRATION_DRY_RUN_KEYS))),
    el('button', {type: 'submit', disabled: store.state.busy}, '执行迁移干跑'),
  );
  form.addEventListener('submit', async event => {
    event.preventDefault();
    try {
      const body = validateMigrationDryRun(exactObject(new FormData(form).get('migration_dry_run_json'), MIGRATION_DRY_RUN_KEYS, 'MigrationDryRunRequest'));
      const source = store.resource(revisionPath(store));
      const operation = store.client.operation(`/api/v1/fmea/revisions/${pathId(selectionOf(store).revisionId)}/migration-dry-runs`, body, requireEtag(source, '源修订'));
      const result = await store.submit(operation);
      if (result) {
        state.dryRunBody = body;
        state.dryRunOperation = operation;
        store.changed?.();
      }
    } catch (error) { report(reportError, error); }
  });
  return form;
}

function migrationConfirmation(store, reportError, state, reportEntry, confirmCallback) {
  if (!reportEntry || !state.dryRunBody || !state.dryRunOperation) return el('p', {className: 'muted'}, '完成一次干跑并读取报告后，才可进行人工确认。');
  if (!reportEntry.path.startsWith('/api/v1/fmea/migration-reports/')) {
    return el('p', {className: 'muted'}, '干跑结果已缓存，但服务端响应没有可确认的 migration report resource ID；不会猜测确认路径。');
  }
  const reportData = reportEntry.resource.data || {};
  const confirmationPath = `${reportEntry.path}/confirmations`;
  const receipt = store.resource(confirmationPath)?.data;
  if (receipt?.migration_id === state.dryRunBody.migration_id && receipt.report_hash === reportData.report_hash && typeof receipt.child_revision_id === 'string' && receipt.child_revision_id) {
    return el('section', {className: 'panel', 'data-resource': confirmationPath, 'data-authority': 'human-confirmed'},
      el('h3', {}, '迁移确认结果 ', badge('confirmed')),
      el('p', {}, `子修订：${receipt.child_revision_id}`),
      details('服务端迁移确认结果（只读）', receipt),
    );
  }
  const dryRunEtag = state.dryRunOperation.etag;
  const version = Number(dryRunEtag?.slice(1, -1));
  const body = {
    migration_id: state.dryRunBody.migration_id,
    report_hash: reportData.report_hash || '',
    source_revision_id: selectionOf(store).revisionId,
    source_revision_hash: state.dryRunBody.source_revision_hash,
    target_domain_pack_id: state.dryRunBody.target_domain_pack_id,
    target_domain_pack_version: state.dryRunBody.target_domain_pack_version,
    target_domain_pack_hash: state.dryRunBody.target_domain_pack_hash,
    dry_run: state.dryRunBody,
    dry_run_idempotency_key: state.dryRunOperation.key,
    dry_run_source_version: version,
    confirm_migration: true,
  };
  const form = el('form', {className: 'panel', 'data-operation': 'migration-confirm'},
    el('h3', {}, '人工确认迁移'),
    el('p', {className: 'muted'}, '仅确认原始干跑报告；原始干跑 key 与来源版本会原样绑定，页面不会自动确认。'),
    details('迁移报告（只读）', reportData),
    el('p', {}, `报告资源版本：${reportEntry.resource.etag || '服务端未返回'}；干跑 key：${state.dryRunOperation.key}；来源版本：${Number.isInteger(version) ? version : '无效'}`),
    el('button', {type: 'submit', 'data-operation': 'migration-confirm', disabled: store.state.busy || !HASH.test(body.report_hash) || !Number.isInteger(version) || version < 1}, '确认迁移'),
  );
  form.addEventListener('submit', event => {
    event.preventDefault();
    try {
      if (!HASH.test(body.report_hash)) throw new Error('迁移报告没有可验证的 report_hash');
      if (!Number.isInteger(version) || version < 1) throw new Error('原始干跑没有有效来源版本');
      confirmOperation(confirmCallback, reportError, '确认迁移', confirmationPath, body, reportEntry.resource, {
        onSuccess: data => typeof data?.child_revision_id === 'string' && data.child_revision_id
          ? `/api/v1/fmea/revisions/${pathId(data.child_revision_id)}` : null,
        onConflict: revisionPath(store),
      });
    } catch (error) { report(reportError, error); }
  });
  return form;
}

export function renderTemplatesView({store, confirm: confirmCallback, reportError}) {
  const state = stateFor(store);
  const draftEntry = draftResource(store);
  const patchEntry = patchResource(store);
  const reportEntry = reportResource(store, state);
  const panel = el('section', {},
    el('h2', {}, '模板与迁移交付'),
    el('p', {className: 'banner'}, '模板草稿、模型补丁建议、迁移干跑与人工确认保持独立状态；服务端资源版本是唯一依据。'),
    draftUploadForm(store, reportError),
    renderDraft(store, draftEntry),
    patchRunForm(store, draftEntry, reportError),
    patchDetails(store, patchEntry, reportError, confirmCallback),
    migrationForm(store, reportError, state),
    el('section', {className: 'panel'},
      el('h3', {}, '迁移报告与人工确认'),
      reportEntry ? el('p', {}, `原始干跑报告：${reportEntry.path}`) : el('p', {className: 'muted'}, '暂无迁移报告资源。'),
      migrationConfirmation(store, reportError, state, reportEntry, confirmCallback),
    ),
  );
  return panel;
}
