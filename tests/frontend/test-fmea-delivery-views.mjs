import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';

class FakeNode {
  constructor(tagName = '#node', text = '') {
    this.tagName = tagName.toUpperCase();
    this.children = [];
    this.parentNode = null;
    this.attributes = new Map();
    this.listeners = new Map();
    this.textContent = text;
    this.value = '';
    this.checked = false;
    this.disabled = false;
    this.hidden = false;
    this.files = [];
  }

  append(...children) {
    this._text = null;
    for (const child of children.flat(Infinity)) {
      if (child == null) continue;
      const node = child instanceof FakeNode ? child : new FakeNode('#text', String(child));
      node.parentNode = this;
      this.children.push(node);
    }
  }

  appendChild(child) { this.append(child); return child; }
  replaceChildren(...children) { this.children = []; this._text = null; this.append(...children); }

  setAttribute(name, value) {
    this.attributes.set(name, String(value));
    if (name === 'class') this.className = String(value);
    if (name === 'value') this.value = String(value);
    if (name === 'disabled') this.disabled = true;
  }

  getAttribute(name) { return this.attributes.get(name) ?? null; }
  removeAttribute(name) { this.attributes.delete(name); }

  addEventListener(type, listener) {
    const listeners = this.listeners.get(type) || [];
    listeners.push(listener);
    this.listeners.set(type, listeners);
  }

  dispatchEvent(event) {
    event.target ||= this;
    event.currentTarget = this;
    for (const listener of this.listeners.get(event.type) || []) listener(event);
    return true;
  }

  click() { if (!this.disabled) this.dispatchEvent({type: 'click'}); }

  querySelectorAll(selector) {
    const matches = [];
    const visit = node => {
      for (const child of node.children) {
        if (matchesSelector(child, selector)) matches.push(child);
        visit(child);
      }
    };
    visit(this);
    return matches;
  }

  querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }

  get textContent() {
    return this._text ?? this.children.map(child => child.textContent).join('');
  }

  set textContent(value) { this._text = String(value ?? ''); }
}

function matchesSelector(node, selector) {
  const tag = selector.match(/^[a-z]+/i)?.[0];
  if (tag && node.tagName !== tag.toUpperCase()) return false;
  const attr = selector.match(/\[([^=\]]+)(?:=["']?([^\]"']+)["']?)?\]/);
  if (attr) {
    if (!node.attributes.has(attr[1])) return false;
    if (attr[2] && node.attributes.get(attr[1]) !== attr[2]) return false;
  }
  return !tag || node.tagName === tag.toUpperCase();
}

globalThis.Node = FakeNode;
globalThis.document = {
  createElement: tag => new FakeNode(tag),
  createTextNode: text => new FakeNode('#text', text),
};
globalThis.FormData = class {
  constructor(form) {
    this.values = new Map();
    for (const control of form.querySelectorAll('[name]')) this.values.set(control.getAttribute('name'), control.value);
  }
  get(name) { return this.values.get(name) ?? null; }
};

const {renderTemplatesView} = await import('../../frontend_app/current_console/fmea/views/templates.js');
const {renderExportsView} = await import('../../frontend_app/current_console/fmea/views/exports.js');
const {WorkbenchStore} = await import('../../frontend_app/current_console/fmea/store.js');

const HASH = `sha256:${'a'.repeat(64)}`;
const ARTIFACT_HASH = createHash('sha256').update('artifact').digest('hex');

