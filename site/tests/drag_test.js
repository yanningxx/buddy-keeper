/* 验证拖拽落库：DOM 重排后 persistOrder() 是否把 column_id / position 写回云端；
   并验证只读身份（不是 owner）拖不动、也写不进库。 */
const fs = require('fs');
const path = require('path');
const { JSDOM, VirtualConsole } = require('jsdom');

const HTML = fs.readFileSync(path.join(__dirname, '..', 'index.html'), 'utf8');
const URL0 = 'https://xuyanning-d2g5ejg513e3c8e1d-1414642200.tcloudbaseapp.com/board/index.html';
const REST = 'https://xuyanning-d2g5ejg513e3c8e1d.api.tcloudbasegateway.com/v1/rdb/rest';
const sleep = (ms) => new Promise(r => setTimeout(r, ms));
const results = [];
const check = (n, c, e) => { results.push(!!c); console.log((c ? '  PASS ' : '  FAIL ') + n + (e ? '   ' + e : '')); };

function mkDom(vc) {
  return new JSDOM(HTML, {
    url: URL0, runScripts: 'dangerously', pretendToBeVisual: true, virtualConsole: vc,
    beforeParse(w) {
      w.fetch = (u, o) => fetch(u, o);
      Object.defineProperty(w.navigator, 'clipboard', { value: { writeText: () => Promise.resolve() }, configurable: true });
    },
  });
}

(async () => {
  const vc = new VirtualConsole();
  const errs = [];
  vc.on('jsdomError', e => errs.push(e.message));

  const dom = mkDom(vc);
  const { window } = dom, doc = window.document;
  const $$ = s => Array.from(doc.querySelectorAll(s));

  await sleep(200);
  doc.querySelector('nav button[data-tab="kanban"]').click();
  const t0 = Date.now();
  while (Date.now() - t0 < 25000 && !(window.KB.board && window.KB.cards.length)) await sleep(150);
  await sleep(500);
  if (!window.KB.board) { console.log('日志未就绪，退出'); process.exit(1); }
  const boardId = window.KB.board.id;
  const TOK = window.AUTH.load().access_token;
  const H = { Authorization: 'Bearer ' + TOK };
  console.log('\n看板', boardId, '初始卡片', window.KB.cards.length, '张');
  check('本机身份是 owner，可编辑', window.KB.canEdit === true);

  // 找到 todo 列的第一张卡，移动到 done 列最前面（模拟拖放的 DOM 结果）
  const todoCards = $$('.kb-cards[data-drop="todo"] .kb-card');
  const doneBox = doc.querySelector('.kb-cards[data-drop="done"]');
  check('todo 列有卡片', todoCards.length >= 1, String(todoCards.length));
  const moved = todoCards[0];
  const movedId = moved.dataset.card;
  doneBox.insertBefore(moved, doneBox.firstChild);

  check('persistOrder 已挂到 window', typeof window.persistOrder === 'function');
  window.persistOrder();

  await sleep(2500);
  const rows = await (await fetch(REST + '/bk_cards?select=id,column_id,position&board_id=eq.' + boardId + '&order=column_id.asc,position.asc',
    { headers: H })).json();
  const row = rows.find(x => x.id === movedId);
  check('跨列移动已落库 column_id=done', row && row.column_id === 'done', row ? row.column_id : '未找到');
  check('position 已重排为 0', row && Number(row.position) === 0, row ? String(row.position) : '-');

  const doneOrder = rows.filter(x => x.column_id === 'done').map(x => Number(x.position));
  check('done 列 position 连续无重复',
    JSON.stringify(doneOrder) === JSON.stringify([...new Set(doneOrder)].sort((a, b) => a - b)),
    JSON.stringify(doneOrder));

  // 再移回去，确认可反复（上一步 renderBoard 重建过 DOM，必须按 id 重新取元素）
  const back = doc.querySelector('.kb-cards[data-drop="todo"]');
  const movedAgain = doc.querySelector('.kb-card[data-card="' + movedId + '"]');
  check('重渲后仍能按 id 找到该卡片', !!movedAgain);
  back.appendChild(movedAgain);
  window.persistOrder();
  await sleep(2500);
  const r2 = await (await fetch(REST + '/bk_cards?select=id,column_id&board_id=eq.' + boardId, { headers: H })).json();
  const row2 = r2.find(x => x.id === movedId);
  check('再移回 todo 也落库', row2 && row2.column_id === 'todo', row2 ? row2.column_id : '未找到');

  /* ---------- 只读身份：拖了也不该写 ---------- */
  console.log('\n第二个身份打开同一看板（只读）');
  const dom2 = new JSDOM(HTML, {
    url: URL0 + '?code=' + window.KB.board.share_code,
    runScripts: 'dangerously', pretendToBeVisual: true, virtualConsole: vc,
    beforeParse(w) {
      w.fetch = (u, o) => fetch(u, o);
      Object.defineProperty(w.navigator, 'clipboard', { value: { writeText: () => Promise.resolve() }, configurable: true });
    },
  });
  await sleep(250);
  const t1 = Date.now();
  while (Date.now() - t1 < 25000 && !(dom2.window.KB && dom2.window.KB.board)) await sleep(150);
  await sleep(400);
  const w2 = dom2.window, d2 = w2.document;
  check('第二个身份 canEdit=false', w2.KB.canEdit === false);
  check('第二个身份读到了卡片', w2.KB.cards.length > 0, String(w2.KB.cards.length));

  // 强行在 DOM 里搬一张卡，再调 persistOrder —— 必须被 canEdit 拦住
  const card2 = d2.querySelector('.kb-cards[data-drop="done"] .kb-card');
  const card2Id = card2 ? card2.dataset.card : null;
  const beforeCol = card2Id ? (w2.KB.cards.find(c => c.id === card2Id) || {}).column_id : null;
  if (card2) {
    d2.querySelector('.kb-cards[data-drop="todo"]').appendChild(card2);
    w2.persistOrder();
  }
  await sleep(2500);
  const after = await (await fetch(REST + '/bk_cards?select=id,column_id&id=eq.' + card2Id, { headers: H })).json();
  check('只读身份拖动后库里列号没变',
    after.length === 1 && after[0].column_id === beforeCol,
    'before=' + beforeCol + ' after=' + (after[0] || {}).column_id);

  console.log('\n清理');
  for (const p of ['/bk_cards?board_id=eq.' + boardId, '/bk_boards?id=eq.' + boardId]) {
    const d = await fetch(REST + p, { method: 'DELETE', headers: Object.assign({ Prefer: 'return=minimal' }, H) });
    console.log('  DELETE ->', d.status);
  }
  const real = errs.filter(e => !/Not implemented|css|resource/i.test(e));
  console.log('\n运行期错误:', real.length ? real.slice(0, 3).join(' | ') : '无');
  const p = results.filter(Boolean).length;
  console.log('==== ' + p + '/' + results.length + ' 项通过 ====');
  process.exit(p === results.length && !real.length ? 0 : 1);
})().catch(e => { console.error(e); process.exit(2); });
