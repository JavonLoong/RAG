import test from 'node:test';
import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';

class MiniNode {
  constructor(tagName = '#text', text = '') {
    this.tagName = tagName.toUpperCase();
    this.nodeName = this.tagName;
    this.children = [];
    this.parentNode = null;
    this.attributes = new Map();
    this.listeners = new Map();
    this._text = text;
    this.value = '';
    this.checked = false;
    this.disabled = false;
  }

  setAttribute(name, value) {
    this.attributes.set(name, String(value));
    if (name === 'class') this.className = String(value);
    if (name === 'value') this.value = String(value);
    if (name === 'disabled') this.disabled = true;
  }

  getAttribute(name) { return this.attributes.get(name) ?? null; }

  append(...children) {
    for (const child of children.flat(Infinity)) {
      if (child == null) continue;
      this.children.push(child);
      if (typeof child === 'object') child.parentNode = this;
    }
  }

  addEventListener(type, listener) {
    const entries = this.listeners.get(type) || [];
    entries.push(listener);
    this.listeners.set(type, entries);
  }

  dispatchEvent(event) {
    const actual = typeof event === 'string' ? {type: event} : event;
    actual.currentTarget ??= this;
    actual.target ??= this;
    actual.preventDefault ??= () => { actual.defaultPrevented = true; };
    for (const listener of this.listeners.get(actual.type) || []) listener(actual);
    return !actual.defaultPrevented;
  }

  get textContent() {
    return this._text + this.children.map(child => child.textContent ?? '').join('');
  }

  set textContent(value) {
    this._text = String(value);
    this.children = [];
  }

  matches(selector) {
    const tag = selector.match(/^([a-z]+)/i)?.[1];
    if (tag && this.tagName.toLowerCase() !== tag.toLowerCase()) return false;
    const name = selector.match(/\[name="?([^\]"]+)"?\]/)?.[1];
    if (name && this.getAttribute('name') !== name) return false;
    const authority = selector.match(/\[data-authority="?([^\]"]+)"?\]/)?.[1];
    if (authority && this.getAttribute('data-authority') !== authority) return false;
    return Boolean(tag || name || authority);
  }

  querySelectorAll(selector) {
    const result = [];
    const visit = node => {
      for (const child of node.children) {
        if (child instanceof MiniNode) {
          if (child.matches(selector)) result.push(child);
          visit(child);
        }
      }
    };
    visit(this);
    return result;
  }

  querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
}

class MiniDocument {
  createElement(tagName) { return new MiniNode(tagName); }
  createElementNS(_namespace, tagName) { return new MiniNode(tagName); }
  createTextNode(text) { return new MiniNode('#text', String(text)); }
}

globalThis.Node = MiniNode;
globalThis.document = new MiniDocument();

const selection = {analysisId: 'analysis-1', rowId: 'row-1', revisionId: 'revision-1'};

function makeStore(resources = {}) {
  const calls = [];
  const store = {
    state: {selection, resources, context: null, busy: false, error: ''},
    client: {
      operation(path, body, etag) {
        calls.push({kind: 'operation', path, body, etag});
        return {path, body: JSON.stringify(body), etag, key: 'test-key'};
      },
    },
    resource(path) { return this.state.resources[path]; },
    read(path, options) { calls.push({kind: 'read', path, options}); },
    submit(operation, refreshPath) { calls.push({kind: 'submit', operation, refreshPath}); },
    calls,
  };
  return store;
}

function textButton(root, text) {
  return root.querySelectorAll('button').find(button => button.textContent.includes(text));
}

function setField(root, name, value) {
  const field = root.querySelector(`input[name="${name}"]`) || root.querySelector(`textarea[name="${name}"]`);
  assert.ok(field, `field ${name} should be rendered`);
  field.value = value;
  return field;
}

