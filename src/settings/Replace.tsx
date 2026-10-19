import { AnimatePresence, motion } from 'motion/react'
import { useEffect, useRef, useState } from 'react'
import { api } from '@/api/client'
import { IPlus, ITrash } from '@/components/icons'
import { Button, Chip, Switch, TextInput, Tip } from '@/components/ui'
import { useStore, useT } from '@/store'
import { Section } from './parts'

interface Rule { find: string; replace: string; regex: boolean; case: boolean; enabled: boolean; _k?: number }
let key = 1

export function ReplaceTab() {
  const t = useT()
  const [rules, setRules] = useState<Rule[]>([])
  const [keep, setKeep] = useState('')
  const [loaded, setLoaded] = useState(false)
  const [testText, setTestText] = useState('')
  const [testOut, setTestOut] = useState<{ replaced: string; terms: number } | null>(null)
  const [saved, setSaved] = useState(false)
  const toast = useStore((s) => s.toast)
  const dirty = useRef(false)

  useEffect(() => { api.get<{ rules: Rule[]; keep: string[] }>('/api/glossary').then((g) => { setRules(g.rules.map((r) => ({ ...r, _k: key++ }))); setKeep(g.keep.join('\n')); setLoaded(true) }) }, [])
  const save = async () => {
    try {
      const r = await api.put<{ rules: Rule[]; keep: string[] }>('/api/glossary', { rules: rules.filter((x) => x.find).map(({ _k, ...x }) => x), keep: keep.split('\n').map((x) => x.trim()).filter(Boolean) })
      setRules(r.rules.map((x) => ({ ...x, _k: key++ }))); dirty.current = false; setSaved(true); setTimeout(() => setSaved(false), 1600)
    } catch (e: any) { toast('error', e.message) }
  }
  const edit = (i: number, patch: Partial<Rule>) => { dirty.current = true; setRules((rs) => rs.map((r, j) => (j === i ? { ...r, ...patch } : r))) }
  const runTest = async () => { if (testText) setTestOut(await api.post('/api/glossary/test', { text: testText })) }
  useEffect(() => { if (!testText) setTestOut(null) }, [testText])
  if (!loaded) return <div className="s-page" />
  return (
    <div className="s-page">
      <Section title={t('rep.rules')} desc={t('rep.rules_tip')} right={<Button size="sm" icon={<IPlus size={15} />} onClick={() => { dirty.current = true; setRules((r) => [...r, { find: '', replace: '', regex: false, case: false, enabled: true, _k: key++ }]) }}>{t('rep.add')}</Button>}>
        <div className="rules">
          {rules.length > 0 && <div className="rule head"><span>{t('rep.find')}</span><span>{t('rep.replace')}</span><span>Regex</span><span>Aa</span><span /><span /></div>}
          <AnimatePresence initial={false}>
            {rules.map((r, i) => (
              <motion.div layout key={r._k} className={`rule ${r.enabled ? '' : 'off'}`} initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0, height: 0 }} transition={{ duration: 0.2 }}>
                <TextInput value={r.find} placeholder={t('rep.find')} onChange={(e) => edit(i, { find: e.target.value })} />
                <TextInput value={r.replace} placeholder={t('rep.replace')} onChange={(e) => edit(i, { replace: e.target.value })} />
                <Switch checked={r.regex} label="Regex" onChange={(v) => edit(i, { regex: v })} />
                <Switch checked={r.case} label="Aa" onChange={(v) => edit(i, { case: v })} />
                <Tip label={t('rep.toggle')}><span><Switch checked={r.enabled} label={t('rep.toggle')} onChange={(v) => edit(i, { enabled: v })} /></span></Tip>
                <button type="button" className="mini-btn" aria-label={t('rep.remove')} onClick={() => { dirty.current = true; setRules((rs) => rs.filter((_, j) => j !== i)) }}><ITrash size={15} /></button>
              </motion.div>
            ))}
          </AnimatePresence>
          {rules.length === 0 && <p className="placeholder">{t('rep.empty')}</p>}
        </div>
      </Section>
      <Section title={t('rep.keep')} desc={t('rep.keep_tip')}>
        <textarea className="textarea selectable" rows={5} value={keep} onChange={(e) => { dirty.current = true; setKeep(e.target.value) }} placeholder="Nina&#10;Kael&#10;Eldoria" spellCheck={false} aria-label={t('rep.keep')} />
        <div className="input-row"><Button variant="primary" onClick={save}>{saved ? `✔ ${t('saved')}` : t('common.save')}</Button><Chip>{keep.split('\n').filter((x) => x.trim()).length} {t('rep.protected')}</Chip></div>
      </Section>
      <Section title={t('rep.test')}>
        <div className="input-row"><TextInput value={testText} onChange={(e) => setTestText(e.target.value)} placeholder={t('rep.test_ph')} style={{ flex: 1 }} onKeyDown={(e) => { if (e.key === 'Enter') runTest() }} /><Button onClick={runTest}>{t('rep.test')}</Button></div>
        <AnimatePresence initial={false}>{testOut && <motion.div className="result ok selectable" initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>{testOut.replaced} <Chip>{testOut.terms} {t('rep.protected')}</Chip></motion.div>}</AnimatePresence>
        <p className="muted small">{t('rep.save_first')}</p>
      </Section>
    </div>
  )
}
