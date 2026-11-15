import { AnimatePresence, motion } from 'motion/react'
import { useEffect, useState } from 'react'
import { api } from '@/api/client'
import { ICopy, ICode, IFolder, ISave, ITrash, IRefresh } from '@/components/icons'
import { Button, Chip, Segmented, Slider, Switch } from '@/components/ui'
import { useStore, useT } from '@/store'
import type { OcrScriptInfo, OcrScriptTest, ScriptInspect, Settings } from '@/lib/types'
import exBasic from '../../examples/scripts/ocr_modelo_basico.py?raw'
import exTess from '../../examples/scripts/ocr_tesseract.py?raw'
import exRapid from '../../examples/scripts/ocr_rapidocr.py?raw'
import { ConfirmScript, kb, scriptErr, short } from './Scripts'
import { Result, Row, Section } from './parts'

// Script de OCR (4.1 beta): o arquivo do usuário lê a imagem capturada no lugar dos motores de OCR do app.
type T = ReturnType<typeof useT>
const EXAMPLES = [
  { file: 'ocr_modelo_basico.py', key: 'ocs.ex_basic', lang: 'Python', code: exBasic },
  { file: 'ocr_tesseract.py', key: 'ocs.ex_tess', lang: 'Python + Tesseract', code: exTess },
  { file: 'ocr_rapidocr.py', key: 'ocs.ex_rapid', lang: 'Python + RapidOCR', code: exRapid },
]
const FILTERS = [
  { name: 'Scripts', extensions: ['py', 'pyw', 'js', 'mjs', 'cjs', 'ps1', 'bat', 'cmd', 'sh', 'rb', 'php', 'lua', 'pl', 'exe'] },
  { name: '*', extensions: ['*'] },
]
const CONTRACT_IN = `{"version": 1, "kind": "ocr", "mode": "dual",
 "images": [
  {"channel": "a", "path": ".../a.png", "width": 1292, "height": 256,
   "raw_path": ".../a_raw.png", "raw_width": 640, "raw_height": 122},
  {"channel": "b", "path": ".../b.png", ...}],
 "channels": ["a", "b"],
 "alphabet": "abc(EN)", "ocr_lang": "eng", "lang_hint": "en", "cjk": false,
 "preprocess": {"scale": 2.0, "grayscale": true, ...}}`
const CONTRACT_OUT_JSON = '{"outputs": ["Texto lido em A", "Texto lido em B"]}'
const CONTRACT_OUT_OBJ = '{"outputs": [{"text": "Texto lido em A", "confidence": 92.5},\n             {"text": "Texto lido em B", "confidence": 88}]}'
const CONTRACT_OUT_TXT = 'Texto lido em A\n---\nTexto lido em B'

/** Nome do motor que lê o texto agora (para a linha "Lendo com: …"). */
export function ocrEngineName(t: T, s: Settings | null, engines: { id: string; name: string }[], profileEngine?: string) {
  if (s?.ocr_script?.enabled) return t('ocs.engine')
  return engines.find((e) => e.id === profileEngine)?.name ?? profileEngine ?? '—'
}

/** Seletor exclusivo no topo da aba OCR: motores do app × script do usuário. */
export function OcrSourceCard({ view, setView }: { view: 'builtin' | 'script'; setView: (v: 'builtin' | 'script') => void }) {
  const t = useT()
  const settings = useStore((s) => s.settings)!
  const profile = useStore((s) => s.profile)!
  const ocr = useStore((s) => s.ocr)
  const info = useStore((s) => s.ocrScript)
  const patch = useStore((s) => s.patchSettings)
  const on = !!settings.ocr_script?.enabled
  const usable = !!info?.path && !!info?.exists && !info?.changed
  const pick = async (v: 'builtin' | 'script') => {
    setView(v)
    if (v === 'builtin' && on) await patch({ 'ocr_script.enabled': false })
    if (v === 'script' && !on && usable) await patch({ 'ocr_script.enabled': true })
  }
  return (
    <Section title={t('ocs.source')} desc={t('ocs.source_tip')}
      right={<Chip tone={on ? 'accent' : 'default'}>{t('ocs.reading_with', { name: ocrEngineName(t, settings, ocr, profile.ocr_engine) })}</Chip>}>
      <div data-testid="ocs-source">
        <Segmented value={view} label={t('ocs.source')} onChange={pick}
          options={[{ value: 'builtin', label: t('ocs.src_builtin') }, { value: 'script', label: <>{t('ocs.src_script')} <span className="ocs-beta">beta</span></> }]} />
      </div>
      {view === 'script' && !on && <p className="muted small" data-testid="ocs-not-active">{usable ? t('ocs.not_active') : t('ocs.need_file')}</p>}
      {view === 'builtin' && info?.path && <p className="muted small">{t('ocs.builtin_note')}</p>}
    </Section>
  )
}

