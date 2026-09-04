import test from 'node:test';
import assert from 'node:assert/strict';
import {FmeaClient} from '../../frontend_app/current_console/fmea/api-client.js';

test('browser fetch receives the global receiver rather than the client object', async () => {
  const client = new FmeaClient({origin: 'http://localhost:8000', fetchImpl: async function () {
    assert.equal(this, globalThis);
    return new Response(JSON.stringify({data: {}}));
  }});
  await client.get('/api/v1/fmea/rows/x/review-context');
});

test('API captures real ETags and retains the same key for an explicit retry', async () => {
  const calls = [];
  const client = new FmeaClient({origin: 'http://localhost:8000', fetchImpl: async (url, options) => {
    calls.push({url, options});
    return new Response(JSON.stringify({data: {record_version: 3}}), {headers: {ETag: '"3"'}});
  }});
  client.setToken('local-test-token');
  await client.get('/api/v1/fmea/rows/row-1/review-context');
  const op = client.operation('/api/v1/fmea/rows/row-1/review-decisions', {action: 'defer'}, '"3"');
  await client.execute(op);
  await client.execute(op);
  assert.equal(client.etag('/api/v1/fmea/rows/row-1/review-context'), '"3"');
  assert.equal(calls[1].options.headers.get('If-Match'), '"3"');
  assert.equal(calls[1].options.headers.get('Idempotency-Key'), calls[2].options.headers.get('Idempotency-Key'));
  assert.equal(calls[1].options.headers.get('Authorization'), 'Bearer local-test-token');
});

test('tokens cannot be forwarded outside the same-origin FMEA API', async () => {
  let calls = 0;
  const client = new FmeaClient({origin: 'http://localhost:8000', fetchImpl: async () => { calls++; }});
  client.setToken('secret');
  await assert.rejects(client.get('https://example.invalid/api/v1/fmea/rows/x'), /接口路径/);
  await assert.rejects(client.get('/api/v1/fmea/../../../other'), /接口路径/);
  assert.equal(calls, 0);
  assert.equal(JSON.stringify(client).includes('secret'), false);
});

test('safe problem details preserve conflict identity and do not fabricate success', async () => {
  const client = new FmeaClient({origin: 'http://localhost:8000', fetchImpl: async () =>
    new Response(JSON.stringify({code: 'FMEA_VERSION_CONFLICT', detail: 'version changed', request_id: 'req-1'}), {status: 409})});
  await assert.rejects(client.get('/api/v1/fmea/rows/x/review-context'), error =>
    error.status === 409 && error.code === 'FMEA_VERSION_CONFLICT' && error.requestId === 'req-1');
});

test('pagination treats server cursor as opaque and respects the bounded page size', async () => {
  let seen;
  const client = new FmeaClient({origin: 'http://localhost:8000', fetchImpl: async url => {
    seen = new URL(url);
    return new Response(JSON.stringify({data: {items: [], next_cursor: null}}));
  }});
  await client.page('/api/v1/fmea/rows/x/review-suggestions', 'opaque/+?=', 50);
  assert.equal(seen.searchParams.get('cursor'), 'opaque/+?=');
  assert.equal(seen.searchParams.get('limit'), '50');
  await assert.rejects(client.page('/api/v1/fmea/rows/x/review-suggestions', null, 101));
});

test('cancellation aborts HTTP and propagates AbortError', async () => {
  const client = new FmeaClient({origin: 'http://localhost:8000', fetchImpl: async (_, options) =>
    new Promise((resolve, reject) => options.signal.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError'))))});
  const pending = client.get('/api/v1/fmea/rows/x/review-context');
  client.cancel();
  await assert.rejects(pending, {name: 'AbortError'});
});

test('template import sends bounded multipart bytes without a fabricated If-Match', async () => {
  const calls = [];
  const client = new FmeaClient({origin: 'http://localhost:8000', fetchImpl: async (_, options) => {
    calls.push(options);
    return new Response(JSON.stringify({data: {draft_id: 'draft-1'}}), {headers: {ETag: '"1"'}});
  }});
  const file = new File(['fixture-bytes'], 'template.xlsx');
  const op = client.templateImportOperation(file);
  await client.execute(op);
  await client.execute(op);
  assert.equal(await calls[0].body.get('file').text(), 'fixture-bytes');
  assert.equal(calls[0].headers.has('If-Match'), false);
  assert.equal(calls[0].headers.has('Content-Type'), false);
  assert.equal(calls[0].headers.get('Idempotency-Key'), calls[1].headers.get('Idempotency-Key'));
  assert.throws(() => client.templateImportOperation(new File(['x'], 'bad.txt')));
  assert.throws(() => client.templateImportOperation(new File([new Uint8Array(262145)], 'large.xlsx')));
});
