import { AnimatePresence, motion } from 'motion/react'
import { useEffect, useState } from 'react'
import { api } from '@/api/client'
import { ICopy, ICode, IFolder, ISave, ITrash, IRefresh } from '@/components/icons'
import { Modal } from '@/components/Modal'
import { Button, Chip, Segmented, Slider, Switch, TextInput } from '@/components/ui'
import { useStore, useT } from '@/store'
import type { ScriptInfo, ScriptInspect, Settings } from '@/lib/types'
import exMyMemory from '../../examples/scripts/mymemory_tradutor.py?raw'
import exGlossary from '../../examples/scripts/glossario_offline.js?raw'
import exBasic from '../../examples/scripts/modelo_basico.py?raw'
import { Result, Row, Section } from './parts'

type T = ReturnType<typeof useT>
const CODES = ['no_script', 'not_found', 'not_approved', 'hash_changed', 'no_runtime', 'unsupported', 'timeout', 'exit', 'bad_output', 'count', 'too_big', 'empty', 'script_error', 'start']
const EXAMPLES = [
  { file: 'mymemory_tradutor.py', key: 'sc.ex_mymemory', lang: 'Python', code: exMyMemory },
  { file: 'glossario_offline.js', key: 'sc.ex_glossary', lang: 'Node.js', code: exGlossary },
  { file: 'modelo_basico.py', key: 'sc.ex_basic', lang: 'Python', code: exBasic },
]
const FILTERS = [
  { name: 'Scripts', extensions: ['py', 'pyw', 'js', 'mjs', 'cjs', 'ps1', 'bat', 'cmd', 'sh', 'rb', 'php', 'lua', 'pl', 'exe'] },
  { name: '*', extensions: ['*'] },
]
const CONTRACT_IN = '{"version": 1, "mode": "dual",\n "inputs": ["Texto A", "Texto B"],\n "source_lang": "en", "target_lang": "pt",\n "channels": ["a", "b"]}'
const CONTRACT_OUT_JSON = '{"outputs": ["Tradução A", "Tradução B"]}'
const CONTRACT_OUT_TXT = 'Tradução A\n---\nTradução B'

/** Mensagem amigável para um erro do script (código do backend + detalhe curto). */
export function scriptErr(t: T, code?: string, detail?: string) {
  const c = code && CODES.includes(code) ? code : 'start'
  return t(`sc.err.${c}`, { detail: detail || '' }) + (detail && ['exit', 'script_error', 'count', 'unsupported', 'start'].includes(c) ? ` — ${detail}` : '')
}

export function modeName(t: T, s: Settings | null) {
  if (s?.script?.enabled) return t('sc.mode_script')
  if (s && s.ai.mode !== 'off') return `${t('sc.mode_ai')} (${s.ai.mode === 'gemini' ? 'Gemini' : 'Ollama'})`
  return t('sc.mode_translators')
}

const short = (h: string) => (h ? `${h.slice(0, 12)}…${h.slice(-6)}` : '—')
const kb = (n?: number) => (n == null ? '' : n < 1024 ? `${n} B` : `${(n / 1024).toFixed(1)} KB`)

