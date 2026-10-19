import { AnimatePresence, motion } from 'motion/react'
import { useEffect, useRef, useState } from 'react'
import { api } from '@/api/client'
import { startRecording, type Recorder } from '@/lib/audio'
import { useStore, useT } from '@/store'
import { PNG, PngIcon } from './icons'
import { Modal } from './Modal'
import { Button, RevealText, Select } from './ui'

// (nome, código de reconhecimento, código de tradução/narração)
const LANGS: [string, string, string][] = [
  ['Português', 'pt-BR', 'pt'], ['English', 'en-US', 'en'], ['Español', 'es-ES', 'es'], ['Français', 'fr-FR', 'fr'], ['Deutsch', 'de-DE', 'de'],
  ['বাংলা', 'bn-BD', 'bn'], ['日本語', 'ja-JP', 'ja'], ['中文 (Simplified)', 'zh-CN', 'zh-CN'], ['中文 (Traditional)', 'zh-TW', 'zh-TW'], ['한국어', 'ko-KR', 'ko'],
  ['हिन्दी', 'hi-IN', 'hi'], ['Русский', 'ru-RU', 'ru'], ['Bahasa Indonesia', 'id-ID', 'id'], ['Türkçe', 'tr-TR', 'tr'], ['العربية', 'ar-SA', 'ar'], ['اردو', 'ur-PK', 'ur'],
]
const opts = LANGS.map(([n]) => ({ value: n, label: n }))

