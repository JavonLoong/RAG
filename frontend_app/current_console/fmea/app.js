import {FmeaClient} from './api-client.js';
import {WorkbenchStore} from './store.js';
import {renderAnalysisView} from './views/analysis.js';
import {renderEvidenceView} from './views/evidence.js';
import {renderReviewView} from './views/review.js';
import {renderRiskView} from './views/risk.js';
import {renderPropagationView} from './views/propagation.js';
import {renderGovernanceView} from './views/governance.js';
import {renderTemplatesView} from './views/templates.js';
import {renderExportsView} from './views/exports.js';

const store = new WorkbenchStore(new FmeaClient());
const main = document.getElementById('workbench-main');
const errorNode = document.getElementById('error');
const dialog = document.getElementById('confirmation');
const check = document.getElementById('confirmation-check');
let pendingConfirmation = null;
const views = {analysis: renderAnalysisView, evidence: renderEvidenceView, review: renderReviewView, risk: renderRiskView, propagation: renderPropagationView, governance: renderGovernanceView, templates: renderTemplatesView, exports: renderExportsView};
function reportError(error) { store.state.error = error.message; renderStatus(); }
function confirm(title, path, body, etag, refreshPath) {
  if (store.state.busy) return;
  if (store.state.pending) { reportError(new Error('仍有未决写入，请先重试原请求')); return; }
  const operation = store.client.operation(path, body, etag);
  pendingConfirmation = {operation, refreshPath, selection: store.state.selection};
  document.getElementById('confirmation-title').textContent = title;
  document.getElementById('confirmation-description').textContent = `分析 ${store.state.selection.analysisId}；行 ${store.state.selection.rowId}；修订 ${store.state.selection.revisionId}；操作资源 ${path}，版本 ${etag}。`;
  document.getElementById('confirmation-payload').textContent = operation.body;
  check.checked = false;
  document.getElementById('confirmation-submit').disabled = true;
  dialog.returnValue = '';
  dialog.showModal();
}
check.addEventListener('change', () => { document.getElementById('confirmation-submit').disabled = !check.checked; });
dialog.addEventListener('close', () => {
  const pending = pendingConfirmation;
  pendingConfirmation = null;
  if (dialog.returnValue !== 'confirm' || !check.checked || !pending) return;
  if (pending.selection !== store.state.selection) { reportError(new Error('资源已切换，请重新核对')); return; }
  store.submit(pending.operation, pending.refreshPath);
});
function renderStatus() {
  errorNode.textContent = store.state.error;
  errorNode.hidden = !store.state.error;
  document.getElementById('request-status').textContent = store.state.busy ? '正在请求服务端…' : store.state.notice || (store.state.selection ? '本地连接已设置。' : '请载入已有资源。');
  document.getElementById('cancel-request').hidden = !store.state.busy;
  document.getElementById('retry-request').hidden = !store.state.pending || store.state.busy;
  document.getElementById('retry-refresh').hidden = !store.state.refreshPending || store.state.busy;
  document.querySelector('#connection-form button[type="submit"]').disabled = store.hasUnresolvedWrite;
  document.getElementById('disconnect').disabled = store.hasUnresolvedWrite;
}
function render() {
  renderStatus();
  if (!store.state.selection) return;
  const route = Object.hasOwn(views, location.hash.slice(1)) ? location.hash.slice(1) : 'analysis';
  for (const link of document.querySelectorAll('nav a')) {
    if (link.hash === `#${route}`) link.setAttribute('aria-current', 'page');
    else link.removeAttribute('aria-current');
  }
  main.replaceChildren(views[route]({store, confirm, reportError}));
  main.setAttribute('aria-busy', String(store.state.busy));
}
document.getElementById('connection-form').addEventListener('submit', event => {
  event.preventDefault();
  try {
    const data = new FormData(event.currentTarget);
    const selection = Object.fromEntries(['analysisId', 'rowId', 'revisionId'].map(key => [key, String(data.get(key)).trim()]));
    if (Object.values(selection).some(value => !/^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$/.test(value))) throw new Error('ID 只能包含字母、数字、点、下划线、冒号和连字符');
    const token = String(data.get('token')).trim();
    if (!token) throw new Error('请输入本地访问令牌');
    store.configure(selection, token);
    event.currentTarget.elements.token.value = '';
    location.hash = 'analysis';
    store.loadContext().then(response => {
      if (response && store.state.selection?.rowId === selection.rowId && store.state.selection?.analysisId === selection.analysisId) {
        document.querySelector('.connection').open = false;
        main.focus();
      }
    });
  } catch (error) { reportError(error); }
});
document.getElementById('disconnect').addEventListener('click', () => {
  if (store.hasUnresolvedWrite) { reportError(new Error('仍有进行中或未决的写入，不能断开连接')); return; }
  store.client.setToken(''); location.reload();
});
document.getElementById('cancel-request').addEventListener('click', () => store.cancel());
document.getElementById('retry-refresh').addEventListener('click', () => store.retryRefresh());
document.getElementById('retry-request').addEventListener('click', () => {
  const pending = store.state.pending;
  if (!pending) return;
  // An explicit retry reuses the original serialized operation and UUID.
  pendingConfirmation = {...pending, selection: store.state.selection};
  document.getElementById('confirmation-title').textContent = '重试原请求（结果未知）';
  document.getElementById('confirmation-description').textContent = `行 ${store.state.selection.rowId}；修订 ${store.state.selection.revisionId}；${pending.operation.path}。保留原请求内容与幂等键。`;
  document.getElementById('confirmation-payload').textContent = pending.operation.file ? `模板文件：${pending.operation.file.name}（${pending.operation.file.size} 字节）` : pending.operation.body;
  check.checked = false; document.getElementById('confirmation-submit').disabled = true;
  dialog.returnValue = ''; dialog.showModal();
});
store.addEventListener('change', render);
window.addEventListener('hashchange', () => { render(); main.focus(); });
window.addEventListener('pagehide', () => store.client.setToken(''));
window.addEventListener('beforeunload', event => {
  if (store.hasUnresolvedWrite) { event.preventDefault(); event.returnValue = ''; }
});