export function ScriptsTab() {
  const t = useT()
  const settings = useStore((s) => s.settings)!
  const info = useStore((s) => s.script)
  const patch = useStore((s) => s.patchSettings)
  const toast = useStore((s) => s.toast)
  const ask = useStore((s) => s.ask)
  const [pending, setPending] = useState<ScriptInspect | null>(null)
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null)
  const load = async () => { try { useStore.setState({ script: await api.get<ScriptInfo>('/api/script') }) } catch { /* WS atualiza */ } }
  useEffect(() => { load() }, [])
  const on = !!settings.script?.enabled
  const hasScript = !!info?.path
  const usable = hasScript && !!info?.exists && !info?.changed

  const inspect = async (path: string) => {
    setMsg(null)
    const r = await api.post<ScriptInspect>('/api/script/inspect', { path })
    if (!r.ok) { setMsg({ ok: false, text: scriptErr(t, r.code, r.detail) }); return }
    setPending(r)
  }
  const choose = async () => {
    if (!window.egt) { toast('info', t('sc.need_electron')); return }
    const p = await window.egt.app.pickFile({ filters: FILTERS })
    if (p) await inspect(p)
  }
  const approve = async (p: ScriptInspect) => {
    const r = await api.post<{ ok: boolean; script?: ScriptInfo; settings?: Settings; code?: string; detail?: string }>('/api/script/approve', { path: p.path, sha256: p.sha256, confirmed: true, enable: true })
    setPending(null)
    if (!r.ok) { setMsg({ ok: false, text: scriptErr(t, r.code, r.detail) }); return }
    useStore.setState({ script: r.script!, settings: r.settings! })
    setMsg({ ok: true, text: t('sc.approved', { name: p.name }) })
  }
  const setOn = async (v: boolean) => {
    if (v && !hasScript) { await choose(); return }
    if (v && info && (info.changed || !info.exists)) { if (info.exists) await inspect(info.path); else setMsg({ ok: false, text: scriptErr(t, 'not_found', info.name) }); return }
    await patch({ 'script.enabled': v })
    load()
  }
  const forget = async () => {
    if (!(await ask(t('sc.forget_confirm'), t('sc.forget'), true))) return
    const r = await api.post<{ script: ScriptInfo; settings: Settings }>('/api/script/forget')
    useStore.setState({ script: r.script, settings: r.settings })
    setMsg(null)
  }

  return (
    <div className="s-page" data-testid="sc-page">
      <Section title={t('sc.title')} desc={t('sc.tip')}
        right={<Chip tone={on ? 'accent' : 'default'}>{on ? t('sc.on') : t('common.off')}</Chip>}>
        <div className="ai-warn sc-warn" role="alert" data-testid="sc-warning">
          <span className="ai-warn-ico" aria-hidden>⚠</span>
          <div><p><strong>{t('sc.warn_title')}</strong></p><p>{t('sc.warn_body')}</p></div>
        </div>
        <Row label={t('sc.use')} hint={t('sc.use_tip')}>
          <Switch checked={on} label={t('sc.use')} onChange={setOn} />
        </Row>
        <p className="muted small" data-testid="sc-mode">{t('sc.mode_now', { mode: modeName(t, settings) })}{!on && settings.ai.mode !== 'off' ? ` · ${t('sc.ai_will_off')}` : ''}</p>
      </Section>

      <Section title={t('sc.file')} desc={t('sc.file_tip')}>
        {hasScript && info ? (
          <div className={`sc-file ${info.changed || !info.exists ? 'bad' : ''}`} data-testid="sc-file">
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
        ) : <p className="muted small" data-testid="sc-none">{t('sc.none')}</p>}
        {info?.changed && (
          <div className="ai-warn" role="alert" data-testid="sc-changed"><span className="ai-warn-ico" aria-hidden>⚠</span>
            <div><p>{t('sc.changed')}</p><Button size="sm" onClick={() => inspect(info.path)} data-testid="sc-reconfirm">{t('sc.reconfirm')}</Button></div></div>
        )}
        {info && hasScript && !info.exists && <Result ok={false}>{scriptErr(t, 'not_found', info.name)}</Result>}
        <div className="input-row">
          <Button variant="primary" icon={<IFolder size={15} />} onClick={choose} data-testid="sc-choose">{hasScript ? t('sc.choose_other') : t('sc.choose')}</Button>
          {hasScript && <Button variant="danger" icon={<ITrash size={15} />} onClick={forget} data-testid="sc-forget">{t('sc.forget')}</Button>}
        </div>
        <AnimatePresence initial={false}>{msg && <Result ok={msg.ok}>{msg.text}</Result>}</AnimatePresence>
        <Row label={t('sc.timeout')} hint={t('sc.timeout_tip')}>
          <Slider value={settings.script?.timeout ?? 15} min={1} max={120} step={1} width={220} label={t('sc.timeout')} format={(v) => `${v} s`} onCommit={(v) => patch({ 'script.timeout': v })} />
        </Row>
      </Section>

      <TestCard usable={usable} />
      <ContractCard />
      <ExamplesCard />

      <ConfirmScript p={pending} onCancel={() => setPending(null)} onOk={approve} />
    </div>
  )
}

