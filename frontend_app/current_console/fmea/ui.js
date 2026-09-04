export function el(tag, attributes = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attributes)) {
    if (key.startsWith('on')) node.addEventListener(key.slice(2), value);
    else if (key === 'className') node.className = value;
    else if (key === 'value') node.value = value;
    else if (value === true) node.setAttribute(key, '');
    else if (value !== false && value != null) node.setAttribute(key, String(value));
  }
  for (const child of children.flat(Infinity)) if (child != null) node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  return node;
}
const labels = {known: '已知', unknown: '未知', insufficient_evidence: '证据不足', conflict: '来源冲突', not_applicable: '不适用', supported: '证据支持', partially_supported: '部分支持', contradicted: '证据矛盾', not_supported: '未获支持', draft: '草稿', suggested: '建议待复核', in_review: '复核中', accepted: '人工接受', rejected: '已拒绝', superseded: '已取代', unpublished: '未发布', published: '已发布', withdrawn: '已撤回', queued: '排队中', running: '运行中', cancelling: '取消中', cancelled: '已取消', succeeded: '已完成', failed: '失败', confirmed: '已确认', invalidated: '已失效', proposed: '候选建议', reviewed: '已复核', approved: '已批准'};
export function badge(value) { return el('span', {className: 'badge', 'data-state': value}, `◇ ${labels[value] || value || '未提供'}`); }
export function details(title, value) { return el('details', {}, el('summary', {}, title), el('pre', {}, JSON.stringify(value, null, 2))); }
export function field(label, name, value = '', options = {}) { return el('label', {}, label, el(options.multiline ? 'textarea' : 'input', {name, value, ...options, multiline: undefined})); }
export function select(label, name, values) { return el('label', {}, label, el('select', {name}, values.map(([value, text]) => el('option', {value}, text)))); }
export function button(label, handler, disabled = false) { return el('button', {type: 'button', onclick: handler, disabled}, label); }
export function table(headers, rows) { return el('div', {className: 'table-wrap', 'data-layout': 'responsive-table'}, el('table', {}, el('thead', {}, el('tr', {}, headers.map(label => el('th', {scope: 'col'}, label)))), el('tbody', {}, rows.map(row => el('tr', {}, row.map(value => el('td', {}, value))))))); }
