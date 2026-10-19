'use strict'
// Idiomas da interface: troca de idioma ao vivo, RTL, detecção automática, estouro de texto e screenshots (principal, Geral, Atualizações).
// LANGS="ja ar ru zh-CN hi th de vi" para escolher quais; salva PNGs em $EGT_SHOTS e locales-report.json.
const fs = require('node:fs'); const path = require('node:path')
const OUT = process.env.EGT_SHOTS || 'screenshots'
const LANGS = (process.env.LANGS || 'ja ar ru zh-CN hi th de vi').split(/\s+/).filter(Boolean)
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
module.exports = async ({ app, getMain, backend }) => {
  const main = getMain(); const wc = main.webContents
  const js = (c) => wc.executeJavaScript(c, true)
  const api = async (p, m = 'GET', b) => { const r = await backend.api(p, { method: m, body: b ? JSON.stringify(b) : undefined }); return { status: r.status, body: await r.json() } }
  const shot = async (n, d = 500) => { await sleep(d); fs.writeFileSync(path.join(OUT, n + '.png'), (await wc.capturePage()).toPNG()) }
  const wait = async (cond, ms = 8000) => { const t0 = Date.now(); while (Date.now() - t0 < ms) { if (await js(cond)) return true; await sleep(120) } return false }
  const rep = { checks: [], overflow: {} }
  const ok = (name, pass, extra) => { rep.checks.push({ name, pass: !!pass, ...(extra !== undefined ? { extra } : {}) }); console.log(pass ? 'PASS' : 'FAIL', name, extra ?? '') }
  const setLang = async (l) => { await api('/api/settings', 'PATCH', { changes: { 'ui.language': l } }); await js(`window.egt.app.setLanguage(${JSON.stringify(l)})`); return wait(`document.documentElement.lang === ${JSON.stringify(l)}`) }
  // textos cortados (overflow) nas regiões principais
  const overflowJs = `(() => {
    const out = []; const W = innerWidth
    for (const el of document.querySelectorAll('.titlebar *, .toolbar *, .tb-row *, .statusbar *, .drawer *, .modal *')) {
      const cs = getComputedStyle(el); if (cs.display === 'none' || !el.textContent.trim() || el.children.length > 2) continue
      const r = el.getBoundingClientRect(); if (!r.width) continue
      const clipped = el.scrollWidth > el.clientWidth + 2 && (cs.overflow !== 'visible' || cs.overflowX !== 'visible')
      const ell = clipped && cs.textOverflow === 'ellipsis'
      const off = r.right > W + 2 || r.left < -2
      if ((clipped && !ell && !el.closest('.pane-text')) || off) out.push({ cls: el.className && el.className.toString().slice(0, 40), t: el.textContent.trim().slice(0, 40), clipped, off })
    }
    return out.slice(0, 12)
  })()`
  try {
    main.setSize(1280, 800); main.center(); await sleep(2500)
    await js(`document.querySelector('.intro')?.click()`); await sleep(1000)
    await api('/api/profile', 'PATCH', { target: 'pt', alphabet: 'abc(EN)' }); await api('/api/profile/region', 'POST', { channel: 'uni', bbox: [100, 100, 760, 180] }); await sleep(600)
    await js(`(() => { const s = window.__egt; const c = s.getState().channels.uni; s.setState({ channels: { ...s.getState().channels, uni: { ...c, original: 'Press START to continue your adventure', translated: 'Pressione START para continuar sua aventura · Привет · こんにちは · 你好', rev: c.rev + 1, empty: false, pending: false, ok: true, engine: 'demo', ms: 120 } } }) })()`)
    // padrão = auto; sem sistema em pt → inglês (xvfb: en-US) ou o idioma do sistema
    const st = (await api('/api/settings')).body
    ok('default-language-auto', (st.ui || st.settings?.ui || {}).language === 'auto', (st.ui || st.settings?.ui || {}).language)
    // regras de correspondência: renderer == main
    const util = require(path.join(process.cwd(), 'electron/util.cjs'))
    const cases = { 'pt-PT': 'pt-BR', 'pt': 'pt-BR', 'es-MX': 'es', 'en-GB': 'en', 'zh-Hant-TW': 'zh-TW', 'zh-HK': 'zh-TW', 'zh-CN': 'zh-CN', 'zh': 'zh-CN', 'ar-SA': 'ar', 'ja-JP': 'ja', 'nb-NO': null, 'xx': null, 'uk-UA': 'uk', 'hi-IN': 'hi' }
    let allMain = true, allRend = true
    for (const [tag, want] of Object.entries(cases)) {
      if ((util.matchLocale(tag) ?? null) !== want) { allMain = false; console.log('main mismatch', tag, util.matchLocale(tag)) }
      const r = await js(`window.__egtResolve('auto', [${JSON.stringify(tag)}])`)
      if (r !== (want ?? 'en')) { allRend = false; console.log('renderer mismatch', tag, r) }
    }
    ok('match-rules-main', allMain); ok('match-rules-renderer', allRend)
    ok('fallback-english', (await js(`window.__egtResolve('auto', ['xx-YY','nb'])`)) === 'en')
    ok('explicit-wins', (await js(`window.__egtResolve('de', ['ja-JP'])`)) === 'de')
    ok('tray-main-follows-language', util.makeT('ja')('menu.quit') !== util.makeT('en')('menu.quit'))
    const nLoc = util.LOCALES.length; ok('20-locales', nLoc === 20, nLoc)

    for (const l of LANGS) {
      ok(`switch-${l}`, await setLang(l)); await sleep(700)
      const dir = await js(`document.documentElement.dir`)
      ok(`dir-${l}`, dir === (l === 'ar' ? 'rtl' : 'ltr'), dir)
      rep.overflow[l] = { main: await js(overflowJs) }
      await js(`window.__egt.getState().closeDrawer?.()`); await sleep(300)
      await shot(`90-main-${l}`)
      await js(`window.__egt.getState().openDrawer('general')`); await sleep(900)
      rep.overflow[l].general = await js(overflowJs)
      await shot(`91-general-${l}`, 300)
      await js(`window.__egt.getState().openDrawer('updates')`); await sleep(1800)
      rep.overflow[l].updates = await js(overflowJs)
      await shot(`92-updates-${l}`, 300)
      await js(`window.__egt.getState().closeDrawer?.()`); await sleep(400)
    }
    await setLang('pt-BR'); await api('/api/settings', 'PATCH', { changes: { 'ui.language': 'auto' } })
  } catch (e) { ok('exception', false, String(e && e.stack || e)) }
  fs.writeFileSync(path.join(OUT, 'locales-report.json'), JSON.stringify(rep, null, 1))
  app.quit()
}
