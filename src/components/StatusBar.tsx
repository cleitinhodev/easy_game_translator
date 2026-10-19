import { motion } from 'motion/react'
import { accelParts, fmtMs } from '@/lib/format'
import { useStore, useT } from '@/store'
import { ICpu, IClock, IDatabase, IZap, IWifi, IWifiOff } from './icons'
import { AnimatedNumber, Kbd, Tip } from './ui'

export function StatusBar() {
  const t = useT()
  const m = useStore((s) => s.metrics)
  const profile = useStore((s) => s.profile)
  const ocr = useStore((s) => s.ocr)
  const hk = useStore((s) => s.settings?.hotkeys)
  const platform = window.egt?.platform ?? 'linux'
  const net = m?.net ?? 'unknown'
  const engineName = ocr.find((o) => o.id === (m?.ocr_engine ?? profile?.ocr_engine))?.name ?? '—'
  const netLabel = net === 'online' ? t('status.online') : net === 'offline' ? t('status.offline') : net === 'cache' ? t('status.cache_mode') : t('status.checking')
  return (
    <footer className="statusbar" role="status">
      <Tip label={t('status.net_tip')} side="top">
        <span className={`sb-item net ${net}`}>
          <motion.span key={net} initial={{ scale: 0.4, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} className="net-ico">{net === 'offline' ? <IWifiOff size={14} /> : <IWifi size={14} />}</motion.span>
          <i className="dot" />{netLabel}
        </span>
      </Tip>
      <Tip label={t('status.ocr_tip')} side="top"><span className="sb-item"><ICpu size={14} />{engineName}{m && m.ocr_ms > 0 && <em><AnimatedNumber value={m.ocr_ms} format={(n) => ` · ${Math.round(n)} ms`} /></em>}</span></Tip>
      <Tip label={t('status.latency_tip')} side="top"><span className="sb-item"><IClock size={14} />{t('status.latency')}<em><AnimatedNumber value={m?.latency_ms ?? 0} format={(n) => (n ? fmtMs(n) : '—')} /></em></span></Tip>
      <Tip label={t('status.cache_tip', { n: m?.cache_count ?? 0 })} side="top"><span className="sb-item"><IDatabase size={14} />{t('status.cache')}<em><AnimatedNumber value={(m?.hit_rate ?? 0) * 100} format={(n) => `${Math.round(n)}%`} /></em></span></Tip>
      <Tip label={t('status.fps_tip')} side="top"><span className="sb-item"><IZap size={14} /><em className="n"><AnimatedNumber value={m?.fps ?? 0} format={(n) => n.toFixed(1)} /></em>{t('status.cps')}</span></Tip>
      <span className="grow" />
      {hk?.enabled && (
        <span className="sb-item hotkeys">
          <span>{t('hk.toggle_short')} <bdi dir="ltr">{accelParts(hk.toggle, platform).map((p, i) => <Kbd key={i}>{p}</Kbd>)}</bdi></span>
          <span>{t('hk.now_short')} <bdi dir="ltr">{accelParts(hk.translate_now, platform).map((p, i) => <Kbd key={i}>{p}</Kbd>)}</bdi></span>
        </span>
      )}
    </footer>
  )
}
