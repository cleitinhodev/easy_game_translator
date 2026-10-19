'use strict'
// Só o Box Mode: abre, aguarda uma tradução e salva 18-box.png (e 18b com o painel de controles).
const fs = require('node:fs'); const path = require('node:path')
const OUT = process.env.EGT_SHOTS || 'screenshots'
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
module.exports = async ({ app, getMain, getBox, openBox, backend }) => {
  const api = (p, m = 'GET', b) => backend.api(p, { method: m, body: b ? JSON.stringify(b) : undefined })
  await sleep(2500)
  getMain().webContents.executeJavaScript(`document.querySelector('.intro')?.click()`)
  await api('/api/profile', 'PATCH', { ocr_engine: 'rapidocr', target: 'pt' })
  await api('/api/profile/region', 'POST', { channel: 'uni', bbox: [100, 100, 760, 180] })
  await api('/api/pipeline/start', 'POST')
  await openBox(); await sleep(9000)
  const box = getBox(); box.setBounds({ x: 120, y: 120, width: 760, height: 190 })
  await sleep(600)
  const save = async (n) => fs.writeFileSync(path.join(OUT, n + '.png'), (await box.webContents.capturePage()).toPNG())
  await save('18-box')
  await box.webContents.executeJavaScript(`document.querySelector('.box-card')?.dispatchEvent(new MouseEvent('mouseenter',{bubbles:true})); document.querySelector('.box-card')?.dispatchEvent(new MouseEvent('mousemove',{bubbles:true}))`)
  await sleep(700); await save('18b-box-hover')
  app.quit()
}
