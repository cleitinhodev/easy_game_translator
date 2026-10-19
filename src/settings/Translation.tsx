import { AnimatePresence, motion } from 'motion/react'
import { useEffect, useState } from 'react'
import { api } from '@/api/client'
import { IDown, IGlobe, IUp, IWifiOff } from '@/components/icons'
import { Button, Chip, Switch, TextInput } from '@/components/ui'
import { useStore, useT } from '@/store'
import type { TrEngine } from '@/lib/types'
import { Result, Row, Section } from './parts'

export function TranslationTab() {
  const t = useT()
  const s = useStore((st) => st.settings)!
  const engines = useStore((st) => st.engines)
  const patch = useStore((st) => st.patchSettings)
  const profile = useStore((st) => st.profile)!
  const metrics = useStore((st) => st.metrics)
  const ask = useStore((st) => st.ask)
  const tr = s.translation
  const [servers, setServers] = useState({ libre_url: tr.libre_url, libre_key: tr.libre_key, lingva_url: tr.lingva_url, microsoft_key: tr.microsoft_key, microsoft_region: tr.microsoft_region })
  const [saved, setSaved] = useState(false)
  const [argos, setArgos] = useState<{ installed: boolean; pairs: string[][] } | null>(null)
  const [argosBusy, setArgosBusy] = useState(false)
  const [argosMsg, setArgosMsg] = useState<{ ok: boolean; text: string } | null>(null)
  const [cache, setCache] = useState<{ count: number; hit_rate: number; stats: Record<string, number> } | null>(null)
  const [test, setTest] = useState<{ ok: boolean; text: string } | 'busy' | null>(null)

  const refreshEngines = async () => useStore.setState({ engines: await api.get<TrEngine[]>('/api/translation/engines') })
  const loadArgos = async () => setArgos(await api.get('/api/argos'))
  const loadCache = async () => setCache(await api.get('/api/cache'))
  useEffect(() => { loadArgos(); loadCache(); refreshEngines() }, []) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { const id = setInterval(refreshEngines, 4000); return () => clearInterval(id) }, [])

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
  const saveServers = async () => { await patch(Object.fromEntries(Object.entries(servers).map(([k, v]) => [`translation.${k}`, v]))); setSaved(true); setTimeout(() => setSaved(false), 1600); refreshEngines() }
  const installArgos = async () => {
    setArgosBusy(true); setArgosMsg(null)
    try {
      const alpha = useStore.getState().snapshot!.alphabets.find((a) => a.key === profile.alphabet)
      const from = ({ 'abc(EN)': 'en', 'abc(BR)': 'pt', '你': 'zh', 'अ': 'hi', 'ب': 'ar', 'অ': 'bn', 'абв': 'ru', 'あ': 'ja', '가': 'ko' } as Record<string, string>)[alpha?.key ?? 'abc(EN)'] ?? 'en'
      const r = await api.post<{ message: string }>('/api/argos/install', { src: from, tgt: profile.target })
      setArgosMsg({ ok: true, text: r.message }); loadArgos(); refreshEngines()
    } catch (e: any) { setArgosMsg({ ok: false, text: e.message }) } finally { setArgosBusy(false) }
  }
  const clearCache = async () => { if (await ask(t('tr.cache_confirm'), t('tr.cache_clear'), true)) { await api.del('/api/cache'); loadCache() } }
  const runTest = async () => {
    setTest('busy')
    try {
      const r = await api.post<{ ok: boolean; text: string; engine: string; ms: number; cached: boolean; error: string }>('/api/translation/test', { text: 'Hello world, this is a test.', src: 'en', tgt: profile.target })
      setTest({ ok: r.ok, text: r.ok ? `${r.text}  (${r.cached ? t('main.cache') : r.engine}, ${r.ms} ms)` : r.error })
    } catch (e: any) { setTest({ ok: false, text: e.message }) }
    loadCache()
  }
  const status = (e: TrEngine) => {
    const cd = metrics?.engines?.[e.id]?.cooldown ?? e.cooldown
    if (cd > 0) return <Chip tone="warn">{t('tr.cooldown', { s: Math.ceil(cd) })}</Chip>
    if (!e.available) return <Chip tone="err" title={e.detail}>{t('tr.unavailable')}</Chip>
    return <Chip tone="ok">{t('tr.ready')}</Chip>
  }
  return (
    <div className="s-page">
      <Section title={t('tr.engines')} desc={t('tr.engines_tip')}>
        <div className="eng-list">
          <AnimatePresence initial={false}>
            {engines.map((e, i) => (
              <motion.div layout="position" key={e.id} className={`eng-row ${e.enabled ? '' : 'off'}`} transition={{ type: 'spring', stiffness: 520, damping: 38 }}>
                <span className="eng-n">{i + 1}</span>
                <span className="eng-ico">{e.online ? <IGlobe size={16} /> : <IWifiOff size={16} />}</span>
                <div className="eng-name"><strong>{e.name}</strong><small>{e.online ? t('tr.online') : t('tr.offline_engine')}{!e.available && e.detail ? ` · ${e.detail}` : ''}</small></div>
                {status(e)}
                <button type="button" className="mini-btn" aria-label={t('tr.up')} disabled={i === 0} onClick={() => move(e.id, -1)}><IUp size={15} /></button>
                <button type="button" className="mini-btn" aria-label={t('tr.down')} disabled={i === engines.length - 1} onClick={() => move(e.id, 1)}><IDown size={15} /></button>
                <Switch checked={e.enabled} label={e.name} onChange={(v) => toggle(e.id, v)} />
              </motion.div>
            ))}
          </AnimatePresence>
        </div>
        <Row label={t('tr.cache_only')} hint={t('tr.cache_only_tip')}><Switch checked={tr.cache_only} label={t('tr.cache_only')} onChange={(v) => patch({ 'translation.cache_only': v })} /></Row>
      </Section>

      <Section title={t('tr.servers')} desc={t('tr.keys_note', { path: s.config_path })}>
        <Row label="LibreTranslate URL"><TextInput value={servers.libre_url} onChange={(e) => setServers({ ...servers, libre_url: e.target.value })} style={{ width: 300 }} /></Row>
        <Row label="LibreTranslate key"><TextInput type="password" value={servers.libre_key} onChange={(e) => setServers({ ...servers, libre_key: e.target.value })} style={{ width: 300 }} autoComplete="off" /></Row>
        <Row label="Lingva URL"><TextInput value={servers.lingva_url} onChange={(e) => setServers({ ...servers, lingva_url: e.target.value })} style={{ width: 300 }} /></Row>
        <Row label="Azure key" hint={t('tr.ms_tip')}><TextInput type="password" value={servers.microsoft_key} onChange={(e) => setServers({ ...servers, microsoft_key: e.target.value })} style={{ width: 300 }} autoComplete="off" /></Row>
        <Row label="Azure region"><TextInput value={servers.microsoft_region} onChange={(e) => setServers({ ...servers, microsoft_region: e.target.value })} style={{ width: 180 }} /></Row>
        <div className="input-row"><Button variant="primary" onClick={saveServers}>{saved ? `✔ ${t('saved')}` : t('common.save')}</Button></div>
      </Section>

      <Section title={t('tr.argos')} desc={argos && !argos.installed ? t('tr.argos_missing') : argos ? t('tr.argos_pairs', { n: argos.pairs.length, pairs: argos.pairs.map((p) => p.join('→')).join(', ') || '—' }) : ''}>
        <div className="input-row">
          <Button busy={argosBusy} disabled={!argos?.installed} onClick={installArgos}>{t('tr.argos_install')}</Button>
          <Button variant="ghost" onClick={loadArgos}>{t('ocr.rescan')}</Button>
        </div>
        <AnimatePresence initial={false}>{argosMsg && <Result ok={argosMsg.ok}>{argosMsg.text}</Result>}</AnimatePresence>
      </Section>

      <Section title={t('tr.cache')} desc={cache ? t('tr.cache_stats', { n: cache.count, rate: Math.round((metrics?.hit_rate ?? 0) * 100), live: metrics?.stats.live ?? 0, err: metrics?.stats.errors ?? 0 }) : ''}>
        <div className="input-row">
          <Button variant="danger" onClick={clearCache}>{t('tr.cache_clear')}</Button>
          <Button busy={test === 'busy'} onClick={runTest}>{t('tr.test')}</Button>
        </div>
        <AnimatePresence initial={false}>{test && test !== 'busy' && <Result ok={test.ok}>{test.text}</Result>}</AnimatePresence>
      </Section>
    </div>
  )
}
