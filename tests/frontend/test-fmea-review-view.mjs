import test from 'node:test';
import assert from 'node:assert/strict';
import {renderReviewView} from '../../frontend_app/current_console/fmea/views/review.js';

class Element {
  constructor(tag = '', text = '') { this.tag = tag; this.text = text; this.children = []; this.attributes = {}; this.listeners = {}; }
  append(child) { this.children.push(child); }
  setAttribute(name, value) { this.attributes[name] = value; }
  addEventListener(name, fn) { this.listeners[name] = fn; }
  get textContent() { return this.text + this.children.map(child => child.textContent).join(''); }
}

test('review suggestion entry creates no new operation while a write is unresolved', async () => {
  const previousNode = globalThis.Node;
  const previousDocument = globalThis.document;
  globalThis.Node = Element;
  globalThis.document = {createElement: tag => new Element(tag), createTextNode: text => new Element('', text)};
  try {
    let created = 0;
    let submitted = 0;
    const errors = [];
    const store = {
      hasUnresolvedWrite: true,
      state: {busy: false, selection: {rowId: 'row-1'}, context: {row: {record_version: 1}, field_reviews: [], decision_history: [], reviewability: true}},
      contextPath: () => '/api/v1/fmea/rows/row-1/review-context',
      resource: () => ({etag: '"1"'}),
      client: {operation: () => { created++; return {}; }},
      submit: async () => { submitted++; },
    };
    const panel = renderReviewView({store, confirm: () => {}, reportError: error => errors.push(error.message)});
    const flatten = node => [node, ...node.children.flatMap(flatten)];
    const entry = flatten(panel).find(node => node.tag === 'button' && node.textContent === '请求模型建议');
    assert.ok(entry);
    // Invoke the callback directly as well as inspecting its disabled state.
    await entry.listeners.click();
    assert.equal(created, 0);
    assert.equal(submitted, 0);
    assert.ok(Object.hasOwn(entry.attributes, 'disabled'));
    assert.match(errors[0], /未决|进行中/);
  } finally {
    globalThis.Node = previousNode;
    globalThis.document = previousDocument;
  }
});
