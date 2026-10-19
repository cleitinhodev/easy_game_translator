import { mapBackend } from '@/lib/backendMsg'
import { AnimatePresence } from 'motion/react'
import { useCallback, useEffect, useState } from 'react'
import { api } from '@/api/client'
import { Button, Chip, Segmented, Select, TextInput } from '@/components/ui'
import { useStore, useT } from '@/store'
import { Result, Row, Section } from './parts'

export const GEMINI_MODELS = ['gemini-3.5-flash-lite', 'gemini-3.8-flash', 'gemini-flash-latest']
export const GEMINI_DEFAULT = GEMINI_MODELS[0]
export const AI_STUDIO = 'https://aistudio.google.com'
const OTHER = '__other__'
const cfg = (k: string) => `ai.${k}`          // caminho da configuração (não é chave de tradução)
const MASK = '••••••••'
const openExternal = (u: string) => (window.egt ? window.egt.app.openExternal(u) : window.open(u, '_blank', 'noopener'))
type T = ReturnType<typeof useT>
const ERR_CODES = ['no_key', 'bad_key', 'model_unavailable', 'bad_model', 'rate_limit', 'network', 'empty', 'http', 'ollama_down', 'ollama_model_missing', 'config', 'key_unreadable']

/** Resultado guardado como função do `t` atual: troca de idioma retraduz a mensagem já exibida. */
type Msg = { ok: boolean; text: (t: T) => string }
type TestRes = Msg | 'busy' | null
type EnvVar = { name: string; process: boolean; user: boolean; system: boolean }

function testText(r: { ok: boolean; code?: string; message: string; ms?: number }, t: T) {
  if (r.ok) return r.message + (r.ms ? `  (${r.ms} ms)` : '')
  return r.code && ERR_CODES.includes(r.code) ? t(`ai.err.${r.code}`) : mapBackend(r.message, t)
}

/** Remove uma chave guardada (com confirmação) — usado também na aba Tradução. */
export function useRemoveSecret() {
  const t = useT()
  const ask = useStore((s) => s.ask)
  return useCallback(async (path: string, confirmText: string): Promise<(Msg & { env?: EnvVar[] }) | null> => {
    if (!(await ask(confirmText, t('ai.key_remove'), true))) return null
    try {
      const r = await api.post<{ redacted: string[]; leftovers_removed: string[]; still_found: string[]; env?: EnvVar[] }>('/api/secrets/remove', { path, confirmed: true })
      const n = r.redacted.length + r.leftovers_removed.length
      return { ok: r.still_found.length === 0, text: (tt: T) => r.still_found.length ? tt('ai.key_still_found', { n: r.still_found.length }) : tt('ai.key_removed', { n }), env: r.env }
    } catch (e: any) { const m = String(e.message); return { ok: false, text: () => m } }
  }, [ask, t])
}

export function AiTab() {
  const t = useT()
  const settings = useStore((s) => s.settings)!
  const ai = settings.ai
  const patch = useStore((s) => s.patchSettings)
  const [ctx, setCtx] = useState(ai.context)
  const [saved, setSaved] = useState(false)
  useEffect(() => setCtx(ai.context), [ai.context])
  const mode = ai.mode
  return (
    <div className="s-page">
      <Section title={t('ai.title')} desc={t('ai.tip')} right={<Chip tone={mode !== 'off' ? 'accent' : 'default'}>{mode === 'off' ? t('common.off') : mode === 'gemini' ? 'Gemini' : 'Ollama'}</Chip>}>
        <Row label={t('ai.mode')} hint={t('ai.mode_tip')}>
          <Segmented size="sm" value={mode} label={t('ai.mode')} onChange={(v) => patch({ 'ai.mode': v })}
            options={[{ value: 'off', label: t('ai.mode_off') }, { value: 'gemini', label: 'Gemini' }, { value: 'ollama', label: 'Ollama' }]} />
        </Row>
        <Row label={t('ai.context')} stack><textarea className="textarea selectable" rows={2} value={ctx} onChange={(e) => setCtx(e.target.value)} placeholder={t('ai.context_ph')} /></Row>
        <div className="input-row"><Button size="sm" onClick={async () => { await patch({ 'ai.context': ctx }); setSaved(true); setTimeout(() => setSaved(false), 1600) }}>{saved ? `✔ ${t('saved')}` : t('common.save')}</Button></div>
      </Section>
      <GeminiCard />
      <OllamaCard />
      <p className="muted small">{t('ai.secure_note', { scheme: settings.secrets?.scheme === 'dpapi' ? 'Windows DPAPI' : settings.secrets?.scheme === 'keyring' ? 'keyring' : 'AES-GCM' })}</p>
    </div>
  )
}