const riskPath = '/api/v1/fmea/rows/row-1/risk';
const risk = {
  assessment_id: 'assessment-1', workspace_id: 'workspace-1', row_id: 'row-1', source_record_version: 4,
  evidence_pack_id: 'evidence-pack-1', domain_pack_id: 'domain-1', domain_pack_version: '2026.08',
  rule_pack_id: 'rules-1', rule_pack_version: '2026.08', status: 'proposed',
  dimensions: [{name: 'severity', value: 4, evidence_ids: ['evidence-1'], reason: 'server value', uncertainty: null}],
  derived: {severity_by_consequence_class: [], decision_severity: 4, occurrence: 2, detection: 3, rpn: 24,
    decision_priority: 'review', inherent_risk: null, current_risk: null, target_residual_risk: null,
    verified_residual_risk: null, uncertainty: null, reason: 'server value',
    scoring_rule_pack_id: 'rules-1', scoring_rule_pack_version: '2026.08', evidence_ids: ['evidence-1']},
  proposal_id: 'proposal-1', assistance_suggestion_id: 'suggestion-1', confirmer_actor_id: null,
  invalidated_reason: null, record_version: 5, created_at: '2026-09-04T00:00:00Z', updated_at: '2026-09-04T00:00:00Z',
};

test('risk view uses the retrieved assessment ETag for explicit confirmation', async () => {
  const {renderRiskView} = await import('../../frontend_app/current_console/fmea/views/risk.js');
  const store = makeStore({[riskPath]: {data: risk, etag: '"5"'}});
  const confirmations = [];
  const root = renderRiskView({
    store,
    confirm: (...args) => confirmations.push(args),
    reportError: error => { throw error; },
  });

  textButton(root, '确认风险评分').dispatchEvent('click');
  assert.deepEqual(confirmations[0], [
    '确认风险评分',
    '/api/v1/fmea/rows/row-1/risk-confirmations',
    {proposal_id: 'proposal-1'},
    '"5"',
    riskPath,
  ]);
});

test('propagation view keeps the graph read-only and submits only server-backed edge decisions', async () => {
  const {renderPropagationView} = await import('../../frontend_app/current_console/fmea/views/propagation.js');
  const graphPath = '/api/v1/fmea/propagation-graphs/graph-1';
  const graph = {
    graph_revision_id: 'graph-1', workspace_id: 'workspace-1', analysis_id: 'analysis-1', analysis_record_version: 9,
    topology_snapshot_id: 'topology-1', topology_hash: 'sha256:graph', evidence_pack_ids: ['evidence-pack-1'],
    domain_pack_id: 'domain-1', domain_pack_version: '2026.08', rule_pack_id: 'rules-1', rule_pack_version: '2026.08',
    status: 'proposed', assistance_suggestion_ids: ['suggestion-graph-1'],
    nodes: [{node_id: 'node-a', node_type: 'row', operating_modes: ['normal']},
      {node_id: 'node-b', node_type: 'row', operating_modes: ['normal']}],
    edges: [{edge_id: 'edge-1', analysis_id: 'analysis-1', source_entity_id: 'node-a', target_entity_id: 'node-b',
      relation_type: 'physical', interface_variable: 'pressure', unit: 'Pa', direction: 'forward', threshold: null,
      operating_modes: ['normal'], delay_ms: null, response_time_ms: null, fault_tolerance_time_ms: null,
      barrier_ids: [], evidence_pack_id: 'evidence-pack-1', evidence_ids: ['evidence-1'],
      evidence_support: 'supported', claim_status: 'known', review_status: 'suggested', publication_status: 'unpublished',
      path_length: 1, is_cyclic: false, is_unprocessed: false, is_external: false, is_terminal: true,
      risk_priority: null, record_version: 3}],
    paths: [], unresolved_issue_codes: ['UNREVIEWED_EDGE'], parent_graph_revision_id: null,
    record_version: 3, created_at: '2026-09-04T00:00:00Z',
  };
  const validation = spawnSync(fileURLToPath(new URL('../../.venv/Scripts/python.exe', import.meta.url)), ['-B', '-c',
    'import sys,json; sys.path.insert(0,"api_server/current_console/chroma_rag_poc/src"); from chroma_rag_poc.fmea_propagation_contracts import PropagationGraphData; from chroma_rag_poc.fmea_risk_contracts import RiskAssessmentRecordData; data=json.load(sys.stdin); PropagationGraphData.model_validate(data[0]); RiskAssessmentRecordData.model_validate(data[1])',
  ], {cwd: fileURLToPath(new URL('../../', import.meta.url)), input: JSON.stringify([graph, risk]), encoding: 'utf8'});
  assert.equal(validation.status, 0, validation.stderr || String(validation.error || 'fixture schema validation failed'));
  const store = makeStore({
    '/api/v1/fmea/analyses/analysis-1/propagation-runs': {data: {run_id: 'run-propagation-1', graph: {graph_revision_id: 'graph-1'}}},
    [graphPath]: {data: graph, etag: '"3"'},
  });
  const confirmations = [];
  const root = renderPropagationView({store, confirm: (...args) => confirmations.push(args), reportError: error => { throw error; }});

  assert.ok(root.querySelector('svg'), 'propagation graph should be an SVG projection');
  assert.match(root.textContent, /edge-1/, 'the reviewed edge is present in the retrieved graph');
  assert.equal(textButton(root, '编辑传播图'), undefined, 'no graph editing command is allowed');
  setField(root, 'edge_decisions', '[{"edge_id":"edge-1","action":"accept","reason":"人工核对"}]');
  textButton(root, '确认传播复核').dispatchEvent('click');
  assert.deepEqual(confirmations[0], [
    '确认传播复核',
    '/api/v1/fmea/propagation-graphs/graph-1/reviews',
    {edge_decisions: [{edge_id: 'edge-1', action: 'accept', reason: '人工核对'}], acknowledgements: []},
    '"3"',
    graphPath,
  ]);
});

