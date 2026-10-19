'use strict'
// Menus suspensos (Select): em vários tamanhos de janela, zoom e RTL (árabe), abre cada menu da barra, das
// Configurações > Geral e do painel do Box e confere que o retângulo do popover fica 100% dentro da janela (margem 8 px),
// que não cobre o próprio botão, que a opção selecionada está visível e que fecha com Esc / blur. PNGs em $EGT_SHOTS.
const fs = require('node:fs'); const path = require('node:path')
const OUT = process.env.EGT_SHOTS || 'screenshots'
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
module.exports = async ({ app, getMain, getBox, openBox, backend }) => {
  const main = getMain(); const wc = main.webContents
  const js = (c, w = wc) => w.executeJavaScript(c, true)
  const api = async (p, m = 'GET', b) => { const r = await backend.api(p, { method: m, body: b ? JSON.stringify(b) : undefined }); return { status: r.status, body: await r.json() } }
  const shot = async (w, n, d = 300) => { await sleep(d); fs.writeFileSync(path.join(OUT, n + '.png'), (await w.capturePage()).toPNG()) }
  const wait = async (cond, w = wc, ms = 8000) => { const t0 = Date.now(); while (Date.now() - t0 < ms) { if (await js(cond, w)) return true; await sleep(120) } return false }
  const rep = { checks: [], menus: [] }
  const ok = (name, pass, extra) => { rep.checks.push({ name, pass: !!pass, ...(extra !== undefined ? { extra } : {}) }); if (!pass || process.env.VERBOSE) console.log(pass ? 'PASS' : 'FAIL', name, extra !== undefined ? JSON.stringify(extra) : '') }
  const setLang = async (l) => { await api('/api/settings', 'PATCH', { changes: { 'ui.language': l } }); await js(`window.egt.app.setLanguage(${JSON.stringify(l)})`); return wait(`document.documentElement.lang === ${JSON.stringify(l)}`) }
  // mede o menu aberto do i-ésimo .select dentro de `scope`
  const MEASURE = (scope, i) => `(async () => {
    const b = document.querySelectorAll(${JSON.stringify(scope)})[${i}]; if (!b) return null
    b.scrollIntoView({ block: 'nearest', inline: 'nearest' })
    b.click(); await new Promise(r => setTimeout(r, 650))
    const m = document.querySelector('.select-menu'); if (!m) return { missing: true }
    const r = m.getBoundingClientRect(), t = b.getBoundingClientRect(), vw = window.innerWidth, vh = window.innerHeight
    const sel = m.querySelector('[aria-selected=true]'); let selVis = true
    if (sel) { const s = sel.getBoundingClientRect(); selVis = s.top >= r.top - 1 && s.bottom <= r.bottom + 1 }
    const res = { label: (b.getAttribute('aria-label') || b.innerText).replace(/\\s+/g, ' ').trim().slice(0, 30), vw, vh,
      rect: [r.left, r.top, r.right, r.bottom].map(Math.round), trig: [t.left, t.top, t.right, t.bottom].map(Math.round),
      inside: r.left >= 7.5 && r.top >= 7.5 && r.right <= vw - 7.5 && r.bottom <= vh - 7.5,
      noCover: r.top >= t.bottom - 1 || r.bottom <= t.top + 1, flip: m.dataset.flip, scrolls: m.scrollHeight > m.clientHeight + 1, selVis,
      inBody: m.parentElement === document.body, fixed: getComputedStyle(m).position === 'fixed', n: m.querySelectorAll('[role=option]').length }
    return res })()`
  const close = async (w = wc) => { await w.sendInputEvent({ type: 'keyDown', keyCode: 'Escape' }); await w.sendInputEvent({ type: 'keyUp', keyCode: 'Escape' }); await sleep(250); return !(await js(`!!document.querySelector('.select-menu')`, w)) }
  const runScope = async (tag, scope, w = wc, shots = []) => {
    const n = await js(`document.querySelectorAll(${JSON.stringify(scope)}).length`, w)
    ok(`${tag}:has-selects`, n > 0, n)
    for (let i = 0; i < n; i++) {
      const visible = await js(`(() => { const b = document.querySelectorAll(${JSON.stringify(scope)})[${i}]; const r = b.getBoundingClientRect(); return r.width > 0 && r.height > 0 })()`, w)
      if (!visible) continue
      const m = await js(MEASURE(scope, i), w)
      if (!m || m.missing) { ok(`${tag}:#${i}:opened`, false, m); continue }
      rep.menus.push({ tag, i, ...m })
      ok(`${tag}:${m.label}:inside-viewport`, m.inside, { rect: m.rect, vw: m.vw, vh: m.vh })
      ok(`${tag}:${m.label}:not-covering-trigger`, m.noCover, { rect: m.rect, trig: m.trig })
      ok(`${tag}:${m.label}:selected-visible`, m.selVis)
      ok(`${tag}:${m.label}:portal-fixed`, m.inBody && m.fixed)
      if (shots.includes(i)) await shot(w, `${tag}-${i}`, 50)
      ok(`${tag}:${m.label}:esc-closes`, await close(w))
    }
  }
  try {
    await sleep(2500); await js(`document.querySelector('.intro')?.click()`); await sleep(1000)
    await setLang('pt-BR')
    await api('/api/profile/region', 'POST', { channel: 'uni', bbox: [100, 100, 760, 180] }); await sleep(500)
    const TB = '.toolbar .select, .tb-row .select'
    const sizes = [['800x500', 800, 500], ['min-940x640', 940, 640], ['1000x600', 1000, 600], ['1280x800', 1280, 800]]
    main.setMinimumSize(640, 420)
    const fontIdx = async () => js(`[...document.querySelectorAll(${JSON.stringify(TB)})].findIndex(b => b.classList.contains('font-select'))`)
    for (const lang of ['pt-BR', 'ar', 'de']) {
      await setLang(lang); await sleep(400)
      for (const [name, w, h] of sizes) {
        main.unmaximize(); main.setContentSize(w, h); main.center(); await sleep(700)
        const fi = await fontIdx()
        await runScope(`${lang}-${name}-toolbar`, TB, wc, lang !== 'de' && (name === '800x500' || name === '1000x600') ? [fi] : [])
      }
      main.maximize(); await sleep(900)
      await runScope(`${lang}-max-toolbar`, TB, wc, lang === 'ar' ? [await fontIdx()] : [])
      main.unmaximize(); await sleep(400)
    }
    // zoom (Ctrl +/-): o popover continua dentro
    await setLang('pt-BR'); main.setContentSize(1000, 600); main.center(); await sleep(500)
    for (const z of [1.25, 0.8]) { wc.setZoomFactor(z); await sleep(700); await runScope(`zoom${z}-toolbar`, TB, wc, z === 1.25 ? [await fontIdx()] : []) }
    wc.setZoomFactor(1); await sleep(400)

    // redimensionar com o menu aberto: reposiciona e continua dentro
    main.setContentSize(1280, 800); main.center(); await sleep(600)
    const fi = await fontIdx()
    await js(`document.querySelectorAll(${JSON.stringify(TB)})[${fi}].click()`); await sleep(600)
    main.setContentSize(800, 500); await sleep(900)
    const after = await js(`(() => { const m = document.querySelector('.select-menu'); if (!m) return null; const r = m.getBoundingClientRect(); return { open: true, inside: r.left >= 7.5 && r.top >= 7.5 && r.right <= innerWidth - 7.5 && r.bottom <= innerHeight - 7.5, rect: [r.left, r.top, r.right, r.bottom].map(Math.round), vw: innerWidth, vh: innerHeight } })()`)
    ok('resize-while-open:repositioned-inside', after && after.inside, after)
    await shot(wc, 'dd-resize-while-open', 100)
    // blur da janela fecha
    await js(`window.dispatchEvent(new Event('blur'))`); await sleep(400)
    ok('window-blur-closes', !(await js(`!!document.querySelector('.select-menu')`)))
    // teclado ainda funciona: ↓ abre, ↓ + Enter escolhe, menu fecha
    await js(`document.querySelectorAll(${JSON.stringify(TB)})[${fi}].focus()`)
    for (const k of ['Down', 'Down', 'Return']) { await wc.sendInputEvent({ type: 'keyDown', keyCode: k }); await wc.sendInputEvent({ type: 'keyUp', keyCode: k }); await sleep(250) }
    await sleep(600)
    ok('keyboard-select-still-works', (await api('/api/profile')).body.font_family !== 'default', (await api('/api/profile')).body.font_family)
    await api('/api/profile', 'PATCH', { font_family: 'default' })
    // movimento reduzido
    await api('/api/settings', 'PATCH', { changes: { 'ui.reduce_motion': 'on' } }); main.setContentSize(800, 500); await sleep(700)
    ok('reduced-motion-on', await wait(`document.documentElement.dataset.motion === 'reduce' || document.documentElement.dataset.motion === 'on'`, wc, 3000), await js(`document.documentElement.dataset.motion`))
    await runScope('reduced-motion-800x500-toolbar', TB)
    await api('/api/settings', 'PATCH', { changes: { 'ui.reduce_motion': 'system' } })

    // Configurações > Geral (idioma, fonte) em janela pequena, LTR e RTL
    for (const lang of ['pt-BR', 'ar']) {
      await setLang(lang); main.setContentSize(800, 500); main.center(); await sleep(500)
      await js(`window.__egt.getState().openDrawer('general')`); await sleep(1000)
      await runScope(`${lang}-800x500-settings`, '.drawer .select', wc, lang === 'ar' ? [0] : [1])
      await js(`window.__egt.getState().closeDrawer?.()`); await sleep(300)
      await wc.sendInputEvent({ type: 'keyDown', keyCode: 'Escape' }); await wc.sendInputEvent({ type: 'keyUp', keyCode: 'Escape' }); await sleep(600)
    }
    await setLang('pt-BR')

    // painel do Box: janelas pequenas
    await openBox(); await sleep(2500)
    const boxWin = getBox(); const box = boxWin.webContents
    for (const [bw, bh] of [[780, 210], [420, 300], [320, 520]]) {
      boxWin.setBounds({ x: 120, y: 120, width: bw, height: bh }); await sleep(700)
      const opened = await js(`(async () => { if (!document.querySelector('.box-panel')) { document.querySelector('.box-root')?.dispatchEvent(new MouseEvent('mouseover', { bubbles: true })); await new Promise(r => setTimeout(r, 300)); const g = [...document.querySelectorAll('button[aria-label]')].find(b => b.querySelector('svg') && b.closest('.box-bar, .box-top, .box-root') && /config|control|contr/i.test(b.getAttribute('aria-label'))); g?.click(); await new Promise(r => setTimeout(r, 700)) } return !!document.querySelector('.box-panel') })()`, box)
      ok(`box-${bw}x${bh}:panel-open`, opened)
      if (opened) await runScope(`box-${bw}x${bh}`, '.box-panel .select', box, [0])
    }
  } catch (e) { ok('exception', false, String(e && e.stack || e)) }
  const fails = rep.checks.filter((c) => !c.pass)
  console.log(`DROPDOWNS ${rep.checks.length - fails.length}/${rep.checks.length} passed, menus measured: ${rep.menus.length}`)
  fs.writeFileSync(path.join(OUT, 'dropdowns-report.json'), JSON.stringify(rep, null, 1))
  app.quit()
}
