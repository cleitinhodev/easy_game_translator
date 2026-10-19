import { useEffect, useState } from 'react'
import { api } from '@/api/client'
import { useStore, useT } from '@/store'
import { Modal } from './Modal'
import { Button, TextInput } from './ui'

export function ProfileModal() {
  const t = useT()
  const open = useStore((s) => s.modal === 'profile-save')
  const setModal = useStore((s) => s.setModal)
  const toast = useStore((s) => s.toast)
  const current = useStore((s) => s.profile?.name ?? '')
  const [name, setName] = useState('')
  useEffect(() => { if (open) setName(current === 'Padrão' ? '' : current) }, [open, current])
  const save = async () => {
    const n = name.trim()
    if (!n) return
    try { await api.post('/api/profiles', { name: n }); toast('ok', t('toast.profile_saved', { name: n })); setModal(null) } catch (e: any) { toast('error', e.message) }
  }
  return (
    <Modal open={open} onClose={() => setModal(null)} width={440} title={t('main.profile_save_title')}
      footer={<><Button variant="ghost" onClick={() => setModal(null)}>{t('common.cancel')}</Button><Button variant="primary" onClick={save} disabled={!name.trim()}>{t('common.save')}</Button></>}>
      <p className="muted" style={{ marginBottom: 12 }}>{t('main.profile_ask')}</p>
      <TextInput autoFocus value={name} maxLength={60} placeholder={t('main.profile_placeholder')} onChange={(e) => setName(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter') save() }} style={{ width: '100%' }} />
    </Modal>
  )
}
