'use strict'
// Box Mode em vários tamanhos de janela (canal único e dual) para conferir o ajuste automático da fonte.
const fs = require('node:fs'); const path = require('node:path')
const OUT = process.env.EGT_SHOTS || 'screenshots'
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
module.exports = async ({ app, getMain, getBox, openBox, backend }) => {
  const api = (p, m = 'GET', b) => backend.api(p, { method: m, body: b ? JSON.stringify(b) : undefined })
  const rep = []
  try {
    await sleep(2500)
    getMain().webContents.executeJavaScript(`document.querySelector('.intro')?.click()`)
    await api('/api/profile', 'PATCH', { ocr_engine: 'rapidocr', target: 'pt' })
    await api('/api/profile/region', 'POST', { channel: 'uni', bbox: [100, 100, 760, 180] })
    await api('/api/pipeline/start', 'POST')
    await openBox(); await sleep(9000)
    const box = getBox()
    const fs_ = () => box.webContents.executeJavaScript(`[...document.querySelectorAll('.box-text-wrap')].map(e=>e.style.fontSize)`)
    const take = async (name, w, h) => {
      box.setBounds({ x: 60, y: 60, width: w, height: h }); await sleep(1100)
      fs.writeFileSync(path.join(OUT, name + '.png'), (await box.webContents.capturePage()).toPNG())
      rep.push({ name, w, h, fonts: await fs_() })
    }
    await take('30-box-single-760x190', 760, 190)
    await take('31-box-single-1100x300', 1100, 300)
    await take('32-box-single-420x110', 420, 110)
    await api('/api/profile', 'PATCH', { mode: 'dual' })
    await api('/api/profile/region', 'POST', { channel: 'a', bbox: [100, 220, 560, 160] }).catch(() => {})
    await api('/api/profile/region', 'POST', { channel: 'b', bbox: [100, 340, 560, 160] }).catch(() => {})
    await sleep(9000)
    await take('33-box-dual-900x200', 900, 200)
    await take('34-box-dual-1300x320', 1300, 320)
  } catch (e) { rep.push({ error: String(e && e.stack || e) }) }
  fs.writeFileSync(path.join(OUT, 'box-report.json'), JSON.stringify(rep, null, 2))
  app.quit()
}