export function OcrScriptPanel() {
  const t = useT()
  const settings = useStore((s) => s.settings)!
  const info = useStore((s) => s.ocrScript)
  const patch = useStore((s) => s.patchSettings)
  const toast = useStore((s) => s.toast)
  const ask = useStore((s) => s.ask)
  const [pending, setPending] = useState<ScriptInspect | null>(null)
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null)
  const load = async () => { try { useStore.setState({ ocrScript: await api.get<OcrScriptInfo>('/api/ocr-script') }) } catch { /* WS atualiza */ } }
  useEffect(() => { load() }, [])
  const on = !!settings.ocr_script?.enabled
  const hasScript = !!info?.path
  const usable = hasScript && !!info?.exists && !info?.changed

  const inspect = async (path: string) => {
    setMsg(null)
    const r = await api.post<ScriptInspect>('/api/ocr-script/inspect', { path })
    if (!r.ok) { setMsg({ ok: false, text: scriptErr(t, r.code, r.detail) }); return }
    setPending(r)
  }
  const choose = async () => {
    if (!window.egt) { toast('info', t('sc.need_electron')); return }
    const p = await window.egt.app.pickFile({ filters: FILTERS })
    if (p) await inspect(p)
  }
  const approve = async (p: ScriptInspect) => {
    const r = await api.post<{ ok: boolean; ocr_script?: OcrScriptInfo; settings?: Settings; code?: string; detail?: string }>('/api/ocr-script/approve', { path: p.path, sha256: p.sha256, confirmed: true, enable: true })
    setPending(null)
    if (!r.ok) { setMsg({ ok: false, text: scriptErr(t, r.code, r.detail) }); return }
    useStore.setState({ ocrScript: r.ocr_script!, settings: r.settings! })
    setMsg({ ok: true, text: t('ocs.approved', { name: p.name }) })
  }
  const setOn = async (v: boolean) => {
    if (v && !hasScript) { await choose(); return }
    if (v && info && (info.changed || !info.exists)) { if (info.exists) await inspect(info.path); else setMsg({ ok: false, text: scriptErr(t, 'not_found', info.name) }); return }
    await patch({ 'ocr_script.enabled': v })
    load()
  }
  const forget = async () => {
    if (!(await ask(t('ocs.forget_confirm'), t('sc.forget'), true))) return
    const r = await api.post<{ ocr_script: OcrScriptInfo; settings: Settings }>('/api/ocr-script/forget')
    useStore.setState({ ocrScript: r.ocr_script, settings: r.settings })
    setMsg(null)
  }

  return (
    <div className="ocs-panel" data-testid="ocs-page">
      <Section title={t('ocs.title')} desc={t('ocs.tip')} right={<Chip tone={on ? 'accent' : 'default'}>{on ? t('sc.on') : t('common.off')}</Chip>}>
        <div className="ai-warn sc-warn" role="alert" data-testid="ocs-warning">
          <span className="ai-warn-ico" aria-hidden>⚠</span>
          <div><p><strong>{t('sc.warn_title')}</strong></p><p>{t('sc.warn_body')}</p></div>
        </div>
        <Row label={t('ocs.use')} hint={t('ocs.use_tip')}>
          <Switch checked={on} label={t('ocs.use')} onChange={setOn} />
        </Row>
        <p className="muted small">{t('ocs.beta_note')}</p>
      </Section>

      <Section title={t('ocs.file')} desc={t('sc.file_tip')}>
        {hasScript && info ? (
          <div className={`sc-file ${info.changed || !info.exists ? 'bad' : ''}`} data-testid="ocs-file">
            <span className="sc-file-ico"><ICode size={18} /></span>
            <div className="sc-file-main">
              <strong>{info.name}</strong>
              <small className="selectable sc-path" dir="ltr">{info.path}</small>
              <span className="sc-meta">
                <Chip tone={info.runtime_found ? 'ok' : 'warn'}>{info.runtime_found ? info.runtime : t('sc.runtime_missing', { rt: info.runtime || '?' })}</Chip>
                <span className="mono" title={info.sha256}>SHA-256 {short(info.sha256)}</span>
                {info.size != null && <span>{kb(info.size)}</span>}
                {info.runs > 0 && <span>{t('sc.runs', { n: info.runs })}</span>}
              </span>
            </div>
          </div>
        ) : <p className="muted small" data-testid="ocs-none">{t('sc.none')}</p>}
        {info?.changed && (
          <div className="ai-warn" role="alert" data-testid="ocs-changed"><span className="ai-warn-ico" aria-hidden>⚠</span>
            <div><p>{t('sc.changed')}</p><Button size="sm" onClick={() => inspect(info.path)} data-testid="ocs-reconfirm">{t('sc.reconfirm')}</Button></div></div>
        )}
        {info && hasScript && !info.exists && <Result ok={false}>{scriptErr(t, 'not_found', info.name)}</Result>}
        <div className="input-row">
          <Button variant="primary" icon={<IFolder size={15} />} onClick={choose} data-testid="ocs-choose">{hasScript ? t('sc.choose_other') : t('sc.choose')}</Button>
          {hasScript && <Button variant="danger" icon={<ITrash size={15} />} onClick={forget} data-testid="ocs-forget">{t('sc.forget')}</Button>}
        </div>
        <AnimatePresence initial={false}>{msg && <Result ok={msg.ok}>{msg.text}</Result>}</AnimatePresence>
        <Row label={t('sc.timeout')} hint={t('sc.timeout_tip')}>
          <Slider value={settings.ocr_script?.timeout ?? 20} min={1} max={120} step={1} width={220} label={t('sc.timeout')} format={(v) => `${v} s`} onCommit={(v) => patch({ 'ocr_script.timeout': v })} />
        </Row>
        <Row label={t('ocs.base64')} hint={t('ocs.base64_tip')}>
          <Switch checked={!!settings.ocr_script?.send_base64} label={t('ocs.base64')} onChange={(v) => patch({ 'ocr_script.send_base64': v })} />
        </Row>
      </Section>

      <OcrTestCard usable={usable} />
      <OcrContractCard />
      <OcrExamplesCard />

      <ConfirmScript p={pending} onCancel={() => setPending(null)} onOk={approve} title={t('ocs.confirm_title')} testid="ocs" />
    </div>
  )
}

