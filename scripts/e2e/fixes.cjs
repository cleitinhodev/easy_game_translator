'use strict'
// Verifica: (1) botões de fechar longe da zona dos controles nativos da janela; (2) estado "Traduzindo…" ao trocar o idioma.
const fs = require('node:fs'); const path = require('node:path')
const OUT = process.env.EGT_SHOTS || 'screenshots'
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
module.exports = async ({ app, getMain, backend }) => {
  const main = getMain(); const wc = main.webContents
  const js = (c) => wc.executeJavaScript(c, true)
  const api = (p, m = 'GET', b) => backend.api(p, { method: m, body: b ? JSON.stringify(b) : undefined })
  const shot = async (n, d = 500) => { await sleep(d); fs.writeFileSync(path.join(OUT, n + '.png'), (await wc.capturePage()).toPNG()) }
  const results = []
  try {
    main.setSize(1280, 800); main.center(); await sleep(2500)
    await js(`document.querySelector('.intro')?.click()`); await sleep(1500)
    // zona reservada aos botões nativos do Windows (titleBarOverlay): 148px à direita × altura da barra
    const zone = await js(`({ w: 148, h: parseInt(getComputedStyle(document.documentElement).getPropertyValue('--titlebar-h')) || 44, W: innerWidth })`)
    const check = async (name, open, closeSel) => {
      await js(open); await sleep(900)
      const r = await js(`(() => { const e = document.querySelector(${JSON.stringify(closeSel)}); if (!e) return null; const b = e.getBoundingClientRect(); return { x: b.x, y: b.y, w: b.width, h: b.height } })()`)
      const hit = r && (r.x + r.w > zone.W - zone.w) && (r.y < zone.h)
      const dist = r ? Math.round(Math.min(zone.W - (r.x + r.w), 9999)) : null
      results.push({ name, rect: r, overlapsWindowControls: !!hit, distanceFromRightEdge: dist, distanceFromTop: r && Math.round(r.y) })
      await shot(name)
      await js(`document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}))`); await sleep(500)
    }
    const clickBtn = (t) => `(() => { const b=[...document.querySelectorAll('button')].find(x=>(x.getAttribute('aria-label')||'').includes(${JSON.stringify(t)})||x.textContent.trim()===${JSON.stringify(t)}); b&&b.click() })()`
    await check('20-close-settings', clickBtn('Opções'), '.drawer-nav .close-btn')
    await check('21-close-manual', clickBtn('Manual'), '.modal-head .close-left')
    await check('22-close-help', clickBtn('Ajuda'), '.modal-head .close-left')
    // Esc fecha?
    await js(clickBtn('Opções')); await sleep(700)
    await js(`document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}))`); await sleep(600)
    results.push({ name: 'esc-closes-drawer', ok: !(await js(`!!document.querySelector('.drawer')`)) })
    // "Traduzindo…" ao trocar o idioma com a captura estática
    await api('/api/profile', 'PATCH', { ocr_engine: 'rapidocr', target: 'pt' })
    await api('/api/profile/region', 'POST', { channel: 'uni', bbox: [100, 100, 760, 180] })
    await api('/api/pipeline/start', 'POST'); await sleep(6000)
    const before = await js(`document.querySelector('.pane.translation .pane-text')?.textContent`)
    await js(`window.__egt.getState().patchProfile({ target: 'es' })`)
    await sleep(30); const pend = await js(`!!document.querySelector('.pane.translation .chip .spinner')`)
    await shot('23-translating', 0)
    await sleep(2500)
    const after = await js(`document.querySelector('.pane.translation .pane-text')?.textContent`)
    results.push({ name: 'retranslate-ui', before, after, sawTranslatingChip: pend, stillPending: await js(`!!document.querySelector('.pane.translation .chip .spinner')`) })
    await shot('24-translated-en')
    await api('/api/pipeline/stop', 'POST')
  } catch (e) { results.push({ error: String(e && e.stack || e) }) }
  fs.writeFileSync(path.join(OUT, 'fixes-report.json'), JSON.stringify(results, null, 2))
  console.log('[report]', JSON.stringify(results))
  app.quit()
}
