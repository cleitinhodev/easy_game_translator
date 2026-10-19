import { AnimatePresence, motion } from 'motion/react'
import { api } from '@/api/client'
import ninaIcon from '@/assets/nina.png'
import { bboxSize } from '@/lib/format'
import type { Channel } from '@/lib/types'
import { useStore, useT } from '@/store'
import { IGear, ISave, ITrash, IX, IHelp } from './icons'
import { PNG, PngIcon } from './icons'
import { FontPicker } from './FontPicker'
import { Button, Chip, IconButton, Segmented, Select, Slider, Switch, Tip } from './ui'

function StartButton() {
  const t = useT()
  const running = useStore((s) => s.running)
  const toggle = useStore((s) => s.toggle)
  return (
    <Tip label={t('main.start_tip')}>
      <motion.button type="button" className={`start-btn ${running ? 'running' : ''}`} onClick={toggle} whileTap={{ scale: 0.96 }} whileHover={{ y: -1 }} transition={{ type: 'spring', stiffness: 520, damping: 28 }} aria-pressed={running}>
        <span className="start-ring" aria-hidden />
        <span className="start-bg" aria-hidden />
        <AnimatePresence mode="wait" initial={false}>
          <motion.span key={running ? 'stop' : 'start'} className="start-content" initial={{ opacity: 0, scale: 0.6, rotate: running ? -60 : 60 }} animate={{ opacity: 1, scale: 1, rotate: 0 }} exit={{ opacity: 0, scale: 0.6, rotate: running ? 60 : -60 }} transition={{ type: 'spring', stiffness: 520, damping: 30 }}>
            <PngIcon src={running ? PNG.stop : PNG.start} size={24} />
            <span>{running ? t('main.stop') : t('main.start')}</span>
          </motion.span>
        </AnimatePresence>
      </motion.button>
    </Tip>
  )
}

function RegionButton({ ch }: { ch: Channel }) {
  const t = useT()
  const profile = useStore((s) => s.profile)!
  const select = useStore((s) => s.selectRegion)
  const clear = useStore((s) => s.clearRegion)
  const key = ch === 'uni' ? 'region_single' : ch === 'a' ? 'region_a' : 'region_b'
  const size = bboxSize(profile[key as 'region_single'])
  const label = ch === 'uni' ? t('main.region') : ch === 'a' ? t('main.region_a') : t('main.region_b')
  const icon = ch === 'uni' ? PNG.capture : ch === 'a' ? PNG.a : PNG.b
  return (
    <div className={`region-btn ${size ? 'set' : ''}`}>
      <Button tip={t('main.region_tip')} icon={<PngIcon src={icon} size={ch === 'uni' ? 22 : 17} />} onClick={() => select(ch)} className="region-main">
        <span className="region-label">{label}</span>
        <AnimatePresence initial={false}>
          {size && (
            <motion.span key="s" className="region-size" initial={{ opacity: 0, scale: 0.7 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 0.7 }}>
              <bdi dir="ltr">{size.w}×{size.h}</bdi>
            </motion.span>
          )}
        </AnimatePresence>
      </Button>
      <AnimatePresence initial={false}>
        {size && (
          <motion.span initial={{ opacity: 0, scale: 0.6 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 0.6 }}>
            <IconButton label={t('main.region_clear')} className="mini" onClick={() => clear(ch)}><IX size={13} /></IconButton>
          </motion.span>
        )}
      </AnimatePresence>
    </div>
  )
}