function fixtureStore(extraResources = {}) {
  const selection = {analysisId: 'analysis-existing', rowId: 'row-existing', revisionId: 'revision-existing'};
  const revisionPath = `/api/v1/fmea/revisions/${selection.revisionId}`;
  const resources = {
    [revisionPath]: {data: {
      revision_id: selection.revisionId,
      analysis_id: selection.analysisId,
      revision_hash: HASH,
      record_version: 7,
    }, etag: '"7"'},
    [`/api/v1/fmea/template-drafts/draft-existing`]: {data: {
      draft_id: 'draft-existing', source_filename: 'handoff.xlsx', source_sha256: HASH, source_type: 'xlsx', status: 'draft',
    }, etag: '"3"'},
    [`/api/v1/fmea/publications/publication-existing/snapshot`]: {data: {
      snapshot_id: 'snapshot-existing', snapshot_hash: HASH, publication_id: 'publication-existing',
    }},
    ...extraResources,
  };
  const calls = {operations: [], submissions: [], reads: [], downloads: []};
  const client = {
    operation(path, body, etag) {
      const operation = {path, body: JSON.stringify(body), etag, key: `key-${calls.operations.length + 1}`};
      calls.operations.push(operation);
      return operation;
    },
    templateImportOperation(file) {
      const operation = {path: '/api/v1/fmea/template-drafts', file, key: `import-key-${calls.operations.length + 1}`};
      calls.operations.push(operation);
      return operation;
    },
    async download(path) { calls.downloads.push(path); return {blob: new Blob(['artifact']), disposition: 'attachment; filename="verified.xlsx"', etag: `"${ARTIFACT_HASH}"`}; },
  };
  const store = {
    client,
    state: {selection, resources, busy: false, error: '', notice: ''},
    resource(path) { return this.state.resources[path]; },
    async read(path, options) { calls.reads.push({path, options}); return this.state.resources[path]; },
    async submit(operation, refreshPath) {
      calls.submissions.push({operation, refreshPath});
      let response = this.state.resources[operation.path];
      if (operation.path === '/api/v1/fmea/template-drafts') {
        response = {data: {draft_id: 'draft-imported', source_filename: 'imported.docx', source_sha256: HASH, source_type: 'docx', status: 'draft'}, etag: '"3"'};
      } else if (operation.path.endsWith('/patch-runs')) {
        response = {data: {suggestion_id: 'suggestion-imported', status: 'suggested', candidate: {patch_id: 'patch-imported', draft_id: 'draft-imported', target_template_version: '2', target_template_hash: HASH, domain_pack_hash: HASH, evidence_pack_hash: HASH}}, etag: '"2"'};
      } else if (operation.path.endsWith('/migration-dry-runs')) {
        response = {data: {report_id: 'migration-report-imported', migration_id: 'migration-existing', report_hash: HASH, source_revision_id: 'revision-existing', source_revision_hash: HASH, target_domain_pack_id: 'domain-existing', target_domain_pack_version: '2', target_domain_pack_hash: HASH, status: 'dry_run'}, etag: '"4"'};
      }
      if (response) this.state.resources[operation.path] = response;
      if (refreshPath && !this.state.resources[refreshPath]) this.state.resources[refreshPath] = {data: {}};
      return response || {data: {}};
    },
    contextPath() { return `/api/v1/fmea/rows/${selection.rowId}/review-context`; },
  };
  return {store, calls};
}

function submit(form) { form.dispatchEvent({type: 'submit', preventDefault() {}}); }

// Keep mutation caching and refresh behavior real; stub only server transport.
function realStoreFixture(extraResources = {}) {
  const fixture = fixtureStore(extraResources);
  const store = new WorkbenchStore(fixture.store.client);
  store.state.selection = fixture.store.state.selection;
  store.state.resources = fixture.store.state.resources;
  return {...fixture, store};
}

const tick = () => new Promise(resolve => setImmediate(resolve));

