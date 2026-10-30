/* 通过 CDP 精确控制 Chrome：设置视口 → 导航 → 量测布局 → 截图 */
const { spawn } = require('child_process');
const fs = require('fs');
const path = require('path');

const CHROME = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const PORT = 9333;
const URL_ = process.argv[2] || 'http://localhost:5173/index.html?code=4ZX99GZL';
const OUTDIR = path.join(__dirname, '..', 'shots');
const sleep = ms => new Promise(r => setTimeout(r, ms));

async function jget(u) {
  const r = await fetch(u);
  return r.json();
}

class CDP {
  constructor(ws) { this.ws = ws; this.id = 0; this.pend = new Map(); this.evs = [];
    ws.addEventListener('message', e => {
      const m = JSON.parse(e.data);
      if (m.id && this.pend.has(m.id)) { const { res, rej } = this.pend.get(m.id); this.pend.delete(m.id);
        m.error ? rej(new Error(JSON.stringify(m.error))) : res(m.result); }
      else if (m.method) this.evs.push(m);
    });
  }
  send(method, params = {}) {
    const id = ++this.id;
    return new Promise((res, rej) => { this.pend.set(id, { res, rej }); this.ws.send(JSON.stringify({ id, method, params })); });
  }
}

(async () => {
  const userDir = path.join(require('os').tmpdir(), 'cdp-profile-' + Date.now());
  const chrome = spawn(CHROME, [
    '--headless=new', '--disable-gpu', '--hide-scrollbars', '--mute-audio',
    '--no-first-run', '--no-default-browser-check',
    '--remote-debugging-port=' + PORT, '--user-data-dir=' + userDir,
    'about:blank',
  ], { stdio: 'ignore' });

  // 等 DevTools 端口就绪
  let ver = null;
  for (let i = 0; i < 60; i++) {
    try { ver = await jget('http://127.0.0.1:' + PORT + '/json/version'); break; } catch (e) { await sleep(300); }
  }
  if (!ver) { console.error('DevTools 未就绪'); process.exit(2); }

  const tgt = await (await fetch('http://127.0.0.1:' + PORT + '/json/new?about:blank', { method: 'PUT' })).json();
  const ws = new WebSocket(tgt.webSocketDebuggerUrl);
  await new Promise(r => ws.addEventListener('open', r));
  const cdp = new CDP(ws);
  await cdp.send('Page.enable');
  await cdp.send('Runtime.enable');
  await cdp.send('Console.enable');

  const VIEWPORTS = [
    { name: 'v1440', width: 1440, height: 1000, mobile: false },
    { name: 'v1024', width: 1024, height: 1000, mobile: false },
    { name: 'v768',  width: 768,  height: 1000, mobile: false },
    { name: 'v390',  width: 390,  height: 844,  mobile: true  },
  ];

  const report = [];
  for (const vp of VIEWPORTS) {
    await cdp.send('Emulation.setDeviceMetricsOverride', {
      width: vp.width, height: vp.height, deviceScaleFactor: 1, mobile: vp.mobile,
    });
    await cdp.send('Page.navigate', { url: URL_ });
    await sleep(4500);   // 等 boot + 渲染

    const expr = `(() => {
      const de = document.documentElement, b = document.body;
      const r = s => { const e = document.querySelector(s); if(!e) return null;
        const x = e.getBoundingClientRect(); return {w:+x.width.toFixed(1), l:+x.left.toFixed(1), r:+x.right.toFixed(1)}; };
      const cols = [...document.querySelectorAll('.kb-col')].map(e => {
        const x = e.getBoundingClientRect(); return {l:+x.left.toFixed(1), r:+x.right.toFixed(1), w:+x.width.toFixed(1)};
      });
      return {
        innerWidth: innerWidth,
        docScrollWidth: de.scrollWidth,
        bodyScrollWidth: b.scrollWidth,
        horizontalOverflow: de.scrollWidth - innerWidth,
        boardScrollWidth: (document.getElementById('kbBoard')||{}).scrollWidth,
        boardClientWidth: (document.getElementById('kbBoard')||{}).clientWidth,
        colCount: cols.length,
        firstCol: cols[0], lastCol: cols[cols.length-1],
        colsInsideViewport: cols.filter(c => c.r <= innerWidth + 0.5).length,
        nav: r('nav'), navScrollWidth: (document.querySelector('nav')||{}).scrollWidth,
        tabs: [...document.querySelectorAll('nav button')].map(e => Math.round(e.getBoundingClientRect().width)),
        cardCount: document.querySelectorAll('.kb-card').length,
        title: document.querySelector('#boardTitle') ? document.querySelector('#boardTitle').value : null,
        share: document.querySelector('#shareCode') ? document.querySelector('#shareCode').textContent : null,
        status: document.querySelector('#kbStatus') ? document.querySelector('#kbStatus').textContent : null,
        errorCard: !!document.querySelector('#btnRetry'),
      };
    })()`;
    const res = await cdp.send('Runtime.evaluate', { expression: expr, returnByValue: true });
    const m = res.result.value;
    report.push({ vp: vp.name, m });

    const shot = await cdp.send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: true });
    fs.writeFileSync(path.join(OUTDIR, vp.name + '.png'), Buffer.from(shot.data, 'base64'));
    console.log(vp.name, JSON.stringify(m));
  }

  // 收集控制台错误
  const errs = cdp.evs.filter(e => e.method === 'Runtime.exceptionThrown')
    .map(e => e.params.exceptionDetails.text + ' ' + (e.params.exceptionDetails.exception||{}).description);
  console.log('\n控制台异常:', errs.length ? errs.slice(0, 5) : '无');

  fs.writeFileSync(path.join(OUTDIR, 'layout-report.json'), JSON.stringify(report, null, 2));
  chrome.kill();
  process.exit(0);
})().catch(e => { console.error('ERR', e); process.exit(1); });
