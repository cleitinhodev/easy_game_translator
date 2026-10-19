import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import { api, ApiError } from '@/api/client'
import { numLocale } from '@/lib/i18n'
import ninaPng from '@/assets/nina.png'
import { ICheck, ICopy, IChevron, IDownload, IFolder, IInfo, IRefresh, ITrash, IWifiOff } from '@/components/icons'
import { Modal } from '@/components/Modal'
import { LINKS } from '@/components/HelpModal'
import { Button, Chip, IconButton } from '@/components/ui'
import type { CompItem, CompJob, CompList, CompView } from '@/lib/types'
import { useStore, useT } from '@/store'
import { Section } from './parts'

// ------------------------------------------------------------------ utilidades
const fmtBytes = (n: number, lang: string) => {
  const f = (v: number, d = 1) => v.toLocaleString(numLocale(lang), { maximumFractionDigits: d, minimumFractionDigits: 0 })
  if (n >= 1024 ** 3) return `${f(n / 1024 ** 3)} GB`
  if (n >= 1024 ** 2) return `${f(n / 1024 ** 2, n >= 100 * 1024 ** 2 ? 0 : 1)} MB`
  if (n >= 1024) return `${f(n / 1024, 0)} KB`
  return `${n} B`
}
const fmtEta = (s: number | null, t: (k: string, p?: Record<string, string | number>) => string) => {
  if (s == null || !isFinite(s) || s <= 0) return ''
  return s < 90 ? t('comp.eta_s', { n: Math.max(1, Math.round(s)) }) : t('comp.eta_m', { n: Math.round(s / 60) })
}
const errCode = (e: unknown): string => {
  if (e instanceof ApiError) { try { const j = JSON.parse(e.message); return j.code || j.message || '' } catch { return e.message } }
  return String((e as Error)?.message || e)
}
const openExternal = (u: string) => (window.egt ? window.egt.app.openExternal(u) : window.open(u, '_blank'))
const CATS = ['base', 'ocr', 'translation', 'ai', 'voice'] as const
const catOf = (c: CompView) => (c.id === 'python' ? 'base' : c.category)

