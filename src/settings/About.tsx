import { useEffect, useState } from 'react'
import { api } from '@/api/client'
import { ICopy, IFolder, IRefresh } from '@/components/icons'
import { Button, Chip } from '@/components/ui'
import { useStore, useT } from '@/store'

interface About { app: string; version: string; author: string; python: string; platform: string; config_dir: string; logs_dir: string; log_file: string; modules: Record<string, string | null> }

export function BugsTab() {
  const t = useT()
  const [a, setA] = useState<About | null>(null)
  const [text, setText] = useState('')
  const toast = useStore((s) => s.toast)
  const live = useStore((s) => s.logs)
  const load = async () => { const r = await api.get<{ text: string }>('/api/logs?n=200'); setText(r.text) }
  useEffect(() => { api.get<About>('/api/about').then(setA); load() }, [])
  const openP = async (p?: string) => { if (p) await window.egt?.app.openPath(p) }
  return (
    <div className="s-page bugs">
      <p className="muted">{t('bug.tip')}</p>
      <p className="muted small selectable">{t('bug.log')}: <code>{a?.log_file}</code></p>
      <div className="input-row">
        <Button icon={<IFolder size={15} />} onClick={() => openP(a?.logs_dir)}>{t('bug.open_logs')}</Button>
        <Button icon={<IFolder size={15} />} onClick={() => openP(a?.config_dir)}>{t('bug.open_cfg')}</Button>
        <Button icon={<IRefresh size={15} />} onClick={load}>{t('bug.refresh')}</Button>
        <Button icon={<ICopy size={15} />} onClick={() => { navigator.clipboard?.writeText(text); toast('ok', t('common.copied'), 1400) }}>{t('bug.copy')}</Button>
        {live.length > 0 && <Chip tone="warn">{live.length} {t('bug.live')}</Chip>}
      </div>
      <pre className="logbox selectable">{text || t('bug.empty')}{live.length ? '\n' + live.join('\n') : ''}</pre>
    </div>
  )
}
