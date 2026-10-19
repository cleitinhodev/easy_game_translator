import { applyFont, FONTS, fontById } from '@/lib/fonts'
import { useStore, useT } from '@/store'
import { Select } from './ui'

/** Seletor da família de fonte do texto traduzido (cada opção é mostrada na própria fonte). */
export function FontPicker({ width = 150, className = '', compact = false, align = 'left' }: { width?: number | string; className?: string; compact?: boolean; align?: 'left' | 'right' }) {
  const t = useT()
  const id = useStore((s) => s.profile?.font_family ?? 'default')
  const patchProfile = useStore((s) => s.patchProfile)
  const cur = fontById(id)
  return (
    <Select width={width} align={align} menuWidth={compact ? 240 : undefined} className={`font-select ${compact ? 'compact' : ''} ${className}`} label={`${t('font.family')}: ${id === 'default' ? t('font.default') : cur.label}`} value={id}
      display={compact ? <span className="font-aa" style={cur.stack ? { fontFamily: cur.stack } : undefined}>Aa</span> : undefined}
      onChange={(v) => { applyFont(v); patchProfile({ font_family: v }) }}
      options={FONTS.map((f) => ({
        value: f.id,
        label: <span className="font-opt" style={f.stack ? { fontFamily: f.stack } : undefined}>{f.id === 'default' ? t('font.default') : f.label}<i className="font-sample" aria-hidden>Aa Ж あ</i></span>,
      }))} />
  )
}