test('importing draft B after patch A cannot display or act on A and allows an exact draft B patch GET', async () => {
  const oldPath = '/api/v1/fmea/template-patches/patch-a';
  const currentPath = '/api/v1/fmea/template-patches/patch-b';
  const candidate = {patch_id: 'patch-a', draft_id: 'draft-existing', target_template_version: '2', target_template_hash: HASH, domain_pack_hash: HASH, evidence_pack_hash: HASH};
  const oldSuggestion = {suggestion_id: 'suggestion-a', status: 'suggested', candidate};
  const currentSuggestion = {suggestion_id: 'suggestion-b', status: 'suggested', candidate: {...candidate, patch_id: 'patch-b', draft_id: 'draft-b'}};
  const {store, calls} = realStoreFixture({
    '/api/v1/fmea/template-drafts/draft-existing/patch-runs': {data: oldSuggestion, etag: '"1"'},
    [oldPath]: {data: oldSuggestion, etag: '"1"'},
  });
  store.client.execute = async operation => {
    assert.equal(operation.path, '/api/v1/fmea/template-drafts');
    return {data: {draft_id: 'draft-b', source_filename: 'new.docx', source_sha256: HASH, source_type: 'docx', status: 'draft'}, etag: '"1"'};
  };
  store.client.get = async path => {
    assert.equal(path, currentPath);
    return {data: currentSuggestion, etag: '"1"'};
  };
  const confirmations = [];
  const options = {store, reportError: error => { throw error; }, confirm: (...args) => confirmations.push(args)};
  const initial = renderTemplatesView(options);
  assert.ok(initial.querySelector(`[data-resource="${oldPath}"]`));
  const upload = initial.querySelector('form[data-operation="template-draft-import"]');
  upload.querySelector('input[type="file"]').files = [{name: 'new.docx', size: 128}];
  submit(upload);
  await tick();
  assert.equal(store.resource('/api/v1/fmea/template-drafts').data.draft_id, 'draft-b');
  const afterImport = renderTemplatesView(options);
  assert.equal(Boolean(afterImport.querySelector(`[data-resource="${oldPath}"]`)), false);
  assert.doesNotMatch(afterImport.textContent, /patch-a|suggestion-a/);
  assert.equal(afterImport.querySelector('form[data-operation="template-patch-accept"]'), null);
  assert.equal(afterImport.querySelector('form[data-operation="template-patch-reject"]'), null);
  assert.equal(confirmations.length, 0);
  assert.equal(calls.operations.length, 1);

  // An explicitly read canonical patch for the current draft remains usable.
  await store.read(currentPath);
  const current = renderTemplatesView(options);
  const reject = current.querySelector('form[data-operation="template-patch-reject"]');
  assert.equal(reject.querySelector('[name="patch_id"]').value, 'patch-b');
  reject.querySelector('[name="reason"]').value = 'Reviewed draft B';
  submit(reject);
  assert.equal(confirmations[0][1], `${currentPath}/rejection`);
  assert.equal(confirmations[0][2].patch_id, 'patch-b');
});

