import { AnimatePresence, motion } from 'motion/react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { api } from '@/api/client'
import { IChevron, IDown, IGlobe, IKey, IMonitor, IUp, IWifiOff } from '@/components/icons'
import { Button, Chip, Select, Switch, TextInput } from '@/components/ui'
import { numLocale } from '@/lib/i18n'
import { useStore, useT } from '@/store'
import type { TrEngine, TrField, TrMeta, TrTest } from '@/lib/types'
import { Result, Row, Section } from './parts'
import { useRemoveSecret } from './Ai'

type T = ReturnType<typeof useT>
const MASK = '••••••••'
const SAMPLE = 'Hello, adventurer! The gate is closed.'
const ERR_CODES = ['network', 'timeout', 'no_key', 'bad_key', 'quota', 'rate_limit', 'blocked', 'unsupported_lang', 'empty', 'echo', 'bad_response', 'server', 'http', 'config', 'low_quality']
const openExternal = (u: string) => (window.egt ? window.egt.app.openExternal(u) : window.open(u, '_blank', 'noopener'))
const tl = (t: T, k: string) => (k.startsWith('tr.') ? t(k) : k)

/** Mensagem traduzida para um código de erro do backend (+ detalhe técnico curto, sem segredos). */
export function errText(t: T, code: string | undefined, detail?: string) {
  const c = code && ERR_CODES.includes(code) ? code : 'http'
  return t(`tr.err.${c}`) + (detail ? ` (${detail})` : '')
}

function useFormat() {
  const lang = useStore((s) => s.lang)
  return useMemo(() => {
    const nf = new Intl.NumberFormat(numLocale(lang))
    let regions: Intl.DisplayNames | null = null
    try { regions = new Intl.DisplayNames([lang], { type: 'region' }) } catch { regions = null }
    return { n: (x: number) => nf.format(x), country: (c: string) => (c && regions ? regions.of(c) ?? c : c) }
  }, [lang])
}

function limitText(t: T, m: TrMeta, n: (x: number) => string) {
  const { period, amount } = m.limit
  return t(`tr.lim.${period}`, { n: n(amount) })
}

function kindChip(t: T, m: TrMeta) {
  if (m.kind === 'free') return <Chip tone="ok">{t('tr.k.free')}</Chip>
  if (m.kind === 'key') return <Chip tone="accent">{t('tr.k.key')}</Chip>
  if (m.kind === 'self') return <Chip>{t('tr.k.self')}</Chip>
  return <Chip>{t('tr.k.offline')}</Chip>
}

