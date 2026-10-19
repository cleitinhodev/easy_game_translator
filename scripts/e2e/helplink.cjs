'use strict'
// Janela de Ajuda: o botão "Doar" tem de abrir https://www.bugzinho.com/donate via app:open-external (shell.openExternal). Em E2E a chamada só é registrada.
const fs = require('node:fs'); const path = require('node:path')
const OUT = process.env.EGT_SHOTS || 'screenshots'
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
module.exports = async ({ app, getMain }) => {
  const wc = getMain().webContents; const js = (c) => wc.executeJavaScript(c, true)
  const rep = { checks: [] }; const ok = (n, p, e) => { rep.checks.push({ name: n, pass: !!p, ...(e !== undefined ? { extra: e } : {}) }); console.log(p ? 'PASS' : 'FAIL', n, e ?? '') }
  try {
    getMain().setSize(1100, 760); await sleep(2500); await js(`document.querySelector('.intro')?.click()`); await sleep(900)
    global.__egtExternal = []
    await js(`window.__egt.getState().setModal('help')`); await sleep(1200)
    const label = await js(`document.querySelector('.link-btn.don')?.innerText`)
    ok('donate-button-present', !!label, label)
    fs.writeFileSync(path.join(OUT, '95-help.png'), (await wc.capturePage()).toPNG())
    await js(`document.querySelector('.link-btn.don').click()`); await sleep(500)
    ok('donate-opens-new-url', global.__egtExternal.includes('https://www.bugzinho.com/donate'), global.__egtExternal)
    ok('only-one-call', global.__egtExternal.length === 1)
    // os outros links continuam funcionando
    for (const id of ['site', 'yt', 'pat']) { global.__egtExternal.length = 0; await js(`document.querySelector('.link-btn.${id}')?.click()`); await sleep(300); ok(`link-${id}-https`, global.__egtExternal.length === 1 && /^https:\/\//.test(global.__egtExternal[0]), global.__egtExternal) }
    // URL não-https é recusada pelo IPC
    global.__egtExternal.length = 0; await js(`window.egt.app.openExternal('http://example.com'); window.egt.app.openExternal('file:///etc/passwd')`); await sleep(300)
    ok('non-https-rejected', global.__egtExternal.length === 0)
  } catch (e) { ok('exception', false, String(e && e.stack || e)) }
  fs.writeFileSync(path.join(OUT, 'helplink-report.json'), JSON.stringify(rep, null, 1)); app.quit()
}