export function Toolbar() {
  const t = useT()
  const s = useStore()
  const { profile, settings, ocr, profiles, snapshot } = s
  if (!profile || !settings || !snapshot) return null
  const dual = profile.mode === 'dual'
  const ocrStatus = ocr.find((o) => o.id === profile.ocr_engine)

  const saveProfileDialog = () => s.setModal('profile-save')
  const loadProfile = async (name: string) => {
    try { await api.post('/api/profiles/load', { name }); s.toast('ok', t('toast.profile_loaded', { name })); s.refreshThumb('uni'); s.refreshThumb('a'); s.refreshThumb('b') } catch { s.toast('error', t('toast.profile_fail')) }
  }
  const delProfile = async () => {
    if (!profiles.includes(profile.name)) return
    if (await s.ask(t('main.profile_del_ask', { name: profile.name }), t('common.delete'), true)) await api.del(`/api/profiles?name=${encodeURIComponent(profile.name)}`)
  }

  return (
    <section className="toolbar card" aria-label={t('main.toolbar')}>
      <div className="tb-row actions">
        <StartButton />
        <Button tip={t('main.now_tip')} icon={<PngIcon src={PNG.translate} size={22} />} className="now-btn" onClick={s.translateNow}><span className="btn-label">{t('main.now')}</span></Button>
        <span className="vsep" />
        <Segmented size="md" label={t('main.mode')} value={profile.mode} onChange={(v) => s.patchProfile({ mode: v })}
          options={[{ value: 'single', label: <><PngIcon src={PNG.channels} size={17} /><span>{t('main.single')}</span></>, tip: t('main.mode_tip') }, { value: 'dual', label: <><PngIcon src={PNG.channels} size={17} className="flip" /><span>{t('main.dual')}</span></>, tip: t('main.mode_tip') }]} />
        <div className="regions">
          <AnimatePresence mode="popLayout" initial={false}>
            {dual ? (
              <motion.div key="dual" className="regions-in" initial={{ opacity: 0, x: 14 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -14 }} transition={{ duration: 0.22, ease: [0.22, 0.9, 0.24, 1] }}>
                <RegionButton ch="a" /><RegionButton ch="b" />
              </motion.div>
            ) : (
              <motion.div key="single" className="regions-in" initial={{ opacity: 0, x: 14 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -14 }} transition={{ duration: 0.22, ease: [0.22, 0.9, 0.24, 1] }}>
                <RegionButton ch="uni" />
              </motion.div>
            )}
          </AnimatePresence>
        </div>
        <span className="grow" />
        <Button tip={t('main.box_tip')} className={`toggle-btn ${s.boxOpen ? 'active' : ''}`} icon={<PngIcon src={PNG.box} size={20} />} onClick={s.toggleBox} aria-pressed={s.boxOpen}>
          <span className="collapsible">{t('main.box')}</span>
        </Button>
        <Button tip={t('main.manual_tip')} icon={<PngIcon src={PNG.speak} size={18} />} onClick={() => s.setModal('manual')}><span className="collapsible">{t('main.manual')}</span></Button>
        <Button tip={t('main.settings_tip')} icon={<IGear size={18} />} onClick={() => s.openDrawer()}><span className="collapsible">{t('main.settings')}</span></Button>
        <Tip label={t('main.help_tip')}>
          <motion.button type="button" className="help-btn" aria-label={t('main.help')} onClick={() => s.setModal('help')} whileHover={{ scale: 1.08, rotate: -4 }} whileTap={{ scale: 0.92 }}>
            <img src={ninaIcon} alt="" draggable={false} /><IHelp size={13} className="help-q" />
          </motion.button>
        </Tip>
      </div>

      <div className="tb-row options">
        <label className="opt-group">
          <span className="opt-label">{t('main.profile')}</span>
          <span className="opt-ctl">
          <Select width={150} label={t('main.profile')} value={profiles.includes(profile.name) ? profile.name : ''} placeholder={profile.name}
            options={profiles.length ? profiles.map((p) => ({ value: p, label: p })) : [{ value: '', label: t('main.no_profiles'), disabled: true }]} onChange={loadProfile} />
          <IconButton label={t('main.profile_save')} onClick={saveProfileDialog}><ISave size={16} /></IconButton>
          <IconButton label={t('main.profile_del')} onClick={delProfile} disabled={!profiles.includes(profile.name)}><ITrash size={16} /></IconButton>
        </span>
        </label>
        <label className="opt-group">
          <span className="opt-label">{t('main.alphabet')}</span>
          <span className="opt-ctl">
          <Select width={140} label={t('main.alphabet')} value={profile.alphabet} onChange={(v) => s.patchProfile({ alphabet: v })}
            options={snapshot.alphabets.map((a) => ({ value: a.key, label: <span className="alpha-opt"><b>{a.key}</b> {a.title.split('·').pop()?.trim()}</span> }))} />
        </span>
        </label>
        <label className="opt-group">
          <span className="opt-label">{t('main.ocr')}</span>
          <span className="opt-ctl">
          <Select width={132} label={t('main.ocr')} value={profile.ocr_engine} onChange={(v) => s.patchProfile({ ocr_engine: v })}
            icon={<span className={`dot-s ${ocrStatus?.available ? 'ok' : 'err'}`} />}
            options={ocr.map((o) => ({ value: o.id, label: o.name, sub: o.available ? t('ocr.installed_short') : t('ocr.not_installed_short') }))} />
        </span>
        </label>
        <label className="opt-group">
          <span className="opt-label">{t('main.target')}</span>
          <span className="opt-ctl">
          <Select width={146} label={t('main.target')} value={profile.target} onChange={(v) => s.patchProfile({ target: v })}
            options={snapshot.languages.map((l) => ({ value: l.code, label: <span><b className="code">{l.code.toUpperCase().replace('-', '·')}</b> {l.name}</span> }))} />
        </span>
        </label>
        <label className="opt-group">
          <span className="opt-label">{t('main.interval')}</span>
          <span className="opt-ctl">
          <Tip label={t('main.interval_tip')}><span><Slider width={136} min={0.2} max={5} step={0.1} value={profile.interval} label={t('main.interval')} format={(v) => `${v.toFixed(1)} s`} onCommit={(v) => s.patchProfile({ interval: v })} /></span></Tip>
        </span>
        </label>
        <label className="opt-group font-group">
          <span className="opt-label">{t('main.font')}</span>
          <span className="opt-ctl">
          <Slider width={92} min={10} max={48} step={1} value={profile.font_size} label={t('main.font')} format={(v) => `${v}`} onChange={(v) => document.documentElement.style.setProperty('--fs', `${v}px`)} onCommit={(v) => s.patchProfile({ font_size: v })} />
          <FontPicker width={58} compact align="right" />
        </span>
        </label>
        <span className="grow" />
        <Tip label={t('tr.cache_only_tip')}>
          <label className="opt-group cacheonly">
            <span className="opt-label">{t('main.cache_only')}</span>
            <Switch checked={settings.translation.cache_only} label={t('main.cache_only')} onChange={(v) => s.patchSettings({ 'translation.cache_only': v })} />
          </label>
        </Tip>
        {settings.translation.cache_only && <Chip tone="warn">{t('main.cache_only_short')}</Chip>}
      </div>
    </section>
  )
}