function OcrTestCard({ usable }: { usable: boolean }) {
  const t = useT()
  const [mode, setMode] = useState<'single' | 'dual'>('single')
  const [source, setSource] = useState<'sample' | 'capture'>('sample')
  const [busy, setBusy] = useState(false)
  const [res, setRes] = useState<OcrScriptTest | null>(null)
  const [showJson, setShowJson] = useState(false)
  const run = async () => {
    setBusy(true); setRes(null)
    try { setRes(await api.post<OcrScriptTest>('/api/ocr-script/test', { mode, source })) }
    catch (e: any) { setRes({ ok: false, images: [], code: 'start', detail: String(e.message) === 'no_region' ? t('ocs.no_region') : String(e.message) }) }
    setBusy(false)
  }
  const chName = (c: string) => (c === 'a' ? t('ocs.ch_a') : c === 'b' ? t('ocs.ch_b') : t('sc.single'))
  return (
    <Section title={t('sc.test')} desc={t('ocs.test_tip')}>
      <Row label={t('sc.test_mode')}>
        <Segmented size="sm" value={mode} label={t('sc.test_mode')} onChange={setMode}
          options={[{ value: 'single', label: t('sc.single') }, { value: 'dual', label: t('sc.dual') }]} />
      </Row>
      <Row label={t('ocs.test_image')}>
        <Segmented size="sm" value={source} label={t('ocs.test_image')} onChange={setSource}
          options={[{ value: 'sample', label: t('ocs.test_sample') }, { value: 'capture', label: t('ocs.test_capture') }]} />
      </Row>
      <div className="input-row">
        <Button variant="primary" icon={<IRefresh size={15} />} busy={busy} disabled={!usable} onClick={run} data-testid="ocs-test">{t('sc.test_run')}</Button>
        {!usable && <span className="muted small">{t('sc.test_need')}</span>}
      </div>
      <AnimatePresence initial={false}>
        {res && (
          <motion.div className="ocs-results" initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0, height: 0 }} data-testid={res.ok ? 'ocs-test-out' : 'ocs-test-fail'}>
            {res.images.map((im) => (
              <div key={im.channel} className="ocs-res" data-testid={`ocs-res-${im.channel}`}>
                <div className="ocs-res-head"><strong>{chName(im.channel)}</strong><small className="muted">{im.width} × {im.height} px</small>
                  {res.ok && im.confidence != null && <Chip tone={im.confidence >= 70 ? 'ok' : im.confidence >= 45 ? 'warn' : 'err'} title={t('main.confidence')}>{Math.round(im.confidence)}%</Chip>}</div>
                <div className="ocs-figs">
                  <figure><figcaption>{t('ocs.thumb')}</figcaption><img src={im.thumb} alt={t('ocs.thumb')} data-testid="ocs-thumb" /></figure>
                  <figure><figcaption>{t('ocs.received')}</figcaption><img src={im.processed} alt={t('ocs.received')} className="checker" /></figure>
                </div>
                {res.ok && <div className="preview-read selectable" dir="auto"><b>{t('ocr.read')}</b> {im.text ? <span className="ocs-text">{im.text}</span> : <em className="muted">{t('main.no_text')}</em>}</div>}
              </div>
            ))}
            {res.ok
              ? <p className="muted small">{res.format === 'json' ? 'JSON' : t('sc.plain')} · {res.ms} ms
                  {' · '}<button type="button" className="linkish" onClick={() => setShowJson(!showJson)}>{showJson ? t('ocs.hide_json') : t('ocs.show_json')}</button></p>
              : <Result ok={false}><span data-testid="ocs-test-err">{scriptErr(t, res.code, res.detail)}</span></Result>}
            {res.ok && showJson && <pre className="sc-code selectable" dir="ltr" data-testid="ocs-json">{JSON.stringify(res.payload, null, 1)}</pre>}
          </motion.div>
        )}
      </AnimatePresence>
    </Section>
  )
}

