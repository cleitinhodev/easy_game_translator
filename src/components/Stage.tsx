import { AnimatePresence, motion } from 'motion/react'
import ninaPng from '@/assets/nina.png'
import { bboxSize } from '@/lib/format'
import type { Channel } from '@/lib/types'
import { useStore, useT } from '@/store'
import { ICheck, ICopy, IRefresh, IZap } from './icons'
import { PNG, PngIcon } from './icons'
import { Button, Chip, IconButton, RevealText, Tip } from './ui'
import { useState } from 'react'

function Skeleton() {
  return <div className="skeleton" aria-hidden><i style={{ width: '82%' }} /><i style={{ width: '64%' }} /><i style={{ width: '38%' }} /></div>
}

function CopyBtn({ text }: { text: string }) {
  const t = useT()
  const [done, setDone] = useState(false)
  return (
    <IconButton label={done ? t('common.copied') : t('common.copy')} className="mini" disabled={!text} onClick={() => { navigator.clipboard?.writeText(text); setDone(true); setTimeout(() => setDone(false), 1200) }}>
      <AnimatePresence mode="wait" initial={false}>
        <motion.span key={done ? 'y' : 'n'} initial={{ scale: 0.5, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} exit={{ scale: 0.5, opacity: 0 }} transition={{ duration: 0.12 }} style={{ display: 'flex' }}>
          {done ? <ICheck size={14} /> : <ICopy size={14} />}
        </motion.span>
      </AnimatePresence>
    </IconButton>
  )
}

function Pane({ kind, ch, compact }: { kind: 'original' | 'translation'; ch: Channel; compact?: boolean }) {
  const t = useT()
  const v = useStore((s) => s.channels[ch])
  const running = useStore((s) => s.running)
  const typewriter = useStore((s) => s.settings?.ui.typewriter ?? true)
  const thumb = useStore((s) => s.thumbs[ch])
  const refreshThumb = useStore((s) => s.refreshThumb)
  const isTr = kind === 'translation'
  const text = isTr ? v.translated : v.original
  const rev = isTr ? v.rev : v.orev
  return (
    <div className={`pane ${kind} ${compact ? 'compact' : ''}`}>
      <div className="pane-head">
        <span className="pane-title"><i className="pane-dot" />{isTr ? t('main.translation') : t('main.original')}</span>
        <span className="pane-meta">
          <AnimatePresence initial={false} mode="popLayout">
            {isTr && v.rev > 0 && v.engine && (
              <motion.span key={`${v.rev}-e`} initial={{ opacity: 0, y: -4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
                <Chip tone={v.cached ? 'accent' : 'default'} title={v.cached ? t('main.from_cache') : v.engine}>{v.cached ? <><IZap size={11} /> {t('main.cache')}</> : v.engine}{v.ms ? ` · ${Math.round(v.ms)} ms` : ''}</Chip>
              </motion.span>
            )}
            {!isTr && v.confidence != null && v.orev > 0 && (
              <motion.span key={`${v.orev}-c`} initial={{ opacity: 0, y: -4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
                <Chip tone={v.confidence >= 70 ? 'ok' : v.confidence >= 45 ? 'warn' : 'err'} title={t('main.confidence')}>{Math.round(v.confidence)}%</Chip>
              </motion.span>
            )}
          </AnimatePresence>
          <AnimatePresence initial={false}>
            {isTr && v.pending && (
              <motion.span key="pend" initial={{ opacity: 0, scale: 0.85 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 0.85 }} transition={{ duration: 0.14 }}>
                <Chip tone="accent"><span className="spinner" /> {t('main.translating')}</Chip>
              </motion.span>
            )}
          </AnimatePresence>
          <CopyBtn text={text} />
        </span>
      </div>
      <div className="pane-body selectable">
        {!isTr && thumb && (
          <div className="thumb">
            <img src={thumb} alt={t('main.captured_region')} draggable={false} />
            <IconButton label={t('main.refresh_preview')} className="mini thumb-refresh" onClick={() => refreshThumb(ch)}><IRefresh size={13} /></IconButton>
          </div>
        )}
        {text ? (
          <RevealText text={text} rev={rev} typewriter={isTr && typewriter} className={`pane-text ${(v.empty && !isTr) || (isTr && v.pending) ? 'stale' : ''}`} />
        ) : running || (isTr && v.pending) ? (
          <Skeleton />
        ) : (
          <p className="placeholder">{t('main.waiting')}</p>
        )}
        {isTr && !v.ok && v.error && <div className="pane-error">⚠ {t('main.translate_fail')}</div>}
      </div>
    </div>
  )
}

function EmptyState() {
  const t = useT()
  const profile = useStore((s) => s.profile)!
  const select = useStore((s) => s.selectRegion)
  const dual = profile.mode === 'dual'
  return (
    <motion.div className="empty card" initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }} transition={{ duration: 0.3, ease: [0.22, 0.9, 0.24, 1] }}>
      <div className="empty-art">
        <span className="empty-glow" />
        <motion.img src={ninaPng} alt="" draggable={false} animate={{ y: [0, -6, 0] }} transition={{ duration: 4.5, repeat: Infinity, ease: 'easeInOut' }} />
      </div>
      <h2>{t('empty.title')}</h2>
      <p>{dual ? t('empty.desc_dual') : t('empty.desc')}</p>
      <ol className="steps">
        <li><b>1</b><span>{t('empty.step1')}</span></li>
        <li><b>2</b><span>{t('empty.step2')}</span></li>
        <li><b>3</b><span>{t('empty.step3')}</span></li>
      </ol>
      <div className="empty-cta">
        {dual ? (
          <><Button variant="primary" icon={<PngIcon src={PNG.a} size={16} />} onClick={() => select('a')}>{t('main.region_a')}</Button>
            <Button variant="primary" icon={<PngIcon src={PNG.b} size={16} />} onClick={() => select('b')}>{t('main.region_b')}</Button></>
        ) : (
          <Button variant="primary" icon={<PngIcon src={PNG.capture} size={20} />} onClick={() => select('uni')}>{t('main.region')}</Button>
        )}
      </div>
    </motion.div>
  )
}

function ChannelCard({ ch }: { ch: 'a' | 'b' }) {
  const t = useT()
  const profile = useStore((s) => s.profile)!
  const key = ch === 'a' ? 'region_a' : 'region_b'
  const size = bboxSize(profile[key])
  const select = useStore((s) => s.selectRegion)
  return (
    <motion.div className="channel card" initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: 0.28, delay: ch === 'b' ? 0.06 : 0, ease: [0.22, 0.9, 0.24, 1] }}>
      <div className="channel-head">
        <span className="channel-badge"><PngIcon src={ch === 'a' ? PNG.a : PNG.b} size={15} /></span>
        <strong>{ch === 'a' ? t('main.channel_a') : t('main.channel_b')}</strong>
        {size ? <Chip><bdi dir="ltr">{size.w}×{size.h}</bdi></Chip> : <Chip tone="warn">{t('main.no_region')}</Chip>}
        <span className="grow" />
        <Button size="sm" variant="ghost" icon={<PngIcon src={PNG.capture} size={15} />} onClick={() => select(ch)}>{size ? t('main.change') : t('main.region')}</Button>
      </div>
      {size ? (
        <div className="channel-panes">
          <Pane kind="original" ch={ch} compact /><Pane kind="translation" ch={ch} />
        </div>
      ) : (
        <div className="channel-empty"><Tip label={t('main.region_tip')}><Button variant="primary" icon={<PngIcon src={ch === 'a' ? PNG.a : PNG.b} size={16} />} onClick={() => select(ch)}>{ch === 'a' ? t('main.region_a') : t('main.region_b')}</Button></Tip></div>
      )}
    </motion.div>
  )
}

export function Stage() {
  const profile = useStore((s) => s.profile)
  if (!profile) return <div className="stage" />
  const dual = profile.mode === 'dual'
  const hasRegion = Object.keys(profile.channels).length > 0
  return (
    <main className="stage">
      <AnimatePresence mode="wait" initial={false}>
        {!hasRegion && !dual ? (
          <EmptyState key="empty" />
        ) : dual ? (
          <motion.div key="dual" className="stage-grid dual" initial={{ opacity: 0, scale: 0.985 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 0.985 }} transition={{ duration: 0.22 }}>
            <ChannelCard ch="a" /><ChannelCard ch="b" />
          </motion.div>
        ) : (
          <motion.div key="single" className="stage-grid single" initial={{ opacity: 0, scale: 0.985 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 0.985 }} transition={{ duration: 0.22 }}>
            <div className="card pane-card"><Pane kind="original" ch="uni" /></div>
            <div className="card pane-card accent"><Pane kind="translation" ch="uni" /></div>
          </motion.div>
        )}
      </AnimatePresence>
    </main>
  )
}
