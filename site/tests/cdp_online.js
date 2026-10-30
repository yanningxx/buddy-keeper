/* 对线上地址做端到端验证：遇到平台「确定访问」门禁则模拟点击，再量测渲染与控制台错误 */
const { spawn } = require('child_process');
const fs = require('fs');
const path = require('path');
const os = require('os');

const CHROME = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const PORT = 9334;
const TARGET = process.argv[2];
const TAG = process.argv[3] || 'online';
const OUT = path.join(__dirname, '..', 'shots');
const sleep = ms => new Promise(r => setTimeout(r, ms));

class CDP {
  constructor(ws) { this.ws = ws; this.id = 0; this.pend = new Map(); this.evs = [];
    ws.addEventListener('message', e => {
      const m = JSON.parse(e.data);
      if (m.id && this.pend.has(m.id)) { const { res, rej } = this.pend.get(m.id); this.pend.delete(m.id);
        m.error ? rej(new Error(JSON.stringify(m.error))) : res(m.result); }
      else if (m.method) this.evs.push(m);
    });
  }
  send(method, params = {}) { const id = ++this.id;
    return new Promise((res, rej) => { this.pend.set(id, { res, rej }); this.ws.send(JSON.stringify({ id, method, params })); });
  }
}

(async () => {
  const profile = path.join(os.tmpdir(), 'cdp2-' + Date.now());
  const chrome = spawn(CHROME, ['--headless=new', '--disable-gpu', '--hide-scrollbars', '--mute-audio',
    '--no-first-run', '--remote-debugging-port=' + PORT, '--user-data-dir=' + profile, 'about:blank'], { stdio: 'ignore' });

  let ok = null;
  for (let i = 0; i < 60; i++) { try { ok = await (await fetch(`http://127.0.0.1:${PORT}/json/version`)).json(); break; } catch (e) { await sleep(300); } }
  const tgt = await (await fetch(`http://127.0.0.1:${PORT}/json/new?about:blank`, { method: 'PUT' })).json();
  const ws = new WebSocket(tgt.webSocketDebuggerUrl);
  await new Promise(r => ws.addEventListener('open', r));
  const cdp = new CDP(ws);
  await cdp.send('Page.enable'); await cdp.send('Runtime.enable'); await cdp.send('Log.enable');
  await cdp.send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 1000, deviceScaleFactor: 1, mobile: false });

  await cdp.send('Page.navigate', { url: TARGET });
  await sleep(3500);

  const evalq = async (expr) => (await cdp.send('Runtime.evaluate', { expression: expr, returnByValue: true, awaitPromise: true })).result.value;

  let gate = await evalq('!!document.getElementById("submitBtn")');
  console.log('平台门禁页:', gate ? '出现' : '未出现');
  if (gate) {
    const btnText = await evalq('document.getElementById("submitBtn").textContent');
    console.log('按钮文案:', btnText);
    // 等倒计时结束再点
    for (let i = 0; i < 20; i++) {
      const disabled = await evalq('document.getElementById("submitBtn").disabled');
      if (!disabled) break; await sleep(500);
    }
    await evalq('document.getElementById("submitBtn").click()');
    await sleep(4000);
    gate = await evalq('!!document.getElementById("submitBtn")');
    console.log('点击后仍在门禁页:', gate);
  }

  const m = await evalq(`(() => ({
    url: location.href,
    title: document.title,
    tab: document.body.dataset.tab,
    hasBoard: !!(window.KB && window.KB.board),
    boardTitle: window.KB && window.KB.board ? window.KB.board.title : null,
    share: document.getElementById('shareCode') ? document.getElementById('shareCode').textContent : null,
    status: document.getElementById('kbStatus') ? document.getElementById('kbStatus').textContent : null,
    cardCount: document.querySelectorAll('.kb-card').length,
    colCount: document.querySelectorAll('.kb-col').length,
    errorCard: !!document.getElementById('btnRetry'),
    overflow: document.documentElement.scrollWidth - innerWidth,
  }))()`);
  console.log(JSON.stringify(m, null, 2));

  const errs = cdp.evs.filter(e => e.method === 'Runtime.exceptionThrown')
    .map(e => (e.params.exceptionDetails.exception || {}).description || e.params.exceptionDetails.text);
  const logs = cdp.evs.filter(e => e.method === 'Log.entryAdded' && e.params.entry.level === 'error')
    .map(e => e.params.entry.text + ' ' + (e.params.entry.url || ''));
  console.log('JS 异常:', errs.length ? errs.slice(0, 4) : '无');
  console.log('网络/资源错误:', logs.length ? logs.slice(0, 6) : '无');

  const shot = await cdp.send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: true });
  fs.writeFileSync(path.join(OUT, TAG + '.png'), Buffer.from(shot.data, 'base64'));
  chrome.kill();
  process.exit(0);
})().catch(e => { console.error('ERR', e); process.exit(1); });