// ------------------------------------------------------------------ aba
export function UpdatesTab() {
  const t = useT()
  const lang = useStore((s) => s.lang)
  const toast = useStore((s) => s.toast)
  const ask = useStore((s) => s.ask)
  const cfg = useStore((s) => s.snapshot?.app)
  const appVersion = useStore((s) => s.appVersion)
  const tick = useStore((s) => s.compTick)
  const [data, setData] = useState<CompList | null>(null)
  const [err, setErr] = useState('')
  const [checking, setChecking] = useState<Record<string, boolean>>({})
  const [checkingAll, setCheckingAll] = useState(false)
  const [open, setOpen] = useState<string | null>(null)
  const [dlg, setDlg] = useState<{ id: string; item: string } | null>(null)
  const autoChecked = useRef(false)

  const load = useCallback(async () => {
    try { setData(await api.get<CompList>('/api/components')); setErr('') } catch (e: any) { setErr(e.message) }
  }, [])
  useEffect(() => { load() }, [load, tick])

  const replace = (v: CompView) => setData((d) => (d ? { ...d, components: d.components.map((c) => (c.id === v.id ? v : c)) } : d))

  const checkOne = useCallback(async (id: string) => {
    setChecking((m) => ({ ...m, [id]: true }))
    try { replace(await api.post<CompView>(`/api/components/${id}/check`, {})) } catch { /* mostra o estado atual */ }
    setChecking((m) => ({ ...m, [id]: false }))
  }, [])

  // ao abrir: confere só o que o usuário usa e está faltando (para já mostrar o tamanho)
  useEffect(() => {
    if (!data || autoChecked.current || !data.summary.needed.length) return
    autoChecked.current = true
    data.summary.needed.forEach((id) => { checkOne(id) })
  }, [data, checkOne])

  const checkAll = async () => {
    setCheckingAll(true)
    try { setData(await api.post<CompList>('/api/components/check', {})) } catch (e: any) { toast('warn', t('comp.err.generic')) }
    setCheckingAll(false)
  }

  const rescan = async (id = '') => {
    try { const r = await api.post<CompList>(id ? `/api/components/${id}/rescan` : '/api/components/rescan', {}); setData(r); toast('ok', t('comp.rescanned'), 2200) } catch { toast('warn', t('comp.err.generic')) }
  }

  const folder = async (id: string) => {
    const r = await window.egt?.components.openFolder(id)
    if (r && !r.ok) toast('warn', t('comp.folder_fail'))
  }

  const changeRoot = async () => {
    const p = await window.egt?.components.pickFolder({ title: t('comp.pick_title') })
    if (!p) return
    const v = await api.post<{ ok: boolean; errors: string[]; warnings: string[] }>('/api/components/validate-dir', { path: p })
    if (!v.ok) { toast('warn', t('comp.dir_bad')); return }
    const move = await ask(t('comp.root_confirm', { path: p }), t('comp.use_folder'))
    if (!move) return
    const r = await api.post<{ ok: boolean }>('/api/components/location', { id: 'root', path: p, copy_existing: true })
    if (r.ok) { toast('ok', t('comp.root_changed'), 2600); load() } else toast('warn', t('comp.dir_bad'))
  }
  const resetRoot = async () => { await api.post('/api/components/location', { id: 'root', path: '', reset: true }); load() }

  const changeFolder = async (id: string) => {
    const p = await window.egt?.components.pickFolder({ title: t('comp.pick_title') })
    if (!p) return
    const r = await api.post<{ ok: boolean; warnings?: string[] }>('/api/components/location', { id, path: p, copy_existing: true })
    if (r.ok) { toast('ok', t('comp.folder_changed'), 2400); load() } else toast('warn', t('comp.dir_bad'))
  }
  const resetFolder = async (id: string) => { await api.post('/api/components/location', { id, path: '', reset: true }); load() }

  const remove = async (c: CompView, item = '', name = '') => {
    if (!(await ask(t('comp.remove_confirm', { name: name || t(`comp.${c.id}.name`) }), t('comp.remove'), true))) return
    try { await api.post(`/api/components/${c.id}/remove`, { item, confirmed: true }); toast('ok', t('comp.removed'), 2200); load() } catch (e) { toast('warn', t(`comp.err.${errCode(e)}`) === `comp.err.${errCode(e)}` ? t('comp.err.generic') : t(`comp.err.${errCode(e)}`)) }
  }

  const byCat = useMemo(() => {
    const m: Record<string, CompView[]> = {}
    ;(data?.components || []).forEach((c) => { (m[catOf(c)] ||= []).push(c) })
    return m
  }, [data])

  const needed = data?.components.filter((c) => c.needed) || []
  const offline = !!data?.components.some((c) => c.offline)
  const demoOffline = offline

  return (
    <div className="s-page comp-page">
      <div className="about-hero slim">
        <img src={ninaPng} alt="" draggable={false} />
        <div>
          <h3>{cfg?.name ?? 'Easy Game Translator'}</h3>
          <p>v{appVersion || cfg?.version} · by CleitinhoDEV</p>
          <div className="input-row">
            <Button size="sm" onClick={() => openExternal(LINKS.channel)}>YouTube</Button>
            <Button size="sm" onClick={() => openExternal(LINKS.patreon)}>Patreon</Button>
            <Button size="sm" onClick={() => openExternal(LINKS.website)}>Website</Button>
          </div>
        </div>
      </div>

      {err && <div className="comp-banner info"><IInfo size={17} /><div><b>{t('comp.err.load')}</b></div><Button size="sm" onClick={load}>{t('comp.retry')}</Button></div>}

      {data && (
        <motion.div layout className={`comp-summary ${data.summary.all_ok ? 'ok' : 'todo'}`} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
          <span className="sum-ic">{data.summary.all_ok ? <ICheck size={22} /> : <IDownload size={20} />}</span>
          <div className="sum-txt">
            <b>{data.summary.all_ok ? t('comp.sum_ok') : t('comp.sum_todo')}</b>
            <small>{data.summary.all_ok ? t('comp.sum_ok_sub') : t('comp.sum_todo_sub', { names: needed.map((c) => t(`comp.${c.id}.name`)).join(', ') })}</small>
          </div>
          <Button size="sm" icon={<IRefresh size={14} />} busy={checkingAll} onClick={checkAll}>{t('comp.check_all')}</Button>
        </motion.div>
      )}

      <AnimatePresence>
        {demoOffline && (
          <motion.div className="comp-banner info" initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0, height: 0 }}>
            <IWifiOff size={18} /><div><b>{t('comp.offline_t')}</b><small>{t('comp.offline_s')}</small></div>
            <Button size="sm" onClick={checkAll} busy={checkingAll}>{t('comp.retry')}</Button>
          </motion.div>
        )}
      </AnimatePresence>

      {data && (
        <div className="comp-root">
          <div><b>{t('comp.root')}</b><small className="selectable">{data.paths.root}</small></div>
          <div className="input-row">
            <Button size="sm" icon={<IFolder size={14} />} onClick={() => folder('root')}>{t('comp.open_folder')}</Button>
            <Button size="sm" variant="ghost" onClick={changeRoot}>{t('comp.change_folder')}</Button>
            {data.paths.root !== data.paths.default_root && <Button size="sm" variant="ghost" onClick={resetRoot}>{t('comp.default_folder')}</Button>}
            <Button size="sm" variant="ghost" icon={<IRefresh size={14} />} onClick={() => rescan()}>{t('comp.rescan')}</Button>
          </div>
        </div>
      )}

      {data && CATS.filter((k) => byCat[k]?.length).map((k) => (
        <Section key={k} title={t(`comp.cat.${k}`)} desc={t(`comp.cat.${k}_d`)}>
          <div className="comp-list">
            {byCat[k].map((c) => (
              <CompRow key={c.id} c={c} lang={lang} busy={!!checking[c.id]} expanded={open === c.id}
                onToggle={() => setOpen(open === c.id ? null : c.id)}
                onInstall={(item) => setDlg({ id: c.id, item: item ?? c.primary.item ?? '' })}
                onFolder={() => folder(c.id)} onCheck={() => checkOne(c.id)} onRescan={() => rescan(c.id)}
                onChange={() => changeFolder(c.id)} onReset={() => resetFolder(c.id)} onRemove={(item, name) => remove(c, item, name)}
                onItemCheck={async (item) => { await api.post(`/api/components/${c.id}/check`, { item }); load() }} />
            ))}
          </div>
        </Section>
      ))}

      <details className="comp-adv">
        <summary>{t('comp.versions')}</summary>
        <ModuleList />
      </details>
      <p className="muted small">{t('upd.note')}</p>

      <DownloadModal target={dlg} view={dlg ? data?.components.find((c) => c.id === dlg.id) : undefined} lang={lang}
        onClose={() => { setDlg(null); load() }}
        onManual={() => { if (dlg) setOpen(dlg.id); setDlg(null) }} />
    </div>
  )
}