export function ManualModal() {
  const t = useT()
  const open = useStore((s) => s.modal === 'manual')
  const setModal = useStore((s) => s.setModal)
  const [speak, setSpeak] = useState('Português')
  const [target, setTarget] = useState('English')
  const [src, setSrc] = useState('')
  const [dst, setDst] = useState('')
  const [rev, setRev] = useState(0)
  const [status, setStatus] = useState<{ text: string; tone: 'mute' | 'err' | 'ok' }>({ text: '', tone: 'mute' })
  const [busy, setBusy] = useState(false)
  const [recording, setRecording] = useState(false)
  const [level, setLevel] = useState(0)
  const [narrating, setNarrating] = useState(false)
  const seq = useRef(0)
  const rec = useRef<Recorder | null>(null)
  const audio = useRef<HTMLAudioElement | null>(null)
  const typewriter = useStore((s) => s.settings?.ui.typewriter ?? true)

  const doTranslate = async (text: string, tgtName: string) => {
    const my = ++seq.current
    if (!text.trim()) { setDst(''); setStatus({ text: '', tone: 'mute' }); return }
    setBusy(true); setStatus({ text: t('manual.translating'), tone: 'mute' })
    try {
      const tgt = LANGS.find((l) => l[0] === tgtName)![2]
      const r = await api.post<{ ok: boolean; text: string; engine: string; cached: boolean; ms: number; error?: string }>('/api/translate/manual', { text, tgt })
      if (my !== seq.current) return
      if (!r.ok) setStatus({ text: t('manual.fail', { err: (r.error || '').slice(0, 120) }), tone: 'err' })
      else { setDst(r.text); setRev((v) => v + 1); setStatus({ text: `${t('manual.done')} · ${r.cached ? t('main.cache') : r.engine} · ${r.ms} ms`, tone: 'ok' }) }
    } catch (e: any) { if (my === seq.current) setStatus({ text: t('manual.fail', { err: e.message }), tone: 'err' }) }
    finally { if (my === seq.current) setBusy(false) }
  }
  useEffect(() => {
    if (!open) return
    const id = setTimeout(() => doTranslate(src, target), src ? 550 : 0)
    return () => clearTimeout(id)
  }, [src, target, open]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (!open) { rec.current?.cancel(); rec.current = null; setRecording(false); audio.current?.pause() } }, [open])
  useEffect(() => {
    if (!recording) return
    const id = setInterval(() => setLevel(rec.current?.level() ?? 0), 60)
    return () => clearInterval(id)
  }, [recording])

  const stopMic = async () => {
    const r = rec.current
    if (!r) return
    rec.current = null; setRecording(false); setLevel(0)
    setStatus({ text: t('manual.recognizing'), tone: 'mute' }); setBusy(true)
    try {
      const wav = await r.stop()
      const lang = LANGS.find((l) => l[0] === speak)![1]
      const res = await api.raw<{ text: string }>(`/api/stt?lang=${encodeURIComponent(lang)}`, wav, 'audio/wav')
      setSrc(res.text)
    } catch (e: any) {
      const m = String(e.message || e)
      setStatus({ text: m === 'UnknownValueError' ? t('manual.err_unknown') : m === 'RequestError' ? t('manual.err_service') : m.includes('SpeechRecognition') ? t('manual.err_nomic_pkg') : t('manual.err_nodevice'), tone: 'err' })
    } finally { setBusy(false) }
  }
  const startMic = async () => {
    if (recording) { stopMic(); return }
    try {
      rec.current = await startRecording(() => stopMic())
      setRecording(true); setStatus({ text: t('manual.recording'), tone: 'mute' })
    } catch { setStatus({ text: t('manual.err_nodevice'), tone: 'err' }) }
  }
  const narrate = async () => {
    if (!dst.trim() || narrating) return
    setNarrating(true)
    try {
      const lang = LANGS.find((l) => l[0] === target)![2]
      const blob = await api.blob('/api/tts', { text: dst, lang })
      const a = new Audio(URL.createObjectURL(blob))
      audio.current = a
      a.onended = () => { setNarrating(false); URL.revokeObjectURL(a.src) }
      a.onerror = () => setNarrating(false)
      await a.play()
    } catch (e: any) {
      setNarrating(false)
      setStatus({ text: String(e.message || '').includes('gTTS') ? t('manual.err_notts_pkg') : t('manual.err_tts', { err: String(e.message).slice(0, 100) }), tone: 'err' })
    }
  }

  return (
    <Modal open={open} onClose={() => setModal(null)} title={t('manual.title')} width={820} className="manual">
      <div className="manual-grid">
        <section className="manual-col">
          <div className="manual-bar">
            <span className="opt-label">{t('manual.speak_in')}</span>
            <Select width={170} label={t('manual.speak_in')} value={speak} options={opts} onChange={setSpeak} />
            <Button tip={t('manual.mic_tip')} className={`mic-btn ${recording ? 'rec' : ''}`} icon={<span className="mic-ico"><PngIcon src={PNG.speak} size={18} /><i className="mic-level" style={{ transform: `scale(${1 + level * 1.6})`, opacity: recording ? 0.25 + level * 0.6 : 0 }} /></span>} onClick={startMic} aria-pressed={recording}>
              {recording ? t('manual.stop_rec') : t('manual.mic')}
            </Button>
          </div>
          <textarea className="manual-text selectable" value={src} onChange={(e) => setSrc(e.target.value)} placeholder={t('manual.placeholder')} aria-label={t('manual.placeholder')} autoFocus spellCheck={false} />
        </section>
        <section className="manual-col out">
          <div className="manual-bar">
            <span className="opt-label">{t('manual.translate_to')}</span>
            <Select width={170} label={t('manual.translate_to')} value={target} options={opts} onChange={setTarget} />
            <Button tip={t('manual.listen_tip')} busy={narrating} disabled={!dst.trim()} icon={<PngIcon src={PNG.listen} size={18} />} onClick={narrate}>{t('manual.listen')}</Button>
          </div>
          <div className="manual-out selectable">
            {dst ? <RevealText text={dst} rev={rev} typewriter={typewriter} className="manual-out-text" /> : <p className="placeholder">{busy ? t('manual.translating') : t('manual.out_ph')}</p>}
          </div>
        </section>
      </div>
      <AnimatePresence mode="wait" initial={false}>
        <motion.p key={status.text} className={`manual-status ${status.tone}`} initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: 0.14 }}>{status.text || '\u00a0'}</motion.p>
      </AnimatePresence>
    </Modal>
  )
}