test('governance view requires a retrieved revision/version before destructive lifecycle commands', async () => {
  const {renderGovernanceView} = await import('../../frontend_app/current_console/fmea/views/governance.js');
  const revisionPath = '/api/v1/fmea/revisions/revision-1';
  const revision = {
    revision_id: 'revision-1', workspace_id: 'workspace-1', analysis_id: 'analysis-1', record_version: 11,
    analysis_record_version: 9, revision_hash: 'sha256:revision', analysis_hash: 'sha256:analysis',
    parent_revision_id: null, parent_revision_hash: null, row_versions: [], risk_versions: [],
    propagation_graph_revision_id: 'graph-1', propagation_graph_hash: 'sha256:graph', evidence_pack_hashes: [],
    retrieval_provenance: {requested_profile: 'fmea', resolved_profile: 'fmea', evidence_types: [], source_counts: [], warnings: []},
    domain_pack_identity: ['domain-1', '2026.08'], template_identities: [], scoring_rule_identities: [],
    propagation_rule_identity: null, unresolved_items: [], created_at: '2026-09-04T00:00:00Z',
  };
  const store = makeStore({[revisionPath]: {data: revision, etag: '"11"'}});
  const confirmations = [];
  const root = renderGovernanceView({store, confirm: (...args) => confirmations.push(args), reportError: error => { throw error; }});

  assert.equal(setField(root, 'analysis_record_version', '').value, '');
  setField(root, 'analysis_record_version', '9');
  textButton(root, '组装修订').dispatchEvent('click');
  assert.deepEqual(confirmations[0], [
    '组装修订',
    '/api/v1/fmea/analyses/analysis-1/revisions',
    {parent_revision_id: null, parent_revision_hash: null, confirm_human_approval: true},
    '"9"',
    revisionPath,
  ]);
});

test('governance approval confirmations refresh only the routed approval-events query', async () => {
  const {renderGovernanceView} = await import('../../frontend_app/current_console/fmea/views/governance.js');
  const revisionPath = '/api/v1/fmea/revisions/revision-1';
  const submissionPath = `${revisionPath}/approval-submissions`;
  const approvalResultPath = '/api/v1/fmea/approval-submissions/submission-1/approvals';
  const revision = {
    revision_id: 'revision-1', workspace_id: 'workspace-1', analysis_id: 'analysis-1', record_version: 11,
    analysis_record_version: 9, revision_hash: 'sha256:revision', analysis_hash: 'sha256:analysis',
    parent_revision_id: null, parent_revision_hash: null, row_versions: [], risk_versions: [],
    propagation_graph_revision_id: 'graph-1', propagation_graph_hash: 'sha256:graph', evidence_pack_hashes: [],
    retrieval_provenance: {requested_profile: 'fmea', resolved_profile: 'fmea', evidence_types: [], source_counts: [], warnings: []},
    domain_pack_identity: ['domain-1', '2026.08'], template_identities: [], scoring_rule_identities: [],
    propagation_rule_identity: null, unresolved_items: [], created_at: '2026-09-04T00:00:00Z',
  };
  const store = makeStore({
    [revisionPath]: {data: revision, etag: '"11"'},
    [submissionPath]: {data: {submission_id: 'submission-1', record_version: 12}, etag: '"12"'},
  });
  const confirmations = [];
  let root = renderGovernanceView({
    store,
    confirm: (...args) => {
      confirmations.push(args);
      if (args[1] === approvalResultPath) store.state.resources[approvalResultPath] = {data: {
        approval_id: 'approval-1', record_version: 13,
        replayed: false, audit_event_id: 'audit-1', outbox_event_id: 'outbox-1',
      }, etag: '"13"'};
    },
    reportError: error => { throw error; },
  });

  setField(root, 'approval_reason', '人工核对完成');
  textButton(root, '批准审批').dispatchEvent('click');
  assert.equal(confirmations[0][4], '/api/v1/fmea/revisions/revision-1/approval-events');

  root = renderGovernanceView({store, confirm: (...args) => confirmations.push(args), reportError: error => { throw error; }});
  setField(root, 'approval_withdrawal_reason', '需要重新核对');
  textButton(root, '撤回审批').dispatchEvent('click');
  assert.equal(confirmations[1][4], '/api/v1/fmea/revisions/revision-1/approval-events');
});

