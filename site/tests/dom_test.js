/* 在 jsdom 里真实执行 index.html 的脚本，接真实 CloudBase 接口，验证交互 + 身份/权限闭环。 */
const fs = require('fs');
const path = require('path');
const { JSDOM, VirtualConsole } = require('jsdom');

const HTML_PATH = path.join(__dirname, '..', 'index.html');
const DEPLOY_URL = 'https://xuyanning-d2g5ejg513e3c8e1d-1414642200.tcloudbaseapp.com/board/index.html';
const REST = 'https://xuyanning-d2g5ejg513e3c8e1d.api.tcloudbasegateway.com/v1/rdb/rest';

const results = [];
function check(name, cond, extra) {
  results.push(!!cond);
  console.log((cond ? '  PASS ' : '  FAIL ') + name + (extra ? '   ' + extra : ''));
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
async function waitFor(fn, timeout = 15000, step = 150) {
  const t0 = Date.now();
  while (Date.now() - t0 < timeout) {
    try { const v = fn(); if (v) return v; } catch (e) {}
    await sleep(step);
  }
  return null;
}

function mkDom(html, url, vc) {
  return new JSDOM(html, {
    url,
    runScripts: 'dangerously',
    pretendToBeVisual: true,
    virtualConsole: vc,
    beforeParse(w) {
      w.fetch = (u, o) => fetch(u, o);                       // Node 22 原生 fetch
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

  const dom = mkDom(html, DEPLOY_URL, vc);
  const { window } = dom;
  const doc = window.document;
  const $ = (s) => doc.querySelector(s);
  const $$ = (s) => Array.from(doc.querySelectorAll(s));
  const text = (s) => { const e = $(s); return e ? (e.textContent || '').trim() : ''; };

  await sleep(300);

  console.log('\n[1] 首屏（默认在「值守看板」标签）');
  check('页面标题正确', doc.title.indexOf('值守') >= 0, doc.title);
  check('5 个标签按钮', $$('nav button').length === 5, $$('nav button').map(b => b.dataset.tab).join(','));
  check('默认激活 board 面板', $('#board').classList.contains('on'));
  check('看板标签未加载数据（懒加载）', window.KB.board === null);

  console.log('\n[2] 点开「任务看板」，先登录再拉数据');
  $('nav button[data-tab="kanban"]').click();
  const loaded = await waitFor(() => (window.KB.board ? window.KB.board : null), 25000);
  check('KB.board 已就绪', !!loaded, loaded ? loaded.title : '超时');
  if (!loaded) { console.log('  错误:', errors.join(' | ')); process.exit(1); }
  await sleep(500);

  const ident = window.AUTH.load();
  check('已拿到身份 token', !!(ident && ident.access_token), ident ? 'sub=' + ident.sub : 'null');
  check('身份 id 是 22 字符（真实 uid 而非字面量 anon）',
    !!ident && /^[A-Za-z0-9_-]{22}$/.test(ident.sub), ident ? ident.sub : '');
  check('身份条显示「身份 xxxxxx」', text('#kbIdText').indexOf('身份') === 0, text('#kbIdText'));
  check('localStorage 里存了 device-id', !!window.localStorage.getItem('kb_device_id'),
    window.localStorage.getItem('kb_device_id'));
  check('新看板的 owner_uid 就是本机身份', loaded.owner_uid === ident.sub,
    'owner=' + loaded.owner_uid);
  check('本机可编辑（canEdit=true）', window.KB.canEdit === true);
  check('只读徽标未显示', $('#kbLock').style.display === 'none');
  check('#kanban 上没有 kb-ro 类', !$('#kanban').classList.contains('kb-ro'));

  check('状态栏已同步', text('#kbStatus').indexOf('已同步') >= 0, text('#kbStatus'));
  check('分享码已显示（8 位）', /^[A-Z0-9]{8}$/.test(text('#shareCode')), text('#shareCode'));
  check('渲染出 3 个列表', $$('.kb-col').length === 3, String($$('.kb-col').length));
  const seedCount = $$('.kb-card').length;
  check('首次建板自动灌了 4 张示例卡', seedCount === 4, String(seedCount));
  check('卡片有标题文本', $$('.kb-card-title').length === seedCount);
  check('URL 已写入 ?code=', window.location.search.indexOf('code=') >= 0, window.location.search);
  check('卡片可拖拽（draggable=true）', $('.kb-card').getAttribute('draggable') === 'true');

  console.log('\n[3] 新建卡片');
  const before = $$('.kb-card').length;
  $$('[data-addcard]')[0].click();
  await waitFor(() => $('#cardMask').classList.contains('on'), 3000);
  check('新建弹窗已打开', $('#cardMask').classList.contains('on'));
  $('#cTitle').value = '自动化测试新建的卡片';
  $('#cDesc').value = '由 jsdom 测试脚本写入';
  const tagBtn = $('[data-picktag]');
  if (tagBtn) tagBtn.click();
  $('#btnSaveCard').click();
  const grew = await waitFor(() => $$('.kb-card').length === before + 1, 15000);
  check('卡片数量 +1', !!grew, before + ' -> ' + $$('.kb-card').length);
  check('弹窗已关闭', !$('#cardMask').classList.contains('on'));
  check('新卡片出现在 DOM 里', $$('.kb-card-title').some(e => e.textContent === '自动化测试新建的卡片'));

  console.log('\n[4] 编辑卡片（改标题）');
  const targetCard = $$('.kb-card').find(e => e.querySelector('.kb-card-title').textContent === '自动化测试新建的卡片');
  targetCard.click();
  await waitFor(() => $('#cardMask').classList.contains('on'), 3000);
  check('编辑弹窗打开且标题回填', $('#cTitle').value === '自动化测试新建的卡片', $('#cTitle').value);
  check('删除按钮可见', $('#btnDelCard').style.display !== 'none');
  check('标题输入框可写', $('#cTitle').readOnly === false);
  $('#cTitle').value = '已改名的卡片';
  $('#btnSaveCard').click();
  const renamed = await waitFor(() => $$('.kb-card-title').some(e => e.textContent === '已改名的卡片'), 15000);
  check('标题已更新并重渲', !!renamed);

  console.log('\n[5] 搜索筛选');
  $('#q').value = '已改名';
  $('#q').dispatchEvent(new window.Event('input'));
  await sleep(150);
  const visible = $$('.kb-card').filter(e => e.style.display !== 'none');
  const hidden = $$('.kb-card').filter(e => e.style.display === 'none');
  check('命中 1 张、其余隐藏', visible.length === 1 && hidden.length >= 3,
    'visible=' + visible.length + ' hidden=' + hidden.length);
  $('#q').value = '绝对不存在的关键字zzz';
  $('#q').dispatchEvent(new window.Event('input'));
  await sleep(150);
  check('无结果时出现空态提示',
    $$('.kb-empty').some(e => e.textContent.indexOf('没有符合筛选条件') >= 0));
  $('#q').value = '';
  $('#q').dispatchEvent(new window.Event('input'));
  await sleep(150);

  console.log('\n[6] 成员/标签筛选');
  const fm = $('#fMember'), ft = $('#fTag');
  check('成员下拉已填充', fm.options.length >= 2, 'options=' + fm.options.length);
  check('标签下拉已填充', ft.options.length >= 2, 'options=' + ft.options.length);
  if (ft.options.length > 1) {
    ft.value = ft.options[1].value;
    ft.dispatchEvent(new window.Event('change'));
    await sleep(150);
    check('按标签筛选后卡片数收敛',
      $$('.kb-card').filter(e => e.style.display !== 'none').length < seedCount + 1,
      'visible=' + $$('.kb-card').filter(e => e.style.display !== 'none').length);
    ft.value = '';
    ft.dispatchEvent(new window.Event('change'));
    await sleep(150);
  }

  console.log('\n[7] 删除卡片（含二次确认）');
  const card = $$('.kb-card').find(e => e.querySelector('.kb-card-title').textContent === '已改名的卡片');
  card.click();
  await waitFor(() => $('#cardMask').classList.contains('on'), 3000);
  $('#btnDelCard').click();
  await waitFor(() => $('#confirmMask').classList.contains('on'), 3000);
  check('出现二次确认弹窗', $('#confirmMask').classList.contains('on'));
  check('确认文案提到不可恢复', text('#confirmText').indexOf('永久删除') >= 0, text('#confirmText'));
  const cntBefore = $$('.kb-card').length;
  $('#confirmOk').click();
  const gone = await waitFor(() => $$('.kb-card').length === cntBefore - 1, 15000);
  check('卡片已删除', !!gone, cntBefore + ' -> ' + $$('.kb-card').length);
  check('toast 提示已删除', $('#toast').textContent.indexOf('已删除') >= 0, $('#toast').textContent);

  console.log('\n[8] 添加列表');
  const colBefore = $$('.kb-col').length;
  $('#btnAddColumn').click();
  await waitFor(() => $('#promptMask').classList.contains('on'), 3000);
  $('#promptInput').value = '测试列表';
  $('#promptOk').click();
  const colGrew = await waitFor(() => $$('.kb-col').length === colBefore + 1, 15000);
  check('列表数量 +1', !!colGrew, colBefore + ' -> ' + $$('.kb-col').length);

  console.log('\n[9] 身份弹窗');
  $('#kbIdBox').click();
  await waitFor(() => $('#idMask').classList.contains('on'), 3000);
  check('身份弹窗打开', $('#idMask').classList.contains('on'));
  check('身份码已回填', $('#idCode').value === window.localStorage.getItem('kb_device_id'),
    $('#idCode').value);
  check('说明里带完整 uid', text('#idIntro').indexOf(ident.sub) >= 0);
  doc.querySelector('#idMask [data-close]').click();
  await sleep(120);
  check('关闭后弹窗消失', !$('#idMask').classList.contains('on'));

  console.log('\n[10] Esc 关闭弹窗');
  $$('[data-addcard]')[0].click();
  await waitFor(() => $('#cardMask').classList.contains('on'), 3000);
  doc.dispatchEvent(new window.KeyboardEvent('keydown', { key: 'Escape' }));
  await sleep(120);
  check('Esc 关闭卡片弹窗', !$('#cardMask').classList.contains('on'));

  console.log('\n[11] 刷新按钮');
  $('#btnReload').click();
  await sleep(1500);
  check('刷新后仍在看板', !!window.KB.board);
  check('刷新后列表仍是 4 个', $$('.kb-col').length === 4, String($$('.kb-col').length));

  const boardCode = window.KB.board.share_code, boardId = window.KB.board.id;
  const tokA = window.AUTH.load().access_token;

  console.log('\n[12] 另一个身份打开同一个分享码 → 能看，不能改');
  const dom2 = mkDom(html, DEPLOY_URL + '?code=' + boardCode, vc);
  await sleep(250);
  const ok2 = await waitFor(() => dom2.window.KB && dom2.window.KB.board, 25000);
  check('带 ?code= 打开自动切到看板标签', dom2.window.document.body.dataset.tab === 'kanban',
    dom2.window.document.body.dataset.tab);
  check('读到同一块看板', !!ok2 && ok2.id === boardId, ok2 ? ok2.title : '超时');
  const d2 = dom2.window.document;
  await sleep(400);
  check('第二个页面渲染出卡片', d2.querySelectorAll('.kb-card').length > 0,
    String(d2.querySelectorAll('.kb-card').length));
  const ident2 = dom2.window.AUTH.load();
  check('第二个身份与第一个不同', !!ident2 && ident2.sub !== ident.sub,
    (ident2 || {}).sub + ' vs ' + ident.sub);
  check('第二个页面 canEdit=false', dom2.window.KB.canEdit === false);
  check('#kanban 加了 kb-ro 只读类', d2.querySelector('#kanban').classList.contains('kb-ro'));
  check('显示「只读 · 这个看板属于另一个身份」',
    d2.querySelector('#kbLock').style.display !== 'none' &&
    (d2.querySelector('#kbLock').textContent || '').indexOf('只读') >= 0,
    (d2.querySelector('#kbLock').textContent || '').trim());
  check('标题输入框置为只读', d2.querySelector('#boardTitle').readOnly === true);
  check('卡片不带 draggable', d2.querySelector('.kb-card').getAttribute('draggable') === null);

  // 只读态下点「+ 添加列表」应被拦下
  const colBefore2 = d2.querySelectorAll('.kb-col').length;
  d2.querySelector('#btnAddColumn').click();
  await sleep(250);
  check('只读态点「+ 添加列表」弹不出输入框',
    !d2.querySelector('#promptMask').classList.contains('on'));
  check('只读态给出 toast 提示',
    (d2.querySelector('#toast').textContent || '').indexOf('只读') >= 0,
    (d2.querySelector('#toast').textContent || '').trim());
  check('列表数量没变', d2.querySelectorAll('.kb-col').length === colBefore2);

  // 只读态点卡片 → 只能查看
  d2.querySelector('.kb-card').click();
  await sleep(300);
  check('只读态能打开卡片查看', d2.querySelector('#cardMask').classList.contains('on'));
  check('只读态弹窗标题写明「只读」',
    (d2.querySelector('#cardModalTitle').textContent || '').indexOf('只读') >= 0,
    d2.querySelector('#cardModalTitle').textContent);
  check('只读态没有保存按钮', d2.querySelector('#btnSaveCard').style.display === 'none');
  check('只读态没有删除按钮', d2.querySelector('#btnDelCard').style.display === 'none');
  d2.querySelector('#cardMask [data-close]').click();
  await sleep(120);

  console.log('\n[13] 服务端兜底：绕过前端直接越权写，必须被 RLS 拒');
  const RESTURL = REST;
  const cross = await fetch(RESTURL + '/bk_boards?id=eq.' + boardId, {
    method: 'PATCH',
    headers: { Authorization: 'Bearer ' + ident2.access_token, 'Content-Type': 'application/json', Prefer: 'return=representation' },
    body: JSON.stringify({ title: '第二个身份试图改名' }),
  });
  const crossBody = await cross.json().catch(() => null);
  check('越权 PATCH 影响 0 行', cross.status === 200 && Array.isArray(crossBody) && crossBody.length === 0,
    'status=' + cross.status + ' body=' + JSON.stringify(crossBody));

  const crossIns = await fetch(RESTURL + '/bk_cards', {
    method: 'POST',
    headers: { Authorization: 'Bearer ' + ident2.access_token, 'Content-Type': 'application/json' },
    body: JSON.stringify({ id: 'x' + Date.now().toString(36), board_id: boardId, column_id: 'todo', title: '越权插入', position: 99 }),
  });
  check('越权 INSERT 被 401 拒绝', crossIns.status === 401, 'status=' + crossIns.status);

  const stillMine = await fetch(RESTURL + '/bk_boards?select=title,owner_uid&id=eq.' + boardId, {
    headers: { Authorization: 'Bearer ' + tokA },
  }).then(r => r.json());
  check('看板标题没被改掉', stillMine[0].title !== '第二个身份试图改名', stillMine[0].title);
  check('看板 owner 仍是第一个身份', stillMine[0].owner_uid === ident.sub);

  console.log('\n[14] 错误处理：接口地址坏掉时出现错误卡');
  const badHtml = html.replace(
    /(rest: 'https:\/\/[^']+\/v1\/rdb\/rest)(')/,
    '$1_broken$2');
  check('坏地址替换成功', badHtml !== html);
  const dom3 = mkDom(badHtml, DEPLOY_URL, vc);
  await sleep(250);
  dom3.window.document.querySelector('nav button[data-tab="kanban"]').click();
  const errShown = await waitFor(() => dom3.window.document.querySelector('#btnRetry'), 25000);
  check('出现「重试」按钮的错误卡', !!errShown);
  check('错误文案说明连不上库',
    (dom3.window.document.getElementById('kbBoard').textContent || '').indexOf('连不上云端数据库') >= 0);
  check('状态栏显示连接失败',
    (dom3.window.document.getElementById('kbStatus').textContent || '').indexOf('失败') >= 0);

  console.log('\n[15] 清理测试数据（用第一个身份的 token，RLS 只允许它删）');
  for (const p of ['/bk_cards?board_id=eq.' + boardId, '/bk_boards?id=eq.' + boardId]) {
    const r = await fetch(REST + p, {
      method: 'DELETE',
      headers: { Authorization: 'Bearer ' + tokA, Prefer: 'return=minimal' },
    });
    console.log('  DELETE', p.split('?')[0], '->', r.status);
  }
  const goneCheck = await fetch(REST + '/bk_boards?select=id&id=eq.' + boardId, {
    headers: { Authorization: 'Bearer ' + tokA },
  }).then(r => r.json());
  check('测试看板已删除', Array.isArray(goneCheck) && goneCheck.length === 0);

  const realErrors = errors.filter(e => !/Not implemented|css|resource/i.test(e));
  console.log('\n[16] 运行期错误：' + (realErrors.length ? realErrors.length + ' 条' : '无'));
  realErrors.slice(0, 6).forEach(e => console.log('   - ' + e));

  const passed = results.filter(Boolean).length;
  console.log('\n==== ' + passed + '/' + results.length + ' 项通过 ====');
  process.exit(passed === results.length && realErrors.length === 0 ? 0 : 1);
})().catch((e) => { console.error('HARNESS ERROR', e); process.exit(2); });
