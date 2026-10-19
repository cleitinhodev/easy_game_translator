import { AnimatePresence, MotionConfig, motion } from 'motion/react'
import { useEffect, useState } from 'react'
import { Drawer } from './components/Drawer'
import { HelpModal } from './components/HelpModal'
import { Intro } from './components/Intro'
import { ManualModal } from './components/ManualModal'
import { ConfirmHost } from './components/Modal'
import { ProfileModal } from './components/ProfileModal'
import { Stage } from './components/Stage'
import { StatusBar } from './components/StatusBar'
import { Titlebar } from './components/Titlebar'
import { Toasts } from './components/Toasts'
import { Toolbar } from './components/Toolbar'
import { Button } from './components/ui'
import { useStore, useT } from './store'
import { applyFont } from './lib/fonts'
import { isRtl } from './lib/i18n'
import { BoxView } from './views/BoxView'
import { FlashView, SelectView } from './views/SelectView'

let introShown = false

function useDocumentAttrs() {
  const settings = useStore((s) => s.settings)
  const lang = useStore((s) => s.lang)
  const fs = useStore((s) => s.profile?.font_size)
  useEffect(() => {
    const el = document.documentElement
    el.lang = lang
    el.dir = isRtl(lang) ? 'rtl' : 'ltr'
    el.dataset.platform = window.egt?.platform ?? 'linux'
    window.egt?.getConfig().then((c) => { el.dataset.material = c.material })
    if (!window.egt) el.dataset.material = 'none'
  }, [lang])
  useEffect(() => {
    const m = settings?.ui.reduce_motion ?? 'system'
    document.documentElement.dataset.motion = m === 'on' ? 'reduce' : m === 'off' ? 'full' : 'auto'
  }, [settings?.ui.reduce_motion])
  useEffect(() => { if (fs) document.documentElement.style.setProperty('--fs', `${fs}px`) }, [fs])
  const ff = useStore((s) => s.profile?.font_family)
  useEffect(() => { applyFont(ff) }, [ff])
}

function BackendBanner() {
  const t = useT()
  const conn = useStore((s) => s.conn)
  const ready = useStore((s) => s.ready)
  const [late, setLate] = useState(false)
  const [busy, setBusy] = useState(false)
  useEffect(() => {
    if (conn === 'online') { setLate(false); return }
    const id = setTimeout(() => setLate(true), 2500)
    return () => clearTimeout(id)
  }, [conn])
  const show = ready && conn !== 'online'
  return (
    <AnimatePresence>
      {show && (
        <motion.div className="banner" role="alert" initial={{ opacity: 0, y: -20 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -20 }}>
          <span className="spinner" /> <span>{t('banner.reconnecting')}</span>
          {late && window.egt && <Button size="sm" busy={busy} onClick={async () => { setBusy(true); await window.egt!.restartBackend(); setBusy(false) }}>{t('banner.restart')}</Button>}
        </motion.div>
      )}
    </AnimatePresence>
  )
}

function MainApp() {
  const init = useStore((s) => s.init)
  const ready = useStore((s) => s.ready)
  const settings = useStore((s) => s.settings)
  const profile = useStore((s) => s.profile)
  const running = useStore((s) => s.running)
  const toggle = useStore((s) => s.toggle)
  const now = useStore((s) => s.translateNow)
  const openDrawer = useStore((s) => s.openDrawer)
  const [intro, setIntro] = useState(false)
  useDocumentAttrs()
  useEffect(() => { init() }, [init])
  useEffect(() => {
    if (ready && settings && !introShown) {
      introShown = true
      if (settings.ui.play_intro && !(window.egt && window.location.search.includes('nointro'))) setIntro(true)
    }
  }, [ready, settings])
  useEffect(() => {      // gancho de teste E2E: dispara a intro sob demanda
    const h = () => setIntro(true)
    window.addEventListener('egt:play-intro', h)
    return () => window.removeEventListener('egt:play-intro', h)
  }, [])
  useEffect(() => { window.egt?.app.setState({ running, dual: profile?.mode === 'dual' }) }, [running, profile?.mode])
  useEffect(() => { if (settings) window.egt?.win.setAlwaysOnTop(settings.ui.always_on_top) }, [settings?.ui.always_on_top]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLElement && /^(INPUT|TEXTAREA)$/.test(e.target.tagName) && e.key.length === 1) return
      if (e.key === 'F5') { e.preventDefault(); toggle() }
      else if (e.key === 'F6') { e.preventDefault(); now() }
      else if ((e.ctrlKey || e.metaKey) && e.key === ',') { e.preventDefault(); openDrawer() }
    }
    window.addEventListener('keydown', key)
    return () => window.removeEventListener('keydown', key)
  }, [toggle, now, openDrawer])
  const motionMode = settings?.ui.reduce_motion === 'on' ? 'always' : settings?.ui.reduce_motion === 'off' ? 'never' : 'user'
  return (
    <MotionConfig reducedMotion={motionMode}>
      <div className="app">
        <div className="app-bg" aria-hidden />
        <Titlebar />
        <div className={`runline ${running ? 'on' : ''}`} aria-hidden />
        {ready && profile && settings ? (
          <motion.div className="app-body" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4, ease: [0.22, 0.9, 0.24, 1] }}>
            <Toolbar />
            <Stage />
            <StatusBar />
          </motion.div>
        ) : (
          <div className="app-body loading"><span className="spinner big" /></div>
        )}
        <BackendBanner />
        <Drawer />
        <ManualModal />
        <HelpModal />
        <ProfileModal />
        <ConfirmHost />
        <Toasts />
        <Intro show={intro} full={settings?.ui.intro_full !== false} onDone={() => setIntro(false)} />
      </div>
    </MotionConfig>
  )
}

function BoxApp() {
  const init = useStore((s) => s.init)
  const settings = useStore((s) => s.settings)
  const lang = useStore((s) => s.lang)
  const ff = useStore((s) => s.profile?.font_family)
  useEffect(() => { init() }, [init])
  useEffect(() => { document.documentElement.lang = lang }, [lang])      // a caixa não espelha (RTL só no painel), mas precisa do idioma para as fontes de reserva
  useEffect(() => { applyFont(ff) }, [ff])
  const motionMode = settings?.ui.reduce_motion === 'on' ? 'always' : settings?.ui.reduce_motion === 'off' ? 'never' : 'user'
  return <MotionConfig reducedMotion={motionMode}><BoxView /></MotionConfig>
}

export default function App() {
  const route = location.hash.replace(/^#/, '').split('?')[0]
  if (route === '/box') return <BoxApp />
  if (route === '/select') return <SelectView />
  if (route === '/flash') return <FlashView />
  return <MainApp />
}