export function TranslationTab() {
  const t = useT()
  const s = useStore((st) => st.settings)!
  const engines = useStore((st) => st.engines)
  const patch = useStore((st) => st.patchSettings)
  const metrics = useStore((st) => st.metrics)
  const ask = useStore((st) => st.ask)
  const tr = s.translation
  const [open, setOpen] = useState<Record<string, boolean>>({})
  const [cache, setCache] = useState<{ count: number; hit_rate: number; stats: Record<string, number> } | null>(null)
  const [test, setTest] = useState<{ ok: boolean; text: string } | 'busy' | null>(null)
  const [results, setResults] = useState<Record<string, TrTest | 'busy'>>({})
  const profile = useStore((st) => st.profile)!

  const refreshEngines = useCallback(async () => useStore.setState({ engines: await api.get<TrEngine[]>('/api/translation/engines') }), [])
  const loadCache = async () => setCache(await api.get('/api/cache'))
  useEffect(() => { loadCache(); refreshEngines() }, []) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { const id = setInterval(refreshEngines, 4000); return () => clearInterval(id) }, [refreshEngines])

  const order = engines.map((e) => e.id)
  const move = (id: string, d: -1 | 1) => {
    const i = order.indexOf(id), j = i + d
    if (j < 0 || j >= order.length) return
    const next = [...order]; [next[i], next[j]] = [next[j], next[i]]
    useStore.setState({ engines: next.map((x) => engines.find((e) => e.id === x)!) })   // otimista (anima na hora)
    patch({ 'translation.order': next })
  }
  const toggle = (id: string, on: boolean) => {
    useStore.setState({ engines: engines.map((e) => (e.id === id ? { ...e, enabled: on } : e)) })
    patch({ 'translation.enabled': engines.filter((e) => (e.id === id ? on : e.enabled)).map((e) => e.id) })
  }
  const runOne = useCallback(async (id: string, text: string, src = 'en') => {
    setResults((r) => ({ ...r, [id]: 'busy' }))
    try {
      const r = await api.post<TrTest>('/api/translation/engine_test', { engine: id, text: text.trim() || SAMPLE, src, tgt: profile.target })
      setResults((x) => ({ ...x, [id]: r }))
    } catch (e: any) { setResults((x) => ({ ...x, [id]: { engine: id, ok: false, text: '', code: 'http', message: String(e.message), ms: 0 } })) }
    refreshEngines()
  }, [profile.target, refreshEngines])
  const testAll = async () => { for (const e of engines.filter((x) => x.enabled)) await runOne(e.id, SAMPLE) }
  const clearCache = async () => { if (await ask(t('tr.cache_confirm'), t('tr.cache_clear'), true)) { await api.del('/api/cache'); loadCache() } }
  const runChain = async () => {
    setTest('busy')
    try {
      const r = await api.post<{ ok: boolean; text: string; engine: string; ms: number; cached: boolean; error: string; codes?: Record<string, string> }>('/api/translation/test', { text: 'Hello world, this is a test.', src: 'en', tgt: profile.target })
      const name = (id: string) => engines.find((e) => e.id === id)?.name ?? id
      setTest({ ok: r.ok, text: r.ok ? `${r.text}  (${r.cached ? t('main.cache') : name(r.engine)}, ${r.ms} ms)` : Object.entries(r.codes ?? {}).map(([id, c]) => `${name(id)}: ${errText(t, c)}`).join(' · ') || r.error })
    } catch (e: any) { setTest({ ok: false, text: e.message }) }
    loadCache()
  }
  const on = engines.filter((e) => e.enabled).length
  return (
    <div className="s-page">
      <Section title={t('tr.engines')} desc={t('tr.engines_tip')}
        right={<Button size="sm" onClick={testAll} disabled={!on || Object.values(results).includes('busy')} data-testid="tr-test-all">{t('tr.test_all')}</Button>}>
        <p className="muted small tr-keys-note">{t('tr.keys_note', { path: s.config_path })}</p>
        <div className="eng-list" data-testid="tr-cards">
          <AnimatePresence initial={false}>
            {engines.map((e, i) => (
              <motion.div layout="position" key={e.id} transition={{ type: 'spring', stiffness: 520, damping: 38 }}>
                <ProviderCard e={e} index={i} last={i === engines.length - 1} open={!!open[e.id]} onOpen={(v) => setOpen((o) => ({ ...o, [e.id]: v }))}
                  onMove={(d) => move(e.id, d)} onToggle={(v) => toggle(e.id, v)} result={results[e.id]} onTest={(txt, src) => runOne(e.id, txt, src)}
                  cooldown={metrics?.engines?.[e.id]?.cooldown ?? e.cooldown} refresh={refreshEngines} />
              </motion.div>
            ))}
          </AnimatePresence>
        </div>
        <Row label={t('tr.cache_only')} hint={t('tr.cache_only_tip')}><Switch checked={tr.cache_only} label={t('tr.cache_only')} onChange={(v) => patch({ 'translation.cache_only': v })} /></Row>
      </Section>

      <Section title={t('tr.cache')} desc={cache ? t('tr.cache_stats', { n: cache.count, hits: cache.stats?.cache_hits ?? 0, rate: Math.round((metrics?.hit_rate ?? 0) * 100), live: metrics?.stats.live ?? 0, err: metrics?.stats.errors ?? 0 }) : ''}>
        <div className="input-row">
          <Button variant="danger" onClick={clearCache}>{t('tr.cache_clear')}</Button>
          <Button busy={test === 'busy'} onClick={runChain}>{t('tr.test')}</Button>
        </div>
        <AnimatePresence initial={false}>{test && test !== 'busy' && <Result ok={test.ok}>{test.text}</Result>}</AnimatePresence>
      </Section>
    </div>
  )
}