function TestCard({ usable }: { usable: boolean }) {
  const t = useT()
  const target = useStore((s) => s.profile?.target ?? 'pt')
  const [mode, setMode] = useState<'single' | 'dual'>('single')
  const [a, setA] = useState('The king awaits you in the throne room.')
  const [b, setB] = useState('Mira: I will bring the healing potions.')
  const [busy, setBusy] = useState(false)
  const [res, setRes] = useState<{ ok: boolean; outputs?: string[]; format?: string; ms?: number; code?: string; detail?: string } | null>(null)
  const run = async () => {
    setBusy(true); setRes(null)
    try { setRes(await api.post('/api/script/test', { inputs: mode === 'dual' ? [a, b] : [a], src: 'en', tgt: target })) }
    catch (e: any) { setRes({ ok: false, code: 'start', detail: String(e.message) }) }
    setBusy(false)
  }
  return (
    <Section title={t('sc.test')} desc={t('sc.test_tip')}>
      <Row label={t('sc.test_mode')}>
        <Segmented size="sm" value={mode} label={t('sc.test_mode')} onChange={setMode}
          options={[{ value: 'single', label: t('sc.single') }, { value: 'dual', label: t('sc.dual') }]} />
      </Row>
      <div className="sc-inputs">
        <TextInput value={a} maxLength={2000} onChange={(e) => setA(e.target.value)} aria-label={mode === 'dual' ? t('sc.input_a') : t('sc.input')} placeholder={mode === 'dual' ? t('sc.input_a') : t('sc.input')} className="selectable" dir="auto" data-testid="sc-in-a" />
        {mode === 'dual' && <TextInput value={b} maxLength={2000} onChange={(e) => setB(e.target.value)} aria-label={t('sc.input_b')} placeholder={t('sc.input_b')} className="selectable" dir="auto" data-testid="sc-in-b" />}
      </div>
      <div className="input-row">
        <Button variant="primary" icon={<IRefresh size={15} />} busy={busy} disabled={!usable} onClick={run} data-testid="sc-test">{t('sc.test_run')}</Button>
        {!usable && <span className="muted small">{t('sc.test_need')}</span>}
      </div>
      <AnimatePresence initial={false}>
        {res && (
          <Result ok={res.ok}>
            {res.ok
              ? <span data-testid="sc-test-out">{(res.outputs ?? []).map((o, i) => <span key={i} className="sc-out"><em>{(res.outputs?.length ?? 0) > 1 ? (i ? 'B' : 'A') : '→'}</em> <span className="selectable tr-out" dir="auto">{o || '—'}</span></span>)}
                  <small className="muted"> · {res.format === 'json' ? 'JSON' : t('sc.plain')} · {res.ms} ms</small></span>
              : <span data-testid="sc-test-err">{scriptErr(t, res.code, res.detail)}</span>}
          </Result>
        )}
      </AnimatePresence>
    </Section>
  )
}

function ContractCard() {
  const t = useT()
  return (
    <Section title={t('sc.contract')} desc={t('sc.contract_tip')}>
      <div className="sc-contract" data-testid="sc-contract">
        <p className="sc-contract-lead"><strong>{t('sc.contract_lead')}</strong></p>
        <ol className="sc-steps">
          <li>{t('sc.c_in')}<pre className="sc-code selectable" dir="ltr">{CONTRACT_IN}</pre></li>
          <li>{t('sc.c_out')}<pre className="sc-code selectable" dir="ltr">{CONTRACT_OUT_JSON}</pre>{t('sc.c_out_txt')}<pre className="sc-code selectable" dir="ltr">{CONTRACT_OUT_TXT}</pre></li>
          <li>{t('sc.c_single')}</li>
          <li>{t('sc.c_err')}</li>
          <li>{t('sc.c_limits')}</li>
          <li>{t('sc.c_runtimes')}</li>
        </ol>
      </div>
    </Section>
  )
}

function ExamplesCard() {
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
    <Section title={t('sc.examples')} desc={t('sc.examples_tip')}>
      <div className="sc-examples">
        {EXAMPLES.map((x) => (
          <div key={x.file} className="sc-ex" data-testid={`sc-ex-${x.file}`}>
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

function ConfirmScript({ p, onCancel, onOk }: { p: ScriptInspect | null; onCancel: () => void; onOk: (p: ScriptInspect) => void }) {
  const t = useT()
  const [trust, setTrust] = useState(false)
  useEffect(() => setTrust(false), [p])
  return (
    <Modal open={!!p} onClose={onCancel} width={560} title={t('sc.confirm_title')}
      footer={<><Button variant="ghost" onClick={onCancel}>{t('common.cancel')}</Button>
        <Button variant="primary" disabled={!trust} onClick={() => p && onOk(p)} data-testid="sc-confirm-ok">{t('sc.confirm_ok')}</Button></>}>
      {p && (
        <div className="sc-confirm" data-testid="sc-confirm">
          <div className="ai-warn" role="alert"><span className="ai-warn-ico" aria-hidden>⚠</span><div><p>{t('sc.warn_body')}</p></div></div>
          <dl className="sc-dl">
            <dt>{t('sc.f_name')}</dt><dd><strong>{p.name}</strong> {p.size != null && <small className="muted">({kb(p.size)})</small>}</dd>
            <dt>{t('sc.f_path')}</dt><dd className="selectable mono sc-wrap" dir="ltr">{p.path}</dd>
            <dt>SHA-256</dt><dd className="selectable mono sc-wrap" dir="ltr" data-testid="sc-confirm-sha">{p.sha256}</dd>
            <dt>{t('sc.f_runtime')}</dt><dd>{p.runtime_found ? <Chip tone="ok">{p.runtime}</Chip> : <Chip tone="warn">{t('sc.runtime_missing', { rt: p.runtime || '?' })}</Chip>}</dd>
          </dl>
          <p className="muted small">{t('sc.confirm_note')}</p>
          <label className="sc-check"><input type="checkbox" checked={trust} onChange={(e) => setTrust(e.target.checked)} data-testid="sc-trust" /> {t('sc.trust')}</label>
        </div>
      )}
    </Modal>
  )
}