for (const action of ['accepted', 'rejected']) {
  test(`canonical patch GET displays ${action} decision after real-store mutation and permits a new patch`, async () => {
    const patchPath = '/api/v1/fmea/template-patches/patch-current';
    const runPath = '/api/v1/fmea/template-drafts/draft-existing/patch-runs';
    const candidate = {patch_id: 'patch-current', draft_id: 'draft-existing', target_template_version: '2', target_template_hash: HASH, domain_pack_hash: HASH, evidence_pack_hash: HASH};
    const suggestion = {suggestion_id: 'suggestion-current', status: 'suggested', candidate};
    const decision = {decision_id: 'decision-current', suggestion_id: 'suggestion-current', patch_id: 'patch-current', workspace_id: 'workspace-existing', actor_id: 'reviewer-existing', actor_type: 'human', action, reason: 'Reviewed evidence', base_template_id: 'template-existing', base_template_version: '2', base_template_hash: HASH, candidate, new_template_version: action === 'accepted' ? '3' : null, created_at: '2026-09-04T00:00:00Z'};
    const {store, calls} = realStoreFixture({[runPath]: {data: suggestion, etag: '"1"'}, '/api/v1/fmea/template-patches/aaa-unrelated': {data: {...decision, patch_id: 'aaa-unrelated'}, etag: '"9"'}});
    let decided = false;
    store.client.get = async path => {
      calls.reads.push(path);
      assert.equal(path, patchPath);
      return {data: decided ? decision : suggestion, etag: decided ? '"2"' : '"1"'};
    };
    store.client.execute = async operation => {
      assert.equal(operation.path, `${patchPath}/${action === 'accepted' ? 'acceptance' : 'rejection'}`);
      assert.equal(operation.etag, '"1"');
      assert.equal(JSON.parse(operation.body).patch_id, 'patch-current');
      decided = true;
      return {data: action === 'accepted' ? {template_id: 'template-existing', version: '3', template_hash: HASH, schema_dialect: 'fmea'} : decision, etag: '"2"'};
    };
    const options = {store, reportError: error => { throw error; }, confirm: (_title, path, body, etag, refresh) => store.submit(store.client.operation(path, body, etag), refresh)};
    await store.read(patchPath);
    const root = renderTemplatesView(options);
    const form = root.querySelector(`form[data-operation="template-patch-${action === 'accepted' ? 'accept' : 'reject'}"]`);
    form.querySelector(action === 'accepted' ? '[name="new_template_version"]' : '[name="reason"]').value = action === 'accepted' ? '3' : 'Reviewed evidence';
    submit(form);
    await tick();
    assert.equal(store.state.error, '');
    assert.equal(store.resource(patchPath).etag, '"2"');
    const after = renderTemplatesView(options);
    const panel = after.querySelector(`[data-resource="${patchPath}"]`);
    assert.equal(panel.getAttribute('data-authority'), 'human-confirmed');
    assert.ok(panel.querySelector(`[data-state="${action}"]`));
    assert.match(panel.textContent, /decision-current/);
    assert.match(panel.textContent, /资源版本 "2"/);
    assert.equal(after.querySelector('form[data-operation="template-patch-accept"]'), null);
    assert.equal(after.querySelector('form[data-operation="template-patch-reject"]'), null);

    store.state.resources[runPath] = {data: {...suggestion, suggestion_id: 'suggestion-new', candidate: {...candidate, patch_id: 'patch-new'}}, etag: '"1"'};
    const next = renderTemplatesView(options);
    assert.equal(next.querySelector('form[data-operation="template-patch-accept"]').querySelector('[name="patch_id"]').value, 'patch-new');
  });
}

for (const conflict of [false, true]) {
  test(`migration confirmation real-store refresh uses ${conflict ? 'known source on conflict' : 'receipt child on success'}`, async () => {
    const {store, calls} = realStoreFixture();
    const sourcePath = '/api/v1/fmea/revisions/revision-existing';
    const childPath = '/api/v1/fmea/revisions/child-from-receipt';
    const reportPath = '/api/v1/fmea/migration-reports/report-from-server/confirmations';
    const receipt = {migration_id: 'migration-existing', child_revision_id: 'child-from-receipt', report_hash: HASH, replayed: false};
    store.client.execute = async operation => {
      if (operation.path.endsWith('/migration-dry-runs')) return {data: {report_id: 'report-from-server', migration_id: 'migration-existing', report_hash: HASH}, etag: '"1"'};
      assert.equal(operation.path, reportPath);
      if (conflict) throw Object.assign(new Error('version conflict'), {status: 412});
      return {data: receipt, etag: null};
    };
    store.client.get = async path => {
      calls.reads.push(path);
      if (path === sourcePath) return store.resource(sourcePath);
      if (path === childPath) return {data: {revision_id: 'child-from-receipt'}, etag: '"1"'};
      throw Object.assign(new Error('unsupported GET'), {status: 404});
    };
    const options = {store, reportError: error => { throw error; }, confirm: (_title, path, body, etag, refresh) => store.submit(store.client.operation(path, body, etag), refresh)};
    const dryRun = renderTemplatesView(options).querySelector('form[data-operation="migration-dry-run"]');
    const dryRunBody = {migration_id: 'migration-existing', source_revision_hash: HASH, target_domain_pack_id: 'domain-existing', target_domain_pack_version: '2', target_domain_pack_hash: HASH};
    dryRun.querySelector('[name="migration_dry_run_json"]').value = JSON.stringify(dryRunBody);
    submit(dryRun);
    await tick();
    submit(renderTemplatesView(options).querySelector('form[data-operation="migration-confirm"]'));
    await tick();
    assert.deepEqual(calls.reads, [conflict ? sourcePath : childPath]);
    const body = JSON.parse(calls.operations[1].body);
    assert.deepEqual(body.dry_run, dryRunBody);
    assert.equal(body.dry_run_idempotency_key, calls.operations[0].key);
    assert.equal(body.dry_run_source_version, 7);
    assert.notEqual(calls.operations[1].key, calls.operations[0].key);
    const after = renderTemplatesView(options);
    if (conflict) {
      assert.match(store.state.error, /冲突/);
      assert.ok(after.querySelector('form[data-operation="migration-confirm"]'));
    } else {
      assert.equal(store.state.error, '');
      assert.deepEqual(store.resource(reportPath).data, receipt);
      assert.match(after.textContent, /child-from-receipt/);
      assert.ok(after.querySelector('[data-state="confirmed"]'));
      assert.equal(after.querySelector('form[data-operation="migration-confirm"]'), null);
    }
  });
}

