import test from 'node:test';
import assert from 'node:assert/strict';
import {WorkbenchStore} from '../../frontend_app/current_console/fmea/store.js';

const selection = {analysisId: 'a-1', rowId: 'r-1', revisionId: 'v-1'};
const context = version => ({data: {row: {row_id: 'r-1', analysis_id: 'a-1', record_version: version}, evidence: {refs: []}}, etag: `"${version}"`});
test('changing selected resource rejects a late response from the previous row', async () => {
  let finish;
  const client = {setToken() {}, cancel() {}, get: () => new Promise(resolve => { finish = resolve; })};
  const store = new WorkbenchStore(client);
  store.configure(selection, 'token');
  const pending = store.loadContext();
  store.configure({...selection, rowId: 'r-2'}, 'token');
  finish(context(1));
  await pending;
  assert.equal(store.state.context, null);
});
test('version conflict reloads context without reissuing a mutation', async () => {
  let writes = 0;
  const client = {setToken() {}, cancel() {}, get: async () => context(2), execute: async () => {
    writes++;
    throw Object.assign(new Error('conflict'), {status: 409, code: 'FMEA_VERSION_CONFLICT'});
  }};
  const store = new WorkbenchStore(client);
  store.configure(selection, 'token');
  await store.submit({path: '/api/v1/fmea/rows/r-1/review-decisions'}, store.contextPath());
  assert.equal(writes, 1);
  assert.equal(store.state.context.row.record_version, 2);
  assert.match(store.state.error, /版本|冲突/);
});
test('context from a different analysis is never displayed as the current resource', async () => {
  const bad = context(1); bad.data.row.analysis_id = 'different';
  const store = new WorkbenchStore({setToken() {}, cancel() {}, get: async () => bad});
  store.configure(selection, 'token');
  await store.loadContext();
  assert.equal(store.state.context, null);
  assert.match(store.state.error, /不匹配/);
});

test('successful command refreshes the exact resource identified by its receipt', async () => {
  const reads = [];
  const store = new WorkbenchStore({setToken() {}, cancel() {},
    execute: async () => ({data: {publication_id: 'pub-2'}}),
    get: async path => { reads.push(path); return {data: {publication_id: 'pub-2', status: 'published'}, etag: '"1"'}; },
  });
  store.configure(selection, 'token');
  const publicationPath = '/api/v1/fmea/publications/pub-2';
  await store.submit({path: '/api/v1/fmea/revisions/v-1/publications'}, {
    onSuccess: data => `/api/v1/fmea/publications/${data.publication_id}`,
    onConflict: '/api/v1/fmea/revisions/v-1',
  });
  assert.deepEqual(reads, [publicationPath]);
  assert.equal(store.resource(publicationPath).data.status, 'published');
});

test('a conflict refresh uses the preexisting resource and never fabricates a receipt', async () => {
  const reads = [];
  const store = new WorkbenchStore({setToken() {}, cancel() {},
    execute: async () => { throw Object.assign(new Error('stale'), {status: 412}); },
    get: async path => { reads.push(path); return context(2); },
  });
  store.configure(selection, 'token');
  await store.submit({path: '/api/v1/fmea/revisions/v-1/publications'}, {
    onSuccess: () => { throw new Error('must not evaluate missing success receipt'); },
    onConflict: store.contextPath(),
  });
  assert.deepEqual(reads, [store.contextPath()]);
  assert.equal(store.state.context.row.record_version, 2);
});

test('retryable HTTP failures retain the exact write operation and block silent reset', async () => {
  const op = Object.freeze({path: '/api/v1/fmea/rows/r-1/review-decisions', key: 'same-key'});
  const writes = [];
  const store = new WorkbenchStore({setToken() {}, cancel() {}, execute: async operation => {
    writes.push(operation);
    if (writes.length === 1) throw Object.assign(new Error('temporarily unavailable'), {status: 503, retryable: true});
    return {data: {persisted: true}};
  }});
  store.configure(selection, 'token');
  await store.submit(op);
  assert.equal(store.state.pending?.operation, op);
  assert.throws(() => store.configure({...selection, rowId: 'r-2'}, 'other-token'), /写入|未决/);
  await store.submit(store.state.pending.operation);
  assert.deepEqual(writes, [op, op]);
  assert.equal(store.state.pending, null);
});

test('a connection switch cannot discard an in-flight write', async () => {
  let finish;
  let resets = 0;
  const store = new WorkbenchStore({setToken() { resets++; }, cancel() {}, execute: () => new Promise(resolve => { finish = resolve; })});
  store.configure(selection, 'token');
  const pending = store.submit({path: '/api/v1/fmea/rows/r-1/review-decisions'});
  let switchError;
  try { store.configure({...selection, rowId: 'r-2'}, 'other-token'); } catch (error) { switchError = error; }
  finish({data: {persisted: true}});
  await pending;
  assert.match(switchError?.message || '', /写入|未决/);
  assert.equal(resets, 1);
  assert.equal(store.state.selection.rowId, 'r-1');
  assert.equal(store.state.writing, false);
});

test('a failed read after a successful write offers only a read retry', async () => {
  let writes = 0;
  let reads = 0;
  const receipt = {data: {persisted: true}};
  const store = new WorkbenchStore({setToken() {}, cancel() {}, execute: async () => { writes++; return receipt; },
    get: async () => { if (++reads === 1) throw new Error('read network failure'); return context(2); },
  });
  store.configure(selection, 'token');
  const result = await store.submit({path: '/api/v1/fmea/rows/r-1/review-decisions'}, store.contextPath());
  assert.equal(result, receipt);
  assert.equal(store.state.pending, null);
  assert.equal(store.state.refreshPending, store.contextPath());
  assert.match(store.state.error, /成功回执/);
  await store.retryRefresh();
  assert.equal(writes, 1);
  assert.equal(reads, 2);
  assert.equal(store.state.refreshPending, null);
  assert.equal(store.state.context.row.record_version, 2);
});
