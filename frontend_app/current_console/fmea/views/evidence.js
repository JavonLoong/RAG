import {el, table, button} from '../ui.js';
export function renderEvidenceView({store}) {
  const context = store.state.context;
  const refs = context?.evidence.refs || [];
  const side = el('aside', {className: 'panel', 'aria-label': '证据详情'});
  function show(ref) {
    side.replaceChildren(el('h3', {}, '证据详情'));
    if (!ref) { side.append(el('p', {}, '没有可用证据；不据此推断已知。')); return; }
    side.append(el('p', {}, ref.evidence_id), el('p', {}, `${ref.source_type} · ${ref.is_primary ? '原始证据' : '派生证据'}`), el('p', {}, ref.locator), el('blockquote', {}, ref.quote));
  }
  show(refs[0]);
  const rows = refs.map(ref => [ref.evidence_id, ref.source_type, ref.quote, button(`查看证据 ${ref.evidence_id}`, () => show(ref))]);
  return el('section', {}, el('h2', {}, '证据'), el('p', {className: 'muted'}, `证据包 ${context?.evidence.pack_id || '未载入'}；定位符仅作文本展示。`), el('div', {className: 'split'}, el('section', {className: 'panel'}, table(['证据 ID', '来源', '原文', '详情'], rows)), side));
}