// ------------------------------------------------------------------ linha
function statusInfo(c: CompView, t: (k: string, p?: Record<string, string | number>) => string): { tone: 'ok' | 'accent' | 'default' | 'warn'; text: string } {
  if (c.status === 'unavailable') return { tone: 'default', text: t('comp.st.unavailable') }
  if (c.status === 'ok') return { tone: 'ok', text: c.builtin ? t('comp.st.builtin') : t('comp.st.ok') }
  if (c.status === 'update') return { tone: 'accent', text: t('comp.st.update') }
  return c.needed ? { tone: 'accent', text: t('comp.st.missing') } : { tone: 'default', text: t('comp.st.optional') }
}

function subline(c: CompView, lang: string, t: (k: string, p?: Record<string, string | number>) => string): string {
  if (c.job) return t('comp.working')
  if (c.status === 'ok' || c.status === 'update') {
    const v = c.version && c.id !== 'tessdata' && c.id !== 'gemini' ? t('comp.version', { v: c.version }) : ''
    if (c.status === 'update' && c.latest) return `${v ? v + ' · ' : ''}${t('comp.new_version', { v: c.latest })}`
    if (c.id === 'tessdata' && c.version) return t('comp.langs_n', { n: c.version })
    return v
  }
  if (c.status === 'unavailable') return t('comp.blk.not_windows')
  // faltando
  const miss = c.items.filter((i) => i.needed && !i.installed)
  const size = miss.length ? miss[0].size ?? null : c.size
  if (c.blocker && c.primary.action !== 'install') return t(`comp.blk.${c.blocker}`)
  if (c.check_error === 'no_binary') return t('comp.blk.no_binary')
  if (c.offline) return t('comp.st.offline')
  if (c.primary.action === 'goto_ai') return t('comp.gemini_missing')
  const what = miss.length ? t('comp.missing_what', { what: miss.map((i) => i.name || i.id).join(', ') }) : ''
  const dl = c.heavy ? t('comp.need_download', { size: t('comp.size_heavy') }) : size ? t('comp.need_download', { size: fmtBytes(size, lang) }) : t('comp.size_after')
  return what ? `${what} · ${dl}` : dl
}

