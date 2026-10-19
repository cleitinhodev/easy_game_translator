import { AnimatePresence, motion } from 'motion/react'
import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { api } from '@/api/client'
import { IGear, IMousePointer, IX, IEye } from '@/components/icons'
import { FontPicker } from '@/components/FontPicker'
import { IconButton, RevealText, Segmented, Slider, Switch } from '@/components/ui'
import { isRtl } from '@/lib/i18n'
import type { Channel } from '@/lib/types'
import { useStore, useT } from '@/store'

function hexA(hex: string, a: number) {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex)
  if (!m) return `rgba(20,23,58,${a})`
  const n = parseInt(m[1], 16)
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${a})`
}

const BOX_FIT_SCALE = 0.6

/** Ajusta a fonte para o texto caber na célula (busca binária). */
function useFit(ref: React.RefObject<HTMLElement | null>, enabled: boolean, fixed: number, deps: unknown[]) {
  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    const fit = () => {
      if (!enabled) { el.style.fontSize = `${fixed}px`; return }
      const box = el.parentElement!
      let lo = 11, hi = 40
      while (lo < hi) {
        const mid = Math.ceil((lo + hi) / 2)
        el.style.fontSize = `${mid}px`
        if (el.scrollHeight <= box.clientHeight - 4 && el.scrollWidth <= box.clientWidth) lo = mid
        else hi = mid - 1
      }
      // fator de escala compacto (≈ -35% vs. o ajuste máximo): o texto acompanha o tamanho da janela, mas sobra respiro
      el.style.fontSize = `${Math.max(11, Math.round(lo * BOX_FIT_SCALE))}px`
    }
    fit()
    el.addEventListener('egt-refit', fit)      // fontes carregadas depois: reajusta
    const ro = new ResizeObserver(fit)
    ro.observe(el.parentElement!)
    return () => { ro.disconnect(); el.removeEventListener('egt-refit', fit) }
  }, [enabled, fixed, ...deps]) // eslint-disable-line react-hooks/exhaustive-deps
}

function Cell({ ch, label }: { ch: Channel; label?: string }) {
  const v = useStore((s) => s.channels[ch])
  const box = useStore((s) => s.settings!.box)
  const typewriter = useStore((s) => s.settings!.ui.typewriter)
  const t = useT()
  const ref = useRef<HTMLDivElement>(null)
  const ff = useStore((s) => s.profile?.font_family)
  useEffect(() => { const f = () => ref.current && ref.current.dispatchEvent(new Event('egt-refit')); document.fonts?.addEventListener('loadingdone', f); return () => document.fonts?.removeEventListener('loadingdone', f) }, [])
  useFit(ref, box.auto_font, box.font_size, [v.translated, box.show_original, ff])
  return (
    <div className="box-cell">
      {label && <span className="box-label">{label}</span>}
      <div className="box-fit">
        <div ref={ref} className={`box-text-wrap ${v.pending ? 'pending' : ''}`}>
          {v.translated ? <RevealText text={v.translated} rev={v.rev} typewriter={typewriter} className="box-text" style={{ color: box.text_color }} /> : <p className="box-wait" style={{ color: box.text_color }}>{t('box.waiting')}</p>}
        </div>
      </div>
      {v.pending && <span className="box-pending" aria-label={t('main.translating')} title={t('main.translating')}><span className="spinner" /></span>}
      {box.show_original && v.original && <p className="box-orig">{v.original}</p>}
    </div>
  )
}

const EDGES = ['n', 's', 'e', 'w', 'ne', 'nw', 'se', 'sw'] as const

export function BoxView() {
  const t = useT()
  const lang = useStore((s) => s.lang)
  const settings = useStore((s) => s.settings)
  const profile = useStore((s) => s.profile)
  const clickThrough = useStore((s) => s.clickThrough)
  const patchSettings = useStore((s) => s.patchSettings)
  const [panel, setPanel] = useState(false)
  const [hover, setHover] = useState(false)
  const lastGeo = useRef('')
  const ready = useStore((s) => s.ready)

  useEffect(() => {
    document.documentElement.style.background = 'transparent'
    document.body.style.background = 'transparent'
    document.documentElement.dataset.view = 'box'
  }, [])

  // persiste posição/tamanho no perfil (formato "x,y,w,h" em DIP)
  useEffect(() => {
    const id = setInterval(() => {
      const g = `${window.screenX},${window.screenY},${window.outerWidth},${window.outerHeight}`
      if (g !== lastGeo.current && lastGeo.current !== '') api.patch('/api/profile', { box_geometry: g }).catch(() => {})
      lastGeo.current = g
    }, 1200)
    return () => clearInterval(id)
  }, [])

  // click-through: o mouse atravessa a janela, exceto sobre os controles
  useEffect(() => {
    if (!clickThrough) return
    let over = false
    const mv = (e: MouseEvent) => {
      const now = !!(e.target as HTMLElement).closest('[data-interactive]')
      if (now !== over) { over = now; window.egt?.box.setHover(now) }
    }
    window.addEventListener('mousemove', mv)
    return () => window.removeEventListener('mousemove', mv)
  }, [clickThrough])

  const startResize = async (edge: string, e: React.PointerEvent) => {
    e.preventDefault(); e.stopPropagation()
    const el = e.currentTarget as HTMLElement
    el.setPointerCapture(e.pointerId)
    const b0 = await window.egt?.box.getBounds()
    if (!b0) return
    const sx = e.screenX, sy = e.screenY
    const mv = (ev: PointerEvent) => {
      const dx = ev.screenX - sx, dy = ev.screenY - sy
      let { x, y, width, height } = b0
      if (edge.includes('e')) width += dx
      if (edge.includes('s')) height += dy
      if (edge.includes('w')) { width -= dx; x += dx }
      if (edge.includes('n')) { height -= dy; y += dy }
      window.egt?.box.setBounds({ x, y, width, height })
    }
    const up = () => { el.removeEventListener('pointermove', mv); el.removeEventListener('pointerup', up) }
    el.addEventListener('pointermove', mv); el.addEventListener('pointerup', up)
  }

  if (!settings || !profile || !ready) return <div className="box-root" />
  const b = settings.box
  const dual = profile.mode === 'dual'
  const barVisible = (hover || panel) && !clickThrough
  const handleVisible = clickThrough

  return (
    <div className="box-root" data-interactive-root onMouseEnter={() => setHover(true)} onMouseLeave={() => setHover(false)}>
      <motion.div className={`box-card ${b.borderless ? 'borderless' : ''} ${clickThrough ? 'ct' : ''}`} style={{ background: hexA(b.bg_color, b.alpha) }} initial={{ opacity: 0, scale: 0.96 }} animate={{ opacity: 1, scale: 1 }} transition={{ duration: 0.25 }}>
        <div className={`box-content ${dual ? 'dual' : ''}`}>
          {dual ? <><Cell ch="a" label="A" /><Cell ch="b" label="B" /></> : <Cell ch="uni" />}
        </div>

        <AnimatePresence>
          {barVisible && (
            <motion.div className="box-bar no-drag" data-interactive initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }} transition={{ duration: 0.15 }}>
              <span className="box-grip" aria-hidden />
              <span className="grow" />
              <IconButton label={t('box.controls')} onClick={() => setPanel((p) => !p)} className={panel ? 'on' : ''}><IGear size={15} /></IconButton>
              <IconButton label={t('box.clickthrough')} onClick={() => window.egt?.box.setClickThrough(true)}><IMousePointer size={15} /></IconButton>
              <IconButton label={t('common.close')} onClick={() => window.egt?.box.close()} className="close"><IX size={15} /></IconButton>
            </motion.div>
          )}
        </AnimatePresence>

        <AnimatePresence>
          {handleVisible && (
            <motion.button type="button" className="box-ct-handle no-drag" data-interactive initial={{ opacity: 0, scale: 0.8 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0 }} onClick={() => window.egt?.box.setClickThrough(false)} aria-label={t('box.ct_off')}>
              <IEye size={14} /><span>{t('box.ct_off')}</span>
            </motion.button>
          )}
        </AnimatePresence>

        <AnimatePresence>
          {panel && !clickThrough && (
            <motion.div className="box-panel no-drag" dir={isRtl(lang) ? 'rtl' : 'ltr'} data-interactive initial={{ opacity: 0, y: -6, scale: 0.97 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, scale: 0.97 }} transition={{ type: 'spring', stiffness: 520, damping: 34 }}>
              <label><span>{t('box.opacity')}</span><Slider width={120} min={0.2} max={1} step={0.02} value={b.alpha} onChange={(v) => patchSettings({ 'box.alpha': v })} format={(v) => `${Math.round(v * 100)}%`} /></label>
              <label><span>{t('box.font')}</span><Slider width={120} min={10} max={64} step={1} value={b.font_size} onCommit={(v) => patchSettings({ 'box.font_size': v })} format={(v) => String(v)} /></label>
              <label><span>{t('font.family')}</span><FontPicker width={132} /></label>
              <label className="sw"><span>{t('box.auto_font')}</span><Switch checked={b.auto_font} label={t('box.auto_font')} onChange={(v) => patchSettings({ 'box.auto_font': v })} /></label>
              <label className="sw"><span>{t('box.original')}</span><Switch checked={b.show_original} label={t('box.original')} onChange={(v) => patchSettings({ 'box.show_original': v })} /></label>
              <label className="sw"><span>{t('box.borderless')}</span><Switch checked={b.borderless} label={t('box.borderless')} onChange={(v) => patchSettings({ 'box.borderless': v })} /></label>
              <label className="colors"><span>{t('box.text_color')}</span><input type="color" value={b.text_color} onChange={(e) => patchSettings({ 'box.text_color': e.target.value })} /></label>
              <label className="colors"><span>{t('box.bg_color')}</span><input type="color" value={b.bg_color} onChange={(e) => patchSettings({ 'box.bg_color': e.target.value })} /></label>
              <Segmented size="sm" value={profile.mode} onChange={(v) => api.patch('/api/profile', { mode: v })} options={[{ value: 'single', label: t('main.single') }, { value: 'dual', label: t('main.dual') }]} />
            </motion.div>
          )}
        </AnimatePresence>

        {!clickThrough && EDGES.map((e) => <i key={e} className={`rs rs-${e} no-drag`} onPointerDown={(ev) => startResize(e, ev)} />)}
      </motion.div>
    </div>
  )
}