for (const [name, disposition, etag, expected] of [
  ['bad hash', 'attachment; filename="verified.xlsx"', `"${'0'.repeat(64)}"`, /hash/],
  ['path filename', 'attachment; filename="../escape.xlsx"', `"${ARTIFACT_HASH}"`, /文件名/],
  ['control filename', 'attachment; filename="bad\u0000.xlsx"', `"${ARTIFACT_HASH}"`, /文件名/],
]) {
  test(`artifact ${name} prevents browser download`, async t => {
    const {store} = fixtureStore({'/api/v1/fmea/export-runs/export-existing': {data: {export_run_id: 'export-existing', revision_id: 'revision-existing', status: 'succeeded', artifact_id: 'artifact-existing', format: 'xlsx', draft_preview: true}}});
    store.client.download = async () => ({blob: new Blob(['artifact']), disposition, etag});
    const createURL = t.mock.method(URL, 'createObjectURL');
    let failed;
    const failure = new Promise(resolve => { failed = resolve; });
    const options = {store, confirm() {}, reportError: failed};
    renderExportsView(options).querySelector('button[data-operation="download-artifact"]').click();
    assert.match((await failure).message, expected);
    assert.equal(createURL.mock.callCount(), 0);
    assert.doesNotMatch(renderExportsView(options).textContent, /已下载并保留/);
  });
}

test('templates view constrains in-memory XLSX/DOCX draft input without exposing a local path', () => {
  const {store} = fixtureStore();
  const root = renderTemplatesView({store, confirm() {}, reportError: error => { throw error; }});
  const file = root.querySelector('input[type="file"]');
  assert.ok(file);
  assert.match(file.getAttribute('accept'), /xlsx/);
  assert.match(file.getAttribute('accept'), /docx/);
  assert.equal(file.getAttribute('webkitdirectory'), null);
  assert.equal(file.value, '');
  assert.match(root.textContent, /256 KiB/);
  assert.doesNotMatch(root.textContent, /[A-Za-z]:\\|\\\\/);
});

