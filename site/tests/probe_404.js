/* 查清线上页面到底哪个请求返回 404。只抓 Network.responseReceived 里 status>=400 的记录。 */
const { spawn } = require('child_process');
const path = require('path');
const os = require('os');

const CHROME = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const PORT = 9341;
const TARGET = process.argv[2] || 'https://kanban-board-xuyanning-d2g5ejg513e3c8e1d.webapps.tcloudbase.com/?code=4ZX99GZL';
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

(async () => {
  const profile = path.join(os.tmpdir(), 'cdp404-' + Date.now());
  const chrome = spawn(CHROME, ['--headless=new', '--disable-gpu', '--no-first-run', '--mute-audio',
    '--remote-debugging-port=' + PORT, '--user-data-dir=' + profile, 'about:blank'], { stdio: 'ignore' });
  let ver = null;
  for (let i = 0; i < 60; i++) {
    try { ver = await (await fetch(`http://127.0.0.1:${PORT}/json/version`)).json(); break; } catch (e) { await sleep(300); }
  }
  const tgt = await (await fetch(`http://127.0.0.1:${PORT}/json/new?about:blank`, { method: 'PUT' })).json();
  const ws = new WebSocket(tgt.webSocketDebuggerUrl);
  await new Promise((r) => ws.addEventListener('open', r));
  let id = 0; const pend = new Map(); const bad = []; const all = [];
  ws.addEventListener('message', (e) => {
    const m = JSON.parse(e.data);
    if (m.id && pend.has(m.id)) { const { res } = pend.get(m.id); pend.delete(m.id); res(m.result); return; }
    if (m.method === 'Network.responseReceived') {
      const r = m.params.response;
      all.push(m.params.type + ' ' + r.status + ' ' + r.url);
      if (r.status >= 400) bad.push({ type: m.params.type, status: r.status, url: r.url, mime: r.mimeType });
    }
  });
  const send = (method, params = {}) => new Promise((res) => { const i = ++id; pend.set(i, { res }); ws.send(JSON.stringify({ id: i, method, params })); });

  await send('Network.enable');
  await send('Page.enable');
  await send('Page.navigate', { url: TARGET });
  await sleep(9000);

  console.log('总请求 ' + all.length + ' 条');
  all.forEach((x) => console.log('  ' + x));
  console.log('\n>=400 的请求 ' + bad.length + ' 条');
  bad.forEach((b) => console.log('  [' + b.type + '] ' + b.status + ' ' + b.url + '  mime=' + b.mime));
  process.exit(0);
})();