function CompRow({ c, lang, busy, expanded, onToggle, onInstall, onFolder, onCheck, onRescan, onChange, onReset, onRemove, onItemCheck }: {
  c: CompView; lang: string; busy: boolean; expanded: boolean; onToggle: () => void; onInstall: (item?: string) => void; onFolder: () => void
  onCheck: () => void; onRescan: () => void; onChange: () => void; onReset: () => void; onRemove: (item: string, name: string) => void; onItemCheck: (item: string) => Promise<void>
}) {
  const t = useT()
  const setTab = useStore((s) => s.setTab)
  const st = statusInfo(c, t)
  const pa = c.primary.action
  const primary =
    pa === 'install' ? (
      <Button size="sm" variant={c.primary.optional ? 'default' : 'primary'} icon={<IDownload size={14} />} busy={busy || !!c.job} onClick={() => onInstall()} data-testid={`install-${c.id}`}>
        {c.primary.optional ? t('comp.install_opt') : t('comp.install')}
      </Button>
    ) : pa === 'update' ? (
      <Button size="sm" variant="primary" icon={<IDownload size={14} />} busy={busy || !!c.job} onClick={() => onInstall()}>{t('comp.update')}</Button>
    ) : pa === 'howto' ? (
      <Button size="sm" variant={c.needed ? 'primary' : 'default'} onClick={onToggle}>{t('comp.howto')}</Button>
    ) : pa === 'goto_ai' ? (
      <Button size="sm" variant="primary" onClick={() => setTab('ai')}>{t('comp.goto_ai')}</Button>
    ) : null
  return (
    <motion.div layout="position" className={`comp-row ${c.status} ${expanded ? 'open' : ''}`} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.25 }} data-comp={c.id}>
      <div className="comp-main">
        <span className={`comp-dot ${c.status}`} aria-hidden>{c.status === 'ok' ? <ICheck size={13} /> : c.status === 'update' ? <IDownload size={12} /> : c.status === 'missing' ? '•' : '–'}</span>
        <div className="comp-name">
          <div className="comp-title"><span>{t(`comp.${c.id}.name`)}</span><Chip tone={st.tone}>{st.text}</Chip></div>
          <small className="comp-sub">{subline(c, lang, t)}</small>
          <small className="comp-desc">{t(`comp.${c.id}.desc`)}</small>
          <button type="button" className={`comp-more ${expanded ? 'on' : ''}`} aria-expanded={expanded} onClick={onToggle} data-testid={`more-${c.id}`}>
            <span>{t('comp.advanced')}</span><IChevron size={13} />
          </button>
        </div>
        <div className="comp-actions">
          {primary}
          {c.folder !== null && <IconButton label={t('comp.open_folder')} onClick={onFolder} data-testid={`folder-${c.id}`}><IFolder size={16} /></IconButton>}
        </div>
      </div>
      {c.job && <JobBar job={c.job} lang={lang} compact />}
      <AnimatePresence initial={false}>
        {expanded && (
          <motion.div className="comp-detail" initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }} exit={{ height: 0, opacity: 0 }} transition={{ duration: 0.26, ease: [0.22, 0.9, 0.24, 1] }}>
            <Detail c={c} lang={lang} onInstall={onInstall} onCheck={onCheck} onRescan={onRescan} onChange={onChange} onReset={onReset} onRemove={onRemove} onFolder={onFolder} onItemCheck={onItemCheck} busy={busy} />
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  )
}

