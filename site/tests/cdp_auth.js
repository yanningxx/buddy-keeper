/* 真浏览器（Chrome + CDP）验证登录链路：
   匿名登录 → token 注入 → owner 判定 → token 刷新 → 切换身份变只读。
   针对 localhost 运行，因为 CloudBase 网关的 CORS 只放行环境自有域名与 localhost。 */
const { spawn } = require('child_process');
const fs = require('fs');
const path = require('path');
const os = require('os');

const CHROME = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const PORT = 9337;
const TARGET = process.argv[2] || 'http://localhost:5173/index.html';
const OUT = path.join(__dirname, '..', 'shots');
const REST = 'https://xuyanning-d2g5ejg513e3c8e1d.api.tcloudbasegateway.com/v1/rdb/rest';
const sleep = ms => new Promise(r => setTimeout(r, ms));

const results = [];
const check = (n, c, e) => { results.push(!!c); console.log((c ? '  PASS ' : '  FAIL ') + n + (e ? '   ' + e : '')); };

class CDP {
  constructor(ws) {
    this.ws = ws; this.id = 0; this.pend = new Map(); this.evs = [];
    ws.addEventListener('message', e => {
      const m = JSON.parse(e.data);
      if (m.id && this.pend.has(m.id)) {
        const { res, rej } = this.pend.get(m.id); this.pend.delete(m.id);
        m.error ? rej(new Error(JSON.stringify(m.error))) : res(m.result);
      } else if (m.method) this.evs.push(m);
    });
  }
  send(method, params = {}) {
    const id = ++this.id;
    return new Promise((res, rej) => { this.pend.set(id, { res, rej }); this.ws.send(JSON.stringify({ id, method, params })); });
  }
}