test('templates view follows actual POST cache from import to patch suggestion and GET patch status', async () => {
  const {store, calls} = fixtureStore();
  const root = renderTemplatesView({store, confirm() {}, reportError: error => { throw error; }});
  const upload = root.querySelector('form[data-operation="template-draft-import"]');
  const rawFile = {name: 'new-template.docx', size: 128};
  upload.querySelector('input[type="file"]').files = [rawFile];
  submit(upload);
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(calls.submissions[0].operation.path, '/api/v1/fmea/template-drafts');
  assert.equal(calls.submissions[0].operation.file, rawFile);
  assert.equal(Object.hasOwn(calls.submissions[0].operation, 'body'), false);
  assert.equal(Object.hasOwn(calls.submissions[0].operation, 'etag'), false);
  assert.equal(store.resource('/api/v1/fmea/template-drafts').data.draft_id, 'draft-imported');

  const afterImport = renderTemplatesView({store, confirm() {}, reportError: error => { throw error; }});
  const suggest = afterImport.querySelector('form[data-operation="template-patch-suggest"]');
  suggest.querySelector('[name="template_patch_run_json"]').value = JSON.stringify({
    input_template_version: '1', target_template_id: 'target-existing', target_template_version: '2', target_template_hash: HASH,
    domain_pack_id: 'domain-existing', domain_pack_version: '1', domain_pack_hash: HASH, evidence_pack_id: 'evidence-existing', evidence_pack_hash: HASH,
  });
  submit(suggest);
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(calls.submissions[1].operation.path, '/api/v1/fmea/template-drafts/draft-imported/patch-runs');
  assert.equal(store.resource(calls.submissions[1].operation.path).data.candidate.patch_id, 'patch-imported');

  const afterSuggest = renderTemplatesView({store, confirm() {}, reportError: error => { throw error; }});
  const status = afterSuggest.querySelectorAll('button').find(node => node.textContent === '刷新补丁状态');
  assert.ok(status);
  status.click();
  assert.equal(calls.reads.at(-1).path, '/api/v1/fmea/template-patches/patch-imported');
});

test('templates view submits the actual migration dry-run DTO and preserves its original key/version for confirmation', async () => {
  const {store, calls} = fixtureStore();
  const confirmations = [];
  const root = renderTemplatesView({store, confirm: (...args) => confirmations.push(args), reportError: error => { throw error; }});
  const form = root.querySelector('form[data-operation="migration-dry-run"]');
  assert.ok(form);
  const body = {migration_id: 'migration-existing', source_revision_hash: HASH, target_domain_pack_id: 'domain-existing', target_domain_pack_version: '2', target_domain_pack_hash: HASH};
  form.querySelector('[name="migration_dry_run_json"]').value = JSON.stringify(body);
  submit(form);
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(calls.operations.length, 1);
  assert.deepEqual(JSON.parse(calls.operations[0].body), body);
  assert.equal(calls.operations[0].path, '/api/v1/fmea/revisions/revision-existing/migration-dry-runs');
  assert.equal(calls.operations[0].etag, '"7"');
  const dryRunPath = '/api/v1/fmea/revisions/revision-existing/migration-dry-runs';
  assert.equal(store.resource(dryRunPath).data.report_id, 'migration-report-imported');

  const refreshed = renderTemplatesView({store, confirm: (...args) => confirmations.push(args), reportError: error => { throw error; }});
  const confirmation = refreshed.querySelector('button[data-operation="migration-confirm"]');
  assert.ok(confirmation);
  submit(confirmation.parentNode);
  assert.equal(confirmations.length, 1);
  assert.equal(confirmations[0][1], '/api/v1/fmea/migration-reports/migration-report-imported/confirmations');
  const confirmationBody = confirmations[0][2];
  assert.equal(confirmationBody.dry_run_idempotency_key, calls.operations[0].key);
  assert.equal(confirmationBody.dry_run_source_version, 7);
  assert.equal(confirmations[0][3], '"4"');
});

