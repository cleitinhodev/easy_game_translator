'use strict'
// 4.0.9: verificação automática na intro (cartões online/offline), MyMemory primeiro e a aba Scripts
// (aviso, contrato, confirmação com SHA-256, teste canal único/duplo, saída do script no painel da direita,
// arquivo alterado → pede confirmação de novo, desligar volta aos tradutores). Scripts em pasta neutra (/tmp/egt-scripts).
const fs = require('node:fs'); const path = require('node:path')
const OUT = process.env.EGT_SHOTS || 'screenshots'
const SDIR = '/tmp/egt-scripts'
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
module.exports = async ({ app, getMain, backend }) => {
  const main = getMain(); const wc = main.webContents
  const js = (c) => wc.executeJavaScript(c, true)
  const api = async (p, m = 'GET', b) => { const r = await backend.api(p, { method: m, body: b ? JSON.stringify(b) : undefined }); return { status: r.status, body: await r.json() } }
  const shot = async (n, d = 400) => { await sleep(d); fs.writeFileSync(path.join(OUT, n + '.png'), (await wc.capturePage()).toPNG()) }
  const wait = async (cond, ms = 10000) => { const t0 = Date.now(); while (Date.now() - t0 < ms) { if (await js(cond)) return true; await sleep(150) } return false }
  const rep = { checks: [] }
  const ok = (name, pass, extra) => { rep.checks.push({ name, pass: !!pass, ...(extra !== undefined ? { extra } : {}) }); console.log(pass ? 'PASS' : 'FAIL', name, extra !== undefined ? JSON.stringify(extra).slice(0, 300) : '') }
  const tid = (id) => `document.querySelector('[data-testid=${id}]')`
  const clickT = (id) => js(`(() => { const e = ${tid(id)}; if (!e) return false; e.click(); return true })()`)
  const btn = (txt) => js(`(() => { const b = [...document.querySelectorAll('[data-testid=sc-page] [role=radio]')].find(x => (x.textContent||'').trim() === ${JSON.stringify(txt)}); if (!b) return false; b.click(); return true })()`)
  const drawer = async (tab) => { await js(`window.__egt.getState().openDrawer(${JSON.stringify(tab)}); 0`); await sleep(700) }
  const closeDrawer = async () => { await js(`window.__egt.getState().closeDrawer ? window.__egt.getState().closeDrawer() : document.querySelector('.drawer-layer .scrim')?.dispatchEvent(new MouseEvent('mousedown',{bubbles:true})); 0`); await sleep(700) }
  const right = (sel = '.pane.translation .pane-text') => js(`[...document.querySelectorAll(${JSON.stringify(sel)})].map(e => e.innerText.trim())`)
  try {
    fs.rmSync(SDIR, { recursive: true, force: true }); fs.mkdirSync(SDIR, { recursive: true })
    for (const f of ['mymemory_tradutor.py', 'glossario_offline.js', 'modelo_basico.py']) fs.copyFileSync(path.join(__dirname, '../../examples/scripts', f), path.join(SDIR, f))
    main.setSize(1280, 860)
    // intro com a linha "Verificando tradutores…"
    await sleep(900)
    const introLine = await js(`document.querySelector('.intro-check')?.innerText || ''`)
    await shot('sc-00-intro-autocheck', 100)
    ok('intro:autocheck-line', /Verificando tradutores/.test(introLine), introLine)
    await api('/api/settings', 'PATCH', { changes: { 'ui.language': 'pt-BR', 'ui.typewriter': false } }); await js(`window.egt.app.setLanguage('pt-BR')`)
    // espera a verificação terminar
    let ac = null; const t0 = Date.now()
    while (Date.now() - t0 < 30000) { ac = (await api('/api/translation/autocheck')).body; if (ac && ['done', 'skipped', 'error'].includes(ac.state)) break; await sleep(400) }
    rep.autocheck = ac
    ok('autocheck:finished', ac && ac.state === 'done', ac && { state: ac.state, passed: ac.passed, failed: ac.failed, activated: ac.activated })
    await sleep(1500); await js(`document.querySelector('.intro')?.click()`); await sleep(1200)
    const eng = (await api('/api/translation/engines')).body
    rep.engines = eng.map((e) => ({ id: e.id, enabled: e.enabled, probe: e.probe ? { ok: e.probe.ok, ms: e.probe.ms, auto: e.probe.auto } : null }))
    ok('order:mymemory-first', eng[0].id === 'mymemory', eng.map((e) => e.id).slice(0, 4))
    const passed = eng.filter((e) => e.probe && e.probe.ok).map((e) => e.id)
    ok('autocheck:passed-are-enabled', passed.every((id) => eng.find((e) => e.id === id).enabled), passed)
    rep.passed = passed
    await drawer('translation')
    await wait(`document.querySelectorAll('[data-testid^=tr-card-]').length === 14`)
    ok('tr:autocheck-line', await wait(`!!${tid('tr-autocheck')}`), await js(`${tid('tr-autocheck')}?.innerText || ''`))
    ok('tr:queue-note', await js(`document.body.innerText.includes('Fila')`))
    await js(`document.querySelector('.drawer-body')?.scrollTo?.(0, 0); 0`)
    await shot('sc-01-tradutores-autocheck', 600)

    // aba Scripts
    await drawer('scripts')
    ok('sc:tab', await wait(`!!${tid('sc-page')}`))
    const warn = await js(`${tid('sc-warning')}?.innerText || ''`)
    ok('sc:warning', /Atenção/.test(warn) && /confia/.test(warn), warn.slice(0, 160))
    ok('sc:contract', /Recebe uma ou duas entradas em string e retorna uma ou duas saídas em string/.test(await js(`${tid('sc-contract')}?.innerText || ''`)))
    ok('sc:mode-translators', /Tradutores/.test(await js(`${tid('sc-mode')}.innerText`)), await js(`${tid('sc-mode')}.innerText`))
    await shot('sc-02-scripts-aba')
    await js(`${tid('sc-contract')}.scrollIntoView({ block: 'start' }); 0`); await shot('sc-03-contrato')
    await js(`document.querySelector('[data-testid=sc-ex-glossario_offline\\\\.js]')?.scrollIntoView({ block: 'center' }); 0`); await shot('sc-04-exemplos')

    const useScript = async (file, tag) => {
      global.__egtPickFile = path.join(SDIR, file)
      await drawer('scripts')
      await js(`document.querySelector('.drawer-body')?.scrollTo?.(0, 0); 0`)
      await clickT('sc-choose')
      ok(`${tag}:confirm-dialog`, await wait(`!!${tid('sc-confirm')}`))
      const sha = await js(`${tid('sc-confirm-sha')}?.innerText || ''`)
      ok(`${tag}:confirm-sha`, /^[0-9a-f]{64}$/.test(sha.trim()), sha)
      ok(`${tag}:ok-disabled-without-trust`, await js(`${tid('sc-confirm-ok')}.disabled === true`))
      await shot(`${tag}-01-confirmar`)
      await clickT('sc-trust'); await sleep(200); await clickT('sc-confirm-ok')
      ok(`${tag}:approved`, await wait(`!!${tid('sc-file')}`))
      const s = (await api('/api/settings')).body
      ok(`${tag}:enabled-exclusive`, s.script.enabled === true && s.ai.mode === 'off', { script: s.script.enabled, ai: s.ai.mode })
      ok(`${tag}:mode-script`, /Script/.test(await js(`${tid('sc-mode')}.innerText`)))
      await shot(`${tag}-02-escolhido`)
      // teste canal único
      await js(`${tid('sc-test')}.scrollIntoView({ block: 'center' }); 0`)
      await clickT('sc-test')
      await wait(`!!(${tid('sc-test-out')} || ${tid('sc-test-err')})`, 20000)
      const o1 = await js(`(${tid('sc-test-out')} || ${tid('sc-test-err')})?.innerText || ''`)
      ok(`${tag}:test-single`, !!(await js(`!!${tid('sc-test-out')}`)), o1)
      await shot(`${tag}-03-teste-unico`)
      await btn('Canal duplo'); await sleep(300)
      await clickT('sc-test'); await sleep(400)
      await wait(`(${tid('sc-test-out')}?.querySelectorAll('.sc-out').length || 0) === 2 || !!${tid('sc-test-err')}`, 20000)
      const o2 = await js(`(${tid('sc-test-out')} || ${tid('sc-test-err')})?.innerText || ''`)
      ok(`${tag}:test-dual`, (await js(`${tid('sc-test-out')}?.querySelectorAll('.sc-out').length || 0`)) === 2, o2)
      await shot(`${tag}-04-teste-duplo`)
      await btn('Canal único'); await sleep(200)
      await closeDrawer()
      // captura real (modo demonstração) → saída do script no painel da direita
      await api('/api/profile', 'PATCH', { mode: 'single', ocr_engine: 'rapidocr', target: 'pt', source: 'en' })
      await api('/api/profile/region', 'POST', { channel: 'uni', bbox: [100, 220, 760, 300] })
      await sleep(600)
      await api('/api/pipeline/start', 'POST')
      await wait(`[...document.querySelectorAll('.pane.translation .pane-text')].some(e => e.innerText.trim().length > 3)`, 25000)
      await sleep(9000)   // passa de um ciclo da demonstração (o painel não fica com a saída do script anterior)
      const r1 = await right(); ok(`${tag}:right-pane-single`, r1.some((x) => x.length > 3), r1)
      const engChip = await js(`document.querySelector('.pane.translation .pane-meta')?.innerText || ''`)
      ok(`${tag}:engine-chip`, /Script/.test(engChip), engChip)
      await shot(`${tag}-05-painel-unico`, 300)
      await api('/api/pipeline/stop', 'POST')
      await api('/api/profile', 'PATCH', { mode: 'dual' })
      await api('/api/profile/region', 'POST', { channel: 'a', bbox: [100, 220, 760, 300] })
      await api('/api/profile/region', 'POST', { channel: 'b', bbox: [100, 340, 760, 420] })
      await sleep(600)
      await api('/api/pipeline/start', 'POST')
      await wait(`[...document.querySelectorAll('.pane.translation .pane-text')].filter(e => e.innerText.trim().length > 3).length >= 2`, 25000)
      await sleep(9000)
      const r2 = await right(); ok(`${tag}:right-pane-dual`, r2.filter((x) => x.length > 3).length >= 2, r2)
      await shot(`${tag}-06-painel-duplo`, 300)
      await api('/api/pipeline/stop', 'POST')
      await api('/api/profile', 'PATCH', { mode: 'single' })
      rep[tag] = { test_single: o1, test_dual: o2, right_single: r1, right_dual: r2 }
      await sleep(500)
    }
    await useScript('mymemory_tradutor.py', 'py')
    await useScript('glossario_offline.js', 'js')
    ok('js:glossary-pt', (rep.js.right_single || []).concat(rep.js.right_dual || []).every((x) => /O rei|Pegue|Precisamos|Cuidado|Você encontrou|Mira|Dax|Player42|Alguém/.test(x)), rep.js)

    // arquivo muda → bloqueia e pede confirmação de novo
    fs.appendFileSync(path.join(SDIR, 'glossario_offline.js'), '\n// alterado\n')
    await drawer('scripts')
    await js(`window.__egt.getState().openDrawer('general'); 0`); await sleep(400); await drawer('scripts')
    ok('hash:changed-banner', await wait(`!!${tid('sc-changed')}`, 8000))
    const tr = (await api('/api/script/test', 'POST', { inputs: ['Hello'] })).body
    ok('hash:test-blocked', tr && tr.ok === false && tr.code === 'hash_changed', tr)
    await js(`document.querySelector('.drawer-body')?.scrollTo?.(0, 0); 0`)
    await shot('sc-05-arquivo-alterado')
    await clickT('sc-reconfirm')
    ok('hash:reconfirm-dialog', await wait(`!!${tid('sc-confirm')}`))
    await shot('sc-06-reconfirmar')
    await clickT('sc-trust'); await sleep(150); await clickT('sc-confirm-ok')
    ok('hash:reapproved', await wait(`!${tid('sc-changed')} && !!${tid('sc-file')}`))
    // IA liga → script desliga
    await api('/api/settings', 'PATCH', { changes: { 'ai.mode': 'ollama' } })
    let s = (await api('/api/settings')).body
    ok('exclusive:ai-turns-script-off', s.script.enabled === false, { script: s.script.enabled, ai: s.ai.mode })
    await api('/api/settings', 'PATCH', { changes: { 'ai.mode': 'off' } })
    await drawer('translation'); await sleep(300)
    ok('tr:no-script-banner', await js(`!${tid('tr-script-banner')}`))
    // liga de novo pelo switch e vê o banner nos Tradutores
    await api('/api/settings', 'PATCH', { changes: { 'script.enabled': true } })
    await drawer('translation'); await sleep(500)
    ok('tr:script-banner', await wait(`!!${tid('tr-script-banner')}`))
    await js(`document.querySelector('.drawer-body')?.scrollTo?.(0, 0); 0`)
    await shot('sc-07-tradutores-com-script')
    await api('/api/settings', 'PATCH', { changes: { 'script.enabled': false } })
    s = (await api('/api/settings')).body
    ok('off:back-to-translators', s.script.enabled === false)
    // nada pessoal nas telas: caminhos neutros
    const body = await js(`document.body.innerText`)
    ok('privacy:no-home-path', !/\/home\/|\\Users\\/.test(body))
  } catch (e) { rep.checks.push({ name: 'error', pass: false, extra: String(e && e.stack || e) }); console.log('ERROR', e) }
  rep.failed = rep.checks.filter((c) => !c.pass).map((c) => c.name)
  fs.writeFileSync(path.join(OUT, 'scripts-report.json'), JSON.stringify(rep, null, 1))
  app.quit()
}
