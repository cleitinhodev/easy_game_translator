module.exports = async ({ app, getMain, backend }) => {
  const main = getMain()
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
  main.webContents.on('console-message', (_e, level, msg, line, src) => console.log('[renderer]', level, msg, src + ':' + line))
  await sleep(3000)
  console.log('[dbg]', await main.webContents.executeJavaScript(`JSON.stringify({ws: performance.getEntriesByType('resource').filter(r=>/ws|api/.test(r.name)).map(r=>r.name).slice(0,5), egt: !!window.egt})`))
  console.log('[wsprobe]', await main.webContents.executeJavaScript(`(async()=>{ const c = await window.egt.getConfig(); return await new Promise(res=>{ const ws = new WebSocket('ws://127.0.0.1:'+c.port+'/ws?token='+c.token); const t=setTimeout(()=>res('timeout'),3000); ws.onopen=()=>{console.log('open')}; ws.onmessage=(m)=>{clearTimeout(t);res('msg '+m.data.slice(0,60))}; ws.onclose=(e)=>{clearTimeout(t);res('close '+e.code)}; ws.onerror=()=>console.log('error') })})()`))
  const rr = await backend.api('/api/profile/region', { method: 'POST', body: JSON.stringify({ channel: 'uni', bbox: [100,100,760,180] }) })
  console.log('[post]', rr.status, (await rr.text()).slice(0,200))
  await sleep(1500)
  console.log('[dbg2]', await main.webContents.executeJavaScript(`JSON.stringify({p: window.__egt.getState().profile, conn: window.__egt.getState().conn, html: document.querySelector('.regions')?.innerHTML.slice(0,300)})`))
  setTimeout(() => app.quit(), 300)
}
