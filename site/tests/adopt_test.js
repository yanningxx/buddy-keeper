/* 验证「身份码接管」这条承诺是否真的成立。
   页面文案写的是：换电脑或换浏览器时，把身份码粘过去再登录，就能接管自己建过的看板。
   这句话如果不测，等于把用户唯一的找回通道赌在没跑过的代码上。
   场景：A 建板 → B（另一台设备）打开分享码只读 → 在 B 上粘 A 的身份码 → B 变成可编辑。 */
const fs = require('fs');
const path = require('path');
const { JSDOM, VirtualConsole } = require('jsdom');

const HTML_PATH = path.join(__dirname, '..', 'index.html');
const BASE = 'https://xuyanning-d2g5ejg513e3c8e1d-1414642200.tcloudbaseapp.com/board/index.html';
const REST = 'https://xuyanning-d2g5ejg513e3c8e1d.api.tcloudbasegateway.com/v1/rdb/rest';

const results = [];
function check(name, cond, extra) {
  results.push(!!cond);
  console.log((cond ? '  PASS ' : '  FAIL ') + name + (extra ? '   ' + extra : ''));
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
async function waitFor(fn, timeout = 20000, step = 150) {
  const t0 = Date.now();
  while (Date.now() - t0 < timeout) {
    try { const v = fn(); if (v) return v; } catch (e) {}
    await sleep(step);
  }
  return null;
}

function mkDom(html, url, vc, seedDeviceId) {
  return new JSDOM(html, {
    url,
    runScripts: 'dangerously',
    pretendToBeVisual: true,
    virtualConsole: vc,
    beforeParse(w) {
      w.fetch = (u, o) => fetch(u, o);
      if (seedDeviceId) w.localStorage.setItem('kb_device_id', seedDeviceId);
      Object.defineProperty(w.navigator, 'clipboard', {
        value: { writeText: () => Promise.resolve() }, configurable: true,
      });
      w.matchMedia = w.matchMedia || (() => ({ matches: false, addListener() {}, removeListener() {} }));
    },
  });
}

(async () => {
  const html = fs.readFileSync(HTML_PATH, 'utf8');
  const errors = [];
  const vc = new VirtualConsole();
  vc.on('jsdomError', (e) => errors.push('jsdomError: ' + e.message));
  vc.on('error', (...a) => errors.push('console.error: ' + a.join(' ')));

  // ---- 设备 A：建板 ----
  console.log('\n[1] 设备 A：开页 → 自动登录 → 建一块属于自己的看板');
  const domA = mkDom(html, BASE, vc, null);
  domA.window.document.querySelector('nav button[data-tab="kanban"]').click();
  const boardA = await waitFor(() => domA.window.KB && domA.window.KB.board, 30000);
  check('A 拿到看板', !!boardA, boardA ? boardA.title : '超时');
  if (!boardA) { console.log('  错误:', errors.join(' | ')); process.exit(1); }
  const editableA = await waitFor(() => domA.window.KB.canEdit === true, 8000);
  const idA = domA.window.AUTH.load();
  const devA = domA.window.localStorage.getItem('kb_device_id');
  const codeA = boardA.share_code;
  const boardId = boardA.id;
  check('A 可编辑', !!editableA);
  check('owner 就是 A', boardA.owner_uid === idA.sub, idA.sub);
  check('A 的身份码已生成', !!devA && devA.length >= 8, devA);
  check('A 的身份码不等于 uid（身份码是设备前缀，uid 是登录后派生）', devA !== idA.sub);

  // ---- 设备 B：另一台机器打开分享码 ----
  console.log('\n[2] 设备 B（另一台机器）：打开同一个分享码 → 只能看');
  const DOM_B_ID = 'kb-fake0ther-machine-' + Date.now().toString(36) + '-zzzzzz';
  const domB = mkDom(html, BASE + '?code=' + codeA, vc, DOM_B_ID);
  const boardB = await waitFor(() => domB.window.KB && domB.window.KB.board, 30000);
  check('B 读到同一块看板', !!boardB && boardB.id === boardId, boardB ? boardB.title : '超时');
  await sleep(400);
  const idB = domB.window.AUTH.load();
  check('B 的 uid 与 A 不同', !!idB && idB.sub !== idA.sub, (idB || {}).sub + ' vs ' + idA.sub);
  check('B 的 device-id 就是预置的那个', domB.window.localStorage.getItem('kb_device_id') === DOM_B_ID);
  check('B 只读（canEdit=false）', domB.window.KB.canEdit === false);
  check('B 加了 kb-ro 类', domB.window.document.querySelector('#kanban').classList.contains('kb-ro'));

  // ---- 在 B 上粘 A 的身份码 ----
  console.log('\n[3] 在设备 B 上打开身份弹窗，粘入 A 的身份码并登录');
  const dB = domB.window.document;
  dB.querySelector('#kbIdBox').click();
  await waitFor(() => dB.querySelector('#idMask').classList.contains('on'), 3000);
  check('身份弹窗已打开', dB.querySelector('#idMask').classList.contains('on'));
  check('身份码输入框当前回填的是 B 自己的码',
    dB.querySelector('#idCode').value === DOM_B_ID, dB.querySelector('#idCode').value);

  // 先试一个明显不对的短码，应被拦下且不切身份
  dB.querySelector('#idCode').value = 'abc';
  dB.querySelector('#btnIdUse').click();
  await sleep(300);
  check('过短的身份码被拒（toast 提示）',
    (dB.querySelector('#toast').textContent || '').indexOf('不对') >= 0,
    (dB.querySelector('#toast').textContent || '').trim());
  check('被拒后身份没变', domB.window.localStorage.getItem('kb_device_id') === DOM_B_ID);

  // 粘真实身份码
  dB.querySelector('#kbIdBox').click();
  await waitFor(() => dB.querySelector('#idMask').classList.contains('on'), 3000);
  dB.querySelector('#idCode').value = devA;
  dB.querySelector('#btnIdUse').click();

  const adopted = await waitFor(
    () => domB.window.KB.canEdit === true && domB.window.KB.board, 30000);
  check('接管后 canEdit 翻成 true', !!adopted && domB.window.KB.canEdit === true);
  check('接管后 device-id 已替换成 A 的',
    domB.window.localStorage.getItem('kb_device_id') === devA,
    domB.window.localStorage.getItem('kb_device_id'));
  const idB2 = domB.window.AUTH.load();
  check('接管后 uid 与 A 完全一致', !!idB2 && idB2.sub === idA.sub, (idB2 || {}).sub);
  check('接管后读到的仍是同一块看板',
    !!adopted && adopted.id === boardId, adopted ? adopted.share_code : '');
  await sleep(400);
  check('接管后 kb-ro 类已摘掉',
    !domB.window.document.querySelector('#kanban').classList.contains('kb-ro'));
  check('接管后标题输入框可写',
    domB.window.document.querySelector('#boardTitle').readOnly === false);
  check('接管后卡片恢复 draggable',
    domB.window.document.querySelector('.kb-card').getAttribute('draggable') === 'true');
  check('接管后状态栏已同步',
    (dB.querySelector('#kbStatus').textContent || '').indexOf('已同步') >= 0,
    (dB.querySelector('#kbStatus').textContent || '').trim());

  // ---- 接管之后真的能写 ----
  console.log('\n[4] 接管后真的能改这块看板（不只是按钮放开了）');
  const oldTitle = domB.window.KB.board.title;
  const newTitle = '接管后改的标题 ' + Date.now().toString(36).slice(-4);
  const t = dB.querySelector('#boardTitle');
  t.value = newTitle;
  t.dispatchEvent(new domB.window.Event('change'));
  await sleep(1500);
  const rows = await fetch(REST + '/bk_boards?select=title,owner_uid&id=eq.' + boardId, {
    headers: { Authorization: 'Bearer ' + idB2.access_token },
  }).then((r) => r.json());
  check('库里标题已改成本次输入', rows[0] && rows[0].title === newTitle,
    rows[0] ? rows[0].title : '无返回');
  check('owner 未因接管而被改写', rows[0] && rows[0].owner_uid === idA.sub);

  // ---- 重置身份：换一个干净的设备身份，看板应变只读 ----
  console.log('\n[5] 在 B 上点「重置身份」→ 换新身份，同一块看板回到只读');
  dB.querySelector('#kbIdBox').click();
  await waitFor(() => dB.querySelector('#idMask').classList.contains('on'), 3000);
  dB.querySelector('#btnIdReset').click();
  await waitFor(() => dB.querySelector('#confirmMask').classList.contains('on'), 3000);
  check('重置前有二次确认', dB.querySelector('#confirmMask').classList.contains('on'));
  check('确认文案提醒会丢身份',
    (dB.querySelector('#confirmText').textContent || '').indexOf('只读') >= 0,
    (dB.querySelector('#confirmText').textContent || '').trim());
  dB.querySelector('#confirmOk').click();
  const reset = await waitFor(() => {
    const s = domB.window.AUTH.load();
    return s && s.sub && s.sub !== idA.sub ? s : null;
  }, 30000);
  check('重置后拿到了新身份', !!reset, reset ? reset.sub : '超时');
  check('重置后 device-id 不再是 A 的',
    domB.window.localStorage.getItem('kb_device_id') !== devA);
  const roAfterReset = await waitFor(() => domB.window.KB.board && domB.window.KB.canEdit === false, 30000);
  check('重置后同一块看板变只读', !!roAfterReset);
  check('重置后没有跳到别的看板（还是刚才那块）',
    !!roAfterReset && domB.window.KB.board.id === boardId,
    roAfterReset ? domB.window.KB.board.share_code : '');
  check('重置后显示只读徽标',
    dB.querySelector('#kbLock').style.display !== 'none',
    (dB.querySelector('#kbLock').textContent || '').trim());

  // ---- 清理 ----
  console.log('\n[6] 清理测试看板（用 A 的 token，RLS 只放行它）');
  for (const p of ['/bk_cards?board_id=eq.' + boardId, '/bk_boards?id=eq.' + boardId]) {
    const r = await fetch(REST + p, {
      method: 'DELETE',
      headers: { Authorization: 'Bearer ' + idA.access_token, Prefer: 'return=minimal' },
    });
    console.log('  DELETE', p.split('?')[0], '->', r.status);
  }
  const gone = await fetch(REST + '/bk_boards?select=id&id=eq.' + boardId, {
    headers: { Authorization: 'Bearer ' + idA.access_token },
  }).then((r) => r.json());
  check('测试看板已删除', Array.isArray(gone) && gone.length === 0, '原标题=' + oldTitle);

  const realErrors = errors.filter((e) => !/Not implemented|css|resource/i.test(e));
  console.log('\n[7] 运行期错误：' + (realErrors.length ? realErrors.length + ' 条' : '无'));
  realErrors.slice(0, 6).forEach((e) => console.log('   - ' + e));

  const passed = results.filter(Boolean).length;
  console.log('\n==== ' + passed + '/' + results.length + ' 项通过 ====');
  process.exit(passed === results.length && realErrors.length === 0 ? 0 : 1);
})().catch((e) => { console.error('HARNESS ERROR', e); process.exit(2); });
