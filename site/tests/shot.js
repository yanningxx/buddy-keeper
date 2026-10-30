/* 通用截图：node _shot.js <url> <outName> [width] [height] */
const { spawn } = require('child_process');
const fs = require('fs'); const path = require('path'); const os = require('os');
const CHROME = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const PORT = 9335 + Math.floor(Math.random() * 200);
const [url, name, w = '1440', h = '1000'] = process.argv.slice(2);
const sleep = ms => new Promise(r => setTimeout(r, ms));
class CDP { constructor(ws){this.ws=ws;this.id=0;this.pend=new Map();
  ws.addEventListener('message',e=>{const m=JSON.parse(e.data);
    if(m.id&&this.pend.has(m.id)){const{res,rej}=this.pend.get(m.id);this.pend.delete(m.id);m.error?rej(new Error(JSON.stringify(m.error))):res(m.result);}});}
  send(method,params={}){const id=++this.id;return new Promise((res,rej)=>{this.pend.set(id,{res,rej});this.ws.send(JSON.stringify({id,method,params}));});}}
(async()=>{
  const profile = path.join(os.tmpdir(),'shot-'+Date.now());
  const ch = spawn(CHROME,['--headless=new','--disable-gpu','--hide-scrollbars','--mute-audio',
    '--remote-debugging-port='+PORT,'--user-data-dir='+profile,'about:blank'],{stdio:'ignore'});
  for(let i=0;i<60;i++){try{await (await fetch(`http://127.0.0.1:${PORT}/json/version`)).json();break;}catch(e){await sleep(300);}}
  const t = await (await fetch(`http://127.0.0.1:${PORT}/json/new?about:blank`,{method:'PUT'})).json();
  const ws = new WebSocket(t.webSocketDebuggerUrl);
  await new Promise(r=>ws.addEventListener('open',r));
  const cdp = new CDP(ws);
  await cdp.send('Page.enable'); await cdp.send('Runtime.enable');
  await cdp.send('Emulation.setDeviceMetricsOverride',{width:+w,height:+h,deviceScaleFactor:1,mobile:+w<640});
  await cdp.send('Page.navigate',{url});
  await sleep(4000);
  // 若遇平台门禁则点掉
  const g = await cdp.send('Runtime.evaluate',{expression:'!!document.getElementById("submitBtn")',returnByValue:true});
  if(g.result.value){
    for(let i=0;i<20;i++){
      const d = await cdp.send('Runtime.evaluate',{expression:'document.getElementById("submitBtn").disabled',returnByValue:true});
      if(!d.result.value) break; await sleep(500);
    }
    await cdp.send('Runtime.evaluate',{expression:'document.getElementById("submitBtn").click()'});
    await sleep(4000);
  }
  const shot = await cdp.send('Page.captureScreenshot',{format:'png',captureBeyondViewport:true});
  fs.writeFileSync(path.join(__dirname,'shots',name+'.png'), Buffer.from(shot.data,'base64'));
  const info = await cdp.send('Runtime.evaluate',{expression:'JSON.stringify({title:document.title,h1:(document.querySelector("h1")||{}).textContent,tabs:[...document.querySelectorAll("nav button")].map(b=>b.textContent),overflow:document.documentElement.scrollWidth-innerWidth})',returnByValue:true});
  console.log(name, info.result.value);
  ch.kill(); process.exit(0);
})().catch(e=>{console.error(e);process.exit(1);});
