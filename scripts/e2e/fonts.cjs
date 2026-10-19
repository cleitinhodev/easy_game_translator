'use strict'
// Seletor de fonte: abre o seletor, troca a família (via API do perfil), confere aplicação na janela principal e no Box,
// persistência, validação e que as fontes embutidas realmente carregaram (document.fonts). Salva PNGs em $EGT_SHOTS.
const fs = require('node:fs'); const path = require('node:path')
const OUT = process.env.EGT_SHOTS || 'screenshots'
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
const SAMPLE = 'Привет, мир! Ёлка · Γειά σου · 你好，世界！ · こんにちは、世界 · 안녕하세요 — The quick brown fox jumps over the lazy dog'
const BUNDLED = { nunito: 'Nunito', poppins: 'Poppins', atkinson: 'Atkinson Hyperlegible', pixel: 'Press Start 2P', orbitron: 'Orbitron', bangers: 'Bangers', inter: 'Inter Variable' }
module.exports = async ({ app, getMain, getBox, openBox, backend }) => {
  const main = getMain(); const wc = main.webContents
  const js = (c, w = wc) => w.executeJavaScript(c, true)
  const api = async (p, m = 'GET', b) => { const r = await backend.api(p, { method: m, body: b ? JSON.stringify(b) : undefined }); return { status: r.status, body: await r.json() } }
  const shot = async (w, n, d = 500) => { await sleep(d); fs.writeFileSync(path.join(OUT, n + '.png'), (await w.capturePage()).toPNG()) }
  const wait = async (cond, w = wc, ms = 8000) => { const t0 = Date.now(); while (Date.now() - t0 < ms) { if (await js(cond, w)) return true; await sleep(120) } return false }
  const rep = { checks: [] }
  const ok = (name, pass, extra) => { rep.checks.push({ name, pass: !!pass, ...(extra !== undefined ? { extra } : {}) }); console.log(pass ? 'PASS' : 'FAIL', name, extra ?? '') }
  const inject = (w) => js(`(() => { const s = window.__egt; const c = s.getState().channels.uni; s.setState({ channels: { ...s.getState().channels, uni: { ...c, original: 'Sample', translated: ${JSON.stringify(SAMPLE)}, rev: c.rev + 1, empty: false, pending: false, ok: true } } }) })()`, w)
  try {
    main.setSize(1280, 760); main.center(); await sleep(2500)
    await js(`document.querySelector('.intro')?.click()`); await sleep(1000)
    await api('/api/profile', 'PATCH', { target: 'pt', alphabet: 'abc(EN)' })
    await api('/api/profile/region', 'POST', { channel: 'uni', bbox: [100, 100, 760, 180] }); await sleep(800)
    await inject(wc); await sleep(600)

    // padrão: sem --tr-font (aparência idêntica à de antes)
    ok('default-no-var', await js(`document.documentElement.style.getPropertyValue('--tr-font') === ''`))
    ok('default-profile-field', (await api('/api/profile')).body.font_family === 'default')

    // seletor na barra, ao lado do controle de tamanho
    const near = await js(`(() => { const g = document.querySelector('.tb-row.options .opt-group.font-group'); return !!g && !!g.querySelector('.slider-wrap, input[type=range], [role=slider]') && !!g.querySelector('.font-select') })()`)
    ok('picker-next-to-size-slider', near)
    await js(`document.querySelector('.tb-row.options .font-group .font-select').click()`); await sleep(700)
    const opts = await js(`[...document.querySelectorAll('.select-menu [role=option]')].map(o => ({ t: o.innerText.replace(/\\s+/g,' ').trim(), ff: getComputedStyle(o.querySelector('.font-opt')).fontFamily.slice(0, 40) }))`)
    ok('14-options', opts.length === 14, opts.length)
    ok('options-preview-own-font', opts.filter((o) => o.ff).length === 14 && new Set(opts.map((o) => o.ff)).size >= 13, opts.map((o) => o.ff.split(',')[0]))
    await shot(wc, '80-font-picker-open', 300)
    // teclado: ↓ ↓ Enter escolhe a 3ª opção
    await js(`document.activeElement.blur?.(); document.querySelector('.tb-row.options .font-group .font-select').focus()`)
    await wc.sendInputEvent({ type: 'keyDown', keyCode: 'Down' }); await wc.sendInputEvent({ type: 'keyUp', keyCode: 'Down' })
    await sleep(200)
    await wc.sendInputEvent({ type: 'keyDown', keyCode: 'Return' }); await wc.sendInputEvent({ type: 'keyUp', keyCode: 'Return' })
    await sleep(900)
    const afterKey = (await api('/api/profile')).body.font_family
    ok('keyboard-select', afterKey === 'arial' || afterKey === 'verdana' || afterKey === 'georgia', afterKey)
    await js(`document.activeElement.blur()`)

    // cada família embutida carrega de verdade
    for (const [id, fam] of Object.entries(BUNDLED)) {
      await api('/api/profile', 'PATCH', { font_family: id })
      ok(`applied-${id}`, await wait(`document.documentElement.dataset.trFont === ${JSON.stringify(id)}`))
      await js(`document.fonts.load('16px "${fam}"', 'Aa Привет').then(() => true)`)
      ok(`font-loaded-${id}`, await js(`document.fonts.check('16px "${fam}"', 'Aa')  && [...document.fonts].some(f => f.family.replace(/"/g,'') === ${JSON.stringify(fam)} && f.status === 'loaded')`))
      const used = await js(`getComputedStyle(document.querySelector('.pane.translation .pane-text')).fontFamily`)
      ok(`translation-pane-uses-${id}`, used.replace(/"/g, '').startsWith(fam), used.slice(0, 50))
    }
    // validação do backend
    const bad = await api('/api/profile', 'PATCH', { font_family: 'x;}</style>' })
    ok('invalid-id-falls-back', bad.body.profile.font_family === 'default', bad.body.profile.font_family)

    // 3 fontes: janela principal + Box
    await openBox(); await sleep(2500)
    const boxWin = getBox(); boxWin.setBounds({ x: 100, y: 100, width: 780, height: 210 }); const box = boxWin.webContents
    const stack = {}
    for (const [id, tag] of [['nunito', '81'], ['pixel', '82'], ['bangers', '83']]) {
      await api('/api/profile', 'PATCH', { font_family: id })
      await wait(`document.documentElement.dataset.trFont === ${JSON.stringify(id)}`); await wait(`document.documentElement.dataset.trFont === ${JSON.stringify(id)}`, box)
      await inject(wc); await inject(box); await sleep(900)
      await shot(wc, `${tag}-main-${id}`, 600)
      const bf = await js(`getComputedStyle(document.querySelector('.box-text-wrap')).fontFamily + ' | ' + getComputedStyle(document.querySelector('.box-text-wrap')).fontSize`, box)
      stack[id] = bf
      ok(`box-uses-${id}`, bf.replace(/"/g, '').startsWith(BUNDLED[id]), bf.slice(0, 60))
      const fits = await js(`(() => { const w = document.querySelector('.box-text-wrap'); const f = w.parentElement; return w.scrollHeight <= f.clientHeight + 2 })()`, box)
      ok(`box-text-fits-${id}`, fits)
      await shot(box, `${tag}b-box-${id}`, 300)
    }
    // reabre a janela de configurações: seletor também nas Configurações > Geral
    await js(`window.__egt.getState().openDrawer('general')`); await sleep(900)
    ok('picker-in-settings', await js(`!!document.querySelector('.drawer .font-select') && !!document.querySelector('.font-preview')`))
    await shot(wc, '84-settings-font', 400)
    await api('/api/profile', 'PATCH', { font_family: 'default' })
    ok('back-to-default-clears-var', await wait(`document.documentElement.style.getPropertyValue('--tr-font') === ''`))
  } catch (e) { ok('exception', false, String(e && e.stack || e)) }
  fs.writeFileSync(path.join(OUT, 'fonts-report.json'), JSON.stringify(rep, null, 1))
  app.quit()
}
