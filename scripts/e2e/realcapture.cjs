'use strict'
// Captura REAL (sem EGT_DEMO): abre uma janela com uma "legenda" na tela do X (xvfb), seleciona essa região,
// inicia o pipeline com o RapidOCR e confere que o texto lido é o que está na tela. Rode SEM EGT_DEMO:
//   EGT_DEMO=0 bash scripts/e2e/run.sh realcapture.cjs        (EGT_OCR=tesseract para testar o Tesseract)
const fs = require('node:fs'); const path = require('node:path')
const OUT = process.env.EGT_SHOTS || 'screenshots'
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
module.exports = async ({ app, getMain, backend }) => {
  const main = getMain(); const wc = main.webContents
  const js = (c) => wc.executeJavaScript(c, true)
  const api = async (p, m = 'GET', b) => { const r = await backend.api(p, { method: m, body: b ? JSON.stringify(b) : undefined }); return r.json() }
  const rep = { checks: [] }
  const ok = (name, pass, extra) => { rep.checks.push({ name, pass: !!pass, extra }); console.log(pass ? 'PASS' : 'FAIL', name, extra !== undefined ? JSON.stringify(extra) : '') }
  try {
    main.setBounds({ x: 0, y: 0, width: 1100, height: 720 }); await sleep(2500)
    await js(`document.querySelector('.intro')?.click()`); await sleep(1200)
    await api('/api/settings', 'PATCH', { changes: { 'ui.language': 'en' } }); await js(`window.egt.app.setLanguage('en')`); await sleep(800)
    await api('/api/profile', 'PATCH', { ocr_engine: process.env.EGT_OCR || 'rapidocr', alphabet: 'abc(EN)', target: 'pt' })
    // uma "legenda de jogo" numa janela separada, em posição conhecida da tela do X
    const { BrowserWindow } = require('electron')
    const SUB = 'Take this key. It opens the old cellar door.'
    const game = new BrowserWindow({ x: 60, y: 780, width: 900, height: 120, frame: false, show: true, webPreferences: { sandbox: true } })
    await game.loadURL('data:text/html;charset=utf-8,' + encodeURIComponent(`<body style="margin:0;background:#141428;color:#f2f2f2;font:600 34px DejaVu Sans,Arial,sans-serif;display:flex;align-items:center;padding-left:24px;height:120px">${SUB}</body>`))
    await sleep(1200)
    const gb = game.getContentBounds()
    ok('game-window-shown', gb.width > 0, gb)
    const bbox = [gb.x, gb.y, gb.x + gb.width, gb.y + gb.height]
    await api('/api/profile/region', 'POST', { channel: 'uni', bbox }); await sleep(800)
    await api('/api/pipeline/start', 'POST'); await sleep(500)
    let txt = '', tr = ''
    for (let i = 0; i < 90 && !/cellar/i.test(txt); i++) { await sleep(500); txt = await js(`window.__egt.getState().channels.uni.original || ''`) }
    for (let i = 0; i < 30 && !tr; i++) { await sleep(500); tr = await js(`window.__egt.getState().channels.uni.translated || ''`) }
    ok('real-capture-ocr-reads-screen', /take this key.*cellar door/i.test(txt.replace(/\\s+/g, ' ')), { bbox, txt })
    ok('translation-arrived (online)', !!tr, tr)
    fs.writeFileSync(path.join(OUT, 'realcapture.png'), (await wc.capturePage()).toPNG())
    await api('/api/pipeline/stop', 'POST')
  } catch (e) { ok('exception', false, String(e && e.stack || e)) }
  fs.writeFileSync(path.join(OUT, 'realcapture-report.json'), JSON.stringify(rep, null, 1))
  app.quit()
}