function GeminiCard() {
  const t = useT()
  const settings = useStore((s) => s.settings)!
  const ai = settings.ai
  const state = settings.secrets?.state[cfg('gemini_key')] ?? (ai.gemini_key ? 'ok' : 'none')
  const patch = useStore((s) => s.patchSettings)
  const ask = useStore((s) => s.ask)
  const removeSecret = useRemoveSecret()
  const [key, setKey] = useState(ai.gemini_key)
  const known = GEMINI_MODELS.includes(ai.gemini_model)
  const [sel, setSel] = useState(known ? ai.gemini_model : OTHER)
  const [custom, setCustom] = useState(known ? '' : ai.gemini_model)
  const [res, setRes] = useState<TestRes>(null)
  const [saved, setSaved] = useState(false)
  const [env, setEnv] = useState<{ vars: EnvVar[]; platform: string } | null>(null)
  const [envMsg, setEnvMsg] = useState<Msg | null>(null)
  useEffect(() => setKey(ai.gemini_key), [ai.gemini_key, state])
  useEffect(() => { const k = GEMINI_MODELS.includes(ai.gemini_model); setSel(k ? ai.gemini_model : OTHER); if (!k) setCustom(ai.gemini_model) }, [ai.gemini_model])
  const loadEnv = useCallback(() => { api.get<{ vars: EnvVar[]; platform: string }>('/api/secrets/env').then(setEnv).catch(() => setEnv(null)) }, [])
  useEffect(() => { loadEnv() }, [loadEnv, ai.env_key_found])
  const model = (sel === OTHER ? custom : sel).trim()
  const save = async () => {
    const ch: Record<string, unknown> = {}
    if (key !== MASK && key.trim() && key !== ai.gemini_key) ch[cfg('gemini_key')] = key.trim()
    if (model && model !== ai.gemini_model) ch[cfg('gemini_model')] = model
    if (Object.keys(ch).length) await patch(ch)
    if (ch[cfg('gemini_key')]) setKey(MASK)
    setSaved(true); setTimeout(() => setSaved(false), 1600)
  }
  const test = async () => {
    await save(); setRes('busy')
    try { const r = await api.post<{ ok: boolean; code?: string; message: string; ms?: number }>('/api/ai/test', { provider: 'gemini', model }); setRes({ ok: r.ok, text: (tt: T) => testText(r, tt) }) } catch (e: any) { const m = String(e.message); setRes({ ok: false, text: () => m }) }
  }
  const remove = async () => {
    const r = await removeSecret(cfg('gemini_key'), t('ai.key_remove_confirm'))
    if (!r) return
    setKey(''); setRes(r); loadEnv()
  }
  const removeEnv = async (name: string) => {
    if (!(await ask(t('ai.env_remove_confirm', { name }), t('ai.env_remove'), true))) return
    try {
      const r = await api.post<{ removed_user: boolean; system_level: boolean }>('/api/secrets/env/remove', { name, confirmed: true })
      setEnvMsg({ ok: r.removed_user && !r.system_level, text: (tt: T) => r.system_level ? tt('ai.env_system', { name }) : tt('ai.env_removed', { name }) })
    } catch (e: any) { const m = String(e.message); setEnvMsg({ ok: false, text: () => m }) }
    loadEnv()
  }
  const vars = env?.vars ?? []
  return (
    <Section title={t('ai.gemini_title')} desc={t('ai.gemini_desc')} right={ai.mode === 'gemini' ? <Chip tone="accent">{t('ai.selected')}</Chip> : undefined}>
      <div className="ai-warn" role="note" data-testid="gemini-warning">
        <span className="ai-warn-ico" aria-hidden>⚠</span>
        <div><p>{t('ai.gemini_warn')}</p>
          <button type="button" className="link" onClick={() => openExternal(AI_STUDIO)}>{t('ai.gemini_warn_link')} ↗</button></div>
      </div>
      <Row label={t('ai.key')} hint={state === 'ok' ? t('ai.key_saved') : t('ai.key_tip')}>
        <div className="input-row">
          <TextInput type="password" autoComplete="off" spellCheck={false} value={key} onChange={(e) => setKey(e.target.value)} onFocus={() => { if (key === MASK) setKey('') }} onBlur={() => { if (!key && state === 'ok') setKey(MASK) }} style={{ width: 280 }} aria-label={t('ai.key')} />
          {state !== 'none' && <Button size="sm" variant="danger" onClick={remove} data-testid="gemini-remove">{t('ai.key_remove')}</Button>}
        </div>
      </Row>
      {state === 'unreadable' && <Result ok={false}>{t('ai.key_unreadable')}</Result>}
      {vars.map((v) => (
        <div key={v.name} className="ai-env" data-testid="env-notice">
          <p className="small">{v.system && !v.user ? t('ai.env_system', { name: v.name }) : env?.platform === 'win32' && v.user ? t('ai.env_found', { name: v.name }) : t('ai.env_process', { name: v.name })}</p>
          {env?.platform === 'win32' && v.user && <Button size="sm" variant="danger" onClick={() => removeEnv(v.name)}>{t('ai.env_remove')}</Button>}
        </div>
      ))}
      <AnimatePresence initial={false}>{envMsg && <Result ok={envMsg.ok}>{envMsg.text(t)}</Result>}</AnimatePresence>
      <Row label={t('ai.model')}>
        <div className="input-row">
          <Select value={sel} width={230} label={t('ai.model')} onChange={setSel}
            options={[...GEMINI_MODELS.map((m) => ({ value: m, label: m, sub: m === GEMINI_DEFAULT ? t('ai.recommended') : undefined })), { value: OTHER, label: t('ai.model_other') }]} />
          {sel === OTHER && <TextInput value={custom} onChange={(e) => setCustom(e.target.value)} placeholder="gemini-…" style={{ width: 200 }} aria-label={t('ai.model_custom')} />}
        </div>
      </Row>
      <div className="input-row">
        <Button variant="primary" onClick={save}>{saved ? `✔ ${t('saved')}` : t('common.save')}</Button>
        <Button busy={res === 'busy'} onClick={test} data-testid="test-gemini">{t('ai.test_gemini')}</Button>
      </div>
      <AnimatePresence initial={false}>{res && res !== 'busy' && <Result ok={res.ok}>{res.text(t)}</Result>}</AnimatePresence>
    </Section>
  )
}

