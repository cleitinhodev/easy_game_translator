'use strict'
// Intro 4.0.6: as luzes giram até o fim da música e a logo cresce devagar (1,0 → ~1,07). Quadros em ~1 s, 4 s e 6,5 s,
// medindo o ângulo da órbita e a escala da logo; depois o mesmo com "reduzir movimento" (sem rotação, escala mínima).
const fs = require('node:fs'); const path = require('node:path')
const OUT = process.env.EGT_SHOTS || 'screenshots'
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
module.exports = async ({ app, getMain, backend }) => {
  const wc = getMain().webContents
  const js = (c) => wc.executeJavaScript(c, true)
  const api = (p, m = 'GET', b) => backend.api(p, { method: m, body: b ? JSON.stringify(b) : undefined })
  const rep = { frames: [], checks: [] }
  const ok = (name, pass, extra) => { rep.checks.push({ name, pass: !!pass, extra }); console.log(pass ? 'PASS' : 'FAIL', name, JSON.stringify(extra ?? '')) }
  const MEASURE = `(() => {
    const ang = (el) => { if (!el) return null; const m = new DOMMatrix(getComputedStyle(el).transform); return Math.round(Math.atan2(m.b, m.a) * 1800 / Math.PI) / 10 }
    const sc = (el) => { if (!el) return null; const m = new DOMMatrix(getComputedStyle(el).transform); return Math.round(Math.hypot(m.a, m.b) * 1000) / 1000 }
    return { shown: !!document.querySelector('.intro'), orbit: ang(document.querySelector('.intro-orbit')), glow: ang(document.querySelector('.intro-glow')),
             grow: sc(document.querySelector('.intro-grow')), halo: Number(getComputedStyle(document.querySelector('.intro-halo') || document.body).opacity) }
  })()`
  const play = async () => {
    await js(`document.querySelector('.intro')?.click()`); await sleep(900)
    // áudio que "toca" e termina em 7,06 s (como o bemvindo.mp3), sem depender de placa de som no xvfb
    await js(`window.__EGT_INTRO_TEST = { create: () => { const ls = {}; let cur = 0; const emit = (t) => (ls[t] || []).slice().forEach(f => f())
      return { volume: 1, duration: 7.06, get currentTime() { return cur }, set currentTime(v) { cur = v }, pause() {},
        addEventListener(t, f) { (ls[t] = ls[t] || []).push(f) }, removeEventListener(t, f) { ls[t] = (ls[t] || []).filter(x => x !== f) },
        play() { setTimeout(() => emit('loadedmetadata'), 10); const t0 = performance.now(); const iv = setInterval(() => { cur = (performance.now() - t0) / 1000; if (cur >= 7.06) { clearInterval(iv); emit('ended') } }, 50); return Promise.resolve() } } } }; 0`)
    const t0 = Date.now()
    await js(`window.dispatchEvent(new Event('egt:play-intro'))`)
    return t0
  }
  try {
    await sleep(3000)
    await js(`document.querySelector('.intro')?.click()`); await sleep(1200)
    let t0 = await play()
    for (const at of [1000, 4000, 6500]) {
      await sleep(Math.max(0, at - (Date.now() - t0)))
      const m = await js(MEASURE); const real = Date.now() - t0
      fs.writeFileSync(path.join(OUT, `intro-${(at / 1000).toFixed(1)}s.png`), (await wc.capturePage()).toPNG())
      rep.frames.push({ at, real, ...m })
    }
    let gone = null
    while (Date.now() - t0 < 12000) { if (!(await js(`!!document.querySelector('.intro')`))) { gone = Date.now() - t0; break } await sleep(100) }
    const [f1, f4, f6] = rep.frames
    ok('shown-at-6.5s', f6.shown, f6)
    ok('orbit-still-rotating-4s-to-6.5s', f4.orbit !== null && f6.orbit !== null && Math.abs(f6.orbit - f4.orbit) > 5, [f4.orbit, f6.orbit])
    ok('glow-still-rotating-4s-to-6.5s', f4.glow !== null && f6.glow !== null && Math.abs(f6.glow - f4.glow) > 5, [f4.glow, f6.glow])
    ok('logo-grows', f1.grow >= 1 && f4.grow > f1.grow && f6.grow > f4.grow && f6.grow <= 1.08, [f1.grow, f4.grow, f6.grow])
    ok('ends-after-music', gone !== null && gone >= 7000 && gone < 9500, gone)
    // movimento reduzido
    await api('/api/settings', 'PATCH', { changes: { 'ui.reduce_motion': 'on' } }); await sleep(800)
    t0 = await play(); await sleep(2000)
    const r1 = await js(MEASURE); await sleep(1500); const r2 = await js(MEASURE)
    fs.writeFileSync(path.join(OUT, 'intro-reduced.png'), (await wc.capturePage()).toPNG())
    rep.reduced = [r1, r2]
    ok('reduced:no-rotation', r1.orbit === r2.orbit && r1.glow === r2.glow, [r1.orbit, r2.orbit, r1.glow, r2.glow])
    ok('reduced:minimal-scale', r1.grow <= 1.02 && r1.grow === r2.grow, [r1.grow, r2.grow])
    await js(`document.querySelector('.intro')?.click()`); await sleep(900)
    ok('skip-works', !(await js(`!!document.querySelector('.intro')`)))
  } catch (e) { rep.checks.push({ name: 'error', pass: false, extra: String(e && e.stack || e) }); console.log('ERROR', e) }
  rep.failed = rep.checks.filter((c) => !c.pass).map((c) => c.name)
  fs.writeFileSync(path.join(OUT, 'introframes-report.json'), JSON.stringify(rep, null, 1))
  app.quit()
}
