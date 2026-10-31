import { AnimatePresence, motion } from 'motion/react'
import ninaPng from '@/assets/nina.png'
import { useStore, useT } from '@/store'
import { IMenu } from './icons'
import { IconButton, Lights } from './ui'

export function Titlebar() {
  const t = useT()
  const running = useStore((s) => s.running)
  const conn = useStore((s) => s.conn)
  const version = useStore((s) => s.appVersion || s.snapshot?.app.version || '4.0.8')
  const platform = window.egt?.platform ?? 'linux'
  const openMenu = (e: React.MouseEvent) => {
    const r = (e.currentTarget as HTMLElement).getBoundingClientRect()
    window.egt?.win.showMenu({ x: r.left, y: r.bottom + 4 })
  }
  return (
    <header className="titlebar" data-platform={platform}>
      <div className="tb-left">
        <img className="tb-logo" src={ninaPng} alt="" draggable={false} />
        <div className="tb-title">
          <strong>Easy Game Translator</strong>
          <span className="tb-ver">v{version.split('.').slice(0, 2).join('.')}</span>
        </div>
        <Lights active={running} />
      </div>
      <div className="tb-right">
        <motion.div layout className={`status-pill ${conn !== 'online' ? 'off' : running ? 'run' : 'idle'}`} role="status" aria-live="polite">
          <span className="dot" />
          <AnimatePresence mode="wait" initial={false}>
            <motion.span key={conn !== 'online' ? 'off' : running ? 'r' : 'i'} initial={{ opacity: 0, y: 5 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -5 }} transition={{ duration: 0.14 }}>
              {conn !== 'online' ? t('status.offline_backend') : running ? t('status.running') : t('status.stopped')}
            </motion.span>
          </AnimatePresence>
        </motion.div>
        <div className="no-drag">
          <IconButton label={t('menu.title')} onClick={openMenu}><IMenu size={18} /></IconButton>
        </div>
      </div>
    </header>
  )
}