function Detail({ c, lang, onInstall, onCheck, onRescan, onChange, onReset, onRemove, onFolder, onItemCheck, busy }: {
  c: CompView; lang: string; onInstall: (item?: string) => void; onCheck: () => void; onRescan: () => void; onChange: () => void; onReset: () => void
  onRemove: (item: string, name: string) => void; onFolder: () => void; onItemCheck: (item: string) => Promise<void>; busy: boolean
}) {
  const t = useT()
  const toast = useStore((s) => s.toast)
  const copy = (txt: string) => { navigator.clipboard?.writeText(txt); toast('ok', t('common.copied'), 1400) }
  const [all, setAll] = useState(false)
  const items = c.items
  const shown = all ? items : items.filter((i) => i.needed || i.installed || i.user).slice(0, 8)
  const canItems = items.length > 0 && c.id !== 'easyocr'
  return (
    <div className="comp-detail-in">
      {c.blocker && c.blocker !== 'no_download' && c.primary.action === 'install' && <p className="comp-why"><IInfo size={14} /> {t(`comp.blk.${c.blocker}`)}</p>}
      {canItems && (
        <div className="comp-block">
          <h5>{t(`comp.items.${c.id}`)}</h5>
          <div className="comp-items">
            {shown.map((i) => <ItemRow key={i.id} c={c} i={i} lang={lang} onInstall={onInstall} onRemove={onRemove} onItemCheck={onItemCheck} />)}
          </div>
          {items.length > shown.length && <Button size="sm" variant="ghost" onClick={() => setAll(true)}>{t('comp.show_all', { n: items.length })}</Button>}
        </div>
      )}
      {c.id === 'easyocr' && c.items.length > 0 && c.installed && !c.blocker && (
        <div className="comp-block"><Button size="sm" icon={<IDownload size={14} />} onClick={() => onInstall('models')}>{t('comp.easy_models')}</Button></div>
      )}
      <div className="comp-block">
        <h5>{t('comp.manual_title')}</h5>
        {c.manual.notes.map((n) => <p key={n} className="comp-note">{t(`comp.note.${n}`)}</p>)}
        {c.manual.links.length > 0 && (
          <div className="comp-links">{c.manual.links.map((l) => <button key={l.url} type="button" className="link-btn" onClick={() => openExternal(l.url)}>{l.label} ↗</button>)}</div>
        )}
        {c.manual.commands.map((m) => (
          <div key={m.cmd} className="cmd-row">
            <div className="cmd-label">{m.label}</div>
            <code className="cmd selectable">{m.cmd}</code>
            <IconButton label={t('comp.copy_cmd')} onClick={() => copy(m.cmd)}><ICopy size={14} /></IconButton>
          </div>
        ))}
      </div>
      {c.add_files && (
        <div className="comp-block">
          <h5>{t('comp.files_title')}</h5>
          <p className="comp-note">{t(`comp.${c.add_files.key}`)} <small>({c.add_files.exts.join(' ')})</small></p>
          <div className="input-row">
            <Button size="sm" icon={<IFolder size={14} />} onClick={onFolder}>{t('comp.open_folder')}</Button>
            <Button size="sm" icon={<IRefresh size={14} />} onClick={onRescan}>{t('comp.rescan')}</Button>
          </div>
        </div>
      )}
      <div className="comp-block tech">
        <h5>{t('comp.tech_title')}</h5>
        {c.folder && <div className="kv"><span>{t('comp.folder')}</span><code className="selectable">{c.folder}</code></div>}
        {c.location && <div className="kv"><span>{t('comp.found_at')}</span><code className="selectable">{c.location}</code></div>}
        {c.version && <div className="kv"><span>{t('comp.installed_v')}</span><code>{c.version}</code></div>}
        {c.latest && <div className="kv"><span>{t('comp.latest_v')}</span><code>{c.latest}</code></div>}
        {c.size ? <div className="kv"><span>{t('comp.size')}</span><code>{fmtBytes(c.size, lang)}</code></div> : null}
        <div className="input-row">
          <Button size="sm" variant="ghost" icon={<IRefresh size={14} />} busy={busy} onClick={onCheck}>{t('comp.check_one')}</Button>
          {c.folder && <Button size="sm" variant="ghost" onClick={onChange}>{t('comp.change_folder')}</Button>}
          {c.folder_custom && <Button size="sm" variant="ghost" onClick={onReset}>{t('comp.default_folder')}</Button>}
          {c.removable && c.id !== 'ollama' && c.id !== 'tessdata' && <Button size="sm" variant="ghost" icon={<ITrash size={14} />} onClick={() => onRemove('', '')}>{t('comp.remove')}</Button>}
        </div>
      </div>
    </div>
  )
}

