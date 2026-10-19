import { AnimatePresence, motion } from 'motion/react'
import { useRef, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { AiTab } from '@/settings/Ai'
import { BugsTab } from '@/settings/About'
import { UpdatesTab } from '@/settings/Updates'
import { GeneralTab } from '@/settings/General'
import { HistoryTab } from '@/settings/History'
import { OcrTab } from '@/settings/Ocr'
import { ReplaceTab } from '@/settings/Replace'
import { TranslationTab } from '@/settings/Translation'
import { useStore, useT, type TabId } from '@/store'
import { IBug, IDownloadCloud, IHistory, ISliders, ILanguages, IReplace, IScan, ISparkles, IX } from './icons'
import { useFocusTrap } from './ui'

const TABS: { id: TabId; icon: ReactNode; Comp: () => ReactNode }[] = [
  { id: 'general', icon: <ISliders size={17} />, Comp: GeneralTab },
  { id: 'ocr', icon: <IScan size={17} />, Comp: OcrTab },
  { id: 'translation', icon: <ILanguages size={17} />, Comp: TranslationTab },
  { id: 'replace', icon: <IReplace size={17} />, Comp: ReplaceTab },
  { id: 'ai', icon: <ISparkles size={17} />, Comp: AiTab },
  { id: 'history', icon: <IHistory size={17} />, Comp: HistoryTab },
  { id: 'updates', icon: <IDownloadCloud size={17} />, Comp: UpdatesTab },
  { id: 'bugs', icon: <IBug size={17} />, Comp: BugsTab },
]

export function Drawer() {
  const t = useT()
  const { open, tab } = useStore((s) => s.drawer)
  const close = useStore((s) => s.closeDrawer)
  const setTab = useStore((s) => s.setTab)
  const ref = useRef<HTMLDivElement>(null)
  useFocusTrap(open, ref, close)
  const cur = TABS.find((x) => x.id === tab) ?? TABS[0]
  const Comp = cur.Comp
  const onKey = (e: React.KeyboardEvent) => {
    if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return
    const i = TABS.findIndex((x) => x.id === tab)
    const n = (i + (e.key === 'ArrowDown' ? 1 : -1) + TABS.length) % TABS.length
    setTab(TABS[n].id); e.preventDefault()
    ;(e.currentTarget.querySelectorAll('button')[n] as HTMLElement)?.focus()
  }
  return createPortal(
    <AnimatePresence>
      {open && (
        <motion.div className="drawer-layer" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0, transition: { duration: 0.2 } }}>
          <div className="scrim" onMouseDown={close} />
          <motion.aside ref={ref} role="dialog" aria-modal="true" aria-label={t('settings.title')} tabIndex={-1} className="drawer"
            initial={{ x: '100%' }} animate={{ x: 0 }} exit={{ x: '100%', transition: { duration: 0.22, ease: [0.4, 0, 1, 1] } }} transition={{ type: 'spring', stiffness: 380, damping: 40, mass: 0.9 }}>
            <nav className="drawer-nav" role="tablist" aria-orientation="vertical" aria-label={t('settings.title')} onKeyDown={onKey}>
              <div className="nav-head">
                <button type="button" className="close-btn" onClick={close} aria-label={t('common.close')} title={`${t('common.close')} (Esc)`}>
                  <IX size={15} /><span>{t('common.close')}</span>
                </button>
                <h3>{t('main.settings')}</h3>
              </div>
              {TABS.map((x) => (
                <button key={x.id} role="tab" aria-selected={tab === x.id} tabIndex={tab === x.id ? 0 : -1} className={tab === x.id ? 'on' : ''} onClick={() => setTab(x.id)}>
                  {tab === x.id && <motion.span layoutId="tab-pill" className="tab-pill" transition={{ type: 'spring', stiffness: 520, damping: 40 }} />}
                  <span className="tab-ico">{x.icon}</span><span className="tab-lbl">{t(`tab.${x.id}`)}</span>
                </button>
              ))}
            </nav>
            <div className="drawer-content">
              <header className="drawer-head">
                <h3>{t(`tab.${tab}`)}</h3>
              </header>
              <div className="drawer-scroll" role="tabpanel">
                <AnimatePresence mode="wait" initial={false}>
                  <motion.div key={tab} initial={{ opacity: 0, x: 18 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -12 }} transition={{ duration: 0.16, ease: [0.22, 0.9, 0.24, 1] }}>
                    <Comp />
                  </motion.div>
                </AnimatePresence>
              </div>
            </div>
          </motion.aside>
        </motion.div>
      )}
    </AnimatePresence>, document.body)
}
