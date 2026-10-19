import { AnimatePresence, motion } from 'motion/react'
import { useEffect, useState } from 'react'
import { api } from '@/api/client'
import { IFolder, IRefresh, IScan, ICopy, ICheck } from '@/components/icons'
import { Button, Chip, Select, Slider, Switch, TextInput } from '@/components/ui'
import { useStore, useT } from '@/store'
import { Result, Row, Section } from './parts'

interface TessInfo { found: boolean; path: string; version: string; langs: string[]; missing: string[]; error?: string }

function PipCopy({ text }: { text: string }) {
  const [done, setDone] = useState(false)
  const cmd = text.split('  +')[0]
  return (
    <button type="button" className="pip" onClick={() => { navigator.clipboard?.writeText(cmd); setDone(true); setTimeout(() => setDone(false), 1200) }} title={cmd}>
      <code>{text}</code>{done ? <ICheck size={13} /> : <ICopy size={13} />}
    </button>
  )
}

export function OcrTab() {
  const t = useT()
  const profile = useStore((s) => s.profile)!
  const ocr = useStore((s) => s.ocr)
  const settings = useStore((s) => s.settings)!
  const patch = useStore((s) => s.patchSettings)
  const patchProfile = useStore((s) => s.patchProfile)
  const [tests, setTests] = useState<Record<string, { ok: boolean; msg: string } | 'busy'>>({})
  const [tess, setTess] = useState<TessInfo | null>(null)
  const [tessPath, setTessPath] = useState(settings.ocr.tesseract_path)
  const [prev, setPrev] = useState<{ image: string; processed: string; text?: string; ms?: number; confidence?: number | null; error?: string } | 'busy' | null>(null)
  const [scanning, setScanning] = useState(false)

  const rescan = async () => {
    setScanning(true)
    try { const r = await api.get<typeof ocr>('/api/ocr/engines'); useStore.setState({ ocr: r }) } finally { setTimeout(() => setScanning(false), 400) }
  }
  const detect = async () => setTess(await api.get<TessInfo>('/api/ocr/tesseract'))
  useEffect(() => { detect() }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const test = async (id: string) => {
    setTests((x) => ({ ...x, [id]: 'busy' }))
    try { const r = await api.post<{ ok: boolean; message: string }>('/api/ocr/test', { engine: id, alphabet: profile.alphabet }); setTests((x) => ({ ...x, [id]: { ok: r.ok, msg: r.message } })) } catch (e: any) { setTests((x) => ({ ...x, [id]: { ok: false, msg: e.message } })) }
  }
  const saveTess = async (p = tessPath) => { await patch({ 'ocr.tesseract_path': p.trim() }); await detect(); rescan() }
  const browse = async () => { const f = await window.egt?.app.pickFile({ filters: [{ name: 'Tesseract', extensions: ['exe', '*'] }] }); if (f) { setTessPath(f); saveTess(f) } }
  const preview = async () => {
    setPrev('busy')
    try { setPrev(await api.post('/api/capture/preview', { processed: true, read: true, max_width: 640 })) } catch (e: any) { setPrev({ image: '', processed: '', error: e.message === 'no_region' ? t('no_region') : e.message }) }
  }
  const pre = profile.preprocess

  return (
    <div className="s-page">
      <Section title={t('ocr.engine')} desc={t('ocr.engine_tip')} right={<Button size="sm" icon={<motion.span animate={{ rotate: scanning ? 360 : 0 }} transition={{ duration: 0.6 }} style={{ display: 'flex' }}><IRefresh size={15} /></motion.span>} onClick={rescan}>{t('ocr.rescan')}</Button>}>
        <div className="engine-list" role="radiogroup" aria-label={t('ocr.engine')}>
          {ocr.map((e) => {
            const sel = profile.ocr_engine === e.id
            const tr = tests[e.id]
            return (
              <motion.div layout key={e.id} className={`engine-card ${sel ? 'sel' : ''} ${e.available ? '' : 'na'}`} role="radio" aria-checked={sel} tabIndex={0}
                onClick={() => patchProfile({ ocr_engine: e.id })} onKeyDown={(ev) => { if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); patchProfile({ ocr_engine: e.id }) } }}>
                <span className="radio"><AnimatePresence>{sel && <motion.i initial={{ scale: 0 }} animate={{ scale: 1 }} exit={{ scale: 0 }} />}</AnimatePresence></span>
                <div className="engine-main">
                  <div className="engine-title"><strong>{e.name}</strong>
                    <AnimatePresence mode="wait" initial={false}><motion.span key={String(e.available)} initial={{ opacity: 0, scale: 0.85 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0 }}>
                      <Chip tone={e.available ? 'ok' : 'err'}>{e.available ? `✔ ${t('ocr.installed')}` : `✖ ${t('ocr.not_installed')}`}</Chip>
                    </motion.span></AnimatePresence>
                  </div>
                  <p className="muted">{e.note}</p>
                  {!e.available && <PipCopy text={e.pip_hint} />}
                  <AnimatePresence initial={false}>{tr && tr !== 'busy' && <Result ok={tr.ok}>{tr.msg}</Result>}</AnimatePresence>
                </div>
                <Button size="sm" busy={tr === 'busy'} disabled={!e.available} onClick={(ev) => { ev.stopPropagation(); test(e.id) }} variant="ghost">{t('ocr.test')}</Button>
              </motion.div>
            )
          })}
        </div>
      </Section>

      <Section title="Tesseract">
        <Row label={t('ocr.tess_path')} hint={t('ocr.tess_path_tip')} stack>
          <div className="input-row">
            <TextInput value={tessPath} onChange={(e) => setTessPath(e.target.value)} placeholder="C:\\Program Files\\Tesseract-OCR\\tesseract.exe" style={{ flex: 1 }} onKeyDown={(e) => { if (e.key === 'Enter') saveTess() }} />
            <Button icon={<IFolder size={16} />} onClick={browse}>{t('browse')}</Button>
            <Button onClick={detect} icon={<IScan size={16} />}>{t('ocr.detect')}</Button>
            <Button variant="primary" onClick={() => saveTess()}>{t('common.save')}</Button>
          </div>
        </Row>
        <AnimatePresence initial={false}>
          {tess && (
            <motion.div key={String(tess.found)} className={`tess-info ${tess.found ? 'ok' : 'err'}`} initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0, height: 0 }}>
              {tess.found ? (<>
                <div>✔ v{tess.version || '?'} · <code>{tess.path}</code></div>
                {tess.error && <div className="err-text">{tess.error}</div>}
                <div className="chips">{tess.langs.map((l) => <Chip key={l} tone="ok">{l}</Chip>)}</div>
                {tess.missing.length > 0 && <div className="muted">{t('ocr.langs_missing')}: {tess.missing.join(', ')}</div>}
              </>) : <div>✖ {t('ocr.tess_missing')}</div>}
            </motion.div>
          )}
        </AnimatePresence>
        <Row label={t('ocr.psm')} hint={t('ocr.psm_tip')}>
          <Select width={120} label={t('ocr.psm')} value={String(settings.ocr.tesseract_psm)} onChange={(v) => patch({ 'ocr.tesseract_psm': Number(v) })} options={['3', '4', '6', '7', '11', '13'].map((v) => ({ value: v, label: v }))} />
        </Row>
        <Row label={t('ocr.easy_gpu')}><Switch checked={settings.ocr.easyocr_gpu} label={t('ocr.easy_gpu')} onChange={(v) => patch({ 'ocr.easyocr_gpu': v })} /></Row>
      </Section>

      <Section title={t('ocr.pre')} desc={t('ocr.pre_tip')}>
        <Row label={t('ocr.scale')}><Slider width={240} min={1} max={3} step={0.1} value={pre.scale} label={t('ocr.scale')} format={(v) => `${v.toFixed(1)}×`} onCommit={(v) => patchProfile({ preprocess: { scale: Math.round(v * 10) / 10 } })} /></Row>
        <div className="toggle-grid">
          {(['grayscale', 'auto_invert', 'contrast', 'threshold', 'sharpen'] as const).map((k) => (
            <button key={k} type="button" className={`toggle-chip ${pre[k] ? 'on' : ''}`} aria-pressed={pre[k]} title={t(`ocr.${k}_tip`)} onClick={() => patchProfile({ preprocess: { [k]: !pre[k] } })}>
              <span className="tc-box">{pre[k] && <ICheck size={12} />}</span>{t(`ocr.${k}`)}
            </button>
          ))}
        </div>
        <div className="input-row" style={{ marginTop: 12 }}>
          <Button icon={<IScan size={16} />} busy={prev === 'busy'} onClick={preview}>{t('ocr.preview')}</Button>
        </div>
        <AnimatePresence initial={false}>
          {prev && prev !== 'busy' && (
            <motion.div className="preview-box" initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0, height: 0 }}>
              {prev.error ? <div className="err-text">{prev.error}</div> : (<>
                <figure><figcaption>{t('ocr.before')}</figcaption><img src={prev.image} alt="" /></figure>
                <figure><figcaption>{t('ocr.after')}</figcaption><img src={prev.processed} alt="" className="checker" /></figure>
                <div className="preview-read selectable"><b>{t('ocr.read')}</b> {prev.text ? <span>{prev.text}</span> : <em className="muted">{t('main.no_text')}</em>}{prev.ms != null && <Chip>{prev.ms} ms</Chip>}</div>
              </>)}
            </motion.div>
          )}
        </AnimatePresence>
      </Section>
    </div>
  )
}