function OcrContractCard() {
  const t = useT()
  return (
    <Section title={t('sc.contract')} desc={t('ocs.contract_tip')}>
      <div className="sc-contract" data-testid="ocs-contract">
        <p className="sc-contract-lead"><strong>{t('ocs.contract_lead')}</strong></p>
        <ol className="sc-steps">
          <li>{t('ocs.c_in')}<pre className="sc-code selectable" dir="ltr">{CONTRACT_IN}</pre></li>
          <li>{t('ocs.c_images')}</li>
          <li>{t('ocs.c_out')}<pre className="sc-code selectable" dir="ltr">{CONTRACT_OUT_JSON}</pre>{t('ocs.c_out_conf')}<pre className="sc-code selectable" dir="ltr">{CONTRACT_OUT_OBJ}</pre>{t('sc.c_out_txt')}<pre className="sc-code selectable" dir="ltr">{CONTRACT_OUT_TXT}</pre></li>
          <li>{t('ocs.c_dual')}</li>
          <li>{t('ocs.c_empty')}</li>
          <li>{t('ocs.c_after')}</li>
          <li>{t('sc.c_err')}</li>
          <li>{t('ocs.c_limits')}</li>
          <li>{t('sc.c_runtimes')}</li>
        </ol>
      </div>
    </Section>
  )
}

function OcrExamplesCard() {
  const t = useT()
  const toast = useStore((s) => s.toast)
  const [open, setOpen] = useState<string | null>(null)
  const copy = async (code: string) => { try { await navigator.clipboard.writeText(code); toast('ok', t('sc.copied')) } catch { toast('warn', t('toast.action_failed')) } }
  const save = async (file: string, code: string) => {
    if (!window.egt) return
    const p = await window.egt.app.saveFile(file, code)
    if (p) toast('ok', t('sc.saved_ex'))
  }
  return (
    <Section title={t('sc.examples')} desc={t('ocs.examples_tip')}>
      <div className="sc-examples">
        {EXAMPLES.map((x) => (
          <div key={x.file} className="sc-ex" data-testid={`ocs-ex-${x.file}`}>
            <div className="sc-ex-head">
              <span className="sc-file-ico"><ICode size={16} /></span>
              <div className="sc-ex-txt"><strong>{x.file}</strong><small className="muted">{x.lang} · {t(x.key)}</small></div>
              <Button size="sm" variant="ghost" onClick={() => setOpen(open === x.file ? null : x.file)}>{open === x.file ? t('sc.hide') : t('sc.view')}</Button>
              <Button size="sm" variant="ghost" icon={<ICopy size={14} />} onClick={() => copy(x.code)}>{t('sc.copy')}</Button>
              <Button size="sm" icon={<ISave size={14} />} onClick={() => save(x.file, x.code)}>{t('sc.save')}</Button>
            </div>
            <AnimatePresence initial={false}>
              {open === x.file && (
                <motion.pre className="sc-code sc-ex-code selectable" dir="ltr" initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }} exit={{ height: 0, opacity: 0 }}>{x.code}</motion.pre>
              )}
            </AnimatePresence>
          </div>
        ))}
      </div>
    </Section>
  )
}
