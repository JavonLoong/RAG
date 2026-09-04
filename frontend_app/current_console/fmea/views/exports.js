import {badge, button, details, el, field, select} from '../ui.js';

const HASH = /^(?:sha256:)?[0-9a-f]{64}$/;
const ID_MAX = 256;
const viewStates = new WeakMap();

function stateFor(store) {
  const selection = store.state.selection;
  let state = viewStates.get(store);
  if (!state || state.selectionObject !== selection) {
    state = {selectionObject: selection, runId: null, lastDownload: null};
    viewStates.set(store, state);
  }
  return state;
}

function selectionOf(store) { return store.state.selection || {}; }
function pathId(value) { return encodeURIComponent(value); }
function revisionPath(store) { return `/api/v1/fmea/revisions/${pathId(selectionOf(store).revisionId)}`; }
function resourcesWithPrefix(store, prefix) {
  return Object.entries(store.state.resources || {}).filter(([path]) => path.startsWith(prefix)).sort(([a], [b]) => a.localeCompare(b));
}
function firstResource(store, prefix, predicate = () => true) {
  return resourcesWithPrefix(store, prefix).map(([path, resource]) => ({path, resource})).find(({resource}) => resource?.data && predicate(resource.data));
}
function revisionResource(store) { return store.resource(revisionPath(store)); }
function snapshotResource(store) { return firstResource(store, '/api/v1/fmea/publications/', data => data.snapshot_id && data.snapshot_hash); }
function narrativeResource(store) { return firstResource(store, `/api/v1/fmea/revisions/${pathId(selectionOf(store).revisionId)}/export-narrative-runs`); }
function runResource(store, state) {
  if (state.runId) {
    const exact = store.resource(`/api/v1/fmea/export-runs/${pathId(state.runId)}`);
    if (exact) return {path: `/api/v1/fmea/export-runs/${pathId(state.runId)}`, resource: exact};
  }
  const createdPath = `/api/v1/fmea/revisions/${pathId(selectionOf(store).revisionId)}/export-runs`;
  const created = store.resource(createdPath);
  const runId = created?.data?.export_run_id;
  if (runId) return {path: `/api/v1/fmea/export-runs/${pathId(runId)}`, resource: created};
  return firstResource(store, '/api/v1/fmea/export-runs/', data => data.revision_id === selectionOf(store).revisionId);
}
function error(reportError, value) { reportError(value instanceof Error ? value : new Error(String(value))); }
function requireEtag(resource, label) {
  if (!/^"[1-9][0-9]*"$/.test(resource?.etag || '')) throw new Error(`${label}没有可用的服务端版本，请先读取资源`);
  return resource.etag;
}
function text(value, name) {
  if (typeof value !== 'string' || !value.trim() || value.length > ID_MAX) throw new Error(`${name}必须是非空字符串`);
  return value;
}
function hash(value, name) {
  const normalized = text(value, name);
  if (!HASH.test(normalized)) throw new Error(`${name}必须是 64 位小写 SHA-256（可带 sha256: 前缀）`);
  return normalized;
}
function formValue(form, name) { return new FormData(form).get(name); }

function exportForm(store, reportError, state, snapshotEntry, confirmCallback) {
  const snapshot = snapshotEntry?.resource?.data || {};
  const format = select('导出格式', 'format', [['json', 'JSON'], ['xlsx', 'XLSX'], ['docx', 'DOCX']]);
  const mode = select('输出状态', 'publication_mode', [['preview', '草稿预览（不发布）'], ['published', '已发布导出']]);
  format.value = 'json';
  mode.value = 'preview';
  const form = el('form', {className: 'panel', 'data-operation': 'export-run'},
    el('h3', {}, '生成导出'),
    el('p', {className: 'muted'}, '预览与已发布导出是两个明确选择；服务端返回的运行状态与 artifact 身份才是权威结果。'),
    field('snapshot_id', 'snapshot_id', snapshot.snapshot_id || '', {required: true, maxlength: ID_MAX}),
    field('snapshot_hash', 'snapshot_hash', snapshot.snapshot_hash || '', {required: true, maxlength: 71}),
    field('publication_id（预览留空）', 'publication_id', snapshot.publication_id || '', {maxlength: ID_MAX}),
    format, mode,
    el('p', {className: 'muted'}, `修订 If-Match 来源：${revisionResource(store)?.etag || '尚未读取'}；导出创建响应可能没有 ETag，不从 ExportRun 推断版本。`),
    el('button', {type: 'submit', disabled: store.state.busy}, '生成导出运行'),
  );
  form.addEventListener('submit', async event => {
    event.preventDefault();
    try {
      const snapshotId = text(formValue(form, 'snapshot_id'), 'snapshot_id');
      const snapshotHash = hash(formValue(form, 'snapshot_hash'), 'snapshot_hash');
      const published = formValue(form, 'publication_mode') === 'published';
      const publicationId = published ? text(formValue(form, 'publication_id'), 'publication_id') : null;
      const body = {snapshot_id: snapshotId, snapshot_hash: snapshotHash, format: formValue(form, 'format'), publication_id: publicationId, draft_preview: !published, confirm_publication: published};
      if (!['json', 'xlsx', 'docx'].includes(body.format)) throw new Error('format 必须是 json、xlsx 或 docx');
      const path = `/api/v1/fmea/revisions/${pathId(selectionOf(store).revisionId)}/export-runs`;
      const etag = requireEtag(revisionResource(store), '源修订');
      if (published) {
        try { confirmCallback('确认已发布导出', path, body, etag, revisionPath(store)); } catch (confirmError) { error(reportError, confirmError); }
      } else {
        const operation = store.client.operation(path, body, etag);
        const result = await store.submit(operation, revisionPath(store));
        const runId = result?.data?.export_run_id;
        if (runId) state.runId = runId;
      }
    } catch (submitError) { error(reportError, submitError); }
  });
  return form;
}

