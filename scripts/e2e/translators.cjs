'use strict'
// Aba Tradução (4.0.8): um cartão por serviço (status, selos, privacidade, limite, campos, "como conseguir a chave", teste manual),
// chaves criptografadas/mascaradas/removíveis, ordem/ligar, árabe RTL e japonês. Testes manuais vão ao serviço real (só o texto de exemplo).
const fs = require('node:fs'); const path = require('node:path')
const OUT = process.env.EGT_SHOTS || 'screenshots'
const CFG = process.env.EGT_CONFIG_DIR; const UD = process.env.EGT_USER_DATA
const KEY = 'e2e0' + 'fake-deepl-key-0123456789abcdef:fx'   // chave falsa (partida para o scanner de segredos)
const BAIDU = 'e2e0' + 'baidusecret987654'
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
const grepDir = (dir, needle) => {
  const hits = []
  const walk = (d) => { let ents = []; try { ents = fs.readdirSync(d, { withFileTypes: true }) } catch { return }
    for (const e of ents) { const p = path.join(d, e.name); if (e.isDirectory()) walk(p); else { try { const b = fs.readFileSync(p); if (b.includes(needle) || b.includes(Buffer.from(needle, 'utf16le'))) hits.push(p) } catch { /* */ } } } }
  walk(dir); return hits
}
const EXPECT = ['google', 'bing', 'mymemory', 'mozhi', 'yandex', 'apertium', 'libre', 'deepl', 'microsoft', 'gcloud', 'baidu', 'youdao', 'niutrans', 'argos']
module.exports = async ({ app, getMain, backend }) => {
  const main = getMain(); const wc = main.webContents
  const js = (c) => wc.executeJavaScript(c, true)
  const api = async (p, m = 'GET', b) => { const r = await backend.api(p, { method: m, body: b ? JSON.stringify(b) : undefined }); return { status: r.status, body: await r.json() } }
  const shot = async (n, d = 350) => { await sleep(d); fs.writeFileSync(path.join(OUT, n + '.png'), (await wc.capturePage()).toPNG()) }
  const wait = async (cond, ms = 8000) => { const t0 = Date.now(); while (Date.now() - t0 < ms) { if (await js(cond)) return true; await sleep(150) } return false }
  const rep = { checks: [] }
  const ok = (name, pass, extra) => { rep.checks.push({ name, pass: !!pass, ...(extra !== undefined ? { extra } : {}) }); console.log(pass ? 'PASS' : 'FAIL', name, extra !== undefined ? JSON.stringify(extra).slice(0, 300) : '') }
  const setLang = async (l) => { await api('/api/settings', 'PATCH', { changes: { 'ui.language': l } }); await js(`window.egt.app.setLanguage(${JSON.stringify(l)})`); return wait(`document.documentElement.lang === ${JSON.stringify(l)}`) }
  const card = (id) => `document.querySelector('[data-testid=tr-card-${id}]')`
  const open = async (id) => { await js(`(() => { const c = ${card(id)}; if (!c.classList.contains('open')) c.querySelector('[data-testid=tr-open-${id}]').click(); return 0 })()`); await sleep(450) }
  const close = async (id) => { await js(`(() => { const c = ${card(id)}; if (c.classList.contains('open')) c.querySelector('[data-testid=tr-open-${id}]').click(); return 0 })()`); await sleep(400) }
  const top = (id) => js(`${card(id)}.scrollIntoView({ block: 'start' }); 0`)
  const resultText = (id) => js(`(${card(id)}.querySelector('.tr-test .result')?.innerText || '')`)
  const type = (sel, v) => js(`(() => { const i = document.querySelector(${JSON.stringify(sel)}); const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set; set.call(i, ${JSON.stringify(v)}); i.dispatchEvent(new Event('input', { bubbles: true })); return 0 })()`)
  try {
    main.setSize(1180, 940)
    await sleep(2500); await js(`document.querySelector('.intro')?.click()`); await sleep(1000)
    await setLang('pt-BR')
    await js(`window.__egt.getState().openDrawer('translation'); 0`)
    ok('cards:rendered', await wait(`document.querySelectorAll('[data-testid^=tr-card-]').length === 14`), await js(`document.querySelectorAll('[data-testid^=tr-card-]').length`))
    const ids = await js(`[...document.querySelectorAll('[data-testid^=tr-card-]')].map(c => c.dataset.testid.slice(8))`)
    ok('cards:order', JSON.stringify(ids) === JSON.stringify(EXPECT), ids)
    ok('cards:no-lingva', !ids.includes('lingva') && !(await js(`document.body.innerText.includes('Lingva URL')`)))
    const on = await js(`[...document.querySelectorAll('[data-testid^=tr-card-]')].filter(c => c.querySelector('.switch')?.getAttribute('aria-checked') === 'true').map(c => c.dataset.testid.slice(8))`)
    ok('cards:default-enabled', JSON.stringify(on) === JSON.stringify(['google', 'bing', 'mymemory']), on)
    const unof = await js(`[...document.querySelectorAll('[data-testid^=tr-card-]')].filter(c => /Não oficial/.test(c.querySelector('.tr-tags')?.innerText || '')).map(c => c.dataset.testid.slice(8))`)
    ok('cards:unofficial-badges', JSON.stringify(unof) === JSON.stringify(['google', 'bing', 'yandex']), unof)
    ok('cards:no-auto-probe', await js(`!document.body.innerText.includes('testando…')`))
    await shot('tr-01-cards-pt-BR', 500)

    // Google: privacidade, aviso de não oficial, teste manual (vai ao Google com o texto de exemplo)
    await open('google')
    const gtxt = await js(`${card('google')}.innerText`)
    ok('google:privacy', /Quem recebe o texto/.test(gtxt) && /Google/.test(gtxt) && /Estados Unidos/.test(gtxt), gtxt.slice(0, 200))
    ok('google:unofficial-warning', /pode parar de funcionar/i.test(gtxt))
    ok('google:test-box', await js(`!!${card('google')}.querySelector('[data-testid=tr-run-google]')`))
    await js(`${card('google')}.querySelector('[data-testid=tr-run-google]').click(); 0`)
    await wait(`!!${card('google')}.querySelector('.tr-test .result')`, 20000)
    const gr = await resultText('google')
    ok('google:test-result', gr.length > 0, gr)
    ok('google:status-chip', await js(`${card('google')}.querySelector('.tr-head .chip.ok, .tr-head .chip.err') !== null`))
    await top('google'); await shot('tr-02-google-test')
    await close('google')

    // MyMemory: e-mail opcional (dado sensível → criptografado)
    await open('mymemory')
    ok('mymemory:email-field', await js(`!!${card('mymemory')}.querySelector('[data-testid=tr-field-mymemory_email][type=password]')`))
    await close('mymemory')

    // DeepL: como conseguir a chave + link oficial + chave criptografada/mascarada/removível + erro claro no teste
    await open('deepl')
    ok('deepl:howto', await js(`/Como conseguir a chave/.test(${card('deepl')}.querySelector('[data-testid=tr-howto-deepl]')?.innerText || '')`))
    await js(`[...${card('deepl')}.querySelectorAll('[data-testid=tr-howto-deepl] button')][0].click(); 0`); await sleep(300)
    ok('deepl:key-link', (global.__egtExternal || []).some((u) => /^https:\/\/www\.deepl\.com\//.test(u)), global.__egtExternal)
    await type('[data-testid=tr-field-deepl_key]', KEY)
    await js(`document.querySelector('[data-testid=tr-save-deepl]').click(); 0`); await sleep(900)
    let s = (await api('/api/settings')).body
    ok('deepl:key-masked', s.translation.deepl_key === '••••••••' && !JSON.stringify(s).includes(KEY) && s.secrets.state['translation.deepl_key'] === 'ok', s.secrets.state)
    const disk = JSON.parse(fs.readFileSync(path.join(CFG, 'settings.json'), 'utf8'))
    ok('deepl:key-encrypted-blob', typeof disk.translation.deepl_key === 'object' && /^(aesgcm|keyring|dpapi):v1:/.test(disk.translation.deepl_key.enc), String(disk.translation.deepl_key.enc || disk.translation.deepl_key).slice(0, 12))
    ok('deepl:key-not-plaintext', grepDir(CFG, KEY).length === 0 && grepDir(UD, KEY).length === 0)
    const eng = (await api('/api/translation/engines')).body
    ok('engines:no-secret-in-api', !JSON.stringify(eng).includes(KEY) && eng.find((e) => e.id === 'deepl').meta.key_state['translation.deepl_key'] === 'ok')
    ok('deepl:remove-visible', await wait(`!!document.querySelector('[data-testid=tr-remove-deepl_key]')`))
    await js(`document.querySelector('[data-testid=tr-run-deepl]').click(); 0`)
    await wait(`!!${card('deepl')}.querySelector('.tr-test .result')`, 20000)
    const dr = await resultText('deepl')
    ok('deepl:test-clear-error', /Chave recusada|Sem conexão|demorou/.test(dr) && !dr.includes(KEY), dr)
    await top('deepl'); await shot('tr-03-deepl-key')
    await js(`document.querySelector('[data-testid=tr-remove-deepl_key]').click(); 0`)
    ok('deepl:remove-dialog', await wait(`!!document.querySelector('.modal .confirm-text')`))
    await js(`document.querySelector('.modal-foot .btn.danger').click(); 0`)
    await wait(`!document.querySelector('[data-testid=tr-remove-deepl_key]')`); await sleep(600)
    s = (await api('/api/settings')).body
    ok('deepl:removed', s.secrets.state['translation.deepl_key'] === 'none' && s.translation.deepl_key === '', s.secrets.state)
    ok('deepl:nothing-on-disk', grepDir(CFG, KEY).length === 0 && grepDir(UD, KEY).length === 0)
    await close('deepl')

    // Baidu: dois campos (App ID visível + chave secreta mascarada)
    await open('baidu')
    ok('baidu:fields', await js(`!!document.querySelector('[data-testid=tr-field-baidu_appid][type=text]') && !!document.querySelector('[data-testid=tr-field-baidu_key][type=password]')`))
    await type('[data-testid=tr-field-baidu_appid]', '20260000000001'); await type('[data-testid=tr-field-baidu_key]', BAIDU)
    await js(`document.querySelector('[data-testid=tr-save-baidu]').click(); 0`); await sleep(900)
    s = (await api('/api/settings')).body
    ok('baidu:saved', s.translation.baidu_appid === '20260000000001' && s.translation.baidu_key === '••••••••' && grepDir(CFG, BAIDU).length === 0)
    await top('baidu'); await shot('tr-04-baidu-fields')
    await close('baidu')

    // Apertium (pivô pelo espanhol) e LibreTranslate (sem servidor → mensagem clara)
    await open('libre')
    await js(`document.querySelector('[data-testid=tr-run-libre]').click(); 0`)
    await wait(`!!${card('libre')}.querySelector('.tr-test .result')`, 15000)
    ok('libre:not-configured-message', await resultText('libre'), await resultText('libre'))
    await top('libre'); await shot('tr-05-libre')
    await close('libre')

    // ligar + reordenar
    await js(`${card('yandex')}.querySelector('.switch').click(); 0`); await sleep(700)
    s = (await api('/api/settings')).body
    ok('toggle:yandex-on', s.translation.enabled.includes('yandex'), s.translation.enabled)
    await js(`${card('yandex')}.querySelector('.mini-btn[aria-label="Mover para cima"]').click(); 0`); await sleep(800)
    s = (await api('/api/settings')).body
    ok('order:yandex-up', s.translation.order.indexOf('yandex') === 3, s.translation.order)

    // árabe (RTL) e japonês
    for (const l of ['ar', 'ja']) {
      await setLang(l); await sleep(700)
      await open('mozhi')
      const t = await js(`${card('mozhi')}.innerText`)
      ok(`${l}:localized`, !/Quem recebe|Who receives/.test(t) && t.includes('Mozhi'), t.slice(0, 120))
      if (l === 'ar') ok('ar:rtl', await js(`document.documentElement.dir === 'rtl' || getComputedStyle(document.querySelector('.drawer')).direction === 'rtl'`))
      await js(`document.querySelector('.drawer-body')?.scrollTo?.(0, 0); 0`)
      await shot(`tr-06-${l}`)
      await close('mozhi')
    }
  } catch (e) { rep.checks.push({ name: 'error', pass: false, extra: String(e && e.stack || e) }); console.log('ERROR', e) }
  rep.failed = rep.checks.filter((c) => !c.pass).map((c) => c.name)
  fs.writeFileSync(path.join(OUT, 'translators-report.json'), JSON.stringify(rep, null, 1))
  app.quit()
}