test('exports view validates preview and published bodies against ExportRunRequest and binds If-Match to the revision resource', async () => {
  const {store, calls} = fixtureStore();
  const confirmations = [];
  const root = renderExportsView({store, confirm: (...args) => confirmations.push(args), reportError: error => { throw error; }});
  const form = root.querySelector('form[data-operation="export-run"]');
  assert.ok(form);
  form.querySelector('[name="format"]').value = 'xlsx';
  form.querySelector('[name="publication_mode"]').value = 'preview';
  submit(form);
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(calls.operations.length, 1);
  assert.deepEqual(JSON.parse(calls.operations[0].body), {
    snapshot_id: 'snapshot-existing', snapshot_hash: HASH, format: 'xlsx', publication_id: null, draft_preview: true, confirm_publication: false,
  });
  assert.equal(calls.operations[0].etag, '"7"');

  form.querySelector('[name="publication_mode"]').value = 'published';
  submit(form);
  assert.equal(confirmations.length, 1);
  const publishedBody = confirmations[0][2];
  assert.equal(publishedBody.publication_id, 'publication-existing');
  assert.equal(publishedBody.draft_preview, false);
  assert.equal(publishedBody.confirm_publication, true);
  assert.equal(Object.hasOwn(publishedBody, 'record_version'), false);
  assert.equal(confirmations[0][3], '"7"');
  assert.equal(calls.operations.length, 1);

  store.state.resources['/api/v1/fmea/revisions/revision-existing/export-runs'] = {data: {export_run_id: 'run-created', revision_id: 'revision-existing', status: 'queued', format: 'xlsx', draft_preview: true}};
  const withCreatedRun = renderExportsView({store, confirm() {}, reportError: error => { throw error; }});
  withCreatedRun.querySelectorAll('button').find(node => node.textContent === '刷新运行状态').click();
  assert.equal(calls.reads.at(-1).path, '/api/v1/fmea/export-runs/run-created');
});

test('exports view renders narrative suggestions read-only and downloads only the server artifact identity', async () => {
  const narrativePath = '/api/v1/fmea/revisions/revision-existing/export-narrative-runs';
  const runPath = '/api/v1/fmea/export-runs/export-existing';
  const artifactPath = '/api/v1/fmea/export-artifacts/artifact-existing';
  const {store, calls} = fixtureStore({
    [narrativePath]: {data: {suggestion_id: 'narrative-existing', draft: {title: 'Evidence narrative', sections: [], claims: []}}},
    [runPath]: {data: {export_run_id: 'export-existing', revision_id: 'revision-existing', status: 'succeeded', artifact_id: 'artifact-existing', format: 'xlsx', draft_preview: true}},
  });
  const root = renderExportsView({store, confirm() {}, reportError: error => { throw error; }});
  assert.match(root.textContent, /read-only|只读|叙事|建议/i);
  assert.equal(root.querySelector('button[data-operation="accept-narrative"]'), null);
  const download = root.querySelector('button[data-operation="download-artifact"]');
  assert.ok(download);
  download.click();
  await new Promise(resolve => setImmediate(resolve));
  assert.deepEqual(calls.downloads, [artifactPath]);
  assert.equal(calls.reads.length, 0);
});

test('view-local workflow state resets when the store receives a new selection object', async () => {
  const reportPath = '/api/v1/fmea/migration-reports/migration-existing';
  const {store} = fixtureStore({[reportPath]: {data: {migration_id: 'migration-existing', report_hash: HASH}, etag: '"4"'}});
  const root = renderTemplatesView({store, confirm() {}, reportError: error => { throw error; }});
  const form = root.querySelector('form[data-operation="migration-dry-run"]');
  form.querySelector('[name="migration_dry_run_json"]').value = JSON.stringify({migration_id: 'migration-existing', source_revision_hash: HASH, target_domain_pack_id: 'domain-existing', target_domain_pack_version: '2', target_domain_pack_hash: HASH});
  submit(form);
  await new Promise(resolve => setImmediate(resolve));
  store.state.selection = {...store.state.selection, revisionId: 'revision-new'};
  const changed = renderTemplatesView({store, confirm() {}, reportError: error => { throw error; }});
  assert.equal(changed.querySelector('button[data-operation="migration-confirm"]'), null);
});