function runPanel(store, reportError, state, runEntry) {
  if (!runEntry) return el('section', {className: 'panel'}, el('h3', {}, '导出运行状态'), el('p', {className: 'muted'}, '暂无导出运行。'));
  const run = runEntry.resource.data || {};
  if (run.export_run_id) state.runId = run.export_run_id;
  const artifactPath = run.artifact_id ? `/api/v1/fmea/export-artifacts/${pathId(run.artifact_id)}` : null;
  const download = artifactPath ? button('下载服务端 artifact', () => downloadArtifact(store, reportError, state, artifactPath, run), store.state.busy) : null;
  if (download) download.setAttribute('data-operation', 'download-artifact');
  return el('section', {className: 'panel', 'data-resource': runEntry.path},
    el('h3', {}, '导出运行状态 ', badge(run.status || 'queued')),
    el('p', {}, `${run.export_run_id || '未提供'} · ${run.format || '未提供'} · ${run.draft_preview ? '草稿预览' : '已发布导出'}`),
    el('p', {className: 'muted'}, `revision ${run.revision_id || selectionOf(store).revisionId} · snapshot ${run.snapshot_id || '未提供'} · artifact ${run.artifact_id || '尚未生成'}`),
    details('服务端运行 DTO（只读）', run),
    button('刷新运行状态', () => store.read(runEntry.path), store.state.busy), download,
    state.lastDownload ? el('p', {className: 'notice'}, `已下载并保留服务端文件名：${state.lastDownload.filename}；hash identity：${state.lastDownload.hash}`) : null,
  );
}

function normalizedHash(value) { return String(value || '').replace(/^"|"$/g, '').replace(/^sha256:/, ''); }
function safeServerFilename(disposition, fallback) {
  const match = typeof disposition === 'string' && disposition.match(/filename="([^"]+)"/i);
  const filename = match?.[1] || fallback || '';
  if (!filename || filename !== filename.split(/[\\/]/).pop() || /[\u0000-\u001f\u007f]/.test(filename)) throw new Error('服务端文件名不安全');
  return filename;
}

async function downloadArtifact(store, reportError, state, artifactPath, run) {
  try {
    const response = await store.client.download(artifactPath);
    const filename = safeServerFilename(response.disposition, run.filename);
    const hashIdentity = response.etag || '';
    if (!hashIdentity) throw new Error('下载响应没有 artifact hash identity');
    if (!response.blob || typeof response.blob.arrayBuffer !== 'function' || !globalThis.crypto?.subtle) throw new Error('下载响应无法完成 artifact 字节校验');
    const bytes = new Uint8Array(await response.blob.arrayBuffer());
    const digest = new Uint8Array(await crypto.subtle.digest('SHA-256', bytes));
    const actualHash = [...digest].map(value => value.toString(16).padStart(2, '0')).join('');
    if (normalizedHash(hashIdentity) !== actualHash) throw new Error('下载 artifact 字节 hash 与 ETag 不一致');
    const expected = normalizedHash(run.sha256 || run.artifact_sha256 || '');
    if (expected && actualHash !== expected) throw new Error('下载 artifact hash 与服务端 manifest 不一致');
    state.lastDownload = {filename, hash: hashIdentity};
    if (globalThis.URL?.createObjectURL && response.blob) {
      const link = el('a', {href: URL.createObjectURL(response.blob), download: filename});
      link.click();
      globalThis.setTimeout?.(() => URL.revokeObjectURL?.(link.getAttribute('href')), 0);
    }
  } catch (downloadError) { error(reportError, downloadError); }
}

function narrativePanel(store, reportError, narrativeEntry) {
  const panel = el('section', {className: 'panel', 'data-authority': 'model-suggestion'},
    el('h3', {}, '叙事建议（只读）'),
    el('p', {className: 'muted'}, '模型生成的叙事草稿只能查看，不能从此面板接受、编辑或发布。'),
  );
  if (narrativeEntry) {
    const data = narrativeEntry.resource.data || {};
    panel.append(el('p', {}, `${data.suggestion_id || '未提供'} · 资源版本 ${narrativeEntry.resource.etag || '服务端未返回'}`), details('叙事草稿与证据 claims', data.draft || data));
  } else panel.append(el('p', {className: 'muted'}, '暂无已载入叙事建议。'));
  return panel;
}

export function renderExportsView({store, confirm: confirmCallback, reportError}) {
  const state = stateFor(store);
  const snapshotEntry = snapshotResource(store);
  const runEntry = runResource(store, state);
  const narrativeEntry = narrativeResource(store);
  return el('section', {},
    el('h2', {}, '导出与叙事交付'),
    el('p', {className: 'banner'}, '预览是草稿，已发布导出需要人工确认；运行、叙事建议与 artifact 下载均保持服务端状态边界。'),
    exportForm(store, reportError, state, snapshotEntry, confirmCallback),
    runPanel(store, reportError, state, runEntry),
    narrativePanel(store, reportError, narrativeEntry),
  );
}