function statusChip(t: T, e: TrEngine, cooldown: number, res: TrTest | 'busy' | undefined) {
  if (res === 'busy') return <Chip tone="accent"><span className="spinner" />{t('tr.status.testing')}</Chip>
  if (cooldown > 0) return <Chip tone="warn" title={e.error ? errText(t, e.code) : undefined}>{t('tr.cooldown', { s: Math.ceil(cooldown) })}</Chip>
  if (!e.available) {
    const needsKey = e.meta?.kind === 'key' || (e.meta?.kind === 'self')
    return <Chip tone="warn" title={e.detail}>{needsKey ? t('tr.status.not_set') : t('tr.unavailable')}</Chip>
  }
  if (res && !res.ok) return <Chip tone="err" title={errText(t, res.code)}>{t('tr.status.offline')}</Chip>
  if (res?.ok || (e.last_ok ?? 0) > 0) return <Chip tone="ok"><i className="dot-s ok" />{t('tr.status.online')}</Chip>
  if (e.code) return <Chip tone="err" title={errText(t, e.code)}>{t('tr.status.error')}</Chip>
  return <Chip>{t('tr.status.untested')}</Chip>
}

function ProviderCard({ e, index, last, open, onOpen, onMove, onToggle, result, onTest, cooldown, refresh }: {
  e: TrEngine; index: number; last: boolean; open: boolean; onOpen: (v: boolean) => void; onMove: (d: -1 | 1) => void; onToggle: (v: boolean) => void
  result: TrTest | 'busy' | undefined; onTest: (text: string, src: string) => void; cooldown: number; refresh: () => void
}) {
  const t = useT()
  const fmt = useFormat()
  const m = e.meta
  const icon = m?.kind === 'offline' ? <IMonitor size={16} /> : m?.kind === 'key' ? <IKey size={16} /> : e.online ? <IGlobe size={16} /> : <IWifiOff size={16} />
  const bodyId = `tr-body-${e.id}`
  return (
    <div className={`tr-card ${e.enabled ? '' : 'off'} ${open ? 'open' : ''}`} data-testid={`tr-card-${e.id}`}>
      <div className="eng-row tr-head">
        <span className="eng-n">{index + 1}</span>
        <span className="eng-ico">{icon}</span>
        <button type="button" className="tr-title" aria-expanded={open} aria-controls={bodyId} onClick={() => onOpen(!open)} data-testid={`tr-open-${e.id}`}>
          <strong>{e.name}</strong>
          <span className="tr-tags">{m && kindChip(t, m)}{m && !m.official && <Chip tone="warn">{t('tr.unofficial')}</Chip>}</span>
        </button>
        {statusChip(t, e, cooldown, result)}
        <button type="button" className="mini-btn" aria-label={t('tr.up')} disabled={index === 0} onClick={() => onMove(-1)}><IUp size={15} /></button>
        <button type="button" className="mini-btn" aria-label={t('tr.down')} disabled={last} onClick={() => onMove(1)}><IDown size={15} /></button>
        <Switch checked={e.enabled} label={e.name} onChange={onToggle} />
        <button type="button" className={`mini-btn tr-chev ${open ? 'up' : ''}`} aria-label={t('tr.details')} aria-expanded={open} aria-controls={bodyId} onClick={() => onOpen(!open)}><IChevron size={15} /></button>
      </div>
      <AnimatePresence initial={false}>
        {open && m && (
          <motion.div id={bodyId} className="tr-body" initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }} exit={{ height: 0, opacity: 0 }} transition={{ duration: 0.22, ease: [0.22, 0.9, 0.24, 1] }}>
            <div className="tr-body-in">
              {!m.official && (
                <div className="ai-warn" role="note"><span className="ai-warn-ico" aria-hidden>⚠</span><div><p>{t('tr.unofficial_warn')}</p></div></div>
              )}
              <ul className="tr-facts">
                <li><span>{t('tr.privacy_label')}</span>{m.kind === 'offline' ? t('tr.privacy_local') : m.kind === 'self' ? t('tr.privacy_self') : e.id === 'mozhi' ? t('tr.privacy_mozhi') : `${m.receiver}${m.country ? ` (${fmt.country(m.country)})` : ''}`}</li>
                <li><span>{t('tr.limit_label')}</span>{limitText(t, m, fmt.n)}</li>
                {m.note && <li className="tr-note">{t(m.note)}</li>}
              </ul>
              {e.id === 'argos' ? <ArgosBox refresh={refresh} /> : <Fields e={e} m={m} refresh={refresh} />}
              {m.howto && (
                <div className="tr-howto" data-testid={`tr-howto-${e.id}`}>
                  <strong>{t('tr.howto_title')}</strong>
                  <p>{t(m.howto)}</p>
                  <div className="input-row">
                    {m.key_url && <Button size="sm" variant="ghost" onClick={() => openExternal(m.key_url)}>{t('tr.get_key')} ↗</Button>}
                    {m.docs && <Button size="sm" variant="ghost" onClick={() => openExternal(m.docs)}>{t('tr.docs')} ↗</Button>}
                  </div>
                </div>
              )}
              {!m.howto && (m.site || m.docs) && (
                <div className="input-row tr-links">
                  {m.site && <Button size="sm" variant="ghost" onClick={() => openExternal(m.site)}>{t('tr.site')} ↗</Button>}
                  {m.docs && <Button size="sm" variant="ghost" onClick={() => openExternal(m.docs)}>{t('tr.docs')} ↗</Button>}
                </div>
              )}
              <TestBox e={e} result={result} onTest={onTest} />
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

function TestBox({ e, result, onTest }: { e: TrEngine; result: TrTest | 'busy' | undefined; onTest: (text: string, src: string) => void }) {
  const t = useT()
  const [text, setText] = useState(SAMPLE)
  const [src, setSrc] = useState('en')
  const target = useStore((s) => s.profile?.target ?? 'pt')
  const langs = useStore((s) => s.snapshot?.languages ?? [])
  const tname = langs.find((l) => l.code === target)?.name ?? target
  return (
    <div className="tr-test" data-testid={`tr-test-${e.id}`}>
      <Row label={t('tr.test_sample')} hint={t('tr.test_hint', { lang: tname })} stack>
        <div className="input-row tr-test-row">
          <Select value={src} width={150} label={t('tr.test_src')} onChange={setSrc} options={[{ value: '', label: t('tr.src_auto') }, ...langs.map((l) => ({ value: l.code, label: l.name }))]} />
          <TextInput value={text} maxLength={2000} onChange={(ev) => setText(ev.target.value)} style={{ flex: '1 1 220px', minWidth: 180 }} dir="auto" aria-label={t('tr.test_sample')} className="selectable" />
          <Button variant="primary" busy={result === 'busy'} onClick={() => onTest(text, src)} data-testid={`tr-run-${e.id}`}>{t('tr.test_run')}</Button>
        </div>
      </Row>
      <AnimatePresence initial={false}>
        {result && result !== 'busy' && (
          <Result ok={result.ok}>
            {result.ok
              ? <><span className="selectable tr-out" dir="auto">{result.text}</span> <small className="muted">· {t('tr.status.online')} · {result.ms} ms{result.instance ? ` · ${result.instance.replace(/^https?:\/\//, '')}` : ''}</small></>
              : <>{errText(t, result.code)}{result.message ? <small className="muted tr-detail"> — {result.message}</small> : null}</>}
          </Result>
        )}
      </AnimatePresence>
    </div>
  )
}

function Fields({ e, m, refresh }: { e: TrEngine; m: TrMeta; refresh: () => void }) {
  const t = useT()
  const s = useStore((st) => st.settings)!
  const patch = useStore((st) => st.patchSettings)
  const removeSecret = useRemoveSecret()
  const tr = s.translation
  const init = useCallback(() => Object.fromEntries(m.fields.map((f) => [f.key, String(tr[f.key] ?? '')])), [m.fields, tr])
  const [vals, setVals] = useState<Record<string, string>>(init)
  const [msg, setMsg] = useState<{ ok: boolean; text: (tt: T) => string } | null>(null)
  const [saved, setSaved] = useState(false)
  useEffect(() => setVals(init()), [init])
  if (!m.fields.length) return null
  const isSecret = (f: TrField) => f.kind === 'secret' || f.kind === 'email'
  const state = (f: TrField) => s.secrets?.state[`translation.${f.key}`] ?? m.key_state?.[`translation.${f.key}`] ?? 'none'
  const save = async () => {
    const ch: Record<string, unknown> = {}
    for (const f of m.fields) {
      const v = (vals[f.key] ?? '').trim(), old = String(tr[f.key] ?? '')
      if (isSecret(f)) { if (v && v !== MASK) ch[`translation.${f.key}`] = v }
      else if (v !== old) ch[`translation.${f.key}`] = v
    }
    if (Object.keys(ch).length) await patch(ch)
    setSaved(true); setTimeout(() => setSaved(false), 1600); setMsg(null); refresh()
  }
  const remove = async (f: TrField) => {
    const r = await removeSecret(`translation.${f.key}`, t('ai.key_remove_confirm_other'))
    if (!r) return
    setVals((v) => ({ ...v, [f.key]: '' })); setMsg(r); refresh()
  }
  return (
    <div className="tr-fields">
      {m.fields.map((f) => (
        <Row key={f.key} label={t(f.label)} hint={isSecret(f) && state(f) === 'ok' ? t('tr.secret_saved') : undefined}>
          <div className="input-row">
            {f.kind === 'select'
              ? <Select value={vals[f.key] || f.options[0]} width={200} label={t(f.label)} onChange={(v) => setVals({ ...vals, [f.key]: v })}
                  options={f.options.map((o) => ({ value: o, label: o === 'duckduckgo' ? 'DuckDuckGo (Bing)' : o === 'yandex' ? 'Yandex' : o === 'google' ? 'Google' : o }))} />
              : <TextInput type={isSecret(f) ? 'password' : 'text'} autoComplete="off" spellCheck={false} value={vals[f.key] ?? ''} style={{ width: 300 }}
                  placeholder={f.placeholder ? tl(t, f.placeholder) : undefined} aria-label={t(f.label)} data-testid={`tr-field-${f.key}`}
                  onChange={(ev) => setVals({ ...vals, [f.key]: ev.target.value })}
                  onFocus={() => { if (isSecret(f) && vals[f.key] === MASK) setVals({ ...vals, [f.key]: '' }) }}
                  onBlur={() => { if (isSecret(f) && !vals[f.key] && state(f) === 'ok') setVals({ ...vals, [f.key]: MASK }) }} />}
            {isSecret(f) && state(f) !== 'none' && <Button size="sm" variant="danger" onClick={() => remove(f)} data-testid={`tr-remove-${f.key}`}>{t('ai.key_remove')}</Button>}
          </div>
        </Row>
      ))}
      {m.fields.some((f) => isSecret(f) && state(f) === 'unreadable') && <Result ok={false}>{t('ai.key_unreadable')}</Result>}
      <div className="input-row"><Button variant="primary" size="sm" onClick={save} data-testid={`tr-save-${e.id}`}>{saved ? `✔ ${t('saved')}` : t('common.save')}</Button></div>
      <AnimatePresence initial={false}>{msg && <Result ok={msg.ok}>{msg.text(t)}</Result>}</AnimatePresence>
    </div>
  )
}

function ArgosBox({ refresh }: { refresh: () => void }) {
  const t = useT()
  const profile = useStore((st) => st.profile)!
  const [argos, setArgos] = useState<{ installed: boolean; pairs: string[][] } | null>(null)
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null)
  const load = async () => setArgos(await api.get('/api/argos'))
  useEffect(() => { load() }, [])
  const install = async () => {
    setBusy(true); setMsg(null)
    try {
      const alpha = useStore.getState().snapshot!.alphabets.find((a) => a.key === profile.alphabet)
      const from = ({ 'abc(EN)': 'en', 'abc(BR)': 'pt', '你': 'zh', 'अ': 'hi', 'ب': 'ar', 'অ': 'bn', 'абв': 'ru', 'あ': 'ja', '가': 'ko' } as Record<string, string>)[alpha?.key ?? 'abc(EN)'] ?? 'en'
      const r = await api.post<{ message: string }>('/api/argos/install', { src: from, tgt: profile.target })
      setMsg({ ok: true, text: r.message }); load(); refresh()
    } catch (e: any) { setMsg({ ok: false, text: e.message }) } finally { setBusy(false) }
  }
  return (
    <div className="tr-fields">
      <p className="muted small">{argos && !argos.installed ? t('tr.argos_missing') : argos ? t('tr.argos_pairs', { n: argos.pairs.length, pairs: argos.pairs.map((p) => p.join('→')).join(', ') || '—' }) : ''}</p>
      <div className="input-row">
        <Button size="sm" busy={busy} disabled={!argos?.installed} onClick={install}>{t('tr.argos_install')}</Button>
        <Button size="sm" variant="ghost" onClick={load}>{t('ocr.rescan')}</Button>
      </div>
      <AnimatePresence initial={false}>{msg && <Result ok={msg.ok}>{msg.text}</Result>}</AnimatePresence>
    </div>
  )
}
