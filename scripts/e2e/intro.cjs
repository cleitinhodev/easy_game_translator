'use strict'
// Intro: só termina quando o áudio chega ao fim ('ended'); com erro/travado usa o temporizador; limite máximo de segurança.
const fs = require('node:fs'); const path = require('node:path')
const OUT = process.env.EGT_SHOTS || 'screenshots'
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
module.exports = async ({ app, getMain, backend }) => {
  const wc = getMain().webContents
  const js = (c) => wc.executeJavaScript(c, true)
  const api = (p, m = 'GET', b) => backend.api(p, { method: m, body: b ? JSON.stringify(b) : undefined })
  const rep = []
  // áudio falso configurável
  const fake = (kind, extra = '') => `(() => {
    const ls = {}; let cur = 0
    const a = { volume: 1, duration: 7.057, get currentTime() { return cur }, set currentTime(v) { cur = v },
      addEventListener(t, f) { (ls[t] = ls[t] || []).push(f) }, removeEventListener(t, f) { ls[t] = (ls[t] || []).filter(x => x !== f) }, pause() {},
      play() { const emit = (t) => (ls[t] || []).slice().forEach(f => f())
        ${kind === 'ended' ? `setTimeout(() => emit('loadedmetadata'), 20); setInterval(() => { cur += 0.1 }, 100); setTimeout(() => emit('ended'), 1500); return Promise.resolve()` : ''}
        ${kind === 'reject' ? `return Promise.reject(new DOMException('no audio device', 'NotAllowedError'))` : ''}
        ${kind === 'error' ? `setTimeout(() => emit('error'), 500); return Promise.resolve()` : ''}
        ${kind === 'stalled' ? `return Promise.resolve()` : ''}
        ${kind === 'hang' ? `setInterval(() => { cur += 0.1 }, 100); return Promise.resolve()` : ''}
      } }
    return a })`
  const run = async (name, kind, opts, maxMs = 15000) => {
    await js(`document.querySelector('.intro')?.click()`); await sleep(900)
    await js(`window.__EGT_INTRO_TEST = ${kind ? `{ create: ${fake(kind)}, ${opts || ''} }` : 'undefined'}; 0`)
    const t0 = Date.now()
    await js(`window.dispatchEvent(new Event('egt:play-intro'))`)
    await sleep(250)
    let stillShownAt1s = null; let gone = false
    while (Date.now() - t0 < maxMs) {
      const shown = await js(`!!document.querySelector('.intro')`)
      if (!stillShownAt1s && Date.now() - t0 > 900) stillShownAt1s = shown
      if (!shown && Date.now() - t0 > 400) { gone = true; break }
      await sleep(100)
    }
    const log = await js(`window.__introLog`)
    rep.push({ name, hiddenAfterMs: Date.now() - t0, gone, stillShownAt1s, log })
    if (name === 'A-ended') fs.writeFileSync(path.join(OUT, '50-intro.png'), (await wc.capturePage()).toPNG())
  }
  try {
    await sleep(3000)
    await js(`document.querySelector('.intro')?.click()`); await sleep(1500)
    await run('A-ended', 'ended')
    await run('B-play-rejected', 'reject', 'knownMs: 2000, marginMs: 300')
    await run('C-error-event', 'error', 'knownMs: 2000, marginMs: 300')
    await run('D-stalled', 'stalled', 'knownMs: 2500, marginMs: 300, stallMs: 600')
    await run('E-hard-timeout', 'hang', 'knownMs: 1500, hardExtraMs: 800')
    await run('F-real-audio', null, null, 20000)
    await js(`window.__egt.getState().patchSettings({ 'ui.intro_full': false }); 0`)
    await sleep(500)
    await run('G-short-mode', null, null, 8000)
  } catch (e) { rep.push({ error: String(e && e.stack || e) }) }
  fs.writeFileSync(path.join(OUT, 'intro-report.json'), JSON.stringify(rep, null, 1))
  app.quit()
}