function OllamaCard() {
  const t = useT()
  const ai = useStore((s) => s.settings)!.ai
  const patch = useStore((s) => s.patchSettings)
  const [url, setUrl] = useState(ai.ollama_url)
  const [models, setModels] = useState<string[]>([])
  const [status, setStatus] = useState<'checking' | 'up' | 'down'>('checking')
  const [sel, setSel] = useState(ai.ollama_model)
  const [custom, setCustom] = useState('')
  const [res, setRes] = useState<TestRes>(null)
  const [saved, setSaved] = useState(false)
  useEffect(() => setUrl(ai.ollama_url), [ai.ollama_url])
  useEffect(() => setSel(ai.ollama_model), [ai.ollama_model])
  const check = useCallback(async (u: string) => {
    setStatus('checking')
    try { const r = await api.post<{ server: boolean; models: string[] }>('/api/ai/ollama/status', { url: u }); setModels(r.models); setStatus(r.server ? 'up' : 'down') } catch { setModels([]); setStatus('down') }
  }, [])
  useEffect(() => { check(ai.ollama_url) }, [check, ai.ollama_url])
  const opts = [...new Set([...models, ...(ai.ollama_model && ai.ollama_model !== OTHER ? [ai.ollama_model] : [])])]
  const model = (sel === OTHER ? custom : sel).trim()
  const save = async () => {
    const ch: Record<string, unknown> = {}
    if (url.trim() && url.trim() !== ai.ollama_url) ch[cfg('ollama_url')] = url.trim()
    if (model && model !== ai.ollama_model) ch[cfg('ollama_model')] = model
    if (Object.keys(ch).length) await patch(ch)
    setSaved(true); setTimeout(() => setSaved(false), 1600)
  }
  const test = async () => {
    setRes('busy')
    try { const r = await api.post<{ ok: boolean; code?: string; message: string; ms?: number }>('/api/ai/test', { provider: 'ollama', url: url.trim(), model }); setRes({ ok: r.ok, text: (tt: T) => testText(r, tt) }) } catch (e: any) { const m = String(e.message); setRes({ ok: false, text: () => m }) }
  }
  return (
    <Section title={t('ai.ollama_title')} desc={t('ai.ollama_desc')} right={ai.mode === 'ollama' ? <Chip tone="accent">{t('ai.selected')}</Chip> : undefined}>
      <Row label={t('ai.ollama_url')}>
        <div className="input-row">
          <TextInput value={url} onChange={(e) => setUrl(e.target.value)} onBlur={() => check(url.trim())} style={{ width: 240 }} aria-label={t('ai.ollama_url')} spellCheck={false} />
          <span className={`ai-status ${status}`} data-testid="ollama-status"><i className="dot" />{status === 'checking' ? t('ai.ollama_checking') : status === 'up' ? t('ai.ollama_running') : t('ai.ollama_down')}</span>
          <Button size="sm" variant="ghost" onClick={() => check(url.trim())}>{t('ai.ollama_refresh')}</Button>
        </div>
      </Row>
      <Row label={t('ai.model')} hint={status === 'up' && !models.length ? t('ai.ollama_no_models') : undefined}>
        <div className="input-row">
          <Select value={sel} width={230} label={t('ai.model')} onChange={setSel} placeholder={t('ai.model')}
            options={[...opts.map((m) => ({ value: m, label: m, sub: models.length && !models.includes(m) ? t('ai.ollama_not_installed') : undefined })), { value: OTHER, label: t('ai.model_other') }]} />
          {sel === OTHER && <TextInput value={custom} onChange={(e) => setCustom(e.target.value)} placeholder="llama3.2" style={{ width: 180 }} aria-label={t('ai.model_custom')} />}
        </div>
      </Row>
      <div className="input-row">
        <Button variant="primary" onClick={save}>{saved ? `✔ ${t('saved')}` : t('common.save')}</Button>
        <Button busy={res === 'busy'} onClick={test} data-testid="test-ollama">{t('ai.test_ollama')}</Button>
      </div>
      <AnimatePresence initial={false}>{res && res !== 'busy' && <Result ok={res.ok}>{res.text(t)}</Result>}</AnimatePresence>
    </Section>
  )
}