(async () => {
  const isLocal = /localhost|127\.0\.0\.1/.test(TARGET);
  const profile = path.join(os.tmpdir(), 'cdpA-' + Date.now());
  // 本地测试必须绕过系统代理；线上必须走代理才能出网
  const args = ['--headless=new', '--disable-gpu', '--hide-scrollbars', '--mute-audio',
    '--no-first-run', '--remote-debugging-port=' + PORT, '--user-data-dir=' + profile, 'about:blank'];
  if (isLocal) args.unshift('--no-proxy-server');
  const chrome = spawn(CHROME, args, { stdio: 'ignore' });

  let ver = null;
  for (let i = 0; i < 60; i++) { try { ver = await (await fetch(`http://127.0.0.1:${PORT}/json/version`)).json(); break; } catch (e) { await sleep(300); } }
  if (!ver) { console.error('Chrome 未就绪'); process.exit(1); }
  const tgt = await (await fetch(`http://127.0.0.1:${PORT}/json/new?about:blank`, { method: 'PUT' })).json();
  const ws = new WebSocket(tgt.webSocketDebuggerUrl);
  await new Promise(r => ws.addEventListener('open', r));
  const cdp = new CDP(ws);
  await cdp.send('Page.enable');
  await cdp.send('Runtime.enable');
  await cdp.send('Log.enable');
  await cdp.send('Network.enable');
  await cdp.send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 1000, deviceScaleFactor: 1, mobile: false });

  const evalq = async (expr) => (await cdp.send('Runtime.evaluate', { expression: expr, returnByValue: true, awaitPromise: true })).result.value;

  await cdp.send('Page.navigate', { url: TARGET });
  await sleep(2500);

  // CloudBase 测试域名对「浏览器式导航」有「确定访问」门禁，先在真实浏览器里点掉
  if (await evalq('!!document.getElementById("submitBtn")')) {
    console.log('  [门禁] 出现「确定访问」，等待倒计时后点击');
    for (let i = 0; i < 30; i++) {
      if (!(await evalq('document.getElementById("submitBtn").disabled'))) break;
      await sleep(500);
    }
    await evalq('document.getElementById("submitBtn").click()');
    await sleep(3500);
    check('门禁已通过（进入真实页面）',
      (await evalq('!!(window.KB && window.CFG)')) === true,
      await evalq('document.title'));
  }

  console.log('\n[1] 打开页面（默认在「值守看板」）');
  check('页面可访问', (await evalq('document.title')).indexOf('值守') >= 0, await evalq('document.title'));
  check('未提前建板（懒加载）', (await evalq('window.KB.board === null')) === true);

  console.log('\n[2] 切到「任务看板」→ 自动匿名登录 → 拉数据');
  await evalq(`document.querySelector('nav button[data-tab="kanban"]').click()`);
  let ready = null;
  for (let i = 0; i < 80; i++) {
    ready = await evalq('!!(window.KB && window.KB.board)');
    if (ready) break;
    await sleep(300);
  }
  check('看板已加载', ready === true);
  if (!ready) {
    const errs = cdp.evs.filter(e => e.method === 'Runtime.exceptionThrown')
      .map(e => (e.params.exceptionDetails.exception || {}).description);
    console.log('  异常:', errs.slice(0, 4));
    chrome.kill(); process.exit(1);
  }
  await sleep(800);

  const m1 = await evalq(`(() => {
    const s = AUTH.load();
    return {
      sub: s ? s.sub : null,
      tokenLen: s ? s.access_token.length : 0,
      hasRefresh: !!(s && s.refresh_token),
      exp: s ? s.exp : 0,
      device: localStorage.getItem('kb_device_id'),
      owner: KB.board.owner_uid,
      canEdit: KB.canEdit,
      share: KB.board.share_code,
      boardId: KB.board.id,
      title: KB.board.title,
      cards: document.querySelectorAll('.kb-card').length,
      cols: document.querySelectorAll('.kb-col').length,
      idChip: document.getElementById('kbIdText').textContent,
      lockShown: document.getElementById('kbLock').style.display !== 'none',
      roClass: document.getElementById('kanban').classList.contains('kb-ro'),
      status: document.getElementById('kbStatus').textContent,
      tokenA: s ? s.access_token : null,
    };
  })()`);
  console.log('  ' + JSON.stringify({ ...m1, tokenA: '(省略)' }, null, 1).replace(/\n\s*/g, ' '));
  check('拿到真实 uid（22 字符）', /^[A-Za-z0-9_-]{22}$/.test(m1.sub || ''), m1.sub);
  check('token 长度合理（>1000）', m1.tokenLen > 1000, String(m1.tokenLen));
  check('存了 refresh_token', m1.hasRefresh === true);
  check('localStorage 里有 device-id', (m1.device || '').length > 8, m1.device);
  check('看板 owner_uid == 本机 uid', m1.owner === m1.sub, m1.owner);
  check('canEdit = true', m1.canEdit === true);
  check('身份条显示「身份 xxxxxx」', m1.idChip.indexOf('身份') === 0, m1.idChip);
  check('未显示只读徽标', m1.lockShown === false);
  check('无 kb-ro 只读类', m1.roClass === false);
  check('渲染出 3 列 4 卡', m1.cols === 3 && m1.cards === 4, m1.cols + ' 列 / ' + m1.cards + ' 卡');
  check('状态栏显示已同步', m1.status.indexOf('已同步') >= 0, m1.status);

  console.log('\n[3] token 刷新路径（把 exp 改成过期，再 ensure）');
  const refreshed = await evalq(`(async () => {
    const before = AUTH.load().access_token;
    AUTH.st.exp = 0;
    try { localStorage.setItem('kb_auth', JSON.stringify(AUTH.st)); } catch (e) {}
    const s = await AUTH.ensure();
    const r = await fetch(CFG.rest + '/bk_boards?select=id&limit=1', { headers: { Authorization: 'Bearer ' + s.access_token } });
    return { changed: s.access_token !== before, sameSub: s.sub === AUTH.subOf(before), status: r.status, newLen: s.access_token.length };
  })()`);
  check('token 换成了新的', refreshed && refreshed.changed === true, String(refreshed && refreshed.newLen));
  check('刷新后身份不变', refreshed && refreshed.sameSub === true);
  check('新 token 能正常读库', refreshed && refreshed.status === 200, 'status=' + (refreshed || {}).status);

  console.log('\n[4] 浏览器里点「+ 添加卡片」→ 真的写进库');
  const before = await evalq(`document.querySelectorAll('.kb-card').length`);
  await evalq(`document.querySelector('[data-addcard]').click()`);
  await sleep(400);
  await evalq(`document.getElementById('cTitle').value = '浏览器端写入的卡片';
                document.getElementById('btnSaveCard').click()`);
  let after = before;
  for (let i = 0; i < 40; i++) { after = await evalq(`document.querySelectorAll('.kb-card').length`); if (after === before + 1) break; await sleep(300); }
  check('卡片数 +1 且已重渲', after === before + 1, before + ' -> ' + after);
  const inDb = await fetch(REST + '/bk_cards?select=id,title&board_id=eq.' + m1.boardId, {
    headers: { Authorization: 'Bearer ' + m1.tokenA } }).then(r => r.json());
  check('云端确实有这张卡', inDb.some(c => c.title === '浏览器端写入的卡片'), String(inDb.length) + ' 张');

  const shot1 = await cdp.send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: true });
  fs.writeFileSync(path.join(OUT, 'auth-1440.png'), Buffer.from(shot1.data, 'base64'));

  console.log('\n[5] 切换成另一个身份（同一台机器、同一块看板）');
  const sw = await evalq(`(async () => {
    await AUTH.adopt('cdp-other-identity-0001');
    KB.board = null; KB.cards = []; KB.loading = false; KB.boot();
    for (let i = 0; i < 60 && !(KB.board); i++) await new Promise(r => setTimeout(r, 300));
    await new Promise(r => setTimeout(r, 600));
    return {
      sub: AUTH.load().sub,
      owner: KB.board ? KB.board.owner_uid : null,
      canEdit: KB.canEdit,
      roClass: document.getElementById('kanban').classList.contains('kb-ro'),
      lockShown: document.getElementById('kbLock').style.display !== 'none',
      titleRO: document.getElementById('boardTitle').readOnly,
      draggable: document.querySelector('.kb-card') ? document.querySelector('.kb-card').getAttribute('draggable') : 'no-card',
      cards: document.querySelectorAll('.kb-card').length,
      share: KB.board ? KB.board.share_code : null,
    };
  })()`);
  check('身份已切换（uid 不同）', sw && sw.sub && sw.sub !== m1.sub, (sw || {}).sub);
  check('仍能读到同一块看板（分享语义）', sw && sw.share === m1.share, sw && sw.share);
  check('canEdit 变为 false', sw && sw.canEdit === false);
  check('加了 kb-ro 只读类', sw && sw.roClass === true);
  check('显示只读徽标', sw && sw.lockShown === true);
  check('标题输入框 readOnly', sw && sw.titleRO === true);
  check('卡片不再 draggable', sw && sw.draggable === null, String(sw && sw.draggable));

  console.log('\n[6] 只读态在浏览器里尝试越权写');
  const deny = await evalq(`(async () => {
    const t = AUTH.load().access_token;
    const p = await fetch(CFG.rest + '/bk_boards?id=eq.' + KB.board.id, {
      method: 'PATCH',
      headers: { Authorization: 'Bearer ' + t, 'Content-Type': 'application/json', Prefer: 'return=representation' },
      body: JSON.stringify({ title: '只读身份改的标题' })
    });
    const pb = await p.json().catch(() => null);
    const i = await fetch(CFG.rest + '/bk_cards', {
      method: 'POST',
      headers: { Authorization: 'Bearer ' + t, 'Content-Type': 'application/json' },
      body: JSON.stringify({ id: 'z' + Date.now().toString(36), board_id: KB.board.id, column_id: 'todo', title: '越权插入', position: 9 })
    });
    return { patchStatus: p.status, patchRows: Array.isArray(pb) ? pb.length : -1, insStatus: i.status };
  })()`);
  check('越权 PATCH 影响 0 行', deny && deny.patchStatus === 200 && deny.patchRows === 0,
    'status=' + (deny || {}).patchStatus + ' rows=' + (deny || {}).patchRows);
  check('越权 INSERT 返回 401', deny && deny.insStatus === 401, 'status=' + (deny || {}).insStatus);
  const stillOk = await fetch(REST + '/bk_boards?select=title&id=eq.' + m1.boardId, {
    headers: { Authorization: 'Bearer ' + m1.tokenA } }).then(r => r.json());
  check('看板标题没被改', stillOk[0] && stillOk[0].title !== '只读身份改的标题', stillOk[0] && stillOk[0].title);

  const shot2 = await cdp.send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: true });
  fs.writeFileSync(path.join(OUT, 'auth-readonly-1440.png'), Buffer.from(shot2.data, 'base64'));

  console.log('\n[7] 移动端 390px 截图');
  await cdp.send('Emulation.setDeviceMetricsOverride', { width: 390, height: 844, deviceScaleFactor: 1, mobile: true });
  await sleep(600);
  const mob = await evalq(`({
    overflow: document.documentElement.scrollWidth - innerWidth,
    idChipVisible: !!document.getElementById('kbIdBox').offsetParent,
    chipW: Math.round(document.getElementById('kbIdBox').getBoundingClientRect().width),
  })`);
  console.log('  ' + JSON.stringify(mob));
  check('390px 下无横向溢出', mob.overflow <= 0, 'overflow=' + mob.overflow);
  check('身份条在移动端可见', mob.idChipVisible === true);
  const shot3 = await cdp.send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: true });
  fs.writeFileSync(path.join(OUT, 'auth-390.png'), Buffer.from(shot3.data, 'base64'));

  console.log('\n[8] 控制台与网络错误');
  const errs = cdp.evs.filter(e => e.method === 'Runtime.exceptionThrown')
    .map(e => (e.params.exceptionDetails.exception || {}).description || e.params.exceptionDetails.text);
  const logs = cdp.evs.filter(e => e.method === 'Log.entryAdded' && e.params.entry.level === 'error')
    .map(e => e.params.entry.text);
  const failedReq = cdp.evs.filter(e => e.method === 'Network.loadingFailed')
    .map(e => e.params.errorText);
  check('无 JS 异常', errs.length === 0, errs.slice(0, 3).join(' | '));
  check('无 CORS / 网络失败', failedReq.length === 0, failedReq.slice(0, 3).join(' | '));
  if (logs.length) console.log('  console.error:', logs.slice(0, 4));

  console.log('\n[9] 清理测试看板');
  for (const p of ['/bk_cards?board_id=eq.' + m1.boardId, '/bk_boards?id=eq.' + m1.boardId]) {
    const r = await fetch(REST + p, { method: 'DELETE', headers: { Authorization: 'Bearer ' + m1.tokenA, Prefer: 'return=minimal' } });
    console.log('  DELETE', p.split('?')[0], '->', r.status);
  }

  chrome.kill();
  const passed = results.filter(Boolean).length;
  console.log('\n==== ' + passed + '/' + results.length + ' 项通过 ====');
  process.exit(passed === results.length ? 0 : 1);
})().catch(e => { console.error('ERR', e); process.exit(2); });
