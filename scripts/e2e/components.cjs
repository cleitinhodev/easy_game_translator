'use strict'
// Gerenciador de componentes (Configurações > Atualizações) com dados de demonstração.
// Verifica: lista, linha expandida, janela de download com progresso, botão Pasta (IPC chamado + caminho validado),
// mudança de pasta, estado sem internet. Salva PNGs em $EGT_SHOTS e um relatório JSON.
const fs = require('node:fs'); const path = require('node:path')
const OUT = process.env.EGT_SHOTS || 'screenshots'
const MODE = process.env.EGT_E2E_MODE || 'main'
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
module.exports = async ({ app, getMain, backend }) => {
  const main = getMain(); const wc = main.webContents
  const js = (c) => wc.executeJavaScript(c, true)
  const api = async (p, m = 'GET', b) => { const r = await backend.api(p, { method: m, body: b ? JSON.stringify(b) : undefined }); return r.json() }
  const shot = async (n, d = 450) => { await sleep(d); fs.writeFileSync(path.join(OUT, n + '.png'), (await wc.capturePage()).toPNG()) }
  const click = (sel) => js(`(() => { const e = document.querySelector(${JSON.stringify(sel)}); if (!e) return false; e.scrollIntoView({block:'center'}); e.click(); return true })()`)
  const clickText = (txt, scope = 'document') => js(`(() => { const sc=${scope}; if(!sc) return false; const b=[...sc.querySelectorAll('button')].find(x=>x.textContent.trim()===${JSON.stringify(txt)}); if(!b) return false; b.click(); return true })()`)
  const wait = async (cond, ms = 15000) => { const t0 = Date.now(); while (Date.now() - t0 < ms) { if (await js(cond)) return true; await sleep(150) } return false }
  const rep = { mode: MODE, checks: [] }
  const ok = (name, pass, extra) => rep.checks.push({ name, pass: !!pass, ...(extra ? { extra } : {}) })
  try {
    main.setSize(1280, 960); main.center(); await sleep(2500)
    await js(`document.querySelector('.intro')?.click()`); await sleep(1200)
    // textos conferidos em pt-BR (o padrão agora é 'auto' = idioma do sistema)
    await api('/api/settings', 'PATCH', { changes: { 'ui.language': 'pt-BR' } }); await js(`window.egt.app.setLanguage('pt-BR')`); await wait(`document.documentElement.lang === 'pt-BR'`)
    await api('/api/profile', 'PATCH', { ocr_engine: 'tesseract', alphabet: 'abc(EN)' })
    await js(`window.__egt.getState().openDrawer('updates')`)
    ok('list-rendered', await wait(`document.querySelectorAll('.comp-row').length >= 12`))
    await sleep(1800)
    const prefix = MODE === 'frozen' ? '70' : '60'
    await shot(`${prefix}-updates-top`)
    const summary = await js(`document.querySelector('.comp-summary')?.innerText`)
    ok('summary-shows-missing-for-selected-engine', /Faltando/.test(summary || ''), summary)
    // textos sem jargão
    const body = await js(`document.querySelector('.comp-page').innerText`)
    ok('no-jargon', !/site-packages|\\bABI\\b|\\bwheel\\b/i.test(body))
    await js(`document.querySelector('.drawer-body, .drawer .s-body, .drawer')?.scrollTo?.(0, 520)`)

    if (MODE === 'frozen') {
      await click('[data-testid=more-easyocr]'); await sleep(700)
      const t = await js(`document.querySelector('[data-comp=easyocr]').innerText`)
      ok('frozen-honest-easyocr', /não consegue usar|only works|Esta versão instalada/.test(t), t.slice(0, 200))
      await shot(`${prefix}-frozen-easyocr-expanded`)
      const rapid = await js(`document.querySelector('[data-comp=rapidocr]').innerText`)
      ok('frozen-rapid-builtin', /Já vem no programa/.test(rapid), rapid.slice(0, 120))
      await shot(`${prefix}-frozen-rows`)
    } else {
      // linha expandida (manual)
      await click('[data-testid=more-tessdata]'); await sleep(900)
      const exp = await js(`document.querySelector('[data-comp=tessdata]').innerText`)
      ok('manual-expanded', /como instalar manualmente/i.test(exp) && /colocar arquivos/i.test(exp))
      await shot('61-manual-expanded')
      await click('[data-testid=more-tessdata]'); await sleep(500)

      // download: Tesseract (instalador) — confirmar tamanho → progresso → pronto
      ok('install-button-present', await click('[data-testid=install-tesseract]'))
      ok('confirm-shows-size', await wait(`!!document.querySelector('.comp-modal [data-testid=dl-confirm]')`), await js(`document.querySelector('.comp-modal')?.innerText`))
      await shot('62-download-confirm')
      await click('[data-testid=dl-confirm]')
      ok('progress-visible', await wait(`!!document.querySelector('.comp-modal .jobbar .fill')`))
      await sleep(1700)
      const mid = await js(`(() => { const f=document.querySelector('.comp-modal .jobbar .fill'); const m=document.querySelector('.comp-modal .jobmeta')?.innerText; return { w: f?.style.width, m } })()`)
      ok('progress-mid', mid.w && parseFloat(mid.w) > 0 && parseFloat(mid.w) < 100, mid)
      await shot('63-download-progress', 0)
      ok('download-done', await wait(`!!document.querySelector('.comp-modal .done-ic')`, 40000))
      await shot('64-download-done')
      // abrir instalador pede confirmação e só roda dentro da pasta de downloads
      await clickText('Abrir instalador', `document.querySelector('.comp-modal')`); await sleep(500)
      ok('installer-asks-confirmation', !!(await js(`[...document.querySelectorAll('.modal')].some(m => /Abrir o instalador agora/.test(m.innerText))`)))
      await clickText('Abrir instalador', `[...document.querySelectorAll('.modal')].pop()`); await sleep(900)
      const st = await api('/api/components/_demo', 'POST', {})
      ok('installer-opened-via-backend', (st.opened || []).length === 1 && /tesseract-ocr-w64/.test(st.opened[0]), st.opened)
      await clickText('Fechar', `document.querySelector('.comp-modal')`); await sleep(700)

      // botão Pasta → IPC com validação
      global.__egtComponentCalls = []
      await click('[data-testid=folder-tessdata]'); await sleep(900)
      const paths = await api('/api/components/paths')
      const call = (global.__egtComponentCalls || []).find((c) => c.fn === 'open-folder')
      ok('folder-ipc-called', !!call && call.id === 'tessdata', call)
      ok('folder-path-validated', !!call && call.path === paths.dirs.tessdata && fs.statSync(call.path).isDirectory(), call && call.path)
      const bad = await js(`Promise.all([window.egt.components.openFolder('../etc'), window.egt.components.openFolder('nope'), window.egt.components.openFolder('TESS data'), window.egt.components.openFolder(42)])`)
      ok('folder-rejects-bad-ids', bad.every((r) => r.ok === false), bad)
      ok('folder-no-extra-opens', (global.__egtComponentCalls || []).filter((c) => c.fn === 'open-folder').length === 1)

      // mudar pasta raiz (seletor simulado)
      const pick = process.env.EGT_E2E_PICK
      if (pick) {
        await clickText('Mudar pasta…', `document.querySelector('.comp-root')`); await sleep(700)
        await shot('65-change-root-confirm')
        await clickText('Usar esta pasta', `[...document.querySelectorAll('.modal')].pop()`); await sleep(1200)
        const p2 = await api('/api/components/paths')
        ok('root-changed', p2.root === pick, p2.root)
      }

      // instalar um idioma (item) e ver na lista
      await click('[data-testid=more-tessdata]'); await sleep(700)
      const itemBtn = await js(`(() => { const r=document.querySelector('[data-comp=tessdata] .item-row:not(.ok) button.btn:not(.ghost)'); if(!r) return false; r.click(); return true })()`)
      ok('item-install-click', itemBtn)
      await wait(`!!document.querySelector('.comp-modal [data-testid=dl-confirm]')`)
      await click('[data-testid=dl-confirm]')
      ok('item-download-done', await wait(`!!document.querySelector('.comp-modal .done-ic')`, 40000))
      await shot('66-item-done')
      await clickText('Fechar', `document.querySelector('.comp-modal')`); await sleep(900)
      await shot('67-tessdata-after')

      // sem internet
      await api('/api/components/_demo', 'POST', { offline: true })
      await clickText('Verificar tudo'); await sleep(2500)
      ok('offline-banner', !!(await js(`!!document.querySelector('.comp-banner')`)))
      await js(`document.querySelector('.comp-summary').scrollIntoView({block:'start'})`)
      await shot('68-offline-list')
      await click('[data-testid=install-tesseract]').catch(() => {})
      await sleep(1500)
      await shot('69-offline-modal')
      const om = await js(`document.querySelector('.comp-modal')?.innerText || ''`)
      ok('offline-modal-friendly', /Sem internet/.test(om) && !/error|exception|traceback/i.test(om), om.slice(0, 200))
      await api('/api/components/_demo', 'POST', { offline: false })
    }
  } catch (e) { rep.error = String((e && e.stack) || e) }
  rep.failed = rep.checks.filter((c) => !c.pass).map((c) => c.name)
  fs.writeFileSync(path.join(OUT, `components-report-${MODE}.json`), JSON.stringify(rep, null, 2))
  console.log('[report]', JSON.stringify({ mode: MODE, failed: rep.failed, error: rep.error }))
  app.quit()
}
