import { mapBackend } from '@/lib/backendMsg'
import { AnimatePresence } from 'motion/react'
import { useEffect, useState } from 'react'
import { api } from '@/api/client'
import { Button, Chip, Segmented, Switch, TextInput } from '@/components/ui'
import { useStore, useT } from '@/store'
import { Result, Row, Section } from './parts'

export function AiTab() {
  const t = useT()
  const ai = useStore((s) => s.settings)!.ai
  const cfgPath = useStore((s) => s.settings)!.config_path
  const patch = useStore((s) => s.patchSettings)
  const [f, setF] = useState({ gemini_key: ai.gemini_key, gemini_model: ai.gemini_model, ollama_url: ai.ollama_url, ollama_model: ai.ollama_model, context: ai.context })
  const [res, setRes] = useState<{ ok: boolean; text: string } | 'busy' | null>(null)
  const [saved, setSaved] = useState(false)
  useEffect(() => setF({ gemini_key: ai.gemini_key, gemini_model: ai.gemini_model, ollama_url: ai.ollama_url, ollama_model: ai.ollama_model, context: ai.context }), [ai.gemini_key, ai.gemini_model, ai.ollama_url, ai.ollama_model, ai.context])
  const save = async () => { await patch(Object.fromEntries(Object.entries(f).map(([k, v]) => [`ai.${k}`, v]))); setSaved(true); setTimeout(() => setSaved(false), 1600) }
  const test = async () => {
    await save(); setRes('busy')
    try { const r = await api.post<{ ok: boolean; message: string; ms?: number }>('/api/ai/test'); setRes({ ok: r.ok, text: mapBackend(r.message, t) + (r.ms ? `  (${r.ms} ms)` : '') }) } catch (e: any) { setRes({ ok: false, text: e.message }) }
  }
  return (
    <div className="s-page">
      <Section title={t('ai.title')} desc={t('ai.tip')} right={<Chip tone={ai.enabled ? 'accent' : 'default'}>{ai.enabled ? t('common.on') : t('common.off')}</Chip>}>
        <Row label={t('ai.enable')}><Switch checked={ai.enabled} label={t('ai.enable')} onChange={(v) => patch({ 'ai.enabled': v })} /></Row>
        <Row label={t('ai.provider')}><Segmented size="sm" value={ai.provider} label={t('ai.provider')} onChange={(v) => patch({ 'ai.provider': v })} options={[{ value: 'gemini', label: 'Gemini' }, { value: 'ollama', label: 'Ollama (local)' }]} /></Row>
        {ai.provider === 'gemini' ? (<>
          <Row label={t('ai.key')} hint={t('ai.key_tip')}><TextInput type="password" autoComplete="off" value={f.gemini_key} onChange={(e) => setF({ ...f, gemini_key: e.target.value })} placeholder={ai.env_key_found ? 'GEMINI_API_KEY ✔' : ''} style={{ width: 300 }} /></Row>
          <Row label={t('ai.model')}><TextInput value={f.gemini_model} onChange={(e) => setF({ ...f, gemini_model: e.target.value })} style={{ width: 220 }} /></Row>
        </>) : (<>
          <Row label="Ollama URL"><TextInput value={f.ollama_url} onChange={(e) => setF({ ...f, ollama_url: e.target.value })} style={{ width: 300 }} /></Row>
          <Row label={t('ai.model')}><TextInput value={f.ollama_model} onChange={(e) => setF({ ...f, ollama_model: e.target.value })} style={{ width: 220 }} /></Row>
        </>)}
        <Row label={t('ai.context')} stack><textarea className="textarea selectable" rows={3} value={f.context} onChange={(e) => setF({ ...f, context: e.target.value })} placeholder={t('ai.context_ph')} /></Row>
        <p className="muted small">{t('ai.env_note', { path: cfgPath, found: ai.env_key_found ? t('yes') : t('no') })}</p>
        <div className="input-row"><Button variant="primary" onClick={save}>{saved ? `✔ ${t('saved')}` : t('common.save')}</Button><Button busy={res === 'busy'} onClick={test}>{t('ai.test')}</Button></div>
        <AnimatePresence initial={false}>{res && res !== 'busy' && <Result ok={res.ok}>{res.text}</Result>}</AnimatePresence>
      </Section>
    </div>
  )
}