function ItemRow({ c, i, lang, onInstall, onRemove, onItemCheck }: { c: CompView; i: CompItem; lang: string; onInstall: (item?: string) => void; onRemove: (item: string, name: string) => void; onItemCheck: (item: string) => Promise<void> }) {
  const t = useT()
  const [b, setB] = useState(false)
  const removable = c.id === 'tessdata' ? !!i.user : c.id === 'ollama' || c.id === 'argos' ? !!i.installed : false
  const blocked = c.id === 'ollama' ? c.blocker === 'server_off' || (c.detect_extra.server === false) : false
  return (
    <div className={`item-row ${i.installed ? 'ok' : ''}`}>
      <span className="item-name">{i.name || i.id}{i.needed && !i.installed && <Chip tone="accent">{t('comp.st.missing')}</Chip>}</span>
      <small>{i.size ? fmtBytes(i.size, lang) : ''}</small>
      {i.installed ? (
        <>
          <Chip tone="ok">{t('comp.st.ok')}</Chip>
          {removable && <IconButton label={t('comp.remove')} onClick={() => onRemove(i.id, i.name || i.id)}><ITrash size={14} /></IconButton>}
        </>
      ) : blocked ? (
        <small className="muted">{t('comp.blk.server_off')}</small>
      ) : (
        <>
          {i.size == null && <Button size="sm" variant="ghost" busy={b} onClick={async () => { setB(true); await onItemCheck(i.id); setB(false) }}>{t('comp.see_size')}</Button>}
          <Button size="sm" icon={<IDownload size={13} />} onClick={() => onInstall(i.id)}>{t('comp.install')}</Button>
        </>
      )}
    </div>
  )
}

// ------------------------------------------------------------------ barra de progresso
function JobBar({ job, lang, compact }: { job: CompJob; lang: string; compact?: boolean }) {
  const t = useT()
  const pct = job.total > 0 ? Math.min(100, (job.done / job.total) * 100) : null
  const label = job.phase === 'installing' ? t('comp.phase_installing') : job.phase === 'working' && pct == null ? t('comp.phase_working') : t('comp.phase_downloading')
  return (
    <div className={`jobbar ${compact ? 'compact' : ''}`} role="progressbar" aria-valuenow={pct == null ? undefined : Math.round(pct)} aria-valuemin={0} aria-valuemax={100}>
      <div className="track"><div className={`fill ${pct == null || job.phase === 'installing' ? 'indet' : ''}`} style={pct != null && job.phase !== 'installing' ? { width: `${pct}%` } : undefined} /></div>
      <div className="jobmeta">
        <span>{label}{pct != null && job.phase !== 'installing' ? ` · ${Math.round(pct)}%` : ''}</span>
        {job.total > 0 && job.phase === 'downloading' && <span>{fmtBytes(job.done, lang)} / {fmtBytes(job.total, lang)}</span>}
        {job.speed > 0 && job.phase === 'downloading' && <span>{fmtBytes(job.speed, lang)}/s</span>}
        {job.phase === 'downloading' && <span>{fmtEta(job.eta, t)}</span>}
      </div>
    </div>
  )
}