test('risk status selection renders queried B instead of cached POST A and resets on reauth', async () => {
  const {renderRiskView} = await import('../../frontend_app/current_console/fmea/views/risk.js');
  for (const withPost of [true, false]) {
    const store = makeStore(withPost ? {
      '/api/v1/fmea/rows/row-1/risk-proposal-runs': {data: {run_id: 'run-A', assessment: risk}},
    } : {});
    const props = {store, confirm() {}, reportError: error => { throw error; }};
    let root = renderRiskView(props);
    setField(root, 'risk_run_id', 'run-B');
    textButton(root, '查询风险建议状态').dispatchEvent('click');
    assert.equal(store.calls.at(-1).path, '/api/v1/fmea/risk-proposal-runs/run-B');
    store.state.resources['/api/v1/fmea/risk-proposal-runs/run-B'] = {
      data: {run_id: 'run-B', assessment: {...risk, proposal_id: 'proposal-B'}},
    };
    root = renderRiskView(props);
    assert.equal(root.querySelector('[name="risk_run_id"]').value, 'run-B');
    const status = root.querySelectorAll('details').find(item => item.textContent.startsWith('查询到的风险建议状态'));
    assert.ok(status, 'manual GET response must be visible even without a POST receipt');
    assert.match(status.textContent, /run-B/);
    assert.match(root.textContent, /候选提案 proposal-B/);
    assert.doesNotMatch(root.textContent, /候选提案 proposal-1/);
    store.state.selection = {...selection}; // configure/reauth replaces selection identity, even for the same IDs.
    root = renderRiskView(props);
    assert.equal(root.querySelector('[name="risk_run_id"]').value, '');
    assert.doesNotMatch(root.textContent, /run-B|run-A/);
  }
});

test('governance rejection receipt cannot authorize approval withdrawal or prefill publication approval', async () => {
  const {renderGovernanceView} = await import('../../frontend_app/current_console/fmea/views/governance.js');
  const store = makeStore();
  const props = {store, reportError: error => { throw error; }, confirm: (_title, path) => {
    store.state.resources[path] = {data: {
      approval_id: 'rejected-1', record_version: 13,
      replayed: false, audit_event_id: 'audit-rejection', outbox_event_id: 'outbox-rejection',
    }, etag: '"13"'};
  }};
  let root = renderGovernanceView(props);
  setField(root, 'submission_id', 'submission-1');
  setField(root, 'submission_record_version', '12');
  setField(root, 'decision_revision_hash', 'sha256:revision');
  setField(root, 'approval_reason', 'Needs correction');
  textButton(root, '拒绝审批').dispatchEvent('click');
  root = renderGovernanceView(props);
  assert.match(root.textContent, /rejected-1/);
  assert.equal(Boolean(textButton(root, '撤回审批')), false);
  assert.equal(root.querySelector('[name="publication_approval_id"]').value, '');
});

