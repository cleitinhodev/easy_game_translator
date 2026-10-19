import { useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import { useStore, useT } from '@/store'
import { accelParts } from '@/lib/format'
import { Chip, Kbd, Select, Slider, Switch } from '@/components/ui'
import { FontPicker } from '@/components/FontPicker'
import { LOCALES, resolveLang, systemLanguages } from '@/lib/i18n'
import { Row, Section } from './parts'

const ISMAC = (window.egt?.platform ?? '') === 'darwin'

/** Converte um KeyboardEvent em acelerador do Electron (ex.: 'CommandOrControl+Alt+S'). */
function toAccelerator(e: KeyboardEvent): string | null {
  const mods: string[] = []
  if (ISMAC) { if (e.metaKey) mods.push('CommandOrControl'); if (e.ctrlKey) mods.push('Control') }
  else { if (e.ctrlKey) mods.push('CommandOrControl'); if (e.metaKey) mods.push('Super') }
  if (e.altKey) mods.push('Alt')
  if (e.shiftKey) mods.push('Shift')
  const c = e.code
  let key = ''
  if (/^Key[A-Z]$/.test(c)) key = c.slice(3)
  else if (/^Digit\d$/.test(c)) key = c.slice(5)
  else if (/^F\d{1,2}$/.test(c)) key = c
  else if (/^Numpad\d$/.test(c)) key = 'num' + c.slice(6)
  else {
    const map: Record<string, string> = { Space: 'Space', Enter: 'Return', Tab: 'Tab', Backspace: 'Backspace', Delete: 'Delete', Insert: 'Insert', Home: 'Home', End: 'End', PageUp: 'PageUp', PageDown: 'PageDown', ArrowUp: 'Up', ArrowDown: 'Down', ArrowLeft: 'Left', ArrowRight: 'Right', Minus: '-', Equal: '=', Comma: ',', Period: '.', Slash: '/', Semicolon: ';', Backquote: '`' }
    key = map[c] ?? ''
  }
  if (!key) return null
  if (!mods.length && !/^F\d/.test(key)) return null
  return [...mods, key].join('+')
}

function HotkeyInput({ value, onChange, status }: { value: string; onChange: (v: string) => void; status?: { ok: boolean; error?: string } }) {
  const t = useT()
  const [cap, setCap] = useState(false)
  const btn = useRef<HTMLButtonElement>(null)
  useEffect(() => {
    if (!cap) return
    const kd = (e: KeyboardEvent) => {
      e.preventDefault(); e.stopPropagation()
      if (e.key === 'Escape') { setCap(false); return }
      if (['Control', 'Alt', 'Shift', 'Meta'].includes(e.key)) return
      const a = toAccelerator(e)
      if (a) { onChange(a); setCap(false); btn.current?.focus() }
    }
    window.addEventListener('keydown', kd, true)
    return () => window.removeEventListener('keydown', kd, true)
  }, [cap, onChange])
  const platform = window.egt?.platform ?? 'linux'
  return (
    <div className="hk-input">
      <button ref={btn} type="button" className={`hk-btn ${cap ? 'cap' : ''}`} onClick={() => setCap(!cap)} onBlur={() => setCap(false)} aria-label={t('gen.hk_press')}>
        {cap ? <span className="hk-wait">{t('gen.hk_press')}</span> : accelParts(value, platform).map((p, i) => <Kbd key={i}>{p}</Kbd>)}
      </button>
      <AnimatePresence initial={false}>
        {status && (
          <motion.span initial={{ opacity: 0, scale: 0.8 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0 }}>
            {status.ok ? <Chip tone="ok">{t('gen.hk_active')}</Chip> : <Chip tone="err">{status.error === 'in-use' ? t('gen.hk_in_use') : status.error === 'disabled' ? t('gen.hk_off') : t('gen.hk_invalid')}</Chip>}
          </motion.span>
        )}
      </AnimatePresence>
    </div>
  )
}

export function GeneralTab() {
  const t = useT()
  const s = useStore((st) => st.settings)!
  const patch = useStore((st) => st.patchSettings)
  const profile = useStore((st) => st.profile)!
  const patchProfile = useStore((st) => st.patchProfile)
  const [hk, setHk] = useState<Record<string, { ok: boolean; error?: string }>>({})
  const isWin = (window.egt?.platform ?? '') === 'win32'

  const applyHotkeys = async (next: typeof s.hotkeys) => {
    const res = await window.egt?.hotkeys.apply(next as unknown as Record<string, string | boolean>)
    if (res) setHk(res)
  }
  useEffect(() => { applyHotkeys(s.hotkeys) }, []) // eslint-disable-line react-hooks/exhaustive-deps
  const setHotkey = async (key: 'toggle' | 'translate_now' | 'toggle_box', v: string) => {
    const r = await patch({ [`hotkeys.${key}`]: v })
    if (r) applyHotkeys(r.hotkeys)
  }

  return (
    <div className="s-page">
      <Section title={t('gen.interface')}>
        <Row label={t('gen.language')}>
          <Select width={230} align="right" value={s.ui.language} label={t('gen.language')} onChange={(v) => { patch({ 'ui.language': v }); window.egt?.app.setLanguage(v) }}
            options={[{ value: 'auto', label: t('gen.lang_auto'), sub: LOCALES.find((l) => l.code === resolveLang('auto', systemLanguages()))?.native }, ...LOCALES.map((l) => ({ value: l.code, label: <span lang={l.code} dir={l.rtl ? 'rtl' : 'ltr'}>{l.native}</span> }))]} />
        </Row>
        <Row label={t('font.family')} hint={t('font.family_tip')}><FontPicker width={230} /></Row>
        <p className="font-preview" aria-label={t('font.preview')}>The quick brown fox · Привет, мир · Γειά σου · こんにちは · 你好 · 안녕하세요 · مرحبا · สวัสดี · नमस्ते</p>
        <Row label={t('gen.intro')} hint={t('gen.intro_tip')}><Switch checked={s.ui.play_intro} label={t('gen.intro')} onChange={(v) => patch({ 'ui.play_intro': v })} /></Row>
        <Row label={t('gen.intro_full')} hint={t('gen.intro_full_tip')}><Switch checked={s.ui.intro_full !== false} disabled={!s.ui.play_intro} label={t('gen.intro_full')} onChange={(v) => patch({ 'ui.intro_full': v })} /></Row>
        <Row label={t('gen.topmost')} hint={t('gen.topmost_tip')}><Switch checked={s.ui.always_on_top} label={t('gen.topmost')} onChange={(v) => { patch({ 'ui.always_on_top': v }); window.egt?.win.setAlwaysOnTop(v) }} /></Row>
        <Row label={t('gen.clear_empty')} hint={t('gen.clear_empty_tip')}><Switch checked={s.ui.clear_on_empty} label={t('gen.clear_empty')} onChange={(v) => patch({ 'ui.clear_on_empty': v })} /></Row>
        <Row label={t('gen.tray')} hint={t('gen.tray_tip')}><Switch checked={s.ui.close_to_tray} label={t('gen.tray')} onChange={(v) => patch({ 'ui.close_to_tray': v })} /></Row>
        <Row label={t('gen.typewriter')} hint={t('gen.typewriter_tip')}><Switch checked={s.ui.typewriter} label={t('gen.typewriter')} onChange={(v) => patch({ 'ui.typewriter': v })} /></Row>
        <Row label={t('gen.motion')} hint={t('gen.motion_tip')}>
          <Select width={190} label={t('gen.motion')} value={s.ui.reduce_motion} onChange={(v) => patch({ 'ui.reduce_motion': v })} options={[{ value: 'system', label: t('gen.motion_system') }, { value: 'off', label: t('gen.motion_full') }, { value: 'on', label: t('gen.motion_reduced') }]} />
        </Row>
        {isWin && (
          <Row label={t('gen.material')} hint={t('gen.material_tip')}>
            <Select width={190} label={t('gen.material')} value={s.ui.material} onChange={(v) => { patch({ 'ui.material': v }); window.egt?.app.setMaterial(v) }} options={[{ value: 'auto', label: t('gen.material_auto') }, { value: 'mica', label: 'Mica' }, { value: 'acrylic', label: t('gen.material_acrylic') }, { value: 'none', label: t('gen.material_none') }]} />
          </Row>
        )}
      </Section>

      <Section title={t('gen.capture')}>
        <Row label={t('gen.interval')} hint={t('gen.interval_tip')}><Slider width={240} min={0.2} max={5} step={0.1} value={profile.interval} label={t('gen.interval')} format={(v) => `${v.toFixed(1)} s`} onCommit={(v) => patchProfile({ interval: v })} /></Row>
        <Row label={t('gen.stable')} hint={t('gen.stable_tip')}><Slider width={240} min={0} max={2000} step={50} value={s.filters.stable_ms} label={t('gen.stable')} format={(v) => `${v} ms`} onCommit={(v) => patch({ 'filters.stable_ms': v })} /></Row>
        <Row label={t('gen.min_chars')}><Slider width={240} min={1} max={15} step={1} value={s.filters.min_chars} label={t('gen.min_chars')} format={(v) => String(v)} onCommit={(v) => patch({ 'filters.min_chars': v })} /></Row>
        <Row label={t('gen.min_conf')} hint={t('gen.min_conf_tip')}><Slider width={240} min={0} max={90} step={5} value={s.filters.min_confidence} label={t('gen.min_conf')} format={(v) => `${v}%`} onCommit={(v) => patch({ 'filters.min_confidence': v })} /></Row>
      </Section>

      <Section title={t('gen.hotkeys')} desc={t('gen.hotkeys_desc')}>
        <Row label={t('gen.hotkeys_on')}><Switch checked={s.hotkeys.enabled} label={t('gen.hotkeys_on')} onChange={async (v) => { const r = await patch({ 'hotkeys.enabled': v }); if (r) applyHotkeys(r.hotkeys) }} /></Row>
        <Row label={t('gen.hk_toggle')}><HotkeyInput value={s.hotkeys.toggle} onChange={(v) => setHotkey('toggle', v)} status={hk.toggle} /></Row>
        <Row label={t('gen.hk_now')}><HotkeyInput value={s.hotkeys.translate_now} onChange={(v) => setHotkey('translate_now', v)} status={hk.translate_now} /></Row>
        <Row label={t('gen.hk_box')}><HotkeyInput value={s.hotkeys.toggle_box} onChange={(v) => setHotkey('toggle_box', v)} status={hk.toggle_box} /></Row>
        <p className="muted small">{t('gen.hk_format')}</p>
      </Section>

      <Section title={t('gen.box_title')} desc={t('gen.box_desc')}>
        <Row label={t('gen.box_exclude')} hint={t('gen.box_exclude_tip')}><Switch checked={s.box.exclude_from_capture} label={t('gen.box_exclude')} onChange={(v) => { patch({ 'box.exclude_from_capture': v }); window.egt?.box.setExclude(v) }} /></Row>
      </Section>
    </div>
  )
}
