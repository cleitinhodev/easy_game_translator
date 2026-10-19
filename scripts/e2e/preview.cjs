'use strict'
// Miniatura do painel "Original": deve mudar junto com o texto (canal único, dual e refresh forçado).
const fs = require('node:fs'); const path = require('node:path')
const OUT = process.env.EGT_SHOTS || 'screenshots'
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
module.exports = async ({ app, getMain, backend }) => {
  const main = getMain(); const wc = main.webContents
  const js = (c) => wc.executeJavaScript(c, true)
  const api = (p, m = 'GET', b) => backend.api(p, { method: m, body: b ? JSON.stringify(b) : undefined })
  const shot = async (n) => fs.writeFileSync(path.join(OUT, n + '.png'), (await wc.capturePage()).toPNG())
  const rep = []
  const snap = (ch = 0) => js(`(() => { const imgs=[...document.querySelectorAll('.thumb img')]; const i=imgs[${ch}]; const t=[...document.querySelectorAll('.pane-text')].map(e=>e.textContent); return { n: imgs.length, len: i ? i.src.length : 0, sig: i ? i.src.slice(-60) : '', texts: t } })()`)
  try {
    main.setSize(1280, 800); await sleep(2500)
    await js(`document.querySelector('.intro')?.click()`); await sleep(1200)
    await api('/api/profile', 'PATCH', { ocr_engine: 'rapidocr', target: 'pt', mode: 'single' })
    await api('/api/profile/region', 'POST', { channel: 'uni', bbox: [100, 100, 760, 120] })
    await api('/api/pipeline/start', 'POST')
    await sleep(3500); await shot('40-preview-t1'); const a = await snap(); rep.push({ at: 't1', ...a })
    // espera a legenda sintética mudar (período 3 s) e confere que a miniatura mudou junto
    let b
    for (let i = 0; i < 12; i++) { await sleep(1000); b = await snap(); if (b.sig !== a.sig) break }
    await sleep(1200); b = await snap()
    await shot('41-preview-t2'); rep.push({ at: 't2', ...b, previewChanged: b.sig !== a.sig, textChanged: JSON.stringify(b.texts) !== JSON.stringify(a.texts) })
    // refresh forçado (troca de idioma): a miniatura continua presente e atual
    await js(`window.__egt.getState().patchProfile({ target: 'en' })`); await sleep(1500)
    const c = await snap(); rep.push({ at: 'after-target-change', ...c })
    // dual
    await api('/api/pipeline/stop', 'POST')
    await api('/api/profile', 'PATCH', { mode: 'dual' })
    await api('/api/profile/region', 'POST', { channel: 'a', bbox: [100, 220, 760, 90] })
    await api('/api/profile/region', 'POST', { channel: 'b', bbox: [100, 340, 760, 90] })
    await sleep(600); await api('/api/pipeline/start', 'POST'); await sleep(4500)
    await shot('42-preview-dual-t1'); const d1 = [await snap(0), await snap(1)]
    let d2
    for (let i = 0; i < 12; i++) { await sleep(1000); d2 = [await snap(0), await snap(1)]; if (d2[0].sig !== d1[0].sig && d2[1].sig !== d1[1].sig) break }
    await sleep(1200); d2 = [await snap(0), await snap(1)]
    await shot('43-preview-dual-t2')
    rep.push({ at: 'dual', thumbs: d2[0].n, aChanged: d2[0].sig !== d1[0].sig, bChanged: d2[1].sig !== d1[1].sig })
    await api('/api/pipeline/stop', 'POST')
  } catch (e) { rep.push({ error: String(e && e.stack || e) }) }
  fs.writeFileSync(path.join(OUT, 'preview-report.json'), JSON.stringify(rep, null, 2))
  app.quit()
}
