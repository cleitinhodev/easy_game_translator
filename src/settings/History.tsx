import { AnimatePresence, motion } from 'motion/react'
import { useCallback, useEffect, useState } from 'react'
import { api } from '@/api/client'
import { ICopy, IDownload, IRefresh, ITrash } from '@/components/icons'
import { Button, Chip, IconButton } from '@/components/ui'
import { fmtTime } from '@/lib/format'
import type { HistoryItem } from '@/lib/types'
import { useStore, useT } from '@/store'

export function HistoryTab() {
  const t = useT()
  const lang = useStore((s) => s.lang)
  const tick = useStore((s) => s.historyTick)
  const ask = useStore((s) => s.ask)
  const toast = useStore((s) => s.toast)
  const [items, setItems] = useState<HistoryItem[]>([])
  const [count, setCount] = useState(0)
  const load = useCallback(async () => { const r = await api.get<{ items: HistoryItem[]; count: number }>('/api/history?limit=300'); setItems(r.items); setCount(r.count) }, [])
  useEffect(() => { load() }, [load, tick])
  const exportAs = async (fmt: 'txt' | 'csv' | 'json') => {
    const r = await api.get<{ filename: string; content: string; count: number }>(`/api/history/export?fmt=${fmt}`)
    const path = await window.egt?.app.saveFile(r.filename, r.content)
    if (path) toast('ok', t('hist.exported', { n: r.count, path }), 6000)
    else if (!window.egt) { const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([r.content])); a.download = r.filename; a.click() }
  }
  const clear = async () => { if (await ask(t('hist.confirm'), t('hist.clear'), true)) { await api.del('/api/history'); load() } }
  const copy = (txt: string) => { navigator.clipboard?.writeText(txt); toast('ok', t('common.copied'), 1400) }
  return (
    <div className="s-page hist">
      <div className="hist-bar">
        <Chip>{t('hist.total', { n: count })}</Chip>
        <span className="grow" />
        <Button size="sm" icon={<IRefresh size={15} />} onClick={load}>{t('hist.refresh')}</Button>
        {(['txt', 'csv', 'json'] as const).map((f) => <Button key={f} size="sm" icon={<IDownload size={15} />} onClick={() => exportAs(f)} disabled={!count}>{f.toUpperCase()}</Button>)}
        <Button size="sm" variant="danger" icon={<ITrash size={15} />} onClick={clear} disabled={!count}>{t('hist.clear')}</Button>
      </div>
      <div className="hist-list">
        <AnimatePresence initial={false}>
          {items.map((h) => (
            <motion.article layout="position" key={h.id} className="hist-item" initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: 0.2 }}>
              <header>
                <time>{fmtTime(h.ts, lang)}</time>
                {h.channel !== 'uni' && <Chip tone="accent">{h.channel.toUpperCase()}</Chip>}
                <Chip tone={h.from_cache ? 'accent' : 'default'}>{h.from_cache ? t('main.cache') : h.engine}</Chip>
                <small>{h.src || '?'} → {h.tgt}</small>
                <span className="grow" />
                <IconButton label={t('hist.copy_orig')} className="mini" onClick={() => copy(h.original)}><ICopy size={13} /></IconButton>
                <IconButton label={t('hist.copy_tr')} className="mini" onClick={() => copy(h.translated)}><ICopy size={13} /></IconButton>
              </header>
              <p className="o selectable">{h.original}</p>
              <p className="tr selectable">{h.translated}</p>
            </motion.article>
          ))}
        </AnimatePresence>
        {!items.length && <div className="hist-empty"><p>{t('hist.empty')}</p></div>}
      </div>
    </div>
  )
}