// ------------------------------------------------------------------ janela de download
type Step = 'checking' | 'confirm' | 'running' | 'blocked' | 'offline' | 'unavailable'
function DownloadModal({ target, view, lang, onClose, onManual }: { target: { id: string; item: string } | null; view?: CompView; lang: string; onClose: () => void; onManual: () => void }) {
  const t = useT()
  const ask = useStore((s) => s.ask)
  const toast = useStore((s) => s.toast)
  const jobs = useStore((s) => s.compJobs)
  const [step, setStep] = useState<Step>('checking')
  const [info, setInfo] = useState<{ size: number | null; latest: string; note: string; label: string; host: string } | null>(null)
  const [jobId, setJobId] = useState('')
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const key = target ? `${target.id}|${target.item}` : ''

  useEffect(() => {
    if (!target) return
    let live = true
    setStep('checking'); setJobId(''); setInfo(null); setReason('')
    ;(async () => {
      try {
        const r: any = await api.post(`/api/components/${target.id}/check`, target.item ? { item: target.item } : {})
        if (!live) return
        const v: CompView | undefined = target.item ? undefined : r
        let size: number | null = target.item ? (r.size ?? null) : (v?.size ?? null)
        if (target.item && r.error) { setStep(r.error === 'offline' ? 'offline' : 'unavailable'); return }
        const full = await api.get<CompList>('/api/components')
        if (!live) return
        const cv = full.components.find((c) => c.id === target.id)
        if (!cv) { setStep('unavailable'); return }
        if (cv.offline) { setStep('offline'); return }
        if (!target.item && cv.blocker) { setReason(cv.blocker); setStep('blocked'); return }
        if (!target.item && cv.check_error && cv.size == null) { setStep('unavailable'); return }
        if (!target.item) size = cv.size
        const it = cv.items.find((i) => i.id === target.item)
        setInfo({ size: size ?? it?.size ?? null, latest: cv.latest, note: cv.note, label: it?.name || t(`comp.${cv.id}.name`), host: '' })
        setStep('confirm')
      } catch { if (live) setStep('offline') }
    })()
    return () => { live = false }
  }, [key])  // eslint-disable-line react-hooks/exhaustive-deps

  const job = jobId ? jobs[jobId] : undefined
  const start = async () => {
    if (!target) return
    setBusy(true)
    try {
      const j = await api.post<CompJob>(`/api/components/${target.id}/install`, { item: target.item, confirmed: true })
      setJobId(j.id); setStep('running')
    } catch (e) {
      const code = errCode(e)
      if (code === 'offline') setStep('offline')
      else { setReason(code); setStep('blocked') }
    }
    setBusy(false)
  }
  const cancel = async () => { if (jobId) await api.post(`/api/components/jobs/${jobId}/cancel`, {}); }
  const runInstaller = async () => {
    if (!job) return
    if (!(await ask(t('comp.run_confirm'), t('comp.run_open')))) return
    try { await api.post('/api/components/run-installer', { path: job.dest, confirmed: true }); toast('ok', t('comp.run_opened'), 3000) } catch (e) { toast('warn', t(`comp.err.${errCode(e)}`) === `comp.err.${errCode(e)}` ? t('comp.err.generic') : t(`comp.err.${errCode(e)}`)) }
  }

  const name = info?.label || (view ? t(`comp.${view.id}.name`) : '')
  const finished = job && (job.state === 'done' || job.state === 'error' || job.state === 'cancelled')
  const title = view ? `${t(`comp.${view.id}.name`)}${target?.item && info ? ` · ${info.label}` : ''}` : ''
  return (
    <Modal open={!!target} onClose={() => { if (job?.state === 'running') cancel(); onClose() }} width={500} title={title} className="comp-modal">
      <div className="dl" data-step={step === 'running' && job ? job.state : step}>
        {step === 'checking' && <div className="dl-center"><span className="spinner big" /><p>{t('comp.checking')}</p></div>}
        {step === 'offline' && (
          <div className="dl-center"><IWifiOff size={34} /><b>{t('comp.offline_t')}</b><p>{t('comp.offline_dl')}</p>
            <div className="input-row"><Button onClick={onManual}>{t('comp.show_manual')}</Button><Button variant="ghost" onClick={onClose}>{t('common.close')}</Button></div></div>
        )}
        {step === 'unavailable' && (
          <div className="dl-center"><IInfo size={34} /><b>{t('comp.unavail_t')}</b><p>{t('comp.unavail_s')}</p>
            <div className="input-row"><Button onClick={onManual}>{t('comp.show_manual')}</Button><Button variant="ghost" onClick={onClose}>{t('common.close')}</Button></div></div>
        )}
        {step === 'blocked' && (
          <div className="dl-center"><IInfo size={34} /><b>{t('comp.blocked_t')}</b>
            <p>{t(`comp.blk.${reason}`) === `comp.blk.${reason}` ? (t(`comp.err.${reason}`) === `comp.err.${reason}` ? t('comp.err.generic') : t(`comp.err.${reason}`)) : t(`comp.blk.${reason}`)}</p>
            <div className="input-row"><Button variant="primary" onClick={onManual}>{t('comp.show_manual')}</Button><Button variant="ghost" onClick={onClose}>{t('common.close')}</Button></div></div>
        )}
        {step === 'confirm' && info && (
          <div className="dl-confirm">
            <p className="dl-lead">{t('comp.confirm_lead', { name })}</p>
            <div className="dl-facts">
              <div><span>{t('comp.size')}</span><b>{view?.heavy && !target?.item ? t('comp.size_heavy') : info.size ? fmtBytes(info.size, lang) : t('comp.size_unknown')}</b></div>
              {info.latest && <div><span>{t('comp.version_word')}</span><b>{info.latest}</b></div>}
              <div><span>{t('comp.source')}</span><b>{t('comp.source_official')}</b></div>
            </div>
            {view?.heavy && <p className="dl-note">{t('comp.heavy_note')}</p>}
            {info.note === 'no_hash' && <p className="dl-note">{t('comp.nohash_note')}</p>}
            {view && ['python', 'tesseract', 'ollama'].includes(view.id) && !target?.item && <p className="dl-note">{t('comp.installer_note')}</p>}
            <div className="dl-foot"><Button variant="ghost" onClick={onClose}>{t('common.cancel')}</Button><Button variant="primary" icon={<IDownload size={15} />} busy={busy} onClick={start} data-testid="dl-confirm">{view?.heavy && !target?.item ? t('comp.download_size', { size: t('comp.size_heavy') }) : info.size ? t('comp.download_size', { size: fmtBytes(info.size, lang) }) : t('comp.download')}</Button></div>
          </div>
        )}
        {step === 'running' && (
          <div className="dl-run">
            {!job && <div className="dl-center"><span className="spinner big" /></div>}
            {job && job.state === 'running' || job?.state === 'queued' ? (
              <>
                <p className="dl-lead">{job.phase === 'installing' ? t('comp.installing_lead') : t('comp.downloading_lead', { name })}</p>
                <JobBar job={job} lang={lang} />
                <div className="dl-foot"><Button variant="ghost" onClick={cancel} data-testid="dl-cancel">{t('common.cancel')}</Button></div>
              </>
            ) : null}
            {job?.state === 'done' && (
              <div className="dl-center done">
                <motion.span className="done-ic" initial={{ scale: 0.4, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} transition={{ type: 'spring', stiffness: 380, damping: 18 }}><ICheck size={30} /></motion.span>
                <b>{job.installer ? t('comp.downloaded_t') : t('comp.done_t')}</b>
                <p>{job.installer ? t('comp.downloaded_s') : t('comp.done_s')}</p>
                {job.verified && <small className="ver">{t('comp.verified')}</small>}
                <div className="input-row">
                  {job.installer && <Button variant="primary" onClick={runInstaller}>{t('comp.run_open')}</Button>}
                  {job.installer && <Button icon={<IFolder size={14} />} onClick={async () => { await window.egt?.components.openFolder('root') }}>{t('comp.open_folder')}</Button>}
                  <Button variant={job.installer ? 'ghost' : 'primary'} onClick={onClose}>{t('common.close')}</Button>
                </div>
              </div>
            )}
            {finished && job?.state === 'error' && (
              <div className="dl-center"><IInfo size={34} /><b>{t('comp.fail_t')}</b><p>{job.error}</p>{job.remedy && <small>{job.remedy}</small>}
                <div className="input-row"><Button variant="primary" onClick={() => { setStep('confirm'); setJobId('') }}>{t('comp.retry')}</Button><Button onClick={onManual}>{t('comp.show_manual')}</Button><Button variant="ghost" onClick={onClose}>{t('common.close')}</Button></div></div>
            )}
            {finished && job?.state === 'cancelled' && (
              <div className="dl-center"><IInfo size={30} /><b>{t('comp.cancelled_t')}</b><p>{t('comp.cancelled_s')}</p>
                <div className="input-row"><Button variant="primary" onClick={() => { setStep('confirm'); setJobId('') }}>{t('comp.resume')}</Button><Button variant="ghost" onClick={onClose}>{t('common.close')}</Button></div></div>
            )}
          </div>
        )}
      </div>
    </Modal>
  )
}

// ------------------------------------------------------------------ lista antiga de módulos (avançado)
function ModuleList() {
  const t = useT()
  const [a, setA] = useState<{ python: string; platform: string; modules: Record<string, string | null> } | null>(null)
  useEffect(() => { api.get<any>('/api/about').then(setA) }, [])
  return (
    <div>
      <p className="muted small">{a ? `Python ${a.python} · ${a.platform}` : ''}</p>
      <div className="mod-grid">
        {a && Object.entries(a.modules).map(([k, v]) => <div key={k} className={`mod ${v ? 'ok' : 'na'}`}><span>{v ? '✔' : '–'}</span><b>{k}</b><small>{v && v !== 'ok' ? v : v ? '' : t('ocr.not_installed')}</small></div>)}
      </div>
    </div>
  )
}
