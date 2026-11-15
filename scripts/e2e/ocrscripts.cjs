'use strict'
// 4.1 beta: Script de OCR na aba OCR — seletor exclusivo (motores do app × meu script), aviso, contrato,
// confirmação com SHA-256, teste canal único/duplo com miniatura, captura real (modo demonstração) no
// canal único e duplo com miniaturas e painel da direita, arquivo alterado → reconfirmar, voltar aos motores
// do app (RapidOCR/Tesseract continuam lendo) e script de tradução + script de OCR juntos.
// Scripts numa pasta neutra (/tmp/egt-scripts-ocr) para não aparecer caminho pessoal nas telas.
const fs = require('node:fs'); const path = require('node:path')
const OUT = process.env.EGT_SHOTS || 'screenshots'
const SDIR = '/tmp/egt-scripts-ocr'
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
module.exports = async ({ getMain, backend, app }) => {
  const main = getMain(); const wc = main.webContents
  const js = (c) => wc.executeJavaScript(c, true)
  const api = async (p, m = 'GET', b) => { const r = await backend.api(p, { method: m, body: b ? JSON.stringify(b) : undefined }); let body = null; try { body = await r.json() } catch { /* sem corpo */ } return { status: r.status, body } }
  const shot = async (n, d = 400) => { await sleep(d); fs.writeFileSync(path.join(OUT, n + '.png'), (await wc.capturePage()).toPNG()) }
  const wait = async (cond, ms = 10000) => { const t0 = Date.now(); while (Date.now() - t0 < ms) { if (await js(cond)) return true; await sleep(150) } return false }
  const rep = { checks: [] }
  const ok = (name, pass, extra) => { rep.checks.push({ name, pass: !!pass, ...(extra !== undefined ? { extra } : {}) }); console.log(pass ? 'PASS' : 'FAIL', name, extra !== undefined ? JSON.stringify(extra).slice(0, 300) : '') }
  const tid = (id) => `document.querySelector('[data-testid="${id}"]')`
  const clickT = (id) => js(`(() => { const e = ${tid(id)}; if (!e) return false; e.click(); return true })()`)
  const radio = (scope, txt) => js(`(() => { const b = [...document.querySelectorAll('${scope} [role=radio]')].find(x => (x.textContent||'').trim().startsWith(${JSON.stringify(txt)})); if (!b) return false; b.click(); return true })()`)
  const drawer = async (tab) => { await js(`window.__egt.getState().openDrawer(${JSON.stringify(tab)}); 0`); await sleep(700) }
  const closeDrawer = async () => { await js(`window.__egt.getState().closeDrawer ? window.__egt.getState().closeDrawer() : document.querySelector('.drawer-layer .scrim')?.dispatchEvent(new MouseEvent('mousedown',{bubbles:true})); 0`); await sleep(700) }
  const panes = (k) => js(`[...document.querySelectorAll('.pane.${k} .pane-text')].map(e => e.innerText.trim())`)
  const thumbs = () => js(`[...document.querySelectorAll('.pane.original .thumb img')].map(i => ({ w: i.naturalWidth, h: i.naturalHeight, src: i.src.slice(0, 22) }))`)
  const top = () => js(`document.querySelector('.drawer-body')?.scrollTo?.(0, 0); 0`)
  const into = (id, block = 'start') => js(`${tid(id)}?.scrollIntoView({ block: '${block}' }); 0`)
  const stopAll = async () => { await api('/api/pipeline/stop', 'POST'); await sleep(600) }
  const runPipe = async (mode, tag, wantRe) => {
    await api('/api/profile', 'PATCH', { mode })
    if (mode === 'single') await api('/api/profile/region', 'POST', { channel: 'uni', bbox: [100, 220, 760, 300] })
    else { await api('/api/profile/region', 'POST', { channel: 'a', bbox: [100, 220, 760, 300] }); await api('/api/profile/region', 'POST', { channel: 'b', bbox: [100, 340, 760, 420] }) }
    await sleep(500)
    const r0 = await api('/api/pipeline/start', 'POST')
    const n = mode === 'single' ? 1 : 2
    await wait(`[...document.querySelectorAll('.pane.translation .pane-text')].filter(e => e.innerText.trim().length > 3).length >= ${n}`, 30000)
    await sleep(8000)   // passa de um ciclo da demonstração (texto novo depois de ligar)
    const o = await panes('original'); const t = await panes('translation'); const th = await thumbs()
    const chips = await js(`[...document.querySelectorAll('.pane.original .pane-meta')].map(e => e.innerText.trim())`)
    const sb = await js(`document.querySelector('.statusbar')?.innerText || ''`)
    const res = { start: r0.status, original: o, translation: t, thumbs: th, chips, statusbar: sb }
    ok(`${tag}:original`, o.filter((x) => (wantRe || /\w{4}/).test(x)).length >= n, o)
    ok(`${tag}:translation`, t.filter((x) => x.length > 3).length >= n, t)
    ok(`${tag}:thumbnails`, th.length >= n && th.every((x) => x.w > 20 && x.h > 5 && x.src.startsWith('data:image/jpeg')), th)
    return res
  }
  try {
    fs.rmSync(SDIR, { recursive: true, force: true }); fs.mkdirSync(SDIR, { recursive: true })
    for (const f of ['ocr_modelo_basico.py', 'ocr_tesseract.py', 'ocr_rapidocr.py', 'modelo_basico.py']) fs.copyFileSync(path.join(__dirname, '../../examples/scripts', f), path.join(SDIR, f))
    main.setSize(1280, 860)
    await sleep(900)
    await api('/api/settings', 'PATCH', { changes: { 'ui.language': 'pt-BR', 'ui.typewriter': false } }); await js(`window.egt.app.setLanguage('pt-BR')`)
    await sleep(2500); await js(`document.querySelector('.intro')?.click()`); await sleep(1200)
    const ver = await js(`document.querySelector('.titlebar')?.innerText || ''`)
    ok('version:4.1-beta', /4\.1 beta/.test(ver), ver)
    const eng0 = (await api('/api/ocr/engines')).body
    rep.ocr_engines = eng0
    // aba OCR — padrão: motores do app
    await drawer('ocr')
    ok('ocr:tab', await wait(`!!${tid('ocr-page')}`))
    ok('ocr:source-card', await wait(`!!${tid('ocs-source')}`))
    ok('ocr:default-builtin', !(await js(`!!${tid('ocs-page')}`)))
    await top(); await shot('ocs-01-aba-ocr-motores')
    await radio('[data-testid=ocs-source]', 'Meu script'); await sleep(500)
    ok('ocs:panel', await wait(`!!${tid('ocs-page')}`))
    ok('ocs:not-active-note', await js(`!!${tid('ocs-not-active')}`), await js(`${tid('ocs-not-active')}?.innerText || ''`))
    const warn = await js(`${tid('ocs-warning')}?.innerText || ''`)
    ok('ocs:warning', /Atenção/.test(warn) && /confia/.test(warn), warn.slice(0, 200))
    ok('ocs:test-disabled-without-file', await js(`${tid('ocs-test')}?.disabled === true`))
    await top(); await shot('ocs-02-meu-script-aviso')
    const contract = await js(`${tid('ocs-contract')}?.innerText || ''`)
    ok('ocs:contract', /raw_path/.test(contract) && /outputs/.test(contract) && /---/.test(contract), contract.slice(0, 200))
    await into('ocs-contract'); await shot('ocs-03-contrato')
    await into('ocs-ex-ocr_tesseract.py', 'center'); await shot('ocs-04-exemplos')
    let s = (await api('/api/settings')).body
    ok('ocs:still-off-before-approval', s.ocr_script.enabled === false)

    const choose = async (file, tag) => {
      global.__egtPickFile = path.join(SDIR, file)
      await drawer('ocr'); await top()
      if (!(await js(`!!${tid('ocs-page')}`))) { await radio('[data-testid=ocs-source]', 'Meu script'); await sleep(400) }
      await js(`${tid('ocs-choose')}.scrollIntoView({ block: 'center' }); 0`)
      await clickT('ocs-choose')
      ok(`${tag}:confirm-dialog`, await wait(`!!${tid('ocs-confirm')}`))
      const sha = await js(`${tid('ocs-confirm-sha')}?.innerText || ''`)
      ok(`${tag}:confirm-sha`, /^[0-9a-f]{64}$/.test(sha.trim()), sha)
      ok(`${tag}:ok-disabled-without-trust`, await js(`${tid('ocs-confirm-ok')}.disabled === true`))
      await shot(`${tag}-01-confirmar`)
      await clickT('ocs-trust'); await sleep(200); await clickT('ocs-confirm-ok')
      ok(`${tag}:approved`, await wait(`!!${tid('ocs-file')} && !${tid('ocs-confirm')}`))
      const st = (await api('/api/settings')).body
      ok(`${tag}:enabled`, st.ocr_script.enabled === true && /^[0-9a-f]{64}$/.test(st.ocr_script.sha256), st.ocr_script)
      const reading = await js(`[...document.querySelectorAll('.chip')].map(c => c.innerText).find(x => /Lendo com/.test(x)) || ''`)
      ok(`${tag}:reading-with`, /Script de OCR/.test(reading), reading)
      await top(); await shot(`${tag}-02-escolhido`)
    }
    const testUi = async (tag, re) => {
      await radio('[data-testid=ocs-page]', 'Canal único'); await sleep(200)
      await into('ocs-test', 'center'); await clickT('ocs-test')
      await wait(`!!(${tid('ocs-test-out')} || ${tid('ocs-test-fail')})`, 30000); await sleep(500)
      const o1 = await js(`(${tid('ocs-test-out')} || ${tid('ocs-test-fail')})?.innerText || ''`)
      const th1 = await js(`[...document.querySelectorAll('[data-testid=ocs-thumb]')].map(i => i.naturalWidth)`)
      ok(`${tag}:test-single`, (await js(`!!${tid('ocs-test-out')}`)) && re.test(o1), o1)
      ok(`${tag}:test-single-thumb`, th1.length === 1 && th1[0] > 50, th1)
      await into('ocs-test', 'start'); await shot(`${tag}-03-teste-unico`)
      await radio('[data-testid=ocs-page]', 'Canal duplo'); await sleep(200)
      await clickT('ocs-test'); await sleep(300)
      await wait(`(document.querySelectorAll('[data-testid=ocs-thumb]').length === 2) || !!${tid('ocs-test-fail')}`, 30000); await sleep(500)
      const o2 = await js(`(${tid('ocs-test-out')} || ${tid('ocs-test-fail')})?.innerText || ''`)
      const th2 = await js(`[...document.querySelectorAll('[data-testid=ocs-thumb]')].map(i => i.naturalWidth)`)
      ok(`${tag}:test-dual`, (await js(`!!${tid('ocs-res-a')} && !!${tid('ocs-res-b')} && !!${tid('ocs-test-out')}`)), o2)
      ok(`${tag}:test-dual-thumbs`, th2.length === 2 && th2.every((w) => w > 50), th2)
      await into('ocs-test', 'start'); await shot(`${tag}-04-teste-duplo`)
      await radio('[data-testid=ocs-page]', 'Canal único'); await sleep(200)
      return { single: o1, dual: o2 }
    }

    // 1) modelo básico (sem dependências)
    await choose('ocr_modelo_basico.py', 'ocs-basico')
    rep.basic = await testUi('ocs-basico', /imagem de \d+ x \d+ recebida/)
    ok('ocs-basico:dual-text', /Canal A/.test(rep.basic.dual) && /Canal B/.test(rep.basic.dual), rep.basic.dual)
    // mostrar JSON enviado (sem caminho completo)
    await js(`[...document.querySelectorAll('.linkish')].find(b => /JSON/.test(b.innerText))?.click(); 0`); await sleep(400)
    const pj = await js(`${tid('ocs-json')}?.innerText || ''`)
    ok('ocs-basico:payload-redacted', /"kind": "ocr"/.test(pj) && !/\/tmp\/egt-ocrtmp-/.test(pj), pj.slice(0, 200))
    await into('ocs-json', 'center'); await shot('ocs-basico-05-json-enviado')

    // 2) Tesseract (OCR de verdade)
    await choose('ocr_tesseract.py', 'ocs-tess')
    rep.tess = await testUi('ocs-tess', /Hello, adventurer/)
    ok('ocs-tess:dual-b', /Nina: Let.s go to the castle/.test(rep.tess.dual), rep.tess.dual)
    await closeDrawer()
    rep.tess.pipe_single = await runPipe('single', 'pipe-tess-single', /The|Take|We|Careful|You/)
    ok('pipe-tess-single:chip', rep.tess.pipe_single.chips.some((c) => /Script de OCR/.test(c)), rep.tess.pipe_single.chips)
    ok('pipe-tess-single:statusbar', /Script de OCR/.test(rep.tess.pipe_single.statusbar), rep.tess.pipe_single.statusbar)
    const met = (await api('/api/metrics')).body
    ok('pipe-tess-single:metrics-engine', met && met.ocr_engine === 'script', met && met.ocr_engine)
    await shot('ocs-tess-06-janela-unico', 200)
    await stopAll()
    rep.tess.pipe_dual = await runPipe('dual', 'pipe-tess-dual')
    ok('pipe-tess-dual:chat-channel', rep.tess.pipe_dual.original.some((x) => /Player42|Mira|Dax/.test(x)), rep.tess.pipe_dual.original)
    await shot('ocs-tess-07-janela-duplo', 200)
    await stopAll()
    // "Minha região" no teste (captura de verdade da região configurada, modo duplo)
    await drawer('ocr')
    await radio('[data-testid=ocs-page]', 'Canal duplo'); await radio('[data-testid=ocs-page]', 'Minha região'); await sleep(200)
    await into('ocs-test', 'center'); await clickT('ocs-test')
    await wait(`document.querySelectorAll('[data-testid=ocs-thumb]').length === 2 && !!${tid('ocs-test-out')}`, 30000)
    const cap = await js(`${tid('ocs-test-out')}?.innerText || ''`)
    ok('ocs-tess:test-capture-dual', /Player42|Mira|Dax/.test(cap), cap)
    await into('ocs-test', 'start'); await shot('ocs-tess-08-teste-minha-regiao')
    await radio('[data-testid=ocs-page]', 'Exemplo'); await radio('[data-testid=ocs-page]', 'Canal único')
    await closeDrawer()

    // 3) RapidOCR (python com rapidocr no PATH)
    await choose('ocr_rapidocr.py', 'ocs-rapid')
    rep.rapid = await testUi('ocs-rapid', /Hello, adventurer/)
    await closeDrawer()
    await api('/api/profile', 'PATCH', { mode: 'single' })

    // 4) arquivo muda → bloqueia e pede confirmação de novo
    fs.appendFileSync(path.join(SDIR, 'ocr_rapidocr.py'), '\n# alterado\n')
    await drawer('general'); await drawer('ocr')
    ok('hash:changed-banner', await wait(`!!${tid('ocs-changed')}`, 8000))
    const tr = (await api('/api/ocr-script/test', 'POST', { mode: 'single', source: 'sample' })).body
    ok('hash:test-blocked', tr && tr.ok === false && tr.code === 'hash_changed', tr && { ok: tr.ok, code: tr.code })
    const ps = (await api('/api/pipeline/start', 'POST'))
    await sleep(2500)
    const errs = await js(`document.body.innerText`)
    rep.hash_pipe = { status: ps.status }
    await stopAll()
    await top(); await shot('ocs-05-arquivo-alterado')
    await clickT('ocs-reconfirm')
    ok('hash:reconfirm-dialog', await wait(`!!${tid('ocs-confirm')}`))
    await shot('ocs-06-reconfirmar')
    await clickT('ocs-trust'); await sleep(150); await clickT('ocs-confirm-ok')
    ok('hash:reapproved', await wait(`!${tid('ocs-changed')} && !!${tid('ocs-file')}`))
    void errs

    // 5) volta aos motores do app → script desliga; RapidOCR e Tesseract continuam lendo
    await choose('ocr_tesseract.py', 'ocs-tess2')
    await top(); await radio('[data-testid=ocs-source]', 'Motores de OCR'); await sleep(600)
    s = (await api('/api/settings')).body
    ok('exclusive:builtin-turns-script-off', s.ocr_script.enabled === false && !!s.ocr_script.path, s.ocr_script)
    await top(); await shot('ocs-09-voltou-motores')
    await closeDrawer()
    for (const id of ['rapidocr', 'tesseract']) {
      const r = await api('/api/profile', 'PATCH', { ocr_engine: id })
      if (r.status !== 200) { ok(`builtin-${id}:select`, false, r); continue }
      const m = (await api('/api/metrics')).body
      ok(`builtin-${id}:active`, m && m.ocr_engine === id, m && m.ocr_engine)
      rep[`builtin_${id}`] = await runPipe('single', `builtin-${id}`, /The|Take|We|Careful|You/)
      ok(`builtin-${id}:no-script-chip`, !rep[`builtin_${id}`].chips.some((c) => /Script de OCR/.test(c)), rep[`builtin_${id}`].chips)
      await stopAll()
    }
    await api('/api/profile', 'PATCH', { ocr_engine: 'rapidocr' })
    // escolher "script" pelo seletor da barra (API) liga de novo; perfil guarda o motor do app
    const sel = await api('/api/profile', 'PATCH', { ocr_engine: 'script' })
    s = (await api('/api/settings')).body
    const prof = (await api('/api/profile')).body
    ok('toolbar:script-select', sel.status === 200 && s.ocr_script.enabled === true, { status: sel.status })
    ok('toolbar:profile-keeps-builtin', prof && (prof.ocr_engine === 'rapidocr' || (prof.profile && prof.profile.ocr_engine === 'rapidocr')), prof && (prof.ocr_engine || prof.profile?.ocr_engine))
    const tbv = await js(`document.querySelector('.toolbar')?.innerText || ''`)
    ok('toolbar:shows-script', /Script de OCR/.test(tbv), tbv.slice(0, 200))

    // 6) script de tradução + script de OCR juntos (canal duplo)
    global.__egtPickFile = path.join(SDIR, 'modelo_basico.py')
    await drawer('scripts'); await top(); await clickT('sc-choose')
    ok('both:tr-confirm', await wait(`!!${tid('sc-confirm')}`))
    await clickT('sc-trust'); await sleep(150); await clickT('sc-confirm-ok')
    ok('both:tr-approved', await wait(`!!${tid('sc-file')}`))
    s = (await api('/api/settings')).body
    ok('both:both-on', s.script.enabled === true && s.ocr_script.enabled === true, { tr: s.script.enabled, ocr: s.ocr_script.enabled })
    await closeDrawer()
    rep.both = await runPipe('dual', 'both-dual')
    ok('both:translation-from-script', rep.both.translation.filter((x) => /^\[pt\]/.test(x)).length >= 2, rep.both.translation)
    ok('both:ocr-chip', rep.both.chips.some((c) => /Script de OCR/.test(c)), rep.both.chips)
    await shot('ocs-10-janela-dois-scripts', 200)
    await stopAll()
    await api('/api/settings', 'PATCH', { changes: { 'script.enabled': false } })
    await api('/api/profile', 'PATCH', { mode: 'single' })
    rep.final_main = await runPipe('single', 'final-single', /The|Take|We|Careful|You/)
    await shot('ocs-11-janela-painel-direita', 200)
    await stopAll()
    // privacidade: nada de caminho pessoal nas telas
    await drawer('ocr')
    const body = await js(`document.body.innerText`)
    ok('privacy:no-home-path', !/\/home\/|\\Users\\/.test(body))
    // esquecer o script → motores do app
    await api('/api/ocr-script/forget', 'POST')
    s = (await api('/api/settings')).body
    ok('forget:off-and-cleared', s.ocr_script.enabled === false && s.ocr_script.path === '' && s.ocr_script.sha256 === '', s.ocr_script)
    const left = fs.readdirSync(require('node:os').tmpdir()).filter((n) => n.startsWith("egt-ocrtmp-"))
    ok('temp:no-leftover-dirs', left.length === 0, left)
  } catch (e) { rep.checks.push({ name: 'error', pass: false, extra: String(e && e.stack || e) }); console.log('ERROR', e) }
  rep.failed = rep.checks.filter((c) => !c.pass).map((c) => c.name)
  fs.writeFileSync(path.join(OUT, 'ocrscripts-report.json'), JSON.stringify(rep, null, 1))
  app.quit()
}