test('governance publish refresh follows the receipt through the real store; conflicts refresh the revision', async () => {
  const {renderGovernanceView} = await import('../../frontend_app/current_console/fmea/views/governance.js');
  const {WorkbenchStore} = await import('../../frontend_app/current_console/fmea/store.js');
  const revisionPath = '/api/v1/fmea/revisions/revision-1';
  const publicationPath = '/api/v1/fmea/publications/publication-2';
  for (const conflict of [false, true]) {
    const reads = [];
    let complete;
    const store = new WorkbenchStore({setToken() {}, execute: async () => {
      if (conflict) throw Object.assign(new Error('stale'), {status: 412});
      return {data: {publication_id: 'publication-2', manifest_id: 'manifest-2', snapshot_id: 'snapshot-2',
        record_version: 14, replayed: false, audit_event_id: 'audit-publish', outbox_event_id: 'outbox-publish'}};
    }, get: async path => {
      reads.push(path);
      return {data: {publication_id: 'publication-2', workspace_id: 'workspace-1', analysis_id: 'analysis-1',
        revision_id: 'revision-1', revision_hash: 'sha256:revision', approval_id: 'approval-1',
        manifest_id: 'manifest-2', manifest_hash: 'sha256:manifest', snapshot_id: 'snapshot-2', snapshot_hash: 'sha256:snapshot',
        audit_chain_head: 'audit-publish', publisher_actor_id: 'human-1', record_version: 14,
        created_at: '2026-09-04T00:00:00Z', effective_status: 'published', withdrawal: null, supersession: null}, etag: '"14"'};
    }});
    store.configure(selection, 'token');
    store.state.resources[revisionPath] = {data: null, etag: '"11"'};
    let descriptor;
    const root = renderGovernanceView({store, reportError: error => { throw error; },
      confirm: (_title, path, body, etag, refresh) => {
        descriptor = refresh;
        assert.equal(path, '/api/v1/fmea/revisions/revision-1/publications');
        assert.equal(etag, '"11"');
        complete = store.submit({path, body}, refresh);
      },
    });
    setField(root, 'publication_approval_id', 'approval-1');
    setField(root, 'publication_revision_hash', 'sha256:revision');
    textButton(root, '发布修订').dispatchEvent('click');
    await complete;
    assert.deepEqual(reads, [conflict ? revisionPath : publicationPath]);
    if (!conflict) {
      assert.equal(descriptor.onSuccess({publication_id: 'publication:2'}), '/api/v1/fmea/publications/publication%3A2');
      const refreshed = renderGovernanceView({store, confirm() {}, reportError: error => { throw error; }});
      assert.equal(refreshed.querySelector('[name="publication_record_version"]').value, '14');
      assert.match(refreshed.textContent, /发布记录 DTO/);
    }
  }
});

test('propagation and governance resource-ID drafts reset when the selected identity changes', async () => {
  const {renderPropagationView} = await import('../../frontend_app/current_console/fmea/views/propagation.js');
  const {renderGovernanceView} = await import('../../frontend_app/current_console/fmea/views/governance.js');
  const propagationStore = makeStore({
    '/api/v1/fmea/analyses/analysis-1/propagation-runs': {data: {run_id: 'run-1', graph: {graph_revision_id: 'graph-1'}}},
    '/api/v1/fmea/propagation-graphs/graph-1': {data: {graph_revision_id: 'graph-1', nodes: [], edges: [], paths: [], status: 'proposed', record_version: 2}, etag: '"2"'},
  });
  let propagationRoot = renderPropagationView({store: propagationStore, confirm() {}, reportError: error => { throw error; }});
  assert.equal(propagationRoot.querySelector('[name="graph_revision_id"]').value, 'graph-1');
  propagationStore.state.selection = {...selection, revisionId: 'revision-2'};
  propagationRoot = renderPropagationView({store: propagationStore, confirm() {}, reportError: error => { throw error; }});
  assert.equal(propagationRoot.querySelector('[name="graph_revision_id"]').value, '');

  const governanceStore = makeStore({
    '/api/v1/fmea/revisions/revision-1': {data: {revision_id: 'revision-1', analysis_id: 'analysis-1', revision_hash: 'hash-1', analysis_record_version: 3, record_version: 4}, etag: '"4"'},
  });
  let governanceRoot = renderGovernanceView({store: governanceStore, confirm() {}, reportError: error => { throw error; }});
  setField(governanceRoot, 'publication_id', 'publication-1');
  textButton(governanceRoot, '查询发布记录').dispatchEvent('click');
  governanceStore.state.selection = {...selection, revisionId: 'revision-2'};
  governanceRoot = renderGovernanceView({store: governanceStore, confirm() {}, reportError: error => { throw error; }});
  assert.equal(governanceRoot.querySelector('[name="publication_id"]').value, '');
});
